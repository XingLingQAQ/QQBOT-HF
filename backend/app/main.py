"""FastAPI application entrypoint.

Serves the SPA frontend, the JSON API under ``/api``, and the WebSocket terminal
under ``/ws/terminal`` — all on a single port so it works inside a Hugging Face
Docker Space that exposes only ``$PORT``.
"""

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import auth as auth_router
from .routers import files as files_router
from .routers import plugins as plugins_router
from .routers import qrcode as qrcode_router
from .routers import system as system_router
from .routers import terminal as terminal_router

app = FastAPI(title="QQ Bot Management Panel", version="1.0.0")

# --- API routers (all prefixed /api except the WS terminal) ---
app.include_router(auth_router.router, prefix="/api")
app.include_router(qrcode_router.router, prefix="/api")
app.include_router(plugins_router.router, prefix="/api")
app.include_router(system_router.router, prefix="/api")
app.include_router(files_router.router, prefix="/api")
app.include_router(terminal_router.router)  # /ws/terminal


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# --- Static frontend (SPA) ---
_assets_dir = os.path.join(config.STATIC_DIR, "assets")
if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Catch-all: serve static files when present, otherwise the SPA index.html.

    API (``/api/*``) and WebSocket (``/ws/*``) routes are matched before this
    handler by FastAPI's router, so they are never shadowed here.
    """
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        return JSONResponse({"detail": "not found"}, status_code=404)

    # Serve a real static file if it exists (e.g. favicon, vite.svg).
    if full_path:
        candidate = os.path.normpath(os.path.join(config.STATIC_DIR, full_path))
        if candidate.startswith(os.path.realpath(config.STATIC_DIR)) and os.path.isfile(candidate):
            return FileResponse(candidate)

    index_path = os.path.join(config.STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        {"detail": "frontend not built"}, status_code=503
    )
