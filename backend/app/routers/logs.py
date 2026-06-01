"""Read-only viewer for the managed program logs.

Only the fixed whitelist in ``config.LOG_FILES`` is ever opened, so there is no
arbitrary file read surface: the ``name`` path parameter is rejected unless it
is a known key. Reads return the tail of the file (bounded by ``LOG_MAX_BYTES``)
so a large log never blows up the response.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from .. import auth, config

router = APIRouter(tags=["logs"], dependencies=[Depends(auth.require_auth)])


def _resolve(name: str) -> str:
    path = config.LOG_FILES.get(name)
    if path is None:
        raise HTTPException(status_code=404, detail="unknown log")
    return path


def _tail_bytes(path: str, max_bytes: int) -> tuple[str, int, bool]:
    """Return (text, total_size, truncated) reading at most the last max_bytes."""
    size = os.path.getsize(path)
    truncated = size > max_bytes
    with open(path, "rb") as fh:
        if truncated:
            fh.seek(size - max_bytes)
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        # Drop the partial first line so we don't show a half-mangled entry.
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
    return text, size, truncated


@router.get("/logs")
def list_logs():
    """List the available logs with existence + size metadata."""
    items = []
    for name, path in config.LOG_FILES.items():
        exists = os.path.isfile(path)
        items.append(
            {
                "name": name,
                "label": config.LOG_LABELS.get(name, name),
                "exists": exists,
                "size": os.path.getsize(path) if exists else 0,
            }
        )
    return {"logs": items}


@router.get("/logs/{name}")
def read_log(name: str, max_bytes: int = Query(default=config.LOG_MAX_BYTES, ge=1024)):
    """Return the tail of a single log file (bounded by max_bytes/LOG_MAX_BYTES)."""
    path = _resolve(name)
    if not os.path.isfile(path):
        return {
            "name": name,
            "label": config.LOG_LABELS.get(name, name),
            "exists": False,
            "size": 0,
            "truncated": False,
            "content": "",
        }
    cap = min(max_bytes, config.LOG_MAX_BYTES)
    content, size, truncated = _tail_bytes(path, cap)
    return {
        "name": name,
        "label": config.LOG_LABELS.get(name, name),
        "exists": True,
        "size": size,
        "truncated": truncated,
        "content": content,
    }


@router.get("/logs/{name}/download")
def download_log(name: str):
    """Download the full log file as text/plain (attachment)."""
    path = _resolve(name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="log not found")
    with open(path, "rb") as fh:
        raw = fh.read()
    return PlainTextResponse(
        raw.decode("utf-8", errors="replace"),
        headers={"Content-Disposition": f'attachment; filename="{name}.log"'},
    )
