#!/usr/bin/env python3
"""Offline evaluation script for RepoRAG.

Usage:
    python scripts/evaluate.py --dataset examples/eval_dataset.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from app.core.logging import setup_logging
from app.core.providers import get_chat_provider
from app.db.models import Repository
from app.db.session import get_sync_session
from app.ingestion.embeddings import EmbeddingClient
from app.rag.graph import build_rag_graph
from app.retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)


def load_dataset(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def compute_recall_at_k(
    retrieved_paths: list[str], expected_sources: list[str], k: int = 5
) -> float:
    if not expected_sources:
        return 0.0
    top_k = retrieved_paths[:k]
    matched = sum(1 for src in expected_sources if any(src in p for p in top_k))
    return matched / len(expected_sources)


def compute_mrr(
    retrieved_paths: list[str], expected_sources: list[str]
) -> float:
    if not expected_sources:
        return 0.0
    for rank, path in enumerate(retrieved_paths, start=1):
        if any(src in path for src in expected_sources):
            return 1.0 / rank
    return 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate RepoRAG retrieval quality")
    parser.add_argument(
        "--dataset", "-d", required=True, help="Path to eval dataset JSONL"
    )
    parser.add_argument(
        "--recall-k", "-k", type=int, default=5, help="K for Recall@k (default: 5)"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="Path to write JSON results"
    )
    return parser


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error("Dataset not found: %s", args.dataset)
        return

    items = load_dataset(str(dataset_path))
    if not items:
        logger.warning("No items in dataset")
        return

    session = get_sync_session()
    try:
        chat_provider = get_chat_provider()
        embedding_client = EmbeddingClient()
        retriever = HybridRetriever(session, embedding_client)
        graph = build_rag_graph(chat_provider, retriever)

        total_recall = 0.0
        total_mrr = 0.0
        total_citation_cov = 0.0
        total_latency = 0.0
        details: list[dict] = []

        for i, item in enumerate(items):
            repo_url = item.get("repo_url", "")
            question = item.get("question", "")
            expected_sources = item.get("expected_sources", [])

            # Find repo by URL
            owner = name = ""
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                name = parts[-1]
                owner = parts[-2]

            repo = (
                session.query(Repository)
                .filter(Repository.owner == owner, Repository.name == name)
                .first()
            )

            if not repo or repo.status != "completed":
                logger.warning(
                    "Item %d: repo %s not indexed, skipping", i + 1, repo_url
                )
                details.append({
                    "question": question,
                    "status": "skipped",
                    "reason": "Repository not indexed",
                })
                continue

            logger.info("[%d/%d] %s", i + 1, len(items), question[:80])

            start = time.monotonic()

            state = graph.invoke({
                "repo_id": repo.id, "question": question,
                "top_k": args.recall_k,
            })
            elapsed = time.monotonic() - start
            retrieved_paths = [
                c.path or "" for c in state["reranked_chunks"]
            ]
            recall = compute_recall_at_k(
                retrieved_paths, expected_sources, args.recall_k,
            )
            mrr = compute_mrr(retrieved_paths, expected_sources)
            citation_cov = 1.0 if state["citations"] else 0.0

            total_recall += recall
            total_mrr += mrr
            total_citation_cov += citation_cov
            total_latency += elapsed

            details.append({
                "question": question,
                f"recall_at_{args.recall_k}": recall,
                "mrr": mrr,
                "citation_coverage": citation_cov,
                "latency_seconds": round(elapsed, 3),
                "num_retrieved": len(state["reranked_chunks"]),
                "num_citations": len(state["citations"]),
                "confidence": state["confidence"],
            })

        n = len(details)
        metrics = {
            "num_items": n,
            f"recall_at_{args.recall_k}": round(total_recall / n, 4) if n else 0.0,
            "mrr": round(total_mrr / n, 4) if n else 0.0,
            "citation_coverage": round(total_citation_cov / n, 4) if n else 0.0,
            "avg_latency_seconds": round(total_latency / n, 3) if n else 0.0,
            "results": details,
        }

        print(f"\nEvaluation Results ({n} items):")
        for key, value in metrics.items():
            if key == "results":
                continue
            print(f"  {key}: {value}")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(metrics, f, indent=2)
            print(f"\nResults written to {args.output}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
