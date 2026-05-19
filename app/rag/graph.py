from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.providers import ChatProvider
from app.rag.citations import Citation, extract_citations_from_answer, validate_citations
from app.rag.prompts import (
    ANSWER_PROMPT,
    QUESTION_CLASSIFIER_PROMPT,
    QUERY_REWRITE_PROMPT,
    SYSTEM_PROMPT,
)
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.rerank import IdentityReranker, Reranker
from app.retrieval.vector import ScoredChunk

logger = logging.getLogger(__name__)


@dataclass
class RAGState:
    repo_id: str
    question: str
    top_k: int = 8
    question_type: str = ""
    rewritten_queries: list[str] = field(default_factory=list)
    retrieved_chunks: list[ScoredChunk] = field(default_factory=list)
    reranked_chunks: list[ScoredChunk] = field(default_factory=list)
    evidence_sufficient: bool = False
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    confidence: str = "low"


class RAGPipeline:
    def __init__(
        self,
        chat_provider: ChatProvider,
        retriever: HybridRetriever,
        reranker: Reranker | None = None,
    ) -> None:
        self._chat = chat_provider
        self._retriever = retriever
        self._reranker = reranker or IdentityReranker()

    def run(self, repo_id: str, question: str, top_k: int = 8) -> RAGState:
        state = RAGState(repo_id=repo_id, question=question, top_k=top_k)

        state = self._normalize_question(state)
        state = self._query_rewrite(state)
        state = self._hybrid_retrieve(state)
        state = self._rerank(state)
        state = self._evidence_check(state)
        state = self._generate_answer(state)
        state = self._validate_citations(state)

        return state

    def _normalize_question(self, state: RAGState) -> RAGState:
        prompt = QUESTION_CLASSIFIER_PROMPT.format(question=state.question)
        try:
            result = self._chat.chat([
                {"role": "system", "content": "You classify questions precisely."},
                {"role": "user", "content": prompt},
            ])
            state.question_type = result.strip().lower()
        except Exception:
            logger.warning("Question classification failed, defaulting to code_location")
            state.question_type = "code_location"
        return state

    def _query_rewrite(self, state: RAGState) -> RAGState:
        prompt = QUERY_REWRITE_PROMPT.format(
            question=state.question,
            question_type=state.question_type,
        )
        try:
            result = self._chat.chat([
                {"role": "system", "content": "You generate search queries for code retrieval."},
                {"role": "user", "content": prompt},
            ])
            queries = [
                q.strip().lstrip("-_*•0123456789. )")
                for q in result.strip().split("\n")
                if q.strip()
            ]
            state.rewritten_queries = queries[:4] if queries else [state.question]
        except Exception:
            logger.warning("Query rewrite failed, using original question")
            state.rewritten_queries = [state.question]
        return state

    def _hybrid_retrieve(self, state: RAGState) -> RAGState:
        chunk_type_weights = _get_chunk_type_weights(state.question_type)
        all_chunks: dict[str, ScoredChunk] = {}

        for query in state.rewritten_queries[:2]:
            chunks = self._retriever.retrieve(
                query=query,
                repo_id=state.repo_id,
                top_k=state.top_k * 2,
                chunk_type_weights=chunk_type_weights,
            )
            for c in chunks:
                if c.chunk_id not in all_chunks:
                    all_chunks[c.chunk_id] = c
                else:
                    all_chunks[c.chunk_id].score = max(all_chunks[c.chunk_id].score, c.score)

        state.retrieved_chunks = sorted(
            all_chunks.values(), key=lambda x: x.score, reverse=True
        )[:state.top_k * 2]
        return state

    def _rerank(self, state: RAGState) -> RAGState:
        state.reranked_chunks = self._reranker.rerank(
            state.question, state.retrieved_chunks, top_k=state.top_k
        )
        return state

    def _evidence_check(self, state: RAGState) -> RAGState:
        if not state.reranked_chunks:
            state.evidence_sufficient = False
        else:
            max_score = max(c.score for c in state.reranked_chunks) if state.reranked_chunks else 0
            state.evidence_sufficient = max_score > 0.01 or len(state.reranked_chunks) >= 1
        return state

    def _generate_answer(self, state: RAGState) -> RAGState:
        if not state.evidence_sufficient or not state.reranked_chunks:
            state.answer = "I don't have enough information in the indexed repository content to answer this question."
            state.confidence = "low"
            return state

        evidence_parts: list[str] = []
        for i, chunk in enumerate(state.reranked_chunks):
            location = ""
            if chunk.path:
                location = f" [{chunk.path}"
                if chunk.line_start:
                    location += f":L{chunk.line_start}"
                    if chunk.line_end and chunk.line_end != chunk.line_start:
                        location += f"-L{chunk.line_end}"
                location += "]"
            evidence_parts.append(
                f"[Source {i + 1}]{location}\n{chunk.content[:2000]}"
            )
        evidence = "\n\n---\n\n".join(evidence_parts)

        prompt = ANSWER_PROMPT.format(
            system_prompt=SYSTEM_PROMPT,
            evidence=evidence,
            question=state.question,
        )

        try:
            answer = self._chat.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            state.answer = answer
            state.confidence = "medium"
        except Exception:
            logger.exception("Answer generation failed")
            state.answer = "Failed to generate answer due to an internal error."
            state.confidence = "low"

        return state

    def _validate_citations(self, state: RAGState) -> RAGState:
        if not state.answer or not state.reranked_chunks:
            return state

        evidence_urls = {
            c.github_url or c.chunk_id for c in state.reranked_chunks
        }

        state.citations = extract_citations_from_answer(state.answer, evidence_urls)

        is_valid, invalid = validate_citations(state.answer, evidence_urls)
        if not is_valid and invalid:
            logger.warning("Found %d citations not in evidence: %s", len(invalid), invalid)

        if not state.citations:
            state.confidence = "low"
        elif is_valid and len(state.citations) >= 1:
            state.confidence = "high"

        for chunk in state.reranked_chunks:
            if chunk.github_url:
                for cit in state.citations:
                    if cit.url and cit.url in chunk.github_url:
                        if not cit.path:
                            cit.path = chunk.path
                        if cit.line_start is None:
                            cit.line_start = chunk.line_start
                            cit.line_end = chunk.line_end

        return state


def _get_chunk_type_weights(question_type: str) -> dict[str, float] | None:
    weights_map = {
        "architecture": {"code_symbol": 1.5, "markdown_section": 1.0},
        "code_location": {"code_symbol": 2.0, "markdown_section": 0.5},
        "issue_context": {"issue_comment": 2.0, "pr_description": 2.0},
        "usage": {"markdown_section": 2.0, "code_symbol": 0.5},
        "debugging": {"issue_comment": 1.5, "code_symbol": 1.0, "pr_description": 1.5},
    }
    return weights_map.get(question_type)
