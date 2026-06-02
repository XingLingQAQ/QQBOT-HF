"""Central configuration: constants & filesystem paths.

Everything that must survive a container rebuild lives under ``DATA_DIR`` (``/data``).
Secrets (admin credentials) are read from environment variables and never hardcoded.
"""

import json
import os
import secrets


def _int_env(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
    return value


# --- Base directories (all persistent state lives under DATA_DIR) ---
DATA_DIR = os.environ.get("DATA_DIR", "/data")
LAGRANGE_DIR = os.path.join(DATA_DIR, "lagrange")
NONEBOT_DIR = os.path.join(DATA_DIR, "nonebot")
MANAGER_DIR = os.path.join(DATA_DIR, "manager")
PYTHON_PACKAGES_DIR = os.environ.get("PYTHON_PACKAGES_DIR", os.path.join(DATA_DIR, "python-packages"))
NAPCAT_DIR = os.path.join(DATA_DIR, "napcat")  # NapCat writable workdir (config/cache/logs)

# --- Files ---
PLUGINS_JSON = os.path.join(DATA_DIR, "plugins.json")
PYTHON_BIN = os.environ.get("PYTHON_BIN", "/usr/local/bin/python")
QRCODE_PATH = os.path.join(LAGRANGE_DIR, "qr-0.png")
KEYSTORE_PATH = os.path.join(LAGRANGE_DIR, "keystore.json")
ENV_FILE = os.path.join(NONEBOT_DIR, ".env")
# Authoritative login state, written by NoneBot's bot connect/disconnect hooks
# (see bot.py.template). Both Lagrange and NapCat connect to NoneBot as OneBot
# v11 only after the QQ account is logged in, so a connected bot is the single
# source of truth for "online" + the real uin/nickname for either backend.
BOT_LOGIN_JSON = os.path.join(MANAGER_DIR, "bot_login.json")
APPSETTINGS_PATH = os.path.join(LAGRANGE_DIR, "appsettings.json")
LAGRANGE_BIN = os.environ.get("LAGRANGE_BIN", "/opt/lagrange/Lagrange.OneBot")

# NapCat writes the pending login QR here (cache/qrcode.png under its workdir)
# and keeps its OneBot config under config/onebot11.json.
NAPCAT_QRCODE_PATH = os.path.join(NAPCAT_DIR, "cache", "qrcode.png")
NAPCAT_CONFIG_DIR = os.path.join(NAPCAT_DIR, "config")
NAPCAT_ONEBOT_JSON = os.path.join(NAPCAT_CONFIG_DIR, "onebot11.json")
# Quick-login config (persisted): when enabled with a QQ uin, napcat-run.sh
# launches QQ with ``-q <uin>`` so a previously scanned session auto-logs in
# without showing the QR again.
NAPCAT_QUICKLOGIN_JSON = os.path.join(NAPCAT_CONFIG_DIR, "quick_login.json")
# NapCat's built-in WebUI config. NapCat reads it from $NAPCAT_WORKDIR/config.
# The WebUI HTTP server listens on 127.0.0.1:<port> inside the container and is
# never exposed directly; the backend reverse-proxies it at /napcat/* on the
# single public port so it works on a Hugging Face Space.
NAPCAT_WEBUI_JSON = os.path.join(NAPCAT_CONFIG_DIR, "webui.json")

# --- Admin credentials (env-injected, defaults per spec) ---
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

# --- Network ---
PORT = _int_env("PORT", 7860, minimum=1, maximum=65535)
NONEBOT_WS_PORT = 8080
# Self-hosted sign server (VincentZyu233/SignServer) listen port. Kept off 8080
# (NoneBot) and 7860 (backend) to avoid clashes. Lagrange points its
# SignServerUrl at http://127.0.0.1:<SIGNSERVER_PORT>.
SIGNSERVER_PORT = int(os.environ.get("SIGNSERVER_PORT", "8087"))
# NapCat WebUI listen port (loopback only). Reverse-proxied at /napcat/*.
NAPCAT_WEBUI_HOST = "127.0.0.1"
NAPCAT_WEBUI_PORT = _int_env("NAPCAT_WEBUI_PORT", 6099, minimum=1, maximum=65535)
# External path under which the WebUI is reverse-proxied (single public port).
NAPCAT_WEBUI_PROXY_PREFIX = "/napcat"

# --- Static frontend build output ---
STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")

# --- Session / supervisor ---
SESSION_COOKIE = "qqbot_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
SUPERVISOR_HOST = os.environ.get("SUPERVISOR_HOST", "127.0.0.1")
SUPERVISOR_PORT = _int_env("SUPERVISOR_PORT", 9001, minimum=1, maximum=65535)
SECRET_KEY_PATH = os.path.join(MANAGER_DIR, "secret_key")

# Supervisor program names (internal constants, never derived from user input).
PROG_BACKEND = "backend"
PROG_LAGRANGE = "lagrange"
PROG_NONEBOT = "nonebot"
PROG_SIGNSERVER = "signserver"
PROG_NAPCAT = "napcat"

# --- QQ protocol backend selection ---
# "lagrange": Lagrange.OneBot + self-hosted sign server.
# "napcat":   NapCatQQ (no sign server). Selecting napcat stops lagrange + sign
#             server; selecting lagrange stops napcat.
PROTOCOL_LAGRANGE = "lagrange"
PROTOCOL_NAPCAT = "napcat"
VALID_PROTOCOLS = (PROTOCOL_LAGRANGE, PROTOCOL_NAPCAT)
DEFAULT_PROTOCOL = PROTOCOL_LAGRANGE
PROTOCOL_JSON = os.path.join(MANAGER_DIR, "protocol.json")

# --- Log files (read-only viewer) ---
# Whitelist of viewable logs => absolute path under MANAGER_DIR. Names are fixed
# internal constants; the logs API only ever opens paths from this mapping, so
# arbitrary file reads are impossible.
LOG_FILES = {
    "backend": os.path.join(MANAGER_DIR, "backend.log"),
    "lagrange": os.path.join(MANAGER_DIR, "lagrange.log"),
    "signserver": os.path.join(MANAGER_DIR, "signserver.log"),
    "napcat": os.path.join(MANAGER_DIR, "napcat.log"),
    "nonebot": os.path.join(MANAGER_DIR, "nonebot.log"),
    "supervisord": os.path.join(MANAGER_DIR, "supervisord.log"),
}
LOG_LABELS = {
    "backend": "后端服务",
    "lagrange": "Lagrange.OneBot",
    "signserver": "签名服务",
    "napcat": "NapCatQQ",
    "nonebot": "NoneBot",
    "supervisord": "进程管理(Supervisor)",
}
# Max bytes returned by a single log read (tail). Keeps responses bounded.
LOG_MAX_BYTES = 256 * 1024

# Maximum size for text file read/write via the file manager (2 MB).
MAX_TEXT_FILE_SIZE = 2 * 1024 * 1024
MAX_UPLOAD_FILE_SIZE = _int_env("MAX_UPLOAD_FILE_SIZE", 50 * 1024 * 1024)
MAX_UPLOAD_FILES = _int_env("MAX_UPLOAD_FILES", 20, maximum=100)

# Lagrange.OneBot runtime update/config defaults.
LAGRANGE_RELEASE_URL = os.environ.get(
    "LAGRANGE_RELEASE_URL",
    "https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/"
    "Lagrange.OneBot_linux-x64_net9.0_SelfContained.tar.gz",
)
# Default to the container's self-hosted SignServer (VincentZyu233/SignServer).
# The official central sign server is offline, so we sign locally.
LAGRANGE_SIGN_SERVER_URL = os.environ.get(
    "LAGRANGE_SIGN_SERVER_URL",
    f"http://127.0.0.1:{SIGNSERVER_PORT}",
)

# QR code expiry threshold (seconds). A pending qr older than this with no
# successful login is considered expired.
QR_EXPIRY_SECONDS = 120


def _load_or_create_secret_key() -> str:
    """Read the session signing key from disk, generating & persisting it once."""
    try:
        os.makedirs(MANAGER_DIR, exist_ok=True)
        if os.path.exists(SECRET_KEY_PATH):
            with open(SECRET_KEY_PATH, "r", encoding="utf-8") as fh:
                key = fh.read().strip()
                if key:
                    return key
        key = secrets.token_hex(32)
        with open(SECRET_KEY_PATH, "w", encoding="utf-8") as fh:
            fh.write(key)
        try:
            os.chmod(SECRET_KEY_PATH, 0o600)
        except OSError:
            pass
        return key
    except OSError:
        # Fall back to an ephemeral key if /data is not writable (e.g. during
        # unit tests). Sessions simply won't persist across restarts.
        return secrets.token_hex(32)


SECRET_KEY = _load_or_create_secret_key()


def read_protocol() -> str:
    """Return the persisted QQ protocol backend selection, defaulting to lagrange."""
    try:
        with open(PROTOCOL_JSON, "r", encoding="utf-8") as fh:
            value = (json.load(fh) or {}).get("protocol", "")
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PROTOCOL
    return value if value in VALID_PROTOCOLS else DEFAULT_PROTOCOL


def write_protocol(protocol: str) -> None:
    """Persist the QQ protocol backend selection to /data so it survives restarts."""
    if protocol not in VALID_PROTOCOLS:
        raise ValueError(f"invalid protocol: {protocol}")
    os.makedirs(MANAGER_DIR, exist_ok=True)
    with open(PROTOCOL_JSON, "w", encoding="utf-8") as fh:
        json.dump({"protocol": protocol}, fh)


def read_napcat_quicklogin() -> dict:
    """Return the persisted NapCat quick-login config: {"enabled": bool, "qq": str}."""
    enabled, qq = False, ""
    try:
        with open(NAPCAT_QUICKLOGIN_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
        enabled = bool(data.get("enabled", False))
        qq = str(data.get("qq", "") or "").strip()
    except (OSError, json.JSONDecodeError, ValueError):
        return {"enabled": False, "qq": ""}
    if not qq.isdigit():
        qq, enabled = "", False
    return {"enabled": enabled, "qq": qq}


def write_napcat_quicklogin(enabled: bool, qq: str) -> dict:
    """Persist NapCat quick-login config. ``qq`` must be digits when enabled."""
    qq = str(qq or "").strip()
    if enabled and not qq.isdigit():
        raise ValueError("qq must be a numeric QQ uin when quick login is enabled")
    if not qq.isdigit():
        qq = ""
        enabled = False
    os.makedirs(NAPCAT_CONFIG_DIR, exist_ok=True)
    payload = {"enabled": enabled, "qq": qq}
    tmp = NAPCAT_QUICKLOGIN_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, NAPCAT_QUICKLOGIN_JSON)
    return payload


def read_napcat_webui() -> dict:
    """Return NapCat WebUI config: {"token": str, "port": int, "host": str}.

    Reads the same ``webui.json`` NapCat consumes so the panel can surface the
    login token and proxy target. Falls back to defaults when missing/invalid.
    """
    token, port, host = "", NAPCAT_WEBUI_PORT, NAPCAT_WEBUI_HOST
    try:
        with open(NAPCAT_WEBUI_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
        token = str(data.get("token", "") or "")
        if isinstance(data.get("port"), int) and 1 <= data["port"] <= 65535:
            port = data["port"]
        if isinstance(data.get("host"), str) and data["host"]:
            host = data["host"]
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return {"token": token, "port": port, "host": host}


def read_bot_login() -> dict:
    """Return the connected OneBot account: {"online": bool, "uin": str, "nickname": str}.

    Written by NoneBot's bot connect/disconnect lifecycle hooks. Missing/invalid
    file => treated as not connected. This reflects the actually-connected bot,
    independent of which backend (Lagrange/NapCat) is selected.
    """
    try:
        with open(BOT_LOGIN_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {"online": False, "uin": "", "nickname": ""}
    return {
        "online": bool(data.get("online")),
        "uin": str(data.get("uin", "") or ""),
        "nickname": str(data.get("nickname", "") or ""),
    }
