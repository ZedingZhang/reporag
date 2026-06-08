from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agent.graph import build_agent_graph
from app.agent.state import AgentState
from app.db.models import AgentRun, AgentStep, ApprovalRequest
from app.security.approvals import ApprovalManager

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, session, chat_provider=None, retriever=None):
        self._session = session
        self._chat = chat_provider
        self._retriever = retriever

    def create_run(
        self, repo_id: str, task: str, mode: str = "plan_only", top_k: int = 8,
    ) -> str:
        run = AgentRun(
            repo_id=repo_id, task=task, mode=mode,
            status="running",
        )
        self._session.add(run)
        self._session.flush()

        graph = build_agent_graph(self._chat, self._retriever, self._mk_session)
        initial = AgentState(
            run_id=run.id, repo_id=repo_id, task=task,
            mode=mode, top_k=top_k,
        )

        try:
            result = graph.invoke(initial)
            run.plan_json = {
                "task_type": result["task_type"],
                "plan": result["plan"],
                "suggested_tests": result["suggested_tests"],
                "errors": result["errors"],
            }
            run.result_json = {
                "final_summary": result["final_summary"],
                "target_files": result["target_files"][:20],
                "retrieved_chunks": len(result["retrieved_context"]),
                "proposed_patch": result["proposed_patch"][:3000],
                "command_plan": result["command_plan"],
            }
            run.status = result["status"]
            run.updated_at = datetime.now(timezone.utc)
        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            logger.exception("Agent run %s failed", run.id)

        self._session.commit()
        return {"run_id": run.id, "status": run.status}

    def get_run(self, run_id: str) -> dict | None:
        run = self._session.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return None
        steps = (
            self._session.query(AgentStep)
            .filter(AgentStep.run_id == run_id)
            .order_by(AgentStep.created_at)
            .all()
        )
        approvals = (
            self._session.query(ApprovalRequest)
            .filter(ApprovalRequest.run_id == run_id)
            .order_by(ApprovalRequest.created_at)
            .all()
        )
        return {
            "run_id": run.id,
            "repo_id": run.repo_id,
            "task": run.task,
            "mode": run.mode,
            "status": run.status,
            "plan": run.plan_json,
            "result": run.result_json,
            "error": run.error,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "steps": [
                {
                    "step_id": s.id,
                    "step_index": s.step_index,
                    "node_name": s.node_name,
                    "tool_name": s.tool_name,
                    "status": s.status,
                    "latency_ms": s.latency_ms,
                }
                for s in steps
            ],
            "approvals": [
                {
                    "approval_id": a.id,
                    "action_type": a.action_type,
                    "summary": a.summary,
                    "risk_level": a.risk_level,
                    "status": a.status,
                    "review_comment": a.review_comment,
                }
                for a in approvals
            ],
        }

    def get_steps(self, run_id: str) -> list[dict]:
        steps = (
            self._session.query(AgentStep)
            .filter(AgentStep.run_id == run_id)
            .order_by(AgentStep.created_at)
            .all()
        )
        return [
            {
                "step_id": s.id,
                "step_index": s.step_index,
                "node_name": s.node_name,
                "tool_name": s.tool_name,
                "status": s.status,
                "latency_ms": s.latency_ms,
                "input": s.input_json,
                "output": s.output_json,
            }
            for s in steps
        ]

    def resolve_approval(
        self, approval_id: str, decision: str, comment: str = "",
    ) -> dict | None:
        mgr = ApprovalManager(self._session)
        approval = mgr.resolve(approval_id, decision, comment)
        if not approval:
            return None
        self._session.commit()

        run = (
            self._session.query(AgentRun)
            .filter(AgentRun.id == approval.run_id)
            .first()
        )
        if run:
            if decision == "approved":
                run.status = "running"
            else:
                run.status = "failed"
                run.error = f"Approval {approval_id} was rejected: {comment}"
            run.updated_at = datetime.now(timezone.utc)
            self._session.commit()

        return {
            "approval_id": approval.id,
            "run_id": approval.run_id,
            "status": approval.status,
            "review_comment": approval.review_comment,
        }

    def continue_after_approval(self, run_id: str) -> dict | None:
        run = self._session.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return None

        approvals = (
            self._session.query(ApprovalRequest)
            .filter(ApprovalRequest.run_id == run_id)
            .order_by(ApprovalRequest.created_at)
            .all()
        )

        pending = [a for a in approvals if a.status == "pending"]
        if pending:
            return {
                "error": "Run still has pending approvals",
                "status": run.status,
            }

        approved = [a for a in approvals if a.status == "approved"]
        rejected = [a for a in approvals if a.status == "rejected"]
        if rejected and not approved:
            run.status = "failed"
            run.error = "All approvals were rejected"
            run.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            return self.get_run(run_id)

        plan_data = run.plan_json or {}
        result_data = run.result_json or {}

        latest = approved[-1] if approved else None
        state = AgentState(
            run_id=run.id,
            repo_id=run.repo_id or "",
            task=run.task,
            mode=run.mode,
            task_type=plan_data.get("task_type", ""),
            plan=plan_data.get("plan", []),
            suggested_tests=plan_data.get("suggested_tests", []),
            proposed_patch=(
                (latest.payload_json or {}).get("patch")
                if latest and latest.payload_json else result_data.get("proposed_patch", "")
            ),
            approval_id=latest.id if latest else None,
            approval_status="approved" if approved else "not_required",
        )

        self._execute_approved_actions(run, state, approved, result_data)
        self._session.commit()
        return self.get_run(run_id)

    def _execute_approved_actions(
        self,
        run: AgentRun,
        state: AgentState,
        approved: list[ApprovalRequest],
        result_data: dict,
    ) -> None:
        from app.agent.graph import _AgentNodeContext

        ctx = _AgentNodeContext(self._chat, self._retriever, self._mk_session)

        result_data["patch_apply_status"] = "skipped_no_workspace"
        result_data["command_results"] = list(result_data.get("command_results", []))

        has_apply = any(
            a.action_type in ("apply_patch", "execute_plan", "approve_patch_proposal")
            for a in approved
        )

        if has_apply and state.proposed_patch:
            result_data["patch_apply_status"] = "stored_only"
            result_data["patch_apply_note"] = (
                "Patch proposal approved but not applied: "
                "no workspace root configured. Set AGENT_WORKSPACE_ROOT "
                "and AGENT_APPLY_PATCHES=true to enable."
            )

        if state.mode in ("propose_patch",):
            state.status = "completed"
            state.final_summary = (
                "Patch proposal approved. No commands executed per mode policy."
            )
            ctx._record_step(
                state, "apply_patch",
                output_data={"status": result_data["patch_apply_status"]},
            )
            ctx.summarize(state)

            if has_apply:
                ctx._record_step(
                    state, "run_tests",
                    output_data={
                        "status": "skipped (propose_patch mode, tests not executed)",
                    },
                )
        elif state.mode == "execute_after_approval":
            ctx.apply_patch(state)
            ctx.run_tests(state)
            ctx.summarize(state)
            result_data["command_results"] = [
                {"command": c.get("command"), "status": c.get("status")}
                for c in state.command_results
            ]

        run.result_json = {**result_data}
        run.status = state.status
        run.updated_at = datetime.now(timezone.utc)

    def cancel_run(self, run_id: str) -> bool:
        run = self._session.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run or run.status not in ("created", "running", "waiting_approval"):
            return False
        run.status = "cancelled"
        run.updated_at = datetime.now(timezone.utc)
        self._session.commit()
        return True

    def _mk_session(self):
        from app.db.session import get_sync_session
        return get_sync_session()
