from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChatProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], **kwargs: object) -> str:
        ...

    @property
    @abstractmethod
    def model(self) -> BaseChatModel:
        ...


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    @abstractmethod
    def model(self) -> Embeddings:
        ...


class DeepSeekChatProvider(ChatProvider):
    def __init__(self) -> None:
        extra: dict[str, object] = {}
        if settings.deepseek_reasoning_effort:
            extra["reasoning_effort"] = settings.deepseek_reasoning_effort

        self._model = ChatOpenAI(
            openai_api_key=settings.deepseek_api_key,
            openai_api_base=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0,
            **(extra if settings.deepseek_reasoning_effort else {}),
        )

    @property
    def model(self) -> BaseChatModel:
        return self._model

    def chat(self, messages: list[dict], **kwargs: object) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        lc_messages = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))
        response = self._model.invoke(lc_messages, **kwargs)  # type: ignore[arg-type]
        content = response.content
        if isinstance(content, list):
            content = "".join(
                c["text"] if isinstance(c, dict) else str(c) for c in content
            )
        if not content:
            raise ValueError("LLM returned empty response")
        return str(content)


class OpenAICompatibleChatProvider(ChatProvider):
    def __init__(self) -> None:
        self._model = ChatOpenAI(
            openai_api_key=settings.deepseek_api_key,
            openai_api_base=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0,
        )

    @property
    def model(self) -> BaseChatModel:
        return self._model

    def chat(self, messages: list[dict], **kwargs: object) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        lc_messages = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))
        response = self._model.invoke(lc_messages, **kwargs)  # type: ignore[arg-type]
        content = response.content
        if isinstance(content, list):
            content = "".join(
                c["text"] if isinstance(c, dict) else str(c) for c in content
            )
        if not content:
            raise ValueError("LLM returned empty response")
        return str(content)


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self._model = OpenAIEmbeddings(
            openai_api_key=settings.embedding_api_key,
            openai_api_base=settings.embedding_base_url or settings.deepseek_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    @property
    def model(self) -> Embeddings:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = self._model.embed_documents(texts)
        for i, emb in enumerate(result):
            if len(emb) != settings.embedding_dimensions:
                raise ValueError(
                    f"Embedding dimension mismatch at index {i}: "
                    f"expected {settings.embedding_dimensions}, got {len(emb)}. "
                    f"Update EMBEDDING_DIMENSIONS to match the model."
                )
        return result  # type: ignore[return-value]


def get_chat_provider() -> ChatProvider:
    provider = settings.llm_provider
    if provider == "deepseek":
        return DeepSeekChatProvider()
    if provider == "openai_compatible":
        return OpenAICompatibleChatProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def get_embedding_provider() -> EmbeddingProvider:
    provider = settings.embedding_provider
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider()
    if provider == "deepseek":
        return OpenAICompatibleEmbeddingProvider()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")
