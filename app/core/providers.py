from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChatProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[ChatCompletionMessageParam], **kwargs: object) -> str:
        ...


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OpenAICompatibleChatProvider(ChatProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        reasoning_effort: str | None = None,
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._reasoning_effort = reasoning_effort

    def chat(self, messages: list[ChatCompletionMessageParam], **kwargs: object) -> str:
        extra: dict[str, object] = {}
        if self._reasoning_effort:
            extra["reasoning_effort"] = self._reasoning_effort
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                **extra,  # type: ignore[arg-type]
                **kwargs,  # type: ignore[arg-type]
            )
        except Exception as e:
            logger.warning("Chat request failed: %s", e)
            raise
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM returned empty response")
        return content


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self, api_key: str, base_url: str, model: str, dimensions: int
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        result = [e.embedding for e in sorted_data]
        for i, emb in enumerate(result):
            if len(emb) != self._dimensions:
                raise ValueError(
                    f"Embedding dimension mismatch: configured {self._dimensions}, "
                    f"got {len(emb)} at index {i}. "
                    f"Update EMBEDDING_DIMENSIONS to match the model's output."
                )
        return result


def get_chat_provider() -> ChatProvider:
    provider = settings.llm_provider
    if provider in ("deepseek", "openai_compatible"):
        return OpenAICompatibleChatProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            reasoning_effort=settings.deepseek_reasoning_effort or None,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def get_embedding_provider() -> EmbeddingProvider:
    provider = settings.embedding_provider
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")
