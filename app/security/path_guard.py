from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_BASENAMES = {
    ".env", ".git", "__pycache__", ".pytest_cache", ".ruff_cache",
    "node_modules", "venv", ".venv", ".tox",
}

FORBIDDEN_SUFFIXES = (".pyc", ".pem", ".key", ".p12")

FORBIDDEN_NAME_SUBSTRINGS = ("credentials", "secrets", "token", "secret", "password")


@dataclass
class PathCheckResult:
    allowed: bool
    reason: str = ""


class PathGuard:
    def __init__(self, workspace_root: str = "."):
        self._root = Path(workspace_root).resolve()

    def _resolve_under_root(self, path: str) -> tuple[Path | None, str | None]:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            common = os.path.commonpath([str(self._root), str(resolved)])
        except ValueError:
            return None, f"Path outside workspace: {path}"
        if common != str(self._root):
            return None, f"Path outside workspace: {path}"
        return resolved, None

    def _check_forbidden_parts(self, resolved: Path) -> str | None:
        try:
            rel = resolved.relative_to(self._root)
        except ValueError:
            return "Path outside workspace"
        parts = list(rel.parts)

        for part in parts:
            if part in FORBIDDEN_BASENAMES:
                return f"Forbidden path part: {part}"

            for suffix in FORBIDDEN_SUFFIXES:
                if part.endswith(suffix):
                    return f"Forbidden file suffix {suffix}: {part}"

            for substr in FORBIDDEN_NAME_SUBSTRINGS:
                if substr in part.lower():
                    return f"Forbidden pattern '{substr}' in: {part}"

            if part.startswith(".env"):
                return f"Forbidden: {part}"

        return None

    def check_write(self, path: str) -> PathCheckResult:
        resolved, err = self._resolve_under_root(path)
        if err:
            return PathCheckResult(False, reason=err)

        forbidden = self._check_forbidden_parts(resolved)
        if forbidden:
            return PathCheckResult(False, reason=forbidden)

        return PathCheckResult(True)

    def check_read(self, path: str) -> PathCheckResult:
        resolved, err = self._resolve_under_root(path)
        if err:
            return PathCheckResult(False, reason=err)

        forbidden = self._check_forbidden_parts(resolved)
        if forbidden:
            return PathCheckResult(False, reason=forbidden)

        return PathCheckResult(True)
