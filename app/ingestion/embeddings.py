from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.providers import (
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    get_embedding_provider,
)

logger = logging.getLogger(__name__)


class EmbeddingClient:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        if provider is not None:
            self._provider = provider
        else:
            self._provider = get_embedding_provider()
        self._batch_size = 100

    @property
    def dimensions(self) -> int:
        return settings.embedding_dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            logger.debug("Embedding batch %d/%d (size=%d)", i // self._batch_size + 1,
                         (len(texts) - 1) // self._batch_size + 1, len(batch))
            batch_embeddings = self._provider.embed(batch)

            for j, emb in enumerate(batch_embeddings):
                if len(emb) != self.dimensions:
                    raise ValueError(
                        f"Embedding dimension mismatch at index {i + j}: "
                        f"expected {self.dimensions}, got {len(emb)}. "
                        f"Update EMBEDDING_DIMENSIONS to match the model."
                    )

            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        return self._provider.embed_query(text)
