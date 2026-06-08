from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.ingestion.embeddings import EmbeddingClient
from app.retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)


@dataclass
class ContextItem:
    path: str | None
    chunk_type: str
    content_excerpt: str
    github_url: str | None
    line_start: int | None
    line_end: int | None
    score: float


@dataclass
class SearchResult:
    items: list[ContextItem] = field(default_factory=list)
    total: int = 0


def create_repo_context_tool(session, embedding_client=None):
    ec = embedding_client or EmbeddingClient()
    retriever = HybridRetriever(session, ec)

    def search_code(repo_id: str, query: str, top_k: int = 8) -> SearchResult:
        chunks = retriever.retrieve(query=query, repo_id=repo_id, top_k=top_k)
        items = [
            ContextItem(
                path=c.path, chunk_type=c.chunk_type,
                content_excerpt=c.content[:1000],
                github_url=c.github_url,
                line_start=c.line_start, line_end=c.line_end,
                score=c.score,
            )
            for c in chunks
        ]
        return SearchResult(items=items, total=len(items))

    def get_file_context(
        repo_id: str, path: str, around_line: int | None = None,
    ) -> ContextItem | None:
        chunks = retriever.retrieve(
            query=f"file:{path}", repo_id=repo_id, top_k=5,
        )
        for c in chunks:
            if c.path and c.path.endswith(path.split("/")[-1]):
                return ContextItem(
                    path=c.path, chunk_type=c.chunk_type,
                    content_excerpt=c.content[:2000],
                    github_url=c.github_url,
                    line_start=c.line_start, line_end=c.line_end,
                    score=c.score,
                )
        return None

    return search_code, get_file_context
