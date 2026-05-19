from __future__ import annotations

from app.rag.graph import build_rag_graph
from app.retrieval.vector import ScoredChunk


class FakeChatProvider:
    def __init__(self, answer: str = "Generated answer") -> None:
        self.answer = answer

    def chat(self, messages, **kwargs) -> str:
        prompt = messages[-1]["content"]
        if "Classify" in prompt:
            return "code_location"
        if "generate 2-4 alternative" in prompt:
            return "command parsing\nparser"
        return self.answer


class FakeRetriever:
    def __init__(self, chunks: list[ScoredChunk]) -> None:
        self.chunks = chunks

    def retrieve(self, *args, **kwargs) -> list[ScoredChunk]:
        return self.chunks


def test_rag_graph_returns_refusal_when_evidence_is_weak() -> None:
    graph = build_rag_graph(
        FakeChatProvider(),
        FakeRetriever([
            ScoredChunk(
                chunk_id="c1",
                content="weak unrelated content",
                path="src/unrelated.py",
                chunk_type="code_symbol",
                score=0.02,
                vector_score=0.2,
                retrieval_sources={"vector"},
            )
        ]),
    )

    result = graph.invoke({"repo_id": "repo", "question": "unrelated?", "top_k": 1})

    assert result["evidence_sufficient"] is False
    assert "don't have enough information" in result["answer"]
    assert "Relevant sources" not in result["answer"]
    assert result["confidence"] == "low"


def test_rag_graph_extracts_clean_citation_urls() -> None:
    url = "https://github.com/o/r/blob/abc/src/core.py#L10-L20"
    graph = build_rag_graph(
        FakeChatProvider(f"Parsing lives here [{url}]."),
        FakeRetriever([
            ScoredChunk(
                chunk_id="c1",
                content="def parse(): pass",
                path="src/core.py",
                chunk_type="code_symbol",
                score=0.05,
                github_url=url,
                line_start=10,
                line_end=20,
                vector_score=0.5,
                keyword_score=0.2,
                retrieval_sources={"vector", "keyword"},
            )
        ]),
    )

    result = graph.invoke({"repo_id": "repo", "question": "where parse?", "top_k": 1})

    assert result["confidence"] == "high"
    assert result["citations"][0].url == url
    assert result["citations"][0].path == "src/core.py"
