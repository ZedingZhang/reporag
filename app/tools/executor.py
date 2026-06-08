from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass

from app.security.command_guard import CommandGuard

logger = logging.getLogger(__name__)

_guard = CommandGuard()


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    status: str = "completed"
    error: str = ""

    MAX_OUTPUT = 4000


def run_safe_command(
    command: list[str], cwd: str = ".", timeout_s: int = 60,
) -> CommandResult:
    check = _guard.check(command)
    if not check.allowed:
        return CommandResult(
            command=command, status="blocked", error=check.reason,
        )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True,
            timeout=timeout_s,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        return CommandResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout[:CommandResult.MAX_OUTPUT],
            stderr=proc.stderr[:CommandResult.MAX_OUTPUT],
            duration_ms=duration_ms,
            status="completed" if proc.returncode == 0 else "failed",
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            command=command,
            status="timeout",
            error=f"Command timed out after {timeout_s}s",
            duration_ms=timeout_s * 1000,
        )
    except Exception as e:
        return CommandResult(
            command=command,
            status="error",
            error=str(e),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
