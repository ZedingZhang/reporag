from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ingestion.embeddings import EmbeddingClient

logger = logging.getLogger(__name__)


@dataclass
class ScoredChunk:
    chunk_id: str
    content: str
    path: str | None
    chunk_type: str
    score: float
    github_url: str | None = None
    line_start: int | None = None
    line_end: int | None = None


class VectorRetriever:
    def __init__(self, session: Session, embedding_client: EmbeddingClient | None = None) -> None:
        self._session = session
        self._embedding_client = embedding_client or EmbeddingClient()

    def retrieve(
        self, query: str, repo_id: str, top_k: int = 20
    ) -> list[ScoredChunk]:
        query_embedding = self._embedding_client.embed_query(query)
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        sql = text("""
            SELECT
                c.id, c.content, c.path, c.chunk_type,
                1 - (c.embedding <=> :embedding::vector) AS score,
                c.github_url, c.line_start, c.line_end
            FROM chunks c
            WHERE c.repo_id = :repo_id AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        result = self._session.execute(
            sql,
            {
                "embedding": embedding_str,
                "repo_id": repo_id,
                "top_k": top_k,
            },
        )

        chunks: list[ScoredChunk] = []
        for row in result:
            chunks.append(ScoredChunk(
                chunk_id=row.id,
                content=row.content,
                path=row.path,
                chunk_type=row.chunk_type,
                score=float(row.score),
                github_url=row.github_url,
                line_start=row.line_start,
                line_end=row.line_end,
            ))
        return chunks
