from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langgraph.graph import END, StateGraph

from app.rag.citations import Citation, extract_citations_from_answer, validate_citations
from app.rag.prompts import (
    ANSWER_PROMPT,
    QUERY_REWRITE_PROMPT,
    QUESTION_CLASSIFIER_PROMPT,
    SYSTEM_PROMPT,
)
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


def _make_evidence(chunks: list[ScoredChunk]) -> str:
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        url_line = f"URL: {chunk.github_url}" if chunk.github_url else "URL: (no permalink)"
        location = ""
        if chunk.path:
            location = f" [{chunk.path}"
            if chunk.line_start:
                location += f":L{chunk.line_start}"
                if chunk.line_end and chunk.line_end != chunk.line_start:
                    location += f"-L{chunk.line_end}"
            location += "]"
        parts.append(
            f"[Source {i + 1}]{location}\n{url_line}\n{chunk.content[:2000]}"
        )
    return "\n\n---\n\n".join(parts)


def _get_chunk_type_weights(question_type: str) -> dict[str, float] | None:
    weights_map: dict[str, dict[str, float]] = {
        "architecture": {"code_symbol": 1.5, "markdown_section": 1.0},
        "code_location": {"code_symbol": 2.0, "markdown_section": 0.5},
        "issue_context": {"issue_comment": 2.0, "pr_description": 2.0},
        "usage": {"markdown_section": 2.0, "code_symbol": 0.5},
        "debugging": {"issue_comment": 1.5, "code_symbol": 1.0, "pr_description": 1.5},
    }
    return weights_map.get(question_type)


