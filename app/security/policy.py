from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionType(str, Enum):
    APPLY_PATCH = "apply_patch"
    RUN_COMMAND = "run_command"
    CREATE_PR = "create_pr"
    READ_ONLY = "read_only"


def classify_risk(action_type: str, command: list[str] | None = None) -> RiskLevel:
    if action_type in (ActionType.APPLY_PATCH, ActionType.CREATE_PR):
        return RiskLevel.HIGH
    if action_type == ActionType.RUN_COMMAND:
        return _classify_command_risk(command or [])
    if action_type == ActionType.READ_ONLY:
        return RiskLevel.LOW
    return RiskLevel.LOW if action_type == ActionType.READ_ONLY else RiskLevel.MEDIUM


def _classify_command_risk(command: list[str]) -> RiskLevel:
    cmd = " ".join(command).lower()
    high_keywords = ["rm ", "sudo", "curl", "wget", "ssh", "nc ", "chmod", "chown",
                     "git push", "git reset", "pip install", "npm install"]
    medium_keywords = ["pytest", "ruff", "python -m pytest", "pip list"]

    for kw in high_keywords:
        if kw in cmd:
            return RiskLevel.HIGH
    for kw in medium_keywords:
        if kw in cmd:
            return RiskLevel.MEDIUM
    return RiskLevel.HIGH


class ApprovalPolicy:
    def requires_approval(self, action_type: str, command: list[str] | None = None) -> bool:
        risk = classify_risk(action_type, command)
        if risk == RiskLevel.HIGH:
            return True
        if risk == RiskLevel.MEDIUM:
            return True
        return False

    def is_auto_allowed(
        self, action_type: str, mode: str, command: list[str] | None = None,
    ) -> bool:
        risk = classify_risk(action_type, command)
        if risk == RiskLevel.LOW:
            return True
        if mode == "execute_after_approval" and risk == RiskLevel.MEDIUM:
            return False
        return False
