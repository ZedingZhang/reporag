"""Agent evaluation metrics for programmatic use.

CLI entry point: python scripts/evaluate_agent.py --dataset examples/agent_tasks.jsonl
"""

from __future__ import annotations

import json


def load_dataset(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def compute_context_hit_rate(
    retrieved_files: list[str], expected_files: list[str],
) -> float:
    if not expected_files:
        return 0.0
    rset = {_normalize_path(p) for p in retrieved_files}
    matched = sum(
        1 for e in expected_files
        if any(_normalize_path(e) in r for r in rset)
    )
    return matched / len(expected_files)


def compute_approval_required_accuracy(
    expects_high_risk: bool, created_approval: bool,
) -> float:
    if expects_high_risk:
        return 1.0 if created_approval else 0.0
    return 1.0 if not created_approval else 0.5


def compute_plan_success(plan: list[dict]) -> float:
    return 1.0 if plan else 0.0


def _normalize_path(p: str) -> str:
    return p.rsplit("/", 1)[-1] if "/" in p else p
