from __future__ import annotations

from unittest.mock import MagicMock

from app.agent.state import AgentState


class TestContinuationDoesNotRerunPlanning:
    def test_continue_skips_classify_when_approved(self) -> None:
        state = AgentState(
            run_id="r1", repo_id="r1", task="test",
            mode="propose_patch", approval_status="approved",
            suggested_tests=["pytest tests/"],
        )
        assert "classify_task" not in _get_continuation_nodes(state)

    def test_continue_has_apply_and_summarize(self) -> None:
        state = AgentState(
            run_id="r2", repo_id="r1", task="test",
            mode="execute_after_approval", approval_status="approved",
            suggested_tests=["pytest tests/"],
        )
        nodes = _get_continuation_nodes(state)
        assert "apply_patch" in nodes
        assert "summarize" in nodes

    def test_propose_patch_skips_run_tests(self) -> None:
        state = AgentState(
            run_id="r3", repo_id="r1", task="test",
            mode="propose_patch", approval_status="approved",
            suggested_tests=["pytest tests/"],
        )
        nodes = _get_continuation_nodes(state)
        assert "apply_patch" in nodes
        assert "run_tests" not in nodes
        assert "classify_task" not in nodes


class TestContinueRejectsInvalidState:
    def test_still_pending_cannot_continue(self) -> None:
        from app.agent.service import AgentService
        session = MagicMock()
        run = MagicMock()
        run.id = "r1"
        run.status = "waiting_approval"
        session.query.return_value.filter.return_value.first.return_value = run
        approval = MagicMock()
        approval.status = "pending"
        chain = session.query.return_value.filter.return_value
        chain.order_by.return_value.all.return_value = [approval]

        svc = AgentService(session)
        result = svc.continue_after_approval("r1")
        assert result is not None
        assert "Run still has pending approvals" in str(result.get("error", ""))


class TestSuggestedTestsPersisted:
    def test_state_has_suggested_tests_field(self) -> None:
        state = AgentState(
            run_id="r1", repo_id="r1", task="test",
            suggested_tests=["pytest tests/test_x.py", "ruff check ."],
        )
        assert state.suggested_tests == ["pytest tests/test_x.py", "ruff check ."]

    def test_suggested_tests_default_empty(self) -> None:
        state = AgentState(run_id="r1", repo_id="r1", task="test")
        assert state.suggested_tests == []


def _get_continuation_nodes(state: AgentState) -> set[str]:
    nodes: set[str] = set()
    if state.approval_status == "approved":
        nodes.add("apply_patch")
        if state.mode == "execute_after_approval":
            nodes.add("run_tests")
        nodes.add("summarize")
    return nodes
