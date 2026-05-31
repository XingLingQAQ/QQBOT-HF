"""Web terminal over WebSocket, backed by a PTY running ``/bin/bash``.

Protocol (JSON text frames from the client):
    {"type": "input", "data": "<keystrokes>"}
    {"type": "resize", "cols": <int>, "rows": <int>}
Plain (non-JSON) text frames are also treated as raw input for convenience.

Auth: the handshake reads the session cookie ``qqbot_session`` or a ``?token=``
query param and verifies it; failure closes the socket with code 4401.
The child shell inherits the persisted plugin PYTHONPATH and starts in ``/data``.
"""

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import termios

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import auth, config

router = APIRouter()


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, number))


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass


@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    token = websocket.cookies.get(config.SESSION_COOKIE) or websocket.query_params.get(
        "token"
    )
    if not auth.verify_token(token):
        await websocket.close(code=4401)
        return

    await websocket.accept()

    # Fork a child attached to a new PTY; the child execs bash.
    pid, master_fd = pty.fork()
    if pid == 0:
        # --- child process ---
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{config.PYTHON_PACKAGES_DIR}:{env.get('PYTHONPATH', '')}"
        env["TERM"] = "xterm-256color"
        env["HOME"] = os.environ.get("HOME", config.DATA_DIR)
        try:
            os.chdir(config.DATA_DIR)
        except OSError:
            pass
        os.execvpe("/bin/bash", ["/bin/bash", "-l"], env)
        os._exit(1)  # unreachable

    # --- parent process ---
    loop = asyncio.get_event_loop()
    _set_winsize(master_fd, 24, 80)

    async def pty_to_ws() -> None:
        try:
            while True:
                data = await loop.run_in_executor(None, _read_fd, master_fd)
                if not data:
                    break
                await websocket.send_text(data.decode(errors="replace"))
        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    reader_task = asyncio.create_task(pty_to_ws())

    try:
        while True:
            message = await websocket.receive_text()
            payload = None
            try:
                payload = json.loads(message)
            except (json.JSONDecodeError, ValueError):
                payload = None

            if isinstance(payload, dict):
                mtype = payload.get("type")
                if mtype == "resize":
                    rows = _bounded_int(payload.get("rows"), 24, 5, 120)
                    cols = _bounded_int(payload.get("cols"), 80, 20, 300)
                    _set_winsize(master_fd, rows, cols)
                    continue
                if mtype == "input":
                    os.write(master_fd, str(payload.get("data", "")).encode())
                    continue
                # Unknown JSON object: ignore.
                continue

            # Raw text frame -> treat as input.
            os.write(master_fd, message.encode())
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        reader_task.cancel()
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError, OSError):
            pass


def _read_fd(fd: int) -> bytes:
    try:
        return os.read(fd, 65536)
    except OSError:
        return b""
