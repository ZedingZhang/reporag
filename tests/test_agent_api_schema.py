from __future__ import annotations

from app.api.agent_routes import AgentRunResponse, ApprovalResponse


class TestAgentApiSchema:
    def test_agent_run_response_preserves_approvals(self) -> None:
        payload = {
            "run_id": "r1",
            "repo_id": "repo1",
            "task": "test",
            "mode": "propose_patch",
            "status": "waiting_approval",
            "steps": [],
            "approvals": [{
                "approval_id": "a1",
                "action_type": "apply_patch",
                "summary": "Patch",
                "risk_level": "high",
                "status": "pending",
                "review_comment": None,
            }],
        }
        model = AgentRunResponse(**payload)
        assert model.approvals[0].approval_id == "a1"
        assert model.approvals[0].action_type == "apply_patch"
        assert model.approvals[0].risk_level == "high"

    def test_agent_run_response_defaults(self) -> None:
        payload = {
            "run_id": "r1",
            "task": "test",
            "mode": "plan_only",
            "status": "completed",
        }
        model = AgentRunResponse(**payload)
        assert model.steps == []
        assert model.approvals == []
        assert model.plan is None

    def test_approval_response_fields(self) -> None:
        a = ApprovalResponse(
            approval_id="a1", action_type="apply_patch",
            summary="Test", risk_level="high", status="pending",
            review_comment=None,
        )
        assert a.review_comment is None
        d = a.model_dump()
        assert "approval_id" in d
        assert d["approval_id"] == "a1"
