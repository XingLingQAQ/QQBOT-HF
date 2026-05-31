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
APPSETTINGS_PATH = os.path.join(LAGRANGE_DIR, "appsettings.json")
LAGRANGE_BIN = os.environ.get("LAGRANGE_BIN", "/opt/lagrange/Lagrange.OneBot")

# NapCat writes the pending login QR here (cache/qrcode.png under its workdir)
# and keeps its OneBot config under config/onebot11.json.
NAPCAT_QRCODE_PATH = os.path.join(NAPCAT_DIR, "cache", "qrcode.png")
NAPCAT_CONFIG_DIR = os.path.join(NAPCAT_DIR, "config")
NAPCAT_ONEBOT_JSON = os.path.join(NAPCAT_CONFIG_DIR, "onebot11.json")

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