class _NodeContext:
    def __init__(self, chat_provider, retriever, reranker):
        self.chat = chat_provider
        self.retriever = retriever
        self.reranker = reranker

    def normalize_question(self, state: RAGState) -> RAGState:
        prompt = QUESTION_CLASSIFIER_PROMPT.format(question=state.question)
        try:
            result = self.chat.chat([
                {"role": "system", "content": "You classify questions precisely."},
                {"role": "user", "content": prompt},
            ])
            state.question_type = result.strip().lower()
        except Exception:
            logger.warning("Question classification failed, defaulting to code_location")
            state.question_type = "code_location"
        return state

    def query_rewrite(self, state: RAGState) -> RAGState:
        prompt = QUERY_REWRITE_PROMPT.format(
            question=state.question, question_type=state.question_type,
        )
        try:
            result = self.chat.chat([
                {"role": "system", "content": "You generate search queries for code retrieval."},
                {"role": "user", "content": prompt},
            ])
            queries = [
                q.strip().lstrip("-_*0123456789. )")
                for q in result.strip().split("\n")
                if q.strip()
            ]
            state.rewritten_queries = queries[:4] if queries else [state.question]
        except Exception:
            logger.warning("Query rewrite failed, using original question")
            state.rewritten_queries = [state.question]
        return state

    def hybrid_retrieve(self, state: RAGState) -> RAGState:
        weights = _get_chunk_type_weights(state.question_type)
        all_chunks: dict[str, ScoredChunk] = {}
        for query in state.rewritten_queries[:2]:
            chunks = self.retriever.retrieve(
                query=query, repo_id=state.repo_id,
                top_k=state.top_k * 2, chunk_type_weights=weights,
            )
            for c in chunks:
                if c.chunk_id not in all_chunks:
                    all_chunks[c.chunk_id] = c
                else:
                    all_chunks[c.chunk_id].score = max(
                        all_chunks[c.chunk_id].score, c.score,
                    )
        state.retrieved_chunks = sorted(
            all_chunks.values(), key=lambda x: x.score, reverse=True,
        )[:state.top_k * 2]
        return state

    def rerank(self, state: RAGState) -> RAGState:
        state.reranked_chunks = self.reranker.rerank(
            state.question, state.retrieved_chunks, top_k=state.top_k,
        )
        return state

    def evidence_check(self, state: RAGState) -> RAGState:
        if not state.reranked_chunks:
            state.evidence_sufficient = False
        else:
            has_keyword_signal = any(
                c.keyword_score is not None and c.keyword_score > 0
                for c in state.reranked_chunks
            )
            strong_vector_hits = sum(
                1
                for c in state.reranked_chunks[:3]
                if c.vector_score is not None and c.vector_score >= 0.35
            )
            state.evidence_sufficient = has_keyword_signal or strong_vector_hits >= 2
        return state

    def generate_answer(self, state: RAGState) -> RAGState:
        if not state.evidence_sufficient or not state.reranked_chunks:
            state.answer = (
                "I don't have enough information in the indexed repository "
                "content to answer this question."
            )
            state.confidence = "low"
            return state

        evidence = _make_evidence(state.reranked_chunks)
        prompt = ANSWER_PROMPT.format(
            system_prompt=SYSTEM_PROMPT,
            evidence=evidence,
            question=state.question,
        )
        try:
            answer = self.chat.chat([
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

    def validate_citations(self, state: RAGState) -> RAGState:
        if not state.answer or not state.reranked_chunks:
            return state
        if not state.evidence_sufficient:
            return state

        evidence_urls = {c.github_url or c.chunk_id for c in state.reranked_chunks}
        state.citations = extract_citations_from_answer(state.answer, evidence_urls)
        is_valid, invalid_urls = validate_citations(state.answer, evidence_urls)

        if invalid_urls:
            logger.warning(
                "Found %d citations not in evidence: %s", len(invalid_urls), invalid_urls,
            )
            stripped = state.answer
            for url in invalid_urls:
                stripped = stripped.replace(url, "")
            state.answer = stripped.strip()
            if not state.answer:
                state.answer = (
                    "I was unable to provide an answer with verifiable citations "
                    "from the indexed content."
                )
            state.citations = extract_citations_from_answer(state.answer, evidence_urls)
            state.confidence = "low"

        if not state.citations:
            state.citations = _build_fallback_citations(state.reranked_chunks)
            state.answer = _append_citations_to_answer(
                state.answer, state.reranked_chunks,
            )
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


def _build_fallback_citations(chunks: list[ScoredChunk]) -> list[Citation]:
    citations: list[Citation] = []
    seen_urls: set[str] = set()
    for c in chunks:
        url = c.github_url or ""
        if url and url not in seen_urls:
            seen_urls.add(url)
            citations.append(Citation(
                title=c.path or c.chunk_id,
                url=url,
                path=c.path,
                line_start=c.line_start,
                line_end=c.line_end,
            ))
    return citations


def _append_citations_to_answer(answer: str, chunks: list[ScoredChunk]) -> str:
    if not chunks:
        return answer
    lines = [answer.rstrip(), "", "Relevant sources from the repository:"]
    for i, c in enumerate(chunks[:5]):
        label = c.path or c.chunk_id
        url = c.github_url or ""
        if url:
            lines.append(f"- [{label}]({url})")
        else:
            lines.append(f"- {label}")
    return "\n".join(lines)


def build_rag_graph(chat_provider, retriever, reranker=None):
    from app.retrieval.rerank import IdentityReranker
    ctx = _NodeContext(chat_provider, retriever, reranker or IdentityReranker())

    workflow = StateGraph(RAGState)

    workflow.add_node("normalize_question", ctx.normalize_question)
    workflow.add_node("query_rewrite", ctx.query_rewrite)
    workflow.add_node("hybrid_retrieve", ctx.hybrid_retrieve)
    workflow.add_node("rerank", ctx.rerank)
    workflow.add_node("evidence_check", ctx.evidence_check)
    workflow.add_node("generate_answer", ctx.generate_answer)
    workflow.add_node("validate_citations", ctx.validate_citations)

    workflow.set_entry_point("normalize_question")
    workflow.add_edge("normalize_question", "query_rewrite")
    workflow.add_edge("query_rewrite", "hybrid_retrieve")
    workflow.add_edge("hybrid_retrieve", "rerank")
    workflow.add_edge("rerank", "evidence_check")
    workflow.add_edge("evidence_check", "generate_answer")
    workflow.add_edge("generate_answer", "validate_citations")
    workflow.add_edge("validate_citations", END)

    return workflow.compile()
