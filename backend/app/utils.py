"""Shared helpers: safe path joins, plugin manifest IO, dotenv editing."""

import glob
import json
import os
import re
import shlex
import shutil
from typing import Any, Dict, List

from fastapi import HTTPException

from . import config

_PLUGIN_NAME_RE = re.compile(r"^nonebot[-_]plugin[-_][A-Za-z0-9_-]+$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_join(base: str, *paths: str) -> str:
    """Join ``paths`` onto ``base`` and guarantee the result stays inside ``base``.

    Protects against path traversal (``..``) and symlink escapes. Raises a 400
    ``HTTPException`` if the resolved path would leave ``base``.
    """
    base_real = os.path.realpath(base)
    # Treat the joined path as relative to base; strip leading separators so an
    # absolute-looking input cannot escape via os.path.join semantics.
    cleaned = [p.lstrip("/\\") for p in paths if p not in (None, "")]
    candidate = os.path.realpath(os.path.join(base_real, *cleaned)) if cleaned else base_real
    if candidate != base_real and not candidate.startswith(base_real + os.sep):
        raise HTTPException(status_code=400, detail="invalid path")
    return candidate


def prune_overlay_nonebot_core() -> bool:
    """Delete the duplicated NoneBot core from the plugin overlay dir.

    ``pip install --target $PYTHON_PACKAGES_DIR`` (used for every plugin so it
    persists on ``/data``) also drops a full copy of ``nonebot2`` — a hard
    dependency of every plugin — into the overlay. The image now adds the overlay
    to ``sys.path`` at *lowest* priority via a ``.pth`` file, so the system
    nonebot (the one carrying the OneBot v11 adapter) already wins; this cleanup
    is belt-and-suspenders that also keeps ``/data`` lean and self-heals older
    deployments. The image always ships a complete nonebot core + onebot adapter,
    so the overlay copy is safe to remove; genuine plugin packages
    (``nonebot_plugin_*``) stay. Runs on every NoneBot restart, covering the
    runtime install path (panel → /api/plugins/install).

    Returns True if anything was removed.
    """
    overlay = config.PYTHON_PACKAGES_DIR
    if not overlay or not os.path.isdir(overlay):
        return False
    removed = False
    core = os.path.join(overlay, "nonebot")
    if os.path.isdir(core):
        shutil.rmtree(core, ignore_errors=True)
        removed = True
    for meta in glob.glob(os.path.join(overlay, "nonebot2-*.dist-info")) + glob.glob(
        os.path.join(overlay, "nonebot2-*.data")
    ):
        shutil.rmtree(meta, ignore_errors=True)
        removed = True
    return removed


def valid_plugin_name(name: str) -> bool:
    """Validate a plugin package name against the NoneBot plugin convention."""
    return bool(name) and bool(_PLUGIN_NAME_RE.match(name))


def valid_env_key(key: str) -> bool:
    return bool(key) and bool(_ENV_KEY_RE.match(key))


def dotenv_value(value: Any) -> str:
    text = "" if value is None else str(value)
    if text == "" or any(ch.isspace() for ch in text) or any(ch in text for ch in "\"'#$\\"):
        return shlex.quote(text)
    return text


def read_plugins() -> Dict[str, Any]:
    """Read ``plugins.json``; return ``{"plugins": []}`` when missing/corrupt."""
    try:
        with open(config.PLUGINS_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
            return {"plugins": []}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"plugins": []}


def write_plugins(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(config.PLUGINS_JSON), exist_ok=True)
    tmp = config.PLUGINS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, config.PLUGINS_JSON)


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def update_env_file(path: str, key: str, value: str) -> None:
    """Set ``KEY=value`` in a dotenv file, updating in place or appending."""
    if not valid_env_key(key):
        raise HTTPException(status_code=400, detail=f"invalid env key: {key}")
    lines: List[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    new_line = f"{key}={dotenv_value(value)}"
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        existing_key = stripped.split("=", 1)[0].strip()
        if existing_key == key:
            lines[i] = new_line
            found = True
            break
    if not found:
        lines.append(new_line)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
