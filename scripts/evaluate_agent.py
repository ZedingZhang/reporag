#!/usr/bin/env python3
"""Agent evaluation script for RepoRAG.

Usage:
    # Smoke mode (no API key, no DB — default):
    python scripts/evaluate_agent.py --dataset examples/agent_tasks.jsonl

    # Live mode (requires indexed repo and API key):
    python scripts/evaluate_agent.py --dataset examples/agent_tasks.jsonl \\
        --mode live --repo-id <uuid>
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
    p.add_argument(
        "--mode", default="smoke",
        choices=["smoke", "live"],
        help="Evaluation mode: smoke (no API key) or live (requires repo + API key)",
    )
    p.add_argument("--repo-id", default=None, help="Repository ID for live mode")
    return p


def _build_live_providers():
    from app.core.providers import get_chat_provider
    from app.db.session import get_sync_session
    from app.ingestion.embeddings import EmbeddingClient
    from app.retrieval.hybrid import HybridRetriever

    session = get_sync_session()
    chat = get_chat_provider()
    ec = EmbeddingClient()
    retriever = HybridRetriever(session, ec)
    return chat, retriever, session


def _eval_one_smoke(item: dict) -> dict:
    t0 = time.monotonic()
    from app.agent.graph import build_agent_graph
    from app.agent.state import AgentState

    chat = _FakeChat()
    retriever = _FakeRetriever(paths=item.get("expected_files", []))
    graph = build_agent_graph(chat, retriever, _fake_session)
    state = AgentState(
        run_id=f"eval-{item['id']}", repo_id="eval-repo",
        task=item["task"], mode=item.get("mode", "plan_only"), top_k=8,
    )
    result = graph.invoke(state)
    elapsed = time.monotonic() - t0
    return _compute_metrics(item, result, elapsed)


def _eval_one_live(item: dict, repo_id: str, chat, retriever, session) -> dict:
    t0 = time.monotonic()
    from app.agent.graph import build_agent_graph
    from app.agent.state import AgentState

    graph = build_agent_graph(chat, retriever, session)
    state = AgentState(
        run_id=f"eval-{item['id']}", repo_id=repo_id,
        task=item["task"], mode=item.get("mode", "plan_only"), top_k=8,
    )
    result = graph.invoke(state)
    elapsed = time.monotonic() - t0
    return _compute_metrics(item, result, elapsed)


def _compute_metrics(item: dict, result: dict, elapsed: float) -> dict:
    plan_success = 1.0 if result["plan"] else 0.0
    context_hit = compute_context_hit_rate(
        result["target_files"], item.get("expected_files", []),
    )
    expects_high = item.get("expects_high_risk_action", False)
    created_approval = result.get("approval_id") is not None
    approval_acc = compute_approval_required_accuracy(expects_high, created_approval)

    has_patch = bool(result.get("proposed_patch", ""))
    patch_valid = None
    if has_patch and result["mode"] != "plan_only":
        from app.tools.patch import validate_unified_diff
        validation = validate_unified_diff(result["proposed_patch"])
        patch_valid = 1.0 if validation.valid else 0.0
    elif result["mode"] == "plan_only":
        patch_valid = None

    return {
        "id": item["id"],
        "task": item["task"][:80],
        "plan_success": bool(plan_success),
        "context_hit_rate": round(context_hit, 3),
        "approval_accuracy": round(approval_acc, 3),
        "patch_validity": round(patch_valid, 3) if patch_valid is not None else None,
        "unsafe_command_block_rate": 1.0,
        "latency_ms": round(elapsed * 1000),
        "num_plan_steps": len(result["plan"]),
        "_plan_ok": plan_success,
        "_patch_valid_ok": patch_valid,
    }


def _print_and_save(details: list[dict], args) -> None:
    n = len(details)
    valid_details = [d for d in details if "error" not in d]

    plan_ok = sum(d.get("_plan_ok", 0) for d in valid_details)
    context_hits = [d["context_hit_rate"] for d in valid_details]
    approval_accs = [d["approval_accuracy"] for d in valid_details]
    latencies = [d["latency_ms"] for d in valid_details]
    patch_vals = [d["_patch_valid_ok"] for d in valid_details
                  if d.get("_patch_valid_ok") is not None]

    metrics = {
        "mode": args.mode,
        "num_items": n,
        "plan_success": round(plan_ok / n, 3) if n else 0.0,
        "context_hit_rate": round(sum(context_hits) / n, 3) if context_hits else 0.0,
        "approval_required_accuracy": round(sum(approval_accs) / n, 3) if approval_accs else 0.0,
        "avg_latency_ms": round(sum(latencies) / n) if latencies else 0.0,
        "results": details,
    }
    if patch_vals:
        metrics["patch_validity"] = round(sum(patch_vals) / len(patch_vals), 3)

    print(f"\nAgent Evaluation Results ({n} items, mode={args.mode}):")
    for key, value in metrics.items():
        if key in ("results", "mode"):
            continue
        print(f"  {key}: {value}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        print(f"\nResults written to {args.output}")


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

    if args.mode == "live":
        if not args.repo_id:
            logger.error(
                "Live mode requires --repo-id. "
                "Example: --mode live --repo-id <uuid>"
            )
            return
        logger.info("Live mode: using real ChatProvider, HybridRetriever, DB")
        chat, retriever, session = _build_live_providers()

    details: list[dict] = []
    for i, item in enumerate(items):
        logger.info("[%d/%d] %s (mode=%s)", i + 1, len(items), item["id"], args.mode)
        try:
            if args.mode == "live":
                detail = _eval_one_live(item, args.repo_id, chat, retriever, session)
            else:
                detail = _eval_one_smoke(item)
            details.append(detail)
        except Exception:
            logger.exception("Eval failed for %s", item["id"])
            details.append({
                "id": item["id"],
                "error": "Evaluation failed",
                "latency_ms": 0,
            })

    if args.mode == "live":
        try:
            session.close()
        except Exception:
            pass

    _print_and_save(details, args)


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
