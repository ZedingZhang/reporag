from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PatchValidationResult:
    valid: bool
    reason: str = ""
    file_count: int = 0
    files: list[str] = field(default_factory=list)
    hunks: list[str] = field(default_factory=list)


@dataclass
class PatchSummary:
    file_count: int
    added_lines: int
    removed_lines: int
    files: list[str]
    is_no_patch: bool = False


@dataclass
class PatchApplyResult:
    success: bool
    files: list[str] = field(default_factory=list)
    status: str = ""
    stdout: str = ""
    stderr: str = ""
    error: str = ""


def validate_unified_diff(diff: str) -> PatchValidationResult:
    if not diff or not diff.strip():
        return PatchValidationResult(False, reason="Empty diff")

    stripped = diff.strip()

    if stripped.startswith("NO_PATCH"):
        return PatchValidationResult(False, reason=stripped)

    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)

    has_diff_header = bool(re.search(r"^diff --git ", stripped, re.MULTILINE))
    has_hunk = bool(re.search(r"^@@ -\d+,\d+ \+\d+,\d+ @@", stripped, re.MULTILINE))
    has_file_header = bool(re.search(r"^--- a/", stripped, re.MULTILINE))
    has_plusminus = bool(re.search(r"^[\+\-]", stripped, re.MULTILINE))

    if not (has_diff_header or has_hunk or (has_file_header and has_plusminus)):
        return PatchValidationResult(
            False,
            reason="Not a valid unified diff: missing diff header, hunk, or +/- lines",
        )

    file_headers = re.findall(r"^diff --git a/(.+) b/(.+)", stripped, re.MULTILINE)
    files = [f[0] for f in file_headers] if file_headers else ["unknown"]

    if not file_headers:
        match = re.search(r"^\+\+\+ b/(.+)", stripped, re.MULTILINE)
        if match:
            files = [match.group(1)]

    hunks = re.findall(
        r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@.*$",
        stripped, re.MULTILINE,
    )

    return PatchValidationResult(
        valid=True,
        file_count=len(files),
        files=files,
        hunks=hunks,
        reason=f"Valid unified diff with {len(files)} file(s), {len(hunks)} hunk(s)",
    )


def summarize_patch(diff: str) -> PatchSummary:
    result = validate_unified_diff(diff)

    if not result.valid:
        if "NO_PATCH" in (diff or ""):
            return PatchSummary(file_count=0, added_lines=0, removed_lines=0,
                                files=[], is_no_patch=True)
        return PatchSummary(file_count=0, added_lines=0, removed_lines=0, files=[])

    added = len(re.findall(r"^\+[^\+]", diff, re.MULTILINE))
    removed = len(re.findall(r"^\-[^\-]", diff, re.MULTILINE))

    return PatchSummary(
        file_count=result.file_count,
        added_lines=added,
        removed_lines=removed,
        files=result.files,
    )


def apply_patch_to_workspace(diff: str, workspace_root: str) -> PatchApplyResult:
    validation = validate_unified_diff(diff)
    if not validation.valid:
        return PatchApplyResult(
            success=False, status="invalid_diff", error=validation.reason,
        )

    root = Path(workspace_root).resolve()
    if not root.exists():
        return PatchApplyResult(
            success=False, status="no_workspace",
            error=f"Workspace root does not exist: {root}",
        )

    from app.security.path_guard import PathGuard
    guard = PathGuard(str(root))
    for f in validation.files:
        check = guard.check_write(f)
        if not check.allowed:
            return PatchApplyResult(
                success=False, status="path_blocked",
                error=f"PathGuard blocked {f}: {check.reason}",
                files=validation.files,
            )

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".diff", delete=False, prefix="reporag_patch_",
        ) as tmp:
            tmp.write(diff)
            tmp_path = tmp.name

        check_result = subprocess.run(
            ["git", "apply", "--check", tmp_path],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if check_result.returncode != 0:
            return PatchApplyResult(
                success=False, status="check_failed",
                stdout=check_result.stdout[:2000],
                stderr=check_result.stderr[:2000],
                error=f"git apply --check failed: {check_result.stderr[:500]}",
                files=validation.files,
            )

        apply_result = subprocess.run(
            ["git", "apply", tmp_path],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        Path(tmp_path).unlink(missing_ok=True)

        if apply_result.returncode != 0:
            return PatchApplyResult(
                success=False, status="apply_failed",
                stdout=apply_result.stdout[:2000],
                stderr=apply_result.stderr[:2000],
                error=f"git apply failed: {apply_result.stderr[:500]}",
                files=validation.files,
            )

        return PatchApplyResult(
            success=True, status="applied",
            stdout=apply_result.stdout[:2000],
            files=validation.files,
        )

    except subprocess.TimeoutExpired:
        Path(tmp_path).unlink(missing_ok=True)
        return PatchApplyResult(
            success=False, status="timeout",
            error="git apply timed out after 30s",
        )
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        return PatchApplyResult(
            success=False, status="error", error=str(e),
        )
