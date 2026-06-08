from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agent.graph import build_agent_graph
from app.agent.state import AgentState
from app.db.models import AgentRun, AgentStep

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, session, chat_provider, retriever):
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
                "errors": result["errors"],
            }
            run.result_json = {
                "final_summary": result["final_summary"],
                "target_files": result["target_files"][:20],
                "retrieved_chunks": len(result["retrieved_context"]),
            }
            run.status = result["status"]
            run.updated_at = datetime.now(timezone.utc)
        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            logger.exception("Agent run %s failed", run.id)

        self._session.commit()
        return run.id

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
