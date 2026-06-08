from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.tools.patch import apply_patch_to_workspace


class TestApplyPatchToWorkspace:
    def test_no_workspace_returns_error(self) -> None:
        result = apply_patch_to_workspace("diff --git ...", "/nonexistent/path")
        assert not result.success
        assert result.status == "no_workspace"

    def test_invalid_diff_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".git").mkdir()
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            result = apply_patch_to_workspace("not a diff", tmpdir)
            assert not result.success
            assert result.status == "invalid_diff"

    def test_valid_diff_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            test_file = Path(tmpdir, "test.txt")
            test_file.write_text("line1\nline2\n")

            subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "init", "--allow-empty"],
                cwd=tmpdir, capture_output=True,
            )

            diff = (
                "diff --git a/test.txt b/test.txt\n"
                "--- a/test.txt\n"
                "+++ b/test.txt\n"
                "@@ -1,2 +1,3 @@\n"
                " line1\n"
                " line2\n"
                "+line3\n"
            )
            result = apply_patch_to_workspace(diff, tmpdir)
            assert result.success, f"Failed: {result.error} — {result.stderr}"
            assert result.status == "applied"
            assert "test.txt" in result.files
            assert "line3" in test_file.read_text()

    def test_env_file_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            diff = (
                "diff --git a/.env b/.env\n"
                "--- a/.env\n"
                "+++ b/.env\n"
                "@@ -1 +1,2 @@\n"
                " KEY=\n"
                "+KEY2=\n"
            )
            result = apply_patch_to_workspace(diff, tmpdir)
            assert not result.success
            assert result.status == "path_blocked" or "Forbidden" in result.error

    def test_path_outside_workspace_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            diff = (
                "diff --git a/../etc/passwd b/../etc/passwd\n"
                "--- a/../etc/passwd\n"
                "+++ b/../etc/passwd\n"
                "@@ -1 +1,2 @@\n"
                " root::\n"
                "+evil::\n"
            )
            result = apply_patch_to_workspace(diff, tmpdir)
            assert not result.success
