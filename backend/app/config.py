"""Central configuration: constants & filesystem paths.

Everything that must survive a container rebuild lives under ``DATA_DIR`` (``/data``).
Secrets (admin credentials) are read from environment variables and never hardcoded.
"""

import os
import secrets

# --- Base directories (all persistent state lives under DATA_DIR) ---
DATA_DIR = os.environ.get("DATA_DIR", "/data")
LAGRANGE_DIR = os.path.join(DATA_DIR, "lagrange")
NONEBOT_DIR = os.path.join(DATA_DIR, "nonebot")
MANAGER_DIR = os.path.join(DATA_DIR, "manager")
PYTHON_PACKAGES_DIR = os.environ.get("PYTHON_PACKAGES_DIR", os.path.join(DATA_DIR, "python-packages"))

# --- Files ---
PLUGINS_JSON = os.path.join(DATA_DIR, "plugins.json")
PYTHON_BIN = os.environ.get("PYTHON_BIN", "/usr/local/bin/python")
QRCODE_PATH = os.path.join(LAGRANGE_DIR, "qr-0.png")
KEYSTORE_PATH = os.path.join(LAGRANGE_DIR, "keystore.json")
ENV_FILE = os.path.join(NONEBOT_DIR, ".env")
APPSETTINGS_PATH = os.path.join(LAGRANGE_DIR, "appsettings.json")
LAGRANGE_BIN = os.environ.get("LAGRANGE_BIN", "/opt/lagrange/Lagrange.OneBot")

# --- Admin credentials (env-injected, defaults per spec) ---
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

# --- Network ---
PORT = int(os.environ.get("PORT", "7860"))
NONEBOT_WS_PORT = 8080

# --- Static frontend build output ---
STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")

# --- Session / supervisor ---
SESSION_COOKIE = "qqbot_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
SUPERVISOR_HOST = os.environ.get("SUPERVISOR_HOST", "127.0.0.1")
SUPERVISOR_PORT = int(os.environ.get("SUPERVISOR_PORT", "9001"))
SECRET_KEY_PATH = os.path.join(MANAGER_DIR, "secret_key")

# Supervisor program names (internal constants, never derived from user input).
PROG_BACKEND = "backend"
PROG_LAGRANGE = "lagrange"
PROG_NONEBOT = "nonebot"

# Maximum size for text file read/write via the file manager (2 MB).
MAX_TEXT_FILE_SIZE = 2 * 1024 * 1024
MAX_UPLOAD_FILE_SIZE = int(os.environ.get("MAX_UPLOAD_FILE_SIZE", str(50 * 1024 * 1024)))
MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "20"))

# Lagrange.OneBot runtime update/config defaults.
LAGRANGE_RELEASE_URL = os.environ.get(
    "LAGRANGE_RELEASE_URL",
    "https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/"
    "Lagrange.OneBot_linux-x64_net9.0_SelfContained.tar.gz",
)
LAGRANGE_SIGN_SERVER_URL = os.environ.get(
    "LAGRANGE_SIGN_SERVER_URL",
    "https://sign.lagrangecore.org/api/sign/39038",
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
