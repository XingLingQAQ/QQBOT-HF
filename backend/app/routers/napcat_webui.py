"""Reverse proxy for NapCat's built-in WebUI.

NapCat ships a WebUI (login QR, network config, logs, terminal, ...) served by
its own HTTP server on ``127.0.0.1:6099``. A Hugging Face Docker Space only
exposes the single backend port, so we proxy the WebUI through this backend at
``/napcat/*`` (both HTTP and WebSocket).

The WebUI's static bundle hardcodes absolute paths (assets under ``/webui/``,
API under ``/api``). Since NapCat dropped ``prefix`` support in v4.4+, those
absolute paths are rewritten to ``/napcat/webui/`` and ``/napcat/api`` at image
build time (see Dockerfile). This proxy simply strips the ``/napcat`` prefix and
forwards to the WebUI server, so the browser only ever talks to the public port.

Security: every request requires a valid panel session (same-origin cookie),
and the WebUI itself listens on loopback only, so it is never directly exposed.
"""

import asyncio

import httpx
import websockets
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from starlette.responses import RedirectResponse, Response

from .. import auth, config

router = APIRouter(tags=["napcat-webui"])

# Hop-by-hop headers must not be forwarded. content-length/encoding are dropped
# because httpx already decoded the body; Starlette recomputes content-length.
_DROP_REQUEST_HEADERS = {"host", "connection", "keep-alive", "proxy-authorization",
                         "proxy-authenticate", "te", "trailer", "transfer-encoding",
                         "upgrade", "accept-encoding"}
_DROP_RESPONSE_HEADERS = {"connection", "keep-alive", "proxy-authenticate",
                          "proxy-authorization", "te", "trailer", "transfer-encoding",
                          "upgrade", "content-encoding", "content-length"}

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(follow_redirects=False, timeout=30.0)
    return _client


def _upstream_base() -> str:
    cfg = config.read_napcat_webui()
    return f"http://{cfg['host']}:{cfg['port']}"


def _ws_base() -> str:
    cfg = config.read_napcat_webui()
    return f"ws://{cfg['host']}:{cfg['port']}"


def _rewrite_location(location: str) -> str:
    """Re-prefix a root-relative redirect target so it stays inside the proxy."""
    prefix = config.NAPCAT_WEBUI_PROXY_PREFIX
    if location.startswith("/") and not location.startswith(prefix + "/") and location != prefix:
        return prefix + location
    return location


@router.get(config.NAPCAT_WEBUI_PROXY_PREFIX, include_in_schema=False)
async def napcat_root_redirect(_: str = Depends(auth.require_auth)) -> RedirectResponse:
    # Bare /napcat -> the WebUI entrypoint (with trailing slash).
    return RedirectResponse(url=f"{config.NAPCAT_WEBUI_PROXY_PREFIX}/webui/")


@router.api_route(
    config.NAPCAT_WEBUI_PROXY_PREFIX + "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def napcat_http_proxy(path: str, request: Request, _: str = Depends(auth.require_auth)):
    url = f"{_upstream_base()}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    fwd_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _DROP_REQUEST_HEADERS
    }
    body = await request.body()

    client = _get_client()
    try:
        upstream = await client.request(
            request.method, url, headers=fwd_headers, content=body
        )
    except httpx.ConnectError:
        return Response(
            content="NapCat WebUI 未运行（请切换到 NapCat 协议并启动后再试）。",
            status_code=502,
            media_type="text/plain; charset=utf-8",
        )
    except httpx.HTTPError as exc:
        # ReadTimeout/RemoteProtocolError etc. happen while NapCat's QQ core is
        # starting up or crash-looping; surface a clean message rather than a
        # raw 5xx from the dying upstream.
        return Response(
            content=f"NapCat WebUI 暂不可用（{type(exc).__name__}）。请稍候，或前往「进程控制」确认 napcat 已正常运行。",
            status_code=502,
            media_type="text/plain; charset=utf-8",
        )

    resp_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS
    }
    if "location" in {k.lower() for k in resp_headers}:
        for key in list(resp_headers):
            if key.lower() == "location":
                resp_headers[key] = _rewrite_location(resp_headers[key])
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )


async def _pump_client_to_upstream(ws: WebSocket, upstream) -> None:
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                await upstream.send(message["text"])
            elif message.get("bytes") is not None:
                await upstream.send(message["bytes"])
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await upstream.close()


async def _pump_upstream_to_client(ws: WebSocket, upstream) -> None:
    try:
        async for message in upstream:
            if isinstance(message, (bytes, bytearray)):
                await ws.send_bytes(bytes(message))
            else:
                await ws.send_text(message)
    except websockets.ConnectionClosed:
        pass
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@router.websocket(config.NAPCAT_WEBUI_PROXY_PREFIX + "/{path:path}")
async def napcat_ws_proxy(websocket: WebSocket, path: str):
    token = websocket.cookies.get(config.SESSION_COOKIE) or websocket.query_params.get("token")
    if not auth.verify_token(token):
        await websocket.close(code=4401)
        return

    url = f"{_ws_base()}/{path}"
    if websocket.url.query:
        url = f"{url}?{websocket.url.query}"

    subprotocols = websocket.scope.get("subprotocols") or []
    try:
        upstream = await websockets.connect(
            url,
            subprotocols=subprotocols or None,
            open_timeout=10,
            max_size=None,
        )
    except Exception:
        await websocket.close(code=1011)
        return

    await websocket.accept(subprotocol=upstream.subprotocol)
    await asyncio.gather(
        _pump_client_to_upstream(websocket, upstream),
        _pump_upstream_to_client(websocket, upstream),
    )
