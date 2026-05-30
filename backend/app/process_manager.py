"""Thin wrapper around ``supervisorctl`` to control the three managed programs.

Program names are fixed internal constants (``backend`` / ``lagrange`` /
``nonebot``) and are never derived from user input, so there is no command
injection surface here. All subprocess calls use argument arrays (never
``shell=True``).
"""

import subprocess
from typing import Tuple

from . import config

_SERVERURL = f"unix://{config.SUPERVISOR_SOCK}"


def _supervisorctl(*args: str) -> Tuple[int, str]:
    """Run ``supervisorctl -s <sock> <args...>`` and return (rc, combined output)."""
    cmd = ["supervisorctl", "-s", _SERVERURL, *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return 127, "supervisorctl not found"
    except subprocess.TimeoutExpired:
        return 124, "supervisorctl timed out"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def supervisor_ctl(action: str, program: str) -> Tuple[int, str]:
    """Run a supervisor action against a program. ``action`` is whitelisted."""
    if action not in {"start", "stop", "restart", "status"}:
        raise ValueError(f"invalid action: {action}")
    if program not in {config.PROG_BACKEND, config.PROG_LAGRANGE, config.PROG_NONEBOT}:
        raise ValueError(f"invalid program: {program}")
    return _supervisorctl(action, program)


def get_status(program: str) -> str:
    """Return the supervisor state of a program (e.g. RUNNING/STOPPED/FATAL).

    Returns ``UNKNOWN`` if the state cannot be determined.
    """
    rc, output = supervisor_ctl("status", program)
    # `supervisorctl status <prog>` => "lagrange   RUNNING   pid 12, uptime 0:01:23"
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == program:
            return parts[1]
    return "UNKNOWN"


def restart_lagrange() -> Tuple[int, str]:
    return supervisor_ctl("restart", config.PROG_LAGRANGE)


def restart_nonebot() -> Tuple[int, str]:
    return supervisor_ctl("restart", config.PROG_NONEBOT)


def stop_lagrange() -> Tuple[int, str]:
    return supervisor_ctl("stop", config.PROG_LAGRANGE)


def stop_nonebot() -> Tuple[int, str]:
    return supervisor_ctl("stop", config.PROG_NONEBOT)
