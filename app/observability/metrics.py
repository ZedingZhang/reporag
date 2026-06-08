from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunMetrics:
    run_id: str
    total_duration_ms: int = 0
    llm_call_count: int = 0
    tool_call_count: int = 0
    retrieval_count: int = 0
    retrieved_chunks_total: int = 0
    approval_triggered: bool = False
    tests_executed: bool = False
    test_exit_code: int | None = None
    final_status: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_duration_ms": self.total_duration_ms,
            "llm_call_count": self.llm_call_count,
            "tool_call_count": self.tool_call_count,
            "retrieval_count": self.retrieval_count,
            "retrieved_chunks_total": self.retrieved_chunks_total,
            "approval_triggered": self.approval_triggered,
            "tests_executed": self.tests_executed,
            "test_exit_code": self.test_exit_code,
            "final_status": self.final_status,
        }


def aggregate_run_metrics(steps: list[dict], tool_execs: list[dict]) -> RunMetrics:
    m = RunMetrics(run_id="")
    m.llm_call_count = sum(
        1 for s in steps
        if s.get("node_name") in ("classify_task", "build_plan", "summarize",
                                   "propose_patch", "generate_answer")
    )
    m.tool_call_count = sum(
        1 for s in steps if s.get("tool_name")
    ) + len(tool_execs)
    m.retrieval_count = sum(
        1 for s in steps if s.get("node_name") in ("retrieve_context", "hybrid_retrieve")
    )
    m.approval_triggered = any(
        s.get("node_name") == "request_approval" for s in steps
    )
    m.tests_executed = any(
        s.get("node_name") == "run_tests" for s in steps
    )
    total_latency = sum(
        s.get("latency_ms", 0) or 0 for s in steps
    )
    m.total_duration_ms = total_latency
    return m
