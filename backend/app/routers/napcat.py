"""NapCatQQ runtime configuration (quick login).

Quick login lets NapCat reuse a previously scanned session and auto-log in
without showing the QR again. We persist {"enabled", "qq"} under the NapCat
workdir; ``napcat-run.sh`` reads it at launch and passes ``-q <uin>`` to QQ.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth, config, process_manager

router = APIRouter(tags=["napcat"], dependencies=[Depends(auth.require_auth)])


class QuickLoginBody(BaseModel):
    enabled: bool = False
    qq: Optional[str] = ""


@router.get("/napcat/quick-login")
def get_quick_login():
    cfg = config.read_napcat_quicklogin()
    return {**cfg, "protocol": config.read_protocol()}


@router.get("/napcat/webui-info")
def get_webui_info():
    """Report how to reach NapCat's WebUI through the single-port reverse proxy.

    ``url`` points at the proxied WebUI with the login token pre-filled so the
    panel can embed it directly. ``available`` is true only when NapCat is the
    active backend and its process is running (otherwise the WebUI server on
    127.0.0.1:6099 is down and the proxy would 502).
    """
    protocol = config.read_protocol()
    webui = config.read_napcat_webui()
    running = process_manager.get_status(config.PROG_NAPCAT) == "RUNNING"
    available = protocol == config.PROTOCOL_NAPCAT and running
    token = webui.get("token") or ""
    base = f"{config.NAPCAT_WEBUI_PROXY_PREFIX}/webui/"
    url = f"{base}?token={token}" if token else base
    return {
        "protocol": protocol,
        "running": running,
        "available": available,
        "token": token,
        "url": url,
    }


@router.post("/napcat/quick-login")
def set_quick_login(body: QuickLoginBody):
    try:
        cfg = config.write_napcat_quicklogin(body.enabled, body.qq or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Apply immediately only when NapCat is the active backend: restart it so the
    # new launch arguments take effect. Otherwise it applies on next napcat start.
    applied = False
    log = ""
    if config.read_protocol() == config.PROTOCOL_NAPCAT:
        rc, log = process_manager.supervisor_ctl("restart", config.PROG_NAPCAT)
        applied = rc == 0
    return {"ok": True, **cfg, "applied": applied, "log": log}
