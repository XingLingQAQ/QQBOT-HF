"""Plugin management: install / uninstall / configure / toggle / restart."""

import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, config, process_manager, utils

router = APIRouter(
    prefix="/plugins", tags=["plugins"], dependencies=[Depends(auth.require_auth)]
)


class NameBody(BaseModel):
    name: str


class ConfigBody(BaseModel):
    name: str
    config: Dict[str, Any] = Field(default_factory=dict)


class ToggleBody(BaseModel):
    name: str
    enabled: bool


def _module_name(pkg_name: str) -> str:
    """Convert a pip package name to its importable module name."""
    return pkg_name.replace("-", "_")


def _pip_install(name: str) -> subprocess.CompletedProcess:
    """Install/upgrade a plugin into the persistent overlay, crash-free.

    pip's ``--target`` + ``--upgrade`` path ``shutil.rmtree()``s the existing
    package dir before replacing it, which on HF's /data (overlay/fuse) raises
    ``OSError: [Errno 39] Directory not empty`` and aborts the install half-way.
    Instead we install into a fresh empty tempdir (no rmtree possible) and then
    merge the result into the overlay with ``copytree(dirs_exist_ok=True)``,
    overwriting files in place. This gives a clean (re)install/upgrade including
    every transitive dependency, without ever taking pip's destructive path.

    We pass ``--target <tmp>`` explicitly (command-line beats the pip.conf
    ``[install] target=/data`` so the staging dir wins) and strip any inherited
    ``PIP_CONFIG_FILE`` to avoid surprises.
    """
    env = os.environ.copy()
    env.pop("PIP_CONFIG_FILE", None)
    tmp = tempfile.mkdtemp(prefix="qqbot-plugin-")
    try:
        proc = subprocess.run(
            [
                config.PYTHON_BIN,
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--target",
                tmp,
                name,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode == 0:
            os.makedirs(config.PYTHON_PACKAGES_DIR, exist_ok=True)
            shutil.copytree(tmp, config.PYTHON_PACKAGES_DIR, dirs_exist_ok=True)
        return proc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _detect_version(pkg_name: str) -> str:
    try:
        proc = subprocess.run(
            [
                config.PYTHON_BIN,
                "-m",
                "pip",
                "show",
                pkg_name,
                "--path",
                config.PYTHON_PACKAGES_DIR,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    for line in (proc.stdout or "").splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return ""


@router.get("")
def list_plugins():
    return utils.read_plugins()


@router.post("/install")
def install_plugin(body: NameBody):
    name = body.name.strip()
    if not utils.valid_plugin_name(name):
        raise HTTPException(status_code=400, detail="invalid plugin name")
    try:
        proc = _pip_install(name)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="pip not available")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="pip install timed out")
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=log[-4000:] or "install failed")

    data = utils.read_plugins()
    plugins = data.setdefault("plugins", [])
    entry = next((p for p in plugins if p.get("name") == name), None)
    version = _detect_version(name)
    if entry is None:
        plugins.append(
            {
                "name": name,
                "module": _module_name(name),
                "version": version,
                "enabled": True,
                "config": {},
            }
        )
    else:
        entry["version"] = version
        entry["enabled"] = True
        entry.setdefault("module", _module_name(name))
        entry.setdefault("config", {})
    utils.write_plugins(data)
    process_manager.restart_nonebot()
    return {"ok": True, "log": log[-4000:]}


@router.post("/uninstall")
def uninstall_plugin(body: NameBody):
    name = body.name.strip()
    if not utils.valid_plugin_name(name):
        raise HTTPException(status_code=400, detail="invalid plugin name")
    try:
        proc = subprocess.run(
            [
                config.PYTHON_BIN,
                "-m",
                "pip",
                "uninstall",
                "-y",
                name,
            ],
            env={
                **os.environ,
                "PYTHONPATH": f"{config.PYTHON_PACKAGES_DIR}:{os.environ.get('PYTHONPATH', '')}",
            },
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="pip not available")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="pip uninstall timed out")
    log = (proc.stdout or "") + (proc.stderr or "")

    data = utils.read_plugins()
    data["plugins"] = [p for p in data.get("plugins", []) if p.get("name") != name]
    utils.write_plugins(data)
    process_manager.restart_nonebot()
    return {"ok": True, "log": log[-4000:]}


@router.put("/config")
def update_config(body: ConfigBody):
    name = body.name.strip()
    if not utils.valid_plugin_name(name):
        raise HTTPException(status_code=400, detail="invalid plugin name")
    data = utils.read_plugins()
    entry = next((p for p in data.get("plugins", []) if p.get("name") == name), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="plugin not installed")
    entry["config"] = body.config

    # Persist plugin config keys into the NoneBot .env so plugins can read them.
    for key, value in body.config.items():
        safe_key = str(key).strip().upper()
        if not utils.valid_env_key(safe_key):
            raise HTTPException(status_code=400, detail=f"invalid config key: {key}")
        if isinstance(value, (dict, list)):
            raise HTTPException(status_code=400, detail=f"invalid scalar value for: {key}")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise HTTPException(status_code=400, detail=f"invalid config value for: {key}")
        utils.update_env_file(config.ENV_FILE, safe_key, str(value))

    utils.write_plugins(data)
    process_manager.restart_nonebot()
    return {"ok": True}


@router.put("/toggle")
def toggle_plugin(body: ToggleBody):
    name = body.name.strip()
    if not utils.valid_plugin_name(name):
        raise HTTPException(status_code=400, detail="invalid plugin name")
    data = utils.read_plugins()
    entry = next((p for p in data.get("plugins", []) if p.get("name") == name), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="plugin not installed")
    entry["enabled"] = bool(body.enabled)
    utils.write_plugins(data)
    process_manager.restart_nonebot()
    return {"ok": True}


@router.post("/restart")
def restart_plugins():
    rc, output = process_manager.restart_nonebot()
    if rc != 0:
        raise HTTPException(status_code=500, detail=output or "restart failed")
    return {"ok": True}
