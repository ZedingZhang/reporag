from __future__ import annotations

import json
import logging
import time

from langgraph.graph import END, StateGraph

from app.agent.prompts import (
    PLANNER_PROMPT,
    SUMMARIZER_PROMPT,
    TASK_CLASSIFIER_PROMPT,
)
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


class _AgentNodeContext:
    def __init__(self, chat_provider, retriever, session_factory):
        self.chat = chat_provider
        self.retriever = retriever
        self.session_factory = session_factory

    def _record_step(self, state: AgentState, node_name: str, tool_name=None,
                     input_data=None, output_data=None, status="completed",
                     latency_ms=None) -> None:
        from app.db.models import AgentStep
        session = self.session_factory()
        try:
            step = AgentStep(
                run_id=state.run_id,
                step_index=len(state.plan) + 1,
                node_name=node_name,
                tool_name=tool_name,
                input_json=input_data,
                output_json=output_data,
                status=status,
                latency_ms=latency_ms,
            )
            session.add(step)
            session.commit()
        except Exception:
            logger.exception("Failed to record step: %s", node_name)
        finally:
            session.close()

    def _update_run_status(self, run_id: str, status: str) -> None:
        from datetime import datetime, timezone

        from app.db.models import AgentRun
        session = self.session_factory()
        try:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.status = status
                run.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception:
            logger.exception("Failed to update run status")
        finally:
            session.close()

    def classify_task(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        prompt = TASK_CLASSIFIER_PROMPT.format(task=state.task)
        try:
            result = self.chat.chat([
                {"role": "system", "content": "Classify repository maintenance tasks."},
                {"role": "user", "content": prompt},
            ])
            state.task_type = result.strip().lower()
        except Exception:
            logger.warning("Task classification failed, defaulting to question")
            state.task_type = "question"
        self._record_step(
            state, "classify_task",
            output_data={"task_type": state.task_type},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def retrieve_context(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        state.context_queries = [state.task]
        all_chunks = self.retriever.retrieve(
            query=state.task, repo_id=state.repo_id, top_k=state.top_k * 2,
        )
        state.retrieved_context = []
        seen_paths: set[str] = set()
        for c in all_chunks:
            if c.path and c.path not in seen_paths:
                seen_paths.add(c.path)
                state.target_files.append(c.path)
            state.retrieved_context.append({
                "chunk_id": c.chunk_id,
                "path": c.path,
                "chunk_type": c.chunk_type,
                "content": c.content[:1000],
                "github_url": c.github_url,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "score": round(c.score, 4),
            })
        self._record_step(
            state, "retrieve_context",
            output_data={
                "num_chunks": len(state.retrieved_context),
                "target_files": state.target_files[:10],
            },
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def build_plan(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        evidence = _format_evidence(state.retrieved_context)
        prompt = PLANNER_PROMPT.format(task=state.task, evidence=evidence)
        try:
            result = self.chat.chat([
                {"role": "system", "content": "You plan code maintenance tasks."},
                {"role": "user", "content": prompt},
            ])
            plan = _parse_json(result)
            if not plan:
                state.plan = [{
                    "goal": "Analyze task from retrieved context",
                    "files": state.target_files[:5],
                    "evidence_urls": [],
                    "risk_level": "low",
                    "requires_approval": False,
                }]
            else:
                state.task_type = plan.get("task_type", state.task_type)
                state.plan = plan.get("steps", [plan])
        except Exception:
            logger.exception("Plan generation failed")
            state.plan = [{
                "goal": "Error generating plan",
                "files": [],
                "evidence_urls": [],
                "risk_level": "low",
                "requires_approval": False,
            }]
            state.errors.append("Plan generation failed")
        self._record_step(
            state, "build_plan",
            output_data={"num_steps": len(state.plan)},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def propose_patch(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        state.proposed_patch = ""
        if state.mode == "plan_only":
            self._record_step(
                state, "propose_patch",
                output_data={"patch": "skipped (plan_only mode)"},
                latency_ms=0,
            )
            return state
        evidence = _format_evidence(state.retrieved_context)
        plan_text = json.dumps(state.plan, indent=2)
        prompt = (
            f"You are proposing a minimal patch.\n"
            f"Use only files in evidence. Produce unified diff only.\n"
            f"Keep patch minimal. Do not modify secrets or lockfiles.\n"
            f"If evidence insufficient, return NO_PATCH.\n\n"
            f"Task: {state.task}\n\nPlan: {plan_text}\n\nEvidence:\n{evidence}"
        )
        try:
            result = self.chat.chat([
                {"role": "system", "content": "You propose minimal code patches."},
                {"role": "user", "content": prompt},
            ])
            state.proposed_patch = result.strip()
        except Exception:
            logger.exception("Patch proposal failed")
            state.errors.append("Patch proposal failed")

        from app.tools.patch import summarize_patch, validate_unified_diff
        validation = validate_unified_diff(state.proposed_patch)
        summary = summarize_patch(state.proposed_patch)

        self._record_step(
            state, "propose_patch",
            output_data={
                "patch_len": len(state.proposed_patch),
                "valid": validation.valid,
                "validation_reason": validation.reason,
                "files": summary.files,
                "added_lines": summary.added_lines,
                "removed_lines": summary.removed_lines,
                "is_no_patch": summary.is_no_patch,
            },
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def request_approval(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        from app.security.approvals import ApprovalManager

        session = self.session_factory()
        try:
            mgr = ApprovalManager(session)

            needs_approval = False
            for step in state.plan:
                if step.get("requires_approval") and state.mode == "execute_after_approval":
                    needs_approval = True
                    break
            if state.proposed_patch and state.proposed_patch != "NO_PATCH":
                if state.mode in ("propose_patch", "execute_after_approval"):
                    needs_approval = True

            if needs_approval:
                approval_id = mgr.create_approval(
                    run_id=state.run_id,
                    action_type="apply_patch",
                    summary=f"Patch for: {state.task[:100]}",
                    payload={"patch": state.proposed_patch[:2000]},
                    risk_level="medium",
                )
                session.commit()
                state.approval_id = approval_id
                state.approval_status = "pending"
                state.status = "waiting_approval"
                self._update_run_status(state.run_id, "waiting_approval")
            else:
                state.approval_status = "not_required"
        finally:
            session.close()
        self._record_step(
            state, "request_approval",
            output_data={
                "approval_id": state.approval_id,
                "approval_status": state.approval_status,
            },
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def wait_for_approval(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        if state.approval_status == "not_required":
            self._record_step(
                state, "wait_for_approval",
                output_data={"result": "not_required"},
                latency_ms=0,
            )
            return state
        if state.approval_status == "approved":
            self._record_step(
                state, "wait_for_approval",
                output_data={"result": "approved"},
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return state
        if state.approval_status == "rejected":
            state.errors.append("Approval rejected")
            self._record_step(
                state, "wait_for_approval",
                output_data={"result": "rejected"},
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return state
        self._record_step(
            state, "wait_for_approval",
            output_data={"result": "still_pending"},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def apply_patch(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        self._record_step(
            state, "apply_patch",
            output_data={"patch": "stored as proposal, not applied (Phase 3)"},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def run_tests(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        from app.db.models import ToolExecution
        from app.tools.executor import run_safe_command

        for step in state.plan:
            tests = step.get("suggested_tests", [])
            if isinstance(tests, str):
                tests = [tests]
            for test_cmd_str in tests:
                cmd_list = test_cmd_str.split()
                result = run_safe_command(cmd_list)

                rec = {
                    "command": cmd_list,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                }
                if result.error:
                    rec["error"] = result.error
                state.command_plan.append(rec)
                state.command_results.append(rec)

                session = self.session_factory()
                try:
                    te = ToolExecution(
                        run_id=state.run_id,
                        tool_name="run_safe_command",
                        input_json={"command": cmd_list},
                        output_json={
                            "status": result.status,
                            "exit_code": result.exit_code,
                            "stdout": result.stdout[:500],
                            "stderr": result.stderr[:500],
                        },
                        status=result.status,
                        latency_ms=result.duration_ms,
                    )
                    session.add(te)
                    session.commit()
                except Exception:
                    logger.exception("Failed to record tool execution")
                finally:
                    session.close()

        self._record_step(
            state, "run_tests",
            output_data={"commands": state.command_plan},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def summarize(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        prompt = SUMMARIZER_PROMPT.format(
            task=state.task, mode=state.mode, task_type=state.task_type,
            plan=json.dumps(state.plan, indent=2),
            status=state.status,
            errors=json.dumps(state.errors) if state.errors else "none",
        )
        try:
            state.final_summary = self.chat.chat([
                {"role": "system", "content": "You summarize agent runs for developers."},
                {"role": "user", "content": prompt},
            ])
        except Exception:
            logger.exception("Summary generation failed")
            state.final_summary = "Summary generation failed."
            state.errors.append("Summary generation failed")
        if state.status == "waiting_approval":
            state.status = "waiting_approval"
        elif state.errors:
            state.status = "failed"
        else:
            state.status = "completed"
        self._record_step(
            state, "summarize",
            output_data={"summary": state.final_summary[:500]},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state


def _format_evidence(context: list[dict]) -> str:
    parts: list[str] = []
    for i, item in enumerate(context):
        location = ""
        if item.get("path"):
            location = f" [{item['path']}"
            if item.get("line_start"):
                location += f":L{item['line_start']}"
            location += "]"
        url = item.get("github_url", "")
        parts.append(
            f"[Source {i + 1}]{location}\nURL: {url}\n{item.get('content', '')[:1500]}"
        )
    return "\n\n---\n\n".join(parts)


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _mode_routing(state: AgentState) -> str:
    if state.mode == "plan_only":
        return "summarize"
    return "propose_patch"


def _approval_routing(state: AgentState) -> str:
    if state.approval_status == "not_required":
        return "summarize"
    if state.approval_status == "approved":
        return "apply_patch"
    if state.approval_status == "rejected":
        return "summarize"
    return "wait_for_approval"


def build_agent_graph(chat_provider, retriever, session_factory):
    ctx = _AgentNodeContext(chat_provider, retriever, session_factory)

    workflow = StateGraph(AgentState)

    workflow.add_node("classify_task", ctx.classify_task)
    workflow.add_node("retrieve_context", ctx.retrieve_context)
    workflow.add_node("build_plan", ctx.build_plan)
    workflow.add_node("propose_patch", ctx.propose_patch)
    workflow.add_node("request_approval", ctx.request_approval)
    workflow.add_node("wait_for_approval", ctx.wait_for_approval)
    workflow.add_node("apply_patch", ctx.apply_patch)
    workflow.add_node("run_tests", ctx.run_tests)
    workflow.add_node("summarize", ctx.summarize)

    workflow.set_entry_point("classify_task")
    workflow.add_edge("classify_task", "retrieve_context")
    workflow.add_edge("retrieve_context", "build_plan")

    workflow.add_conditional_edges(
        "build_plan", _mode_routing,
        {"propose_patch": "propose_patch", "summarize": "summarize"},
    )
    workflow.add_edge("propose_patch", "request_approval")

    workflow.add_conditional_edges(
        "request_approval", _approval_routing,
        {
            "wait_for_approval": "wait_for_approval",
            "apply_patch": "apply_patch",
            "summarize": "summarize",
        },
    )
    workflow.add_edge("wait_for_approval", END)
    workflow.add_edge("apply_patch", "run_tests")
    workflow.add_edge("run_tests", "summarize")
    workflow.add_edge("summarize", END)

    return workflow.compile()
