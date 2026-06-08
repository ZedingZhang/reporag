from __future__ import annotations

from dataclasses import dataclass

ALLOWED_PREFIXES: list[tuple[str, ...]] = [
    ("pytest",),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("ruff", "check"),
    ("ruff", "format", "--check"),
    ("python", "-m", "ruff", "check"),
    ("python3", "-m", "ruff", "check"),
    ("python", "-m", "ruff", "format", "--check"),
    ("python3", "-m", "ruff", "format", "--check"),
]

BLOCKED_EXECUTABLES = {
    "rm", "sudo", "curl", "wget", "nc", "ssh", "chmod", "chown",
    "git", "npm", "pip", "uv", "poetry", "bash", "sh", "zsh",
    "make", "cmake", "gcc", "g++", "docker", "kubectl", "systemctl",
}

BLOCKED_SUBCOMMANDS = [
    "git push", "git reset --hard", "git push --force",
    "pip install", "npm install",
]

SHELL_METACHARACTERS = {"`", "$(", "${", "|", ";", "&&", "||", ">", "<", "&", "\n"}


def _starts_with(command: list[str], prefix: tuple[str, ...]) -> bool:
    return len(command) >= len(prefix) and tuple(command[:len(prefix)]) == prefix


@dataclass
class CommandCheckResult:
    allowed: bool
    reason: str = ""
    blocked_by: str = ""


class CommandGuard:
    def check(self, command: list[str] | str) -> CommandCheckResult:
        # 1. Must be non-empty list
        if not command:
            return CommandCheckResult(False, reason="Empty command")
        if isinstance(command, str):
            return CommandCheckResult(
                False, reason="Command must be a list, not a string",
            )
        # 2. All elements must be non-empty strings
        for i, arg in enumerate(command):
            if not isinstance(arg, str) or not arg:
                return CommandCheckResult(
                    False,
                    reason=f"Argument {i} is empty or not a string",
                )
        # 3. executable must not contain / or \
        executable = command[0]
        if "/" in executable or "\\" in executable:
            return CommandCheckResult(
                False,
                reason=f"Executable path with / or \\ not allowed: {executable}",
                blocked_by=executable,
            )
        # 4. No argument may contain shell metacharacters
        cmd_str = " ".join(command)
        for meta in SHELL_METACHARACTERS:
            if meta in cmd_str:
                return CommandCheckResult(
                    False,
                    reason=f"Shell metacharacter blocked: {meta}",
                    blocked_by=meta,
                )
        # 5. Check blocked executables
        if executable in BLOCKED_EXECUTABLES:
            return CommandCheckResult(
                False,
                reason=f"Blocked command: {executable}",
                blocked_by=executable,
            )
        # 6. Check blocked subcommands
        for blocked_sub in BLOCKED_SUBCOMMANDS:
            if blocked_sub in cmd_str:
                return CommandCheckResult(
                    False,
                    reason=f"Blocked subcommand: {blocked_sub}",
                    blocked_by=blocked_sub,
                )
        # 7. Must match an allowed prefix
        for prefix in ALLOWED_PREFIXES:
            if _starts_with(command, prefix):
                return CommandCheckResult(True)
        return CommandCheckResult(
            False,
            reason=f"Command prefix not in allowlist: {command[:3]}",
        )
