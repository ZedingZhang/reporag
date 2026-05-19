from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.retrieval.vector import ScoredChunk

logger = logging.getLogger(__name__)


class KeywordRetriever:
    def __init__(self, session: Session) -> None:
        self._session = session

    def retrieve(
        self, query: str, repo_id: str, top_k: int = 20
    ) -> list[ScoredChunk]:
        sql = text("""
            SELECT
                c.id, c.content, c.path, c.chunk_type,
                ts_rank(c.content_tsv, websearch_to_tsquery('english', :query)) AS score,
                c.github_url, c.line_start, c.line_end
            FROM chunks c
            WHERE c.repo_id = :repo_id
              AND c.content_tsv @@ websearch_to_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :top_k
        """)

        result = self._session.execute(
            sql,
            {"query": query, "repo_id": repo_id, "top_k": top_k},
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
