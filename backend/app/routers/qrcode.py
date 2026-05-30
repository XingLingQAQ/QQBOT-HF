"""QR login management: serve the pending QR, report login status, logout/restart."""

import glob
import json
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import auth, config, process_manager

router = APIRouter(tags=["qrcode"], dependencies=[Depends(auth.require_auth)])


@router.get("/qrcode")
def get_qrcode():
    if not os.path.isfile(config.QRCODE_PATH):
        raise HTTPException(status_code=404, detail="no qrcode")
    # Disable caching so the frontend always sees the freshest QR.
    return FileResponse(
        config.QRCODE_PATH,
        media_type="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


def _read_uin() -> str:
    """Best-effort read of the logged-in QQ number (uin) from keystore.json."""
    try:
        with open(config.KEYSTORE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return ""
    # keystore structure varies across Lagrange versions; probe common keys.
    for key in ("Uin", "uin"):
        if isinstance(data.get(key), (int, str)) and str(data.get(key)).strip("0"):
            return str(data[key])
    info = data.get("Info") or data.get("info") or {}
    if isinstance(info, dict):
        for key in ("Uin", "uin"):
            if info.get(key):
                return str(info[key])
    return ""


@router.get("/login-status")
def login_status():
    """Determine login state from keystore/QR files and process status.

    status in: offline / waiting_scan / scanned / online / expired
    """
    lagrange_state = process_manager.get_status(config.PROG_LAGRANGE)
    nonebot_state = process_manager.get_status(config.PROG_NONEBOT)
    keystore_exists = os.path.isfile(config.KEYSTORE_PATH)
    qr_exists = os.path.isfile(config.QRCODE_PATH)

    qq = _read_uin() if keystore_exists else ""
    nickname = ""  # filled by NoneBot get_login_info cache when available; empty otherwise

    status = "offline"
    if keystore_exists and lagrange_state == "RUNNING" and nonebot_state == "RUNNING":
        status = "online"
    elif qr_exists:
        # QR present but not yet logged in: waiting to scan, or expired if stale.
        try:
            age = time.time() - os.path.getmtime(config.QRCODE_PATH)
        except OSError:
            age = 0
        status = "expired" if age > config.QR_EXPIRY_SECONDS else "waiting_scan"
    elif lagrange_state != "RUNNING":
        status = "offline"
    elif keystore_exists:
        # Logged in at Lagrange level but NoneBot not yet connected.
        status = "scanned"

    return {"status": status, "qq": qq, "nickname": nickname}


@router.post("/logout-qq")
def logout_qq():
    """Remove credentials & pending QR, then restart Lagrange to force re-login."""
    removed = []
    for path in (config.KEYSTORE_PATH,):
        try:
            os.remove(path)
            removed.append(os.path.basename(path))
        except FileNotFoundError:
            pass
    for qr in glob.glob(os.path.join(config.LAGRANGE_DIR, "qr-*.png")):
        try:
            os.remove(qr)
            removed.append(os.path.basename(qr))
        except FileNotFoundError:
            pass
    process_manager.restart_lagrange()
    return {"ok": True, "removed": removed}


@router.post("/restart-lagrange")
def restart_lagrange():
    rc, output = process_manager.restart_lagrange()
    if rc != 0:
        raise HTTPException(status_code=500, detail=output or "restart failed")
    return {"ok": True}
