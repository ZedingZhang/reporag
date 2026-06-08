from __future__ import annotations


class TestAgentEvalDataset:
    def test_dataset_has_required_fields(self) -> None:
        from app.evaluation.agent_eval import load_dataset
        items = load_dataset("examples/agent_tasks.jsonl")
        assert len(items) >= 5
        for item in items:
            assert "id" in item
            assert "repo_url" in item
            assert "task" in item
            assert "mode" in item
            assert "expected_files" in item

    def test_dataset_modes_are_valid(self) -> None:
        from app.evaluation.agent_eval import load_dataset
        items = load_dataset("examples/agent_tasks.jsonl")
        for item in items:
            assert item["mode"] in ("plan_only", "propose_patch", "execute_after_approval")


class TestAgentEvalMetrics:
    def test_context_hit_rate_full_match(self) -> None:
        from app.evaluation.agent_eval import compute_context_hit_rate
        assert compute_context_hit_rate(
            ["app/rag/citations.py", "tests/test_citations.py"],
            ["app/rag/citations.py"],
        ) == 1.0

    def test_context_hit_rate_partial_match(self) -> None:
        from app.evaluation.agent_eval import compute_context_hit_rate
        assert compute_context_hit_rate(
            ["app/rag/citations.py"],
            ["app/rag/citations.py", "app/retrieval/hybrid.py"],
        ) == 0.5

    def test_context_hit_rate_no_match(self) -> None:
        from app.evaluation.agent_eval import compute_context_hit_rate
        assert compute_context_hit_rate(
            ["app/other.py"],
            ["app/rag/citations.py"],
        ) == 0.0

    def test_context_hit_rate_empty_expected(self) -> None:
        from app.evaluation.agent_eval import compute_context_hit_rate
        assert compute_context_hit_rate(["a.py"], []) == 0.0

    def test_approval_accuracy_high_risk_with_approval(self) -> None:
        from app.evaluation.agent_eval import compute_approval_required_accuracy
        assert compute_approval_required_accuracy(True, True) == 1.0

    def test_approval_accuracy_high_risk_without_approval(self) -> None:
        from app.evaluation.agent_eval import compute_approval_required_accuracy
        assert compute_approval_required_accuracy(True, False) == 0.0

    def test_approval_accuracy_low_risk_without_approval(self) -> None:
        from app.evaluation.agent_eval import compute_approval_required_accuracy
        assert compute_approval_required_accuracy(False, False) == 1.0

    def test_approval_accuracy_low_risk_with_approval(self) -> None:
        from app.evaluation.agent_eval import compute_approval_required_accuracy
        assert compute_approval_required_accuracy(False, True) == 0.5


class TestEvalModes:
    def test_smoke_mode_is_default(self) -> None:
        from scripts.evaluate_agent import build_parser
        parser = build_parser()
        args = parser.parse_args(["--dataset", "examples/agent_tasks.jsonl"])
        assert args.mode == "smoke"

    def test_live_mode_requires_repo_id(self) -> None:
        from scripts.evaluate_agent import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--dataset", "examples/agent_tasks.jsonl",
            "--mode", "live",
        ])
        assert args.mode == "live"
        assert args.repo_id is None


class TestObservabilityMetrics:
    def test_run_metrics_aggregation(self) -> None:
        from app.observability.metrics import aggregate_run_metrics
        steps = [
            {"node_name": "classify_task", "latency_ms": 100},
            {"node_name": "retrieve_context", "latency_ms": 200},
            {"node_name": "build_plan", "latency_ms": 300},
            {"node_name": "request_approval", "latency_ms": 50},
            {"node_name": "run_tests", "tool_name": "run_safe_command", "latency_ms": 500},
        ]
        m = aggregate_run_metrics(steps, [])
        assert m.llm_call_count >= 2
        assert m.retrieval_count == 1
        assert m.approval_triggered
        assert m.tests_executed
        assert m.total_duration_ms == 1150

    def test_run_metrics_no_approval(self) -> None:
        from app.observability.metrics import aggregate_run_metrics
        steps = [
            {"node_name": "classify_task", "latency_ms": 50},
            {"node_name": "retrieve_context", "latency_ms": 100},
            {"node_name": "build_plan", "latency_ms": 150},
            {"node_name": "summarize", "latency_ms": 200},
        ]
        m = aggregate_run_metrics(steps, [])
        assert not m.approval_triggered
        assert not m.tests_executed
