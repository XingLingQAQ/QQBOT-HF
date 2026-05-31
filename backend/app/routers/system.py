"""System status and in-container maintenance endpoints."""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth, config, process_manager

router = APIRouter(tags=["system"], dependencies=[Depends(auth.require_auth)])


class UpdateLagrangeBody(BaseModel):
    url: Optional[str] = None


_OLD_SIGN_URLS = {
    "",
    "https://sign.lagrangecore.org/api/sign",
    "https://sign.lagrangecore.org/api/sign/30366",
}


def _read_appsettings() -> Dict[str, Any]:
    try:
        with open(config.APPSETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _write_appsettings(data: Dict[str, Any]) -> None:
    os.makedirs(config.LAGRANGE_DIR, exist_ok=True)
    tmp = config.APPSETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, config.APPSETTINGS_PATH)


def _repair_lagrange_config() -> Dict[str, Any]:
    settings = _read_appsettings()
    changed = []

    if settings.get("SignServerUrl") in _OLD_SIGN_URLS:
        settings["SignServerUrl"] = config.LAGRANGE_SIGN_SERVER_URL
        changed.append("SignServerUrl")

    settings.setdefault("Logging", {"LogLevel": {"Default": "Information", "Microsoft": "Warning"}})
    settings.setdefault("SignProxyUrl", "")
    settings.setdefault("MusicSignServerUrl", "")
    settings.setdefault("Account", {"Uin": 0, "Protocol": "Linux", "AutoReconnect": True})
    settings.setdefault("Message", {"IgnoreSelf": True})
    settings.setdefault("QrCode", {"ConsoleCompatibilityMode": False})

    implementations = settings.get("Implementations")
    if not isinstance(implementations, list):
        implementations = []
        settings["Implementations"] = implementations
        changed.append("Implementations")

    reverse = next(
        (item for item in implementations if isinstance(item, dict) and item.get("Type") == "ReverseWebSocket"),
        None,
    )
    desired_reverse = {
        "Type": "ReverseWebSocket",
        "Host": "127.0.0.1",
        "Port": config.NONEBOT_WS_PORT,
        "Suffix": "/onebot/v11/ws",
        "ReconnectInterval": 5000,
        "HeartBeatInterval": 5000,
        "AccessToken": "",
    }
    if reverse is None:
        implementations.append(desired_reverse)
        changed.append("ReverseWebSocket")
    else:
        for key, value in desired_reverse.items():
            if reverse.get(key) != value:
                reverse[key] = value
                changed.append(f"ReverseWebSocket.{key}")

    if changed:
        _write_appsettings(settings)
    return {"changed": sorted(set(changed)), "settings": settings}


def _validate_lagrange_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise HTTPException(status_code=400, detail="invalid release url host")
    if not parsed.path.startswith("/LagrangeDev/Lagrange.Core/releases/download/"):
        raise HTTPException(status_code=400, detail="invalid release url path")
    if not parsed.path.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="invalid release archive")
    return url


def _safe_extract_lagrange_binary(archive: str, dest_dir: str) -> str:
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            target = os.path.realpath(os.path.join(dest_dir, member.name))
            if target != os.path.realpath(dest_dir) and not target.startswith(os.path.realpath(dest_dir) + os.sep):
                raise HTTPException(status_code=400, detail="unsafe archive path")
        tar.extractall(dest_dir, members)
    for root, _, files in os.walk(dest_dir):
        if "Lagrange.OneBot" in files:
            return os.path.join(root, "Lagrange.OneBot")
    raise HTTPException(status_code=500, detail="Lagrange.OneBot not found in archive")


def _run_pip_upgrade() -> str:
    packages = [
        "fastapi>=0.110",
        "uvicorn[standard]>=0.29",
        "python-multipart>=0.0.9",
        "itsdangerous>=2.1",
        "aiofiles>=23.2",
        "websockets>=12.0",
        "nonebot2>=2.5.0",
        "nonebot-adapter-onebot>=2.4.6",
    ]
    try:
        proc = subprocess.run(
            [
                config.PYTHON_BIN,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--target",
                config.PYTHON_PACKAGES_DIR,
                *packages,
            ],
            capture_output=True,
            text=True,
            timeout=900,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="pip not available")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="python dependency update timed out")
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=log[-4000:] or "python dependency update failed")
    return log[-4000:]


@router.get("/status")
def status():
    return {
        "lagrange": process_manager.get_status(config.PROG_LAGRANGE),
        "nonebot": process_manager.get_status(config.PROG_NONEBOT),
        "backend": process_manager.get_status(config.PROG_BACKEND),
    }


@router.get("/system/config")
def system_config():
    settings = _read_appsettings()
    return {
        "lagrangeReleaseUrl": config.LAGRANGE_RELEASE_URL,
        "lagrangeSignServerUrl": settings.get("SignServerUrl") or config.LAGRANGE_SIGN_SERVER_URL,
        "nonebotAdapter": "nonebot-adapter-onebot",
        "nonebotImport": "from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter",
        "nonebotWsUrl": f"ws://127.0.0.1:{config.NONEBOT_WS_PORT}/onebot/v11/ws",
        "maxTextFileSize": config.MAX_TEXT_FILE_SIZE,
        "maxUploadFileSize": config.MAX_UPLOAD_FILE_SIZE,
        "maxUploadFiles": config.MAX_UPLOAD_FILES,
    }


@router.post("/system/repair-lagrange-config")
def repair_lagrange_config():
    result = _repair_lagrange_config()
    rc, output = process_manager.restart_lagrange()
    if rc != 0:
        raise HTTPException(status_code=500, detail=output or "restart lagrange failed")
    return {"ok": True, **result}


@router.post("/system/update-lagrange")
def update_lagrange(body: UpdateLagrangeBody):
    url = _validate_lagrange_url(body.url or config.LAGRANGE_RELEASE_URL)
    os.makedirs(config.MANAGER_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=config.MANAGER_DIR) as tmp_dir:
        archive = os.path.join(tmp_dir, "lagrange.tar.gz")
        try:
            urllib.request.urlretrieve(url, archive)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"download failed: {exc}")
        extract_dir = os.path.join(tmp_dir, "extract")
        os.makedirs(extract_dir, exist_ok=True)
        binary = _safe_extract_lagrange_binary(archive, extract_dir)
        staging = config.LAGRANGE_BIN + ".new"
        shutil.copy2(binary, staging)
        os.chmod(staging, 0o755)
        os.replace(staging, config.LAGRANGE_BIN)
    _repair_lagrange_config()
    rc, output = process_manager.restart_lagrange()
    if rc != 0:
        raise HTTPException(status_code=500, detail=output or "restart lagrange failed")
    return {"ok": True, "url": url}


@router.post("/system/update-python-deps")
def update_python_deps():
    log = _run_pip_upgrade()
    process_manager.restart_nonebot()
    process_manager.restart_lagrange()
    return {"ok": True, "log": log}
