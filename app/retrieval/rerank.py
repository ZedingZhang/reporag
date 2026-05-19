from __future__ import annotations

from abc import ABC, abstractmethod

from app.retrieval.vector import ScoredChunk


class Reranker(ABC):
    @abstractmethod
    def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 8
    ) -> list[ScoredChunk]:
        ...


class IdentityReranker(Reranker):
    def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 8
    ) -> list[ScoredChunk]:
        chunks.sort(key=lambda x: x.score, reverse=True)
        return chunks[:top_k]
