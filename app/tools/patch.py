from __future__ import annotations

import re
from dataclasses import dataclass, field


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
