from __future__ import annotations

from dataclasses import dataclass

ALLOWED_COMMANDS = {
    "pytest",
    "python",
    "ruff",
}

BLOCKED_COMMANDS = {
    "rm",
    "sudo",
    "curl",
    "wget",
    "nc",
    "ssh",
    "chmod",
    "chown",
}

BLOCKED_SUBCOMMANDS = {
    "git push",
    "git reset --hard",
    "git push --force",
}

SHELL_METACHARACTERS = {"`", "$(", "${", "|", ";", "&&", "||", ">", "<"}


@dataclass
class CommandCheckResult:
    allowed: bool
    reason: str = ""
    blocked_by: str = ""


class CommandGuard:
    def check(self, command: list[str]) -> CommandCheckResult:
        if not command:
            return CommandCheckResult(False, reason="Empty command")

        if isinstance(command, str):
            return CommandCheckResult(
                False, reason="Command must be a list, not a string",
            )

        cmd_str = " ".join(command)
        executable = command[0].split("/")[-1]

        for meta in SHELL_METACHARACTERS:
            if meta in cmd_str:
                return CommandCheckResult(
                    False,
                    reason=f"Shell metacharacter blocked: {meta}",
                    blocked_by=meta,
                )

        if executable in BLOCKED_COMMANDS:
            return CommandCheckResult(
                False,
                reason=f"Blocked command: {executable}",
                blocked_by=executable,
            )

        for blocked_sub in BLOCKED_SUBCOMMANDS:
            if blocked_sub in cmd_str:
                return CommandCheckResult(
                    False,
                    reason=f"Blocked subcommand: {blocked_sub}",
                    blocked_by=blocked_sub,
                )

        if executable == "python":
            if len(command) < 2:
                return CommandCheckResult(False, reason="python needs subcommand")
            sub = command[1]
            if sub not in ("-m", "-c"):
                return CommandCheckResult(False, reason=f"python {sub} not allowed")
            if sub == "-m":
                if len(command) < 3:
                    return CommandCheckResult(False, reason="python -m needs module")
                module = command[2]
                if module not in ("pytest", "ruff", "pip"):
                    return CommandCheckResult(
                        False, reason=f"python -m {module} not allowed",
                    )

        if executable not in ALLOWED_COMMANDS and executable not in ("python",):
            return CommandCheckResult(
                False, reason=f"Command not in allowlist: {executable}",
            )

        return CommandCheckResult(True)
