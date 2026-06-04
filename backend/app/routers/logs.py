"""Read-only viewer for the managed program logs.

Only the fixed whitelist in ``config.LOG_FILES`` is ever opened, so there is no
arbitrary file read surface: the ``name`` path parameter is rejected unless it
is a known key. Reads return the tail of the file (bounded by ``LOG_MAX_BYTES``)
so a large log never blows up the response.
"""

import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from .. import auth, config

router = APIRouter(tags=["logs"], dependencies=[Depends(auth.require_auth)])

# Streaming (SSE) tuning.
STREAM_POLL_SECONDS = 1.0  # how often we check the file for newly appended bytes
STREAM_PING_SECONDS = 15.0  # heartbeat comment interval to keep the connection open
STREAM_READ_CHUNK = 256 * 1024  # cap a single appended read so a burst can't blow up


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


def _sse_event(event: str | None, data) -> str:
    """Serialize one SSE frame. ``data`` is JSON-encoded so log text (which is
    full of newlines) never breaks the line-oriented SSE framing."""
    payload = json.dumps(data, ensure_ascii=False)
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {payload}\n\n"


@router.get("/logs/{name}/stream")
async def stream_log(name: str, request: Request):
    """Stream a log file as Server-Sent Events, like ``tail -f``.

    Sends a ``meta`` frame first (exists/size/truncated), then the current tail
    (bounded by ``LOG_MAX_BYTES``), then only the bytes appended afterwards —
    so the client appends incrementally instead of re-pulling the whole tail on
    a timer. Handles rotation/truncation (file shrinks → emit ``reset`` and
    restart) and files that don't exist yet (the process may not have run).
    """
    path = _resolve(name)
    label = config.LOG_LABELS.get(name, name)

    async def gen():
        offset = 0
        existed = False
        # Initial snapshot: meta + current tail.
        if os.path.isfile(path):
            existed = True
            content, size, truncated = _tail_bytes(path, config.LOG_MAX_BYTES)
            offset = size
            yield _sse_event("meta", {"name": name, "label": label, "exists": True, "size": size, "truncated": truncated})
            if content:
                yield _sse_event(None, content)
        else:
            yield _sse_event("meta", {"name": name, "label": label, "exists": False, "size": 0, "truncated": False})

        since_ping = 0.0
        while True:
            if await request.is_disconnected():
                break
            wrote = False
            try:
                if os.path.isfile(path):
                    if not existed:
                        # File just appeared (process started). Start from scratch.
                        existed = True
                        offset = 0
                        yield _sse_event("reset", {"exists": True})
                    size = os.path.getsize(path)
                    if size < offset:
                        # Rotated/truncated: tell the client to clear and restart.
                        offset = 0
                        yield _sse_event("reset", {"exists": True})
                    if size > offset:
                        with open(path, "rb") as fh:
                            fh.seek(offset)
                            raw = fh.read(min(size - offset, STREAM_READ_CHUNK))
                        offset += len(raw)
                        yield _sse_event(None, raw.decode("utf-8", errors="replace"))
                        wrote = True
                elif existed:
                    existed = False
                    yield _sse_event("reset", {"exists": False})
            except OSError:
                pass

            await asyncio.sleep(STREAM_POLL_SECONDS)
            since_ping += STREAM_POLL_SECONDS
            if not wrote and since_ping >= STREAM_PING_SECONDS:
                since_ping = 0.0
                yield ": ping\n\n"  # comment frame; ignored by EventSource, keeps proxies open

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so frames flush immediately
        },
    )


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
