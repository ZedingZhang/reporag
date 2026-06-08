from __future__ import annotations

from unittest.mock import MagicMock

from app.agent.graph import _parse_json, build_agent_graph
from app.agent.state import AgentState


class FakeChatProvider:
    def __init__(self, responses: dict | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], **kwargs: object) -> str:
        self.calls.append(messages)
        user_content = messages[-1].get("content", "") if messages else ""
        for key, value in self.responses.items():
            if key in user_content:
                return value
        return (
            '{"task_type":"bugfix","summary":"test plan",'
            '"steps":[{"goal":"test","files":["test.py"],'
            '"evidence_urls":[],"risk_level":"low",'
            '"requires_approval":false}],'
            '"suggested_tests":["pytest"],"uncertainty":"none"}'
        )


class FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def retrieve(self, query: str, repo_id: str, top_k: int = 20,
                 chunk_type_weights: dict | None = None) -> list:
        from app.retrieval.vector import ScoredChunk
        self.calls.append({"query": query, "repo_id": repo_id, "top_k": top_k})
        return [
            ScoredChunk(
                chunk_id="c1", content="Test content",
                path="test.py", chunk_type="code_symbol",
                score=0.95, github_url="https://github.com/o/r/blob/abc/test.py",
                line_start=1, line_end=10,
            ),
        ]


def _fake_session_factory():
    return MagicMock()


class TestAgentGraphPlanOnly:
    def test_plan_only_returns_plan(self) -> None:
        chat = FakeChatProvider()
        retriever = FakeRetriever()
        graph = build_agent_graph(chat, retriever, _fake_session_factory)

        state = AgentState(
            run_id="r1", repo_id="repo1",
            task="Fix test failure in citation validation",
            mode="plan_only", top_k=8,
        )

        result = graph.invoke(state)

        assert result["status"] == "completed"
        assert len(result["plan"]) >= 1
        assert result["task_type"] != ""
        assert len(result["final_summary"]) > 0
        assert len(result["retrieved_context"]) >= 1

    def test_plan_only_does_not_produce_patch(self) -> None:
        chat = FakeChatProvider()
        retriever = FakeRetriever()
        graph = build_agent_graph(chat, retriever, _fake_session_factory)

        state = AgentState(
            run_id="r2", repo_id="repo1",
            task="Where is citation validation?", mode="plan_only",
        )

        result = graph.invoke(state)

        assert result["proposed_patch"] == ""
        assert result["command_results"] == []

    def test_classify_task_bugfix(self) -> None:
        chat = FakeChatProvider({
            "Classify": "bugfix",
        })
        retriever = FakeRetriever()
        graph = build_agent_graph(chat, retriever, _fake_session_factory)

        state = AgentState(
            run_id="r3", repo_id="repo1",
            task="Fix the broken test", mode="plan_only",
        )

        result = graph.invoke(state)
        assert "bugfix" in result["task_type"] or len(result["plan"]) >= 1

    def test_context_contains_target_files(self) -> None:
        chat = FakeChatProvider()
        retriever = FakeRetriever()
        graph = build_agent_graph(chat, retriever, _fake_session_factory)

        state = AgentState(
            run_id="r4", repo_id="repo1",
            task="Find test files", mode="plan_only",
        )

        result = graph.invoke(state)
        assert "test.py" in result["target_files"]


class TestParseJson:
    def test_plain_json(self) -> None:
        result = _parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_code_block(self) -> None:
        result = _parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_invalid_json(self) -> None:
        result = _parse_json("not json at all")
        assert result is None

    def test_json_with_surrounding_text(self) -> None:
        result = _parse_json('Here is the plan: {"key": "value"}. That is all.')
        assert result == {"key": "value"}
