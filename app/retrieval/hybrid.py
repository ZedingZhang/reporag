from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ingestion.embeddings import EmbeddingClient
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.vector import ScoredChunk, VectorRetriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(
        self,
        session: Session,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._vector = VectorRetriever(session, embedding_client)
        self._keyword = KeywordRetriever(session)

    def retrieve(
        self,
        query: str,
        repo_id: str,
        top_k: int = 20,
        chunk_type_weights: dict[str, float] | None = None,
    ) -> list[ScoredChunk]:
        vector_results = self._vector.retrieve(query, repo_id, top_k=top_k)
        keyword_results = self._keyword.retrieve(query, repo_id, top_k=top_k)

        fused = _reciprocal_rank_fusion(
            vector_results,
            keyword_results,
            k=60,
            weights=chunk_type_weights,
        )

        fused.sort(key=lambda x: x.score, reverse=True)
        return fused[:top_k]


def _reciprocal_rank_fusion(
    ranked_a: list[ScoredChunk],
    ranked_b: list[ScoredChunk],
    k: int = 60,
    weights: dict[str, float] | None = None,
) -> list[ScoredChunk]:
    scores: dict[str, float] = {}
    content_map: dict[str, ScoredChunk] = {}

    for rank, chunk in enumerate(ranked_a, start=1):
        base = 1.0 / (k + rank)
        type_weight = _get_type_weight(chunk.chunk_type, weights)
        scores[chunk.chunk_id] = base * type_weight
        content_map[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(ranked_b, start=1):
        base = 1.0 / (k + rank)
        type_weight = _get_type_weight(chunk.chunk_type, weights)
        extra = base * type_weight
        if chunk.chunk_id in scores:
            scores[chunk.chunk_id] += extra
        else:
            scores[chunk.chunk_id] = extra
        if chunk.chunk_id not in content_map:
            content_map[chunk.chunk_id] = chunk

    result: list[ScoredChunk] = []
    for chunk_id, score in scores.items():
        chunk = content_map[chunk_id]
        chunk.score = score
        result.append(chunk)

    return result


def _get_type_weight(
    chunk_type: str, weights: dict[str, float] | None
) -> float:
    if weights is None:
        return 1.0
    return weights.get(chunk_type, 1.0)
