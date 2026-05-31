"""QQ protocol backend selection (Lagrange vs NapCatQQ).

Selecting ``napcat`` stops Lagrange + the self-hosted sign server and starts
NapCat; selecting ``lagrange`` does the reverse. The choice is persisted under
``/data`` so it survives container restarts (the entrypoint re-derives each
program's ``autostart`` from it).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth, config, process_manager

router = APIRouter(tags=["protocol"], dependencies=[Depends(auth.require_auth)])


class ProtocolBody(BaseModel):
    protocol: str


@router.get("/protocol")
def get_protocol():
    return {
        "protocol": config.read_protocol(),
        "available": list(config.VALID_PROTOCOLS),
    }


@router.post("/protocol")
def set_protocol(body: ProtocolBody):
    protocol = (body.protocol or "").strip()
    if protocol not in config.VALID_PROTOCOLS:
        raise HTTPException(status_code=400, detail="invalid protocol")
    config.write_protocol(protocol)
    log = process_manager.apply_protocol(protocol)
    return {"ok": True, "protocol": protocol, "log": log}
