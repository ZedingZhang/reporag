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

logger = logging.getLogger(__name__)


def load_dataset(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def compute_recall_at_k(retrieved_paths: list[str], expected_sources: list[str], k: int = 5) -> float:
    if not expected_sources:
        return 0.0
    top_k = retrieved_paths[:k]
    matched = sum(1 for src in expected_sources if any(src in p for p in top_k))
    return matched / len(expected_sources)


def compute_mrr(retrieved_paths: list[str], expected_sources: list[str]) -> float:
    if not expected_sources:
        return 0.0
    for rank, path in enumerate(retrieved_paths, start=1):
        if any(src in path for src in expected_sources):
            return 1.0 / rank
    return 0.0


def evaluate(
    dataset_path: str,
    recall_k: int = 5,
) -> dict:
    items = load_dataset(dataset_path)
    if not items:
        logger.warning("No items found in dataset: %s", dataset_path)
        return {"error": "empty dataset"}

    total_recall = 0.0
    total_mrr = 0.0
    total_citation_coverage = 0.0
    total_latency = 0.0
    refusal_correct = 0
    refusal_total = 0

    results: list[dict] = []

    for i, item in enumerate(items):
        logger.info("Evaluating item %d/%d: %s", i + 1, len(items), item.get("question", ""))

        start = time.monotonic()

        # Placeholder for actual retrieval — Phase 5 will wire this up
        retrieved_paths: list[str] = []
        answer = ""
        citations: list[dict] = []

        elapsed = time.monotonic() - start

        recall = compute_recall_at_k(retrieved_paths, item.get("expected_sources", []), recall_k)
        mrr = compute_mrr(retrieved_paths, item.get("expected_sources", []))
        citation_cov = 1.0 if citations else 0.0

        total_recall += recall
        total_mrr += mrr
        total_citation_coverage += citation_cov
        total_latency += elapsed

        results.append({
            "question": item["question"],
            "recall_at_k": recall,
            "mrr": mrr,
            "citation_coverage": citation_cov,
            "latency_seconds": round(elapsed, 3),
            "num_retrieved": len(retrieved_paths),
            "num_citations": len(citations),
        })

    n = len(items)
    metrics = {
        "num_items": n,
        f"recall_at_{recall_k}": round(total_recall / n, 4) if n else 0.0,
        "mrr": round(total_mrr / n, 4) if n else 0.0,
        "citation_coverage": round(total_citation_coverage / n, 4) if n else 0.0,
        "avg_latency_seconds": round(total_latency / n, 3) if n else 0.0,
        "results": results,
    }

    if refusal_total > 0:
        metrics["refusal_correctness"] = round(refusal_correct / refusal_total, 4)

    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate RepoRAG retrieval quality")
    parser.add_argument("--dataset", "-d", required=True, help="Path to eval dataset JSONL")
    parser.add_argument("--recall-k", "-k", type=int, default=5, help="K for Recall@k (default: 5)")
    parser.add_argument("--output", "-o", default=None, help="Path to write JSON results")
    return parser


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    if not Path(args.dataset).exists():
        logger.error("Dataset not found: %s", args.dataset)
        return

    metrics = evaluate(args.dataset, recall_k=args.recall_k)

    print(f"\nEvaluation Results ({metrics.get('num_items', 0)} items):")
    for key, value in metrics.items():
        if key == "results":
            continue
        print(f"  {key}: {value}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
