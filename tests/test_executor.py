from __future__ import annotations

from app.tools.executor import run_safe_command


class TestRunSafeCommand:
    def test_runs_pytest_version(self) -> None:
        result = run_safe_command(["python3", "-m", "pytest", "--version"])
        assert result.status in ("completed", "failed")
        assert result.exit_code != -1
        assert result.duration_ms >= 0

    def test_runs_ruff_check(self) -> None:
        result = run_safe_command(["python3", "-m", "ruff", "check", "--version"])
        assert result.status in ("completed", "failed")
        assert result.exit_code != -1

    def test_blocks_rm(self) -> None:
        result = run_safe_command(["rm", "-rf"])
        assert result.status == "blocked"
        assert result.error != ""

    def test_blocks_curl(self) -> None:
        result = run_safe_command(["curl", "http://example.com"])
        assert result.status == "blocked"

    def test_blocks_shell_metacharacter(self) -> None:
        result = run_safe_command(["ls", "|", "grep"])
        assert result.status == "blocked"

    def test_captures_exit_code_on_failure(self) -> None:
        result = run_safe_command(
            ["python3", "-m", "pytest", "--nonexistent-flag"],
        )
        assert result.status in ("failed", "completed")
        assert result.exit_code != 0

    def test_records_command(self) -> None:
        result = run_safe_command(["python3", "-m", "pytest", "--version"])
        assert result.command == ["python3", "-m", "pytest", "--version"]

    def test_pytest_basic_works(self) -> None:
        result = run_safe_command(
            ["python3", "-m", "pytest", "--version"], timeout_s=30,
        )
        assert result.status in ("completed", "failed")
        assert result.duration_ms > 0
        assert result.duration_ms < 30000

    def test_stdout_captured(self) -> None:
        result = run_safe_command(["python3", "-m", "pytest", "--version"])
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)

    def test_duration_ms_set(self) -> None:
        result = run_safe_command(["python3", "-m", "pytest", "--version"])
        assert result.duration_ms > 0
