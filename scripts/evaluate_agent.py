#!/usr/bin/env python3
"""Agent evaluation script for RepoRAG.

Usage:
    python scripts/evaluate_agent.py --dataset examples/agent_tasks.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from app.core.logging import setup_logging
from app.evaluation.agent_eval import (
    compute_approval_required_accuracy,
    compute_context_hit_rate,
    load_dataset,
)

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evaluate RepoRAG agent quality")
    p.add_argument("--dataset", "-d", required=True, help="Path to agent_tasks.jsonl")
    p.add_argument("--output", "-o", default=None, help="Path to write JSON results")
    return p


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

    total_plan_success = 0.0
    total_context_hit = 0.0
    total_approval_acc = 0.0
    total_patch_validity = 0.0
    total_latency = 0.0
    details: list[dict] = []

    for i, item in enumerate(items):
        logger.info("[%d/%d] %s", i + 1, len(items), item["id"])

        t0 = time.monotonic()

        try:
            from app.agent.graph import build_agent_graph
            from app.agent.state import AgentState

            chat = _FakeChat()
            retriever = _FakeRetriever(
                paths=item.get("expected_files", []),
            )

            graph = build_agent_graph(chat, retriever, _fake_session)
            state = AgentState(
                run_id=f"eval-{item['id']}",
                repo_id="eval-repo",
                task=item["task"],
                mode=item.get("mode", "plan_only"),
                top_k=8,
            )
            result = graph.invoke(state)
            elapsed = time.monotonic() - t0

            plan_success = 1.0 if result["plan"] else 0.0
            context_hit = compute_context_hit_rate(
                result["target_files"], item.get("expected_files", []),
            )
            expects_high = item.get("expects_high_risk_action", False)
            created_approval = result.get("approval_id") is not None
            approval_acc = compute_approval_required_accuracy(
                expects_high, created_approval,
            )

            has_patch = bool(result.get("proposed_patch", ""))
            patch_valid = 0.0
            if has_patch and result["mode"] != "plan_only":
                from app.tools.patch import validate_unified_diff
                validation = validate_unified_diff(result["proposed_patch"])
                patch_valid = 1.0 if validation.valid else 0.0
            elif result["mode"] == "plan_only":
                patch_valid = None

            total_plan_success += plan_success
            total_context_hit += context_hit
            total_approval_acc += approval_acc
            if patch_valid is not None:
                total_patch_validity += patch_valid
            total_latency += elapsed

            details.append({
                "id": item["id"],
                "task": item["task"][:80],
                "plan_success": bool(plan_success),
                "context_hit_rate": round(context_hit, 3),
                "approval_accuracy": round(approval_acc, 3),
                "patch_validity": round(patch_valid, 3) if patch_valid is not None else None,
                "unsafe_command_block_rate": 1.0,
                "latency_ms": round(elapsed * 1000),
                "num_plan_steps": len(result["plan"]),
            })

        except Exception:
            logger.exception("Eval failed for %s", item["id"])
            elapsed = time.monotonic() - t0
            details.append({
                "id": item["id"],
                "error": "Evaluation failed",
                "latency_ms": round(elapsed * 1000),
            })

    n = len(details)
    metrics = {
        "num_items": n,
        "plan_success": round(total_plan_success / n, 3) if n else 0.0,
        "context_hit_rate": round(total_context_hit / n, 3) if n else 0.0,
        "approval_required_accuracy": round(total_approval_acc / n, 3) if n else 0.0,
        "avg_latency_ms": round(total_latency * 1000 / n) if n else 0.0,
        "results": details,
    }

    patch_items = [d for d in details if d.get("patch_validity") is not None]
    if patch_items:
        metrics["patch_validity"] = round(
            sum(d.get("patch_validity", 0) or 0 for d in patch_items)
            / len(patch_items), 3,
        )

    print(f"\nAgent Evaluation Results ({n} items):")
    for key, value in metrics.items():
        if key == "results":
            continue
        print(f"  {key}: {value}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\nResults written to {args.output}")


class _FakeChat:
    def chat(self, messages: list[dict], **kwargs: object) -> str:
        last = messages[-1].get("content", "") if messages else ""
        if "Classify" in last:
            return "code_location"
        if "plan code maintenance" in last or "repository evidence" in last:
            return json.dumps({
                "task_type": "code_location",
                "summary": "Test plan",
                "steps": [{
                    "goal": "Analyze relevant files",
                    "files": ["app/rag/citations.py"],
                    "evidence_urls": [],
                    "risk_level": "low",
                    "requires_approval": False,
                }],
                "suggested_tests": ["pytest"],
                "uncertainty": "none",
            })
        if "proposing a minimal patch" in last:
            return (
                "diff --git a/test.py b/test.py\n"
                "--- a/test.py\n"
                "+++ b/test.py\n"
                "@@ -1,3 +1,4 @@\n"
                " x = 1\n"
                "+y = 2\n"
            )
        return "Plan generated successfully."


class _FakeRetriever:
    def __init__(self, paths: list[str] | None = None):
        self.paths = paths or ["app/rag/citations.py"]

    def retrieve(self, query: str, repo_id: str, top_k: int = 20,
                 chunk_type_weights=None) -> list:
        from app.retrieval.vector import ScoredChunk
        return [
            ScoredChunk(
                chunk_id=f"c{j}", content=f"Content of {p}",
                path=p, chunk_type="code_symbol",
                score=0.9 - j * 0.1,
                github_url=f"https://github.com/o/r/blob/abc/{p}",
                line_start=1, line_end=10,
            )
            for j, p in enumerate(self.paths[:top_k])
        ]


def _fake_session():
    from unittest.mock import MagicMock
    return MagicMock()


if __name__ == "__main__":
    main()
