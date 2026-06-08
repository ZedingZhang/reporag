from __future__ import annotations

from app.security.command_guard import CommandGuard


class TestCommandGuard:
    def setup_method(self) -> None:
        self.guard = CommandGuard()

    def test_allows_pytest(self) -> None:
        result = self.guard.check(["pytest"])
        assert result.allowed, result.reason

    def test_allows_pytest_with_file(self) -> None:
        result = self.guard.check(["pytest", "tests/test_citations.py"])
        assert result.allowed, result.reason

    def test_allows_ruff(self) -> None:
        result = self.guard.check(["ruff", "check", "."])
        assert result.allowed, result.reason

    def test_allows_python_m_pytest(self) -> None:
        result = self.guard.check(["python", "-m", "pytest"])
        assert result.allowed, result.reason

    def test_blocks_rm(self) -> None:
        result = self.guard.check(["rm", "-rf", "/"])
        assert not result.allowed
        assert "rm" in result.blocked_by

    def test_blocks_sudo(self) -> None:
        result = self.guard.check(["sudo", "pytest"])
        assert not result.allowed

    def test_blocks_curl(self) -> None:
        result = self.guard.check(["curl", "http://example.com"])
        assert not result.allowed

    def test_blocks_shell_metacharacter_pipe(self) -> None:
        result = self.guard.check(["ls", "|", "grep"])
        assert not result.allowed
        assert "|" == result.blocked_by

    def test_blocks_shell_metacharacter_semicolon(self) -> None:
        result = self.guard.check(["pytest;", "rm"])
        assert not result.allowed
        assert ";" == result.blocked_by

    def test_blocks_shell_metacharacter_dollar_paren(self) -> None:
        result = self.guard.check(["echo", "$(whoami)"])
        assert not result.allowed
        assert "$(" == result.blocked_by

    def test_blocks_shell_metacharacter_backtick(self) -> None:
        result = self.guard.check(["echo", "`whoami`"])
        assert not result.allowed
        assert "`" == result.blocked_by

    def test_blocks_shell_metacharacter_double_ampersand(self) -> None:
        result = self.guard.check(["pytest", "&&", "rm"])
        assert not result.allowed

    def test_blocks_git_push(self) -> None:
        result = self.guard.check(["git", "push"])
        assert not result.allowed

    def test_blocks_git_reset_hard(self) -> None:
        result = self.guard.check(["git", "reset", "--hard"])
        assert not result.allowed

    def test_blocks_ssh(self) -> None:
        result = self.guard.check(["ssh", "user@host"])
        assert not result.allowed

    def test_blocks_chmod(self) -> None:
        result = self.guard.check(["chmod", "777", "file"])
        assert not result.allowed

    def test_empty_command_rejected(self) -> None:
        result = self.guard.check([])
        assert not result.allowed

    def test_string_command_rejected(self) -> None:
        result = self.guard.check("pytest")
        assert not result.allowed

    def test_blocks_unknown_command(self) -> None:
        result = self.guard.check(["unknown_cmd", "arg"])
        assert not result.allowed

    def test_blocks_python_dash_c(self) -> None:
        assert not self.guard.check(["python3", "-c", "import os"]).allowed

    def test_blocks_python_m_pip(self) -> None:
        assert not self.guard.check(
            ["python3", "-m", "pip", "install", "requests"],
        ).allowed

    def test_blocks_python_m_pip_variant(self) -> None:
        assert not self.guard.check(
            ["python", "-m", "pip", "install", "requests"],
        ).allowed

    def test_blocks_executable_path(self) -> None:
        assert not self.guard.check(
            ["/tmp/python3", "-m", "pytest"],
        ).allowed

    def test_blocks_executable_backslash(self) -> None:
        assert not self.guard.check(
            [".\\python3", "-m", "pytest"],
        ).allowed

    def test_allows_python_m_pytest_file(self) -> None:
        assert self.guard.check(
            ["python3", "-m", "pytest", "tests/test_citations.py"],
        ).allowed

    def test_allows_python_m_pytest_flags(self) -> None:
        assert self.guard.check(
            ["python3", "-m", "pytest", "-q", "--tb=short"],
        ).allowed

    def test_allows_ruff_check(self) -> None:
        assert self.guard.check(["ruff", "check"]).allowed

    def test_blocks_bash(self) -> None:
        assert not self.guard.check(["bash", "script.sh"]).allowed

    def test_blocks_sh(self) -> None:
        assert not self.guard.check(["sh", "script.sh"]).allowed

    def test_blocks_pip_direct(self) -> None:
        assert not self.guard.check(["pip", "install", "requests"]).allowed

    def test_blocks_git(self) -> None:
        assert not self.guard.check(["git", "status"]).allowed
