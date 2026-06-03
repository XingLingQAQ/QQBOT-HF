"""Thin wrapper around ``supervisorctl`` to control the managed programs.

Program names are fixed internal constants (``backend`` / ``lagrange`` /
``nonebot`` / ``signserver`` / ``napcat``) and are never derived from user
input, so there is no command injection surface here. All subprocess calls use
argument arrays (never ``shell=True``).
"""

import subprocess
from typing import Tuple

from . import config

_SERVERURL = f"http://{config.SUPERVISOR_HOST}:{config.SUPERVISOR_PORT}"

# Every program supervisord may manage. Used as the whitelist for any control
# action so that an out-of-set name is rejected before reaching supervisorctl.
_PROGRAMS = frozenset(
    {
        config.PROG_BACKEND,
        config.PROG_LAGRANGE,
        config.PROG_NONEBOT,
        config.PROG_SIGNSERVER,
        config.PROG_NAPCAT,
    }
)


def _supervisorctl(*args: str) -> Tuple[int, str]:
    """Run ``supervisorctl -s <server> <args...>`` and return (rc, combined output)."""
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
    if program not in _PROGRAMS:
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
    # Strip any duplicated NoneBot core that a `pip install --target` (plugin
    # install) left in the overlay dir before (re)starting, otherwise it would
    # shadow the system nonebot+adapter and crash NoneBot. Covers every caller
    # (install/uninstall/toggle/config/restart), not just container boot.
    from . import utils

    utils.prune_overlay_nonebot_core()
    return supervisor_ctl("restart", config.PROG_NONEBOT)


def stop_lagrange() -> Tuple[int, str]:
    return supervisor_ctl("stop", config.PROG_LAGRANGE)


def stop_nonebot() -> Tuple[int, str]:
    return supervisor_ctl("stop", config.PROG_NONEBOT)


def apply_protocol(protocol: str) -> str:
    """Start/stop programs so only the selected QQ protocol backend runs.

    lagrange => start signserver + lagrange, stop napcat.
    napcat   => start napcat, stop lagrange + signserver.

    NoneBot is restarted so it drops the old reverse-WS connection and accepts
    the newly selected backend. Returns a combined log of the supervisor calls.
    Stopping an already-stopped program is not treated as an error.
    """
    if protocol not in config.VALID_PROTOCOLS:
        raise ValueError(f"invalid protocol: {protocol}")

    if protocol == config.PROTOCOL_NAPCAT:
        steps = [
            ("stop", config.PROG_LAGRANGE),
            ("stop", config.PROG_SIGNSERVER),
            ("start", config.PROG_NAPCAT),
        ]
    else:
        steps = [
            ("stop", config.PROG_NAPCAT),
            ("start", config.PROG_SIGNSERVER),
            ("start", config.PROG_LAGRANGE),
        ]
    steps.append(("restart", config.PROG_NONEBOT))

    logs = []
    for action, program in steps:
        _, output = supervisor_ctl(action, program)
        logs.append(f"$ supervisorctl {action} {program}\n{output}".strip())
    return "\n".join(logs)
