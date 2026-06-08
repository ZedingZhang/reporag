from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentState:
    run_id: str
    repo_id: str
    task: str
    mode: str = "plan_only"
    top_k: int = 8

    task_type: str = ""
    plan: list[dict] = field(default_factory=list)
    context_queries: list[str] = field(default_factory=list)
    retrieved_context: list[dict] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)

    proposed_patch: str = ""
    approval_id: Optional[str] = None
    approval_status: Optional[str] = None

    command_plan: list[dict] = field(default_factory=list)
    command_results: list[dict] = field(default_factory=list)

    final_summary: str = ""
    status: str = "created"
    errors: list[str] = field(default_factory=list)
