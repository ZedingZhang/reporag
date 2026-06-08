from __future__ import annotations

import os
from dataclasses import dataclass

FORBIDDEN_PATTERNS = [
    ".env",
    ".git/",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".ruff_cache",
    "credentials",
    "secrets",
    "*.pem",
    "*.key",
]


@dataclass
class PathCheckResult:
    allowed: bool
    reason: str = ""


class PathGuard:
    def __init__(self, workspace_root: str = "."):
        self._root = os.path.abspath(workspace_root)

    def check_write(self, path: str) -> PathCheckResult:
        abs_path = os.path.abspath(path)

        if not abs_path.startswith(self._root):
            return PathCheckResult(
                False,
                reason=f"Path outside workspace: {path}",
            )

        if ".." in path.split(os.sep):
            return PathCheckResult(
                False,
                reason=f"Parent traversal blocked: {path}",
            )

        basename = os.path.basename(path)
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.startswith("*"):
                if basename.endswith(pattern[1:]):
                    return PathCheckResult(
                        False,
                        reason=f"Forbidden file pattern {pattern}: {path}",
                    )
            elif basename == pattern or pattern in path:
                return PathCheckResult(
                    False,
                    reason=f"Forbidden path: {path}",
                )

        return PathCheckResult(True)

    def check_read(self, path: str) -> PathCheckResult:
        if ".." in path.split(os.sep):
            return PathCheckResult(
                False,
                reason=f"Parent traversal blocked: {path}",
            )
        return PathCheckResult(True)
