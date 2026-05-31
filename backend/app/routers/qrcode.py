"""QR login management: serve the pending QR, report login status, logout/restart.

The active QQ protocol backend (Lagrange or NapCatQQ) is read from the persisted
selection, so the same endpoints transparently serve whichever backend is
running: Lagrange writes ``qr-0.png`` + ``keystore.json`` under its dir, while
NapCat writes ``cache/qrcode.png`` under its workdir.
"""

import glob
import json
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import auth, config, process_manager

router = APIRouter(tags=["qrcode"], dependencies=[Depends(auth.require_auth)])


def _qrcode_path() -> str:
    """Return the pending-QR image path for the currently selected backend."""
    if config.read_protocol() == config.PROTOCOL_NAPCAT:
        return config.NAPCAT_QRCODE_PATH
    return config.QRCODE_PATH


@router.get("/qrcode")
def get_qrcode():
    path = _qrcode_path()
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="no qrcode")
    # Disable caching so the frontend always sees the freshest QR.
    return FileResponse(
        path,
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


def _lagrange_login_status():
    """Login state for the Lagrange backend (keystore/QR files + process state)."""
    lagrange_state = process_manager.get_status(config.PROG_LAGRANGE)
    nonebot_state = process_manager.get_status(config.PROG_NONEBOT)
    keystore_exists = os.path.isfile(config.KEYSTORE_PATH)
    qr_exists = os.path.isfile(config.QRCODE_PATH)

    qq = _read_uin() if keystore_exists else ""

    status = "offline"
    if keystore_exists and lagrange_state == "RUNNING" and nonebot_state == "RUNNING":
        status = "online"
    elif qr_exists:
        try:
            age = time.time() - os.path.getmtime(config.QRCODE_PATH)
        except OSError:
            age = 0
        status = "expired" if age > config.QR_EXPIRY_SECONDS else "waiting_scan"
    elif lagrange_state != "RUNNING":
        status = "offline"
    elif keystore_exists:
        status = "scanned"

    return {"status": status, "qq": qq, "nickname": ""}


def _napcat_login_status():
    """Login state for the NapCat backend.

    NapCat stores its session inside the embedded QQ client (not a keystore we
    can parse), and removes ``cache/qrcode.png`` once a scan succeeds. So we
    infer: QR present & fresh => waiting_scan; napcat + nonebot RUNNING with no
    pending QR => online; otherwise offline. qq/nickname are returned empty
    (filled by NoneBot's get_login_info cache when available).
    """
    napcat_state = process_manager.get_status(config.PROG_NAPCAT)
    nonebot_state = process_manager.get_status(config.PROG_NONEBOT)
    qr_exists = os.path.isfile(config.NAPCAT_QRCODE_PATH)

    status = "offline"
    if qr_exists:
        try:
            age = time.time() - os.path.getmtime(config.NAPCAT_QRCODE_PATH)
        except OSError:
            age = 0
        status = "expired" if age > config.QR_EXPIRY_SECONDS else "waiting_scan"
    elif napcat_state == "RUNNING" and nonebot_state == "RUNNING":
        status = "online"
    elif napcat_state != "RUNNING":
        status = "offline"

    return {"status": status, "qq": "", "nickname": ""}


@router.get("/login-status")
def login_status():
    """Determine login state for the active backend.

    status in: offline / waiting_scan / scanned / online / expired
    """
    if config.read_protocol() == config.PROTOCOL_NAPCAT:
        return _napcat_login_status()
    return _lagrange_login_status()


@router.post("/logout-qq")
def logout_qq():
    """Remove credentials & pending QR, then restart the active backend."""
    removed = []
    if config.read_protocol() == config.PROTOCOL_NAPCAT:
        # NapCat keeps its session inside the embedded QQ profile; clear the
        # pending QR and restart so it shows a fresh login QR.
        for qr in (config.NAPCAT_QRCODE_PATH,):
            try:
                os.remove(qr)
                removed.append(os.path.basename(qr))
            except FileNotFoundError:
                pass
        process_manager.supervisor_ctl("restart", config.PROG_NAPCAT)
        return {"ok": True, "removed": removed}

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
    """Restart the active backend (Lagrange or NapCat) to refresh the login QR."""
    if config.read_protocol() == config.PROTOCOL_NAPCAT:
        rc, output = process_manager.supervisor_ctl("restart", config.PROG_NAPCAT)
    else:
        rc, output = process_manager.restart_lagrange()
    if rc != 0:
        raise HTTPException(status_code=500, detail=output or "restart failed")
    return {"ok": True}
