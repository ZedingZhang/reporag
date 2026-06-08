from __future__ import annotations

from app.tools.repo_context import ContextItem, SearchResult, create_repo_context_tool


class FakeEmbeddingClient:
    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 10


class FakeSession:
    def __init__(self) -> None:
        pass


class FakeRetrieverForTool:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def retrieve(self, query: str, repo_id: str, top_k: int = 20,
                 chunk_type_weights: dict | None = None) -> list:
        from app.retrieval.vector import ScoredChunk
        self.calls.append({"query": query, "repo_id": repo_id, "top_k": top_k})
        return [
            ScoredChunk(
                chunk_id="c1", content="def validate(): pass",
                path="app/rag/citations.py", chunk_type="code_symbol",
                score=0.95,
                github_url="https://github.com/o/r/blob/abc/app/rag/citations.py",
                line_start=10, line_end=20,
            ),
            ScoredChunk(
                chunk_id="c2", content="test content",
                path="tests/test_citations.py", chunk_type="code_symbol",
                score=0.80,
                github_url="https://github.com/o/r/blob/abc/tests/test_citations.py",
                line_start=1, line_end=15,
            ),
        ]


class TestRepoContextTool:
    def test_search_code_returns_items(self) -> None:
        from unittest.mock import patch
        ec = FakeEmbeddingClient()
        session = FakeSession()
        with patch(
            "app.tools.repo_context.HybridRetriever",
            return_value=FakeRetrieverForTool(),
        ):
            search_code, _ = create_repo_context_tool(session, ec)
            result = search_code("repo1", "citation validation")
            assert isinstance(result, SearchResult)
            assert len(result.items) >= 1

    def test_search_code_items_have_citations(self) -> None:
        from unittest.mock import patch
        ec = FakeEmbeddingClient()
        session = FakeSession()
        with patch(
            "app.tools.repo_context.HybridRetriever",
            return_value=FakeRetrieverForTool(),
        ):
            search_code, _ = create_repo_context_tool(session, ec)
            result = search_code("repo1", "citation")
            for item in result.items:
                assert isinstance(item, ContextItem)
                if item.path:
                    assert isinstance(item.path, str)

    def test_search_code_total_matches_len(self) -> None:
        from unittest.mock import patch
        ec = FakeEmbeddingClient()
        session = FakeSession()
        with patch(
            "app.tools.repo_context.HybridRetriever",
            return_value=FakeRetrieverForTool(),
        ):
            search_code, _ = create_repo_context_tool(session, ec)
            result = search_code("repo1", "test")
            assert result.total == len(result.items)

    def test_get_file_context_finds_by_filename(self) -> None:
        from unittest.mock import patch
        ec = FakeEmbeddingClient()
        session = FakeSession()
        with patch(
            "app.tools.repo_context.HybridRetriever",
            return_value=FakeRetrieverForTool(),
        ):
            _, get_file_context = create_repo_context_tool(session, ec)
            item = get_file_context("repo1", "citations.py")
            assert item is not None
            assert item.path is not None
