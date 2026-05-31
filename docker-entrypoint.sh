#!/usr/bin/env bash
#
# Container entrypoint. Prepares the persistent /data layout on first boot
# (virtualenv, configs, manifest), renders the supervisord config, then hands
# off to supervisord as PID 1 to supervise backend / lagrange / nonebot.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
VENV_DIR="${VENV_DIR:-$DATA_DIR/venv}"
PORT="${PORT:-7860}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin123}"
STATIC_DIR="${STATIC_DIR:-/app/static}"
TEMPLATES="/app/backend/app/templates"

export DATA_DIR VENV_DIR PORT ADMIN_USER ADMIN_PASS STATIC_DIR

echo "[entrypoint] preparing $DATA_DIR ..."

# 1. Directory layout
mkdir -p "$DATA_DIR/lagrange" \
         "$DATA_DIR/nonebot/data" \
         "$DATA_DIR/manager"

# 2. Virtualenv + fixed dependencies (first run only)
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[entrypoint] creating virtualenv at $VENV_DIR (first boot, this is slow) ..."
  python -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --no-cache-dir --upgrade pip
  "$VENV_DIR/bin/pip" install --no-cache-dir \
      "fastapi>=0.110" "uvicorn[standard]>=0.29" "python-multipart>=0.0.9" \
      "itsdangerous>=2.1" "aiofiles>=23.2" "websockets>=12.0" \
      "nonebot2>=2.5.0" "nonebot-adapter-onebot>=2.4.6"
fi

# 3. First-run config files (never overwrite user edits / persisted state)
[ -f "$DATA_DIR/nonebot/bot.py" ]            || cp "$TEMPLATES/bot.py.template"          "$DATA_DIR/nonebot/bot.py"
[ -f "$DATA_DIR/nonebot/.env" ]              || cp "$TEMPLATES/env.template"             "$DATA_DIR/nonebot/.env"
[ -f "$DATA_DIR/lagrange/appsettings.json" ] || cp "$TEMPLATES/appsettings.json.template" "$DATA_DIR/lagrange/appsettings.json"
[ -f "$DATA_DIR/plugins.json" ]              || echo '{"plugins":[]}' > "$DATA_DIR/plugins.json"

# Keep first-run and old persisted Lagrange configs aligned with the current
# in-container NoneBot reverse-WS wiring, without overwriting custom sign URLs
# unless they are empty or known legacy defaults.
"$VENV_DIR/bin/python" - "$DATA_DIR/lagrange/appsettings.json" "${LAGRANGE_SIGN_SERVER_URL:-https://sign.lagrangecore.org/api/sign/39038}" <<'PY'
import json, os, sys

path, default_sign = sys.argv[1], sys.argv[2]
old_sign_urls = {"", "https://sign.lagrangecore.org/api/sign", "https://sign.lagrangecore.org/api/sign/30366"}
try:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    cfg = {}
if not isinstance(cfg, dict):
    cfg = {}
if cfg.get("SignServerUrl") in old_sign_urls:
    cfg["SignServerUrl"] = default_sign
cfg.setdefault("Logging", {"LogLevel": {"Default": "Information", "Microsoft": "Warning"}})
cfg.setdefault("SignProxyUrl", "")
cfg.setdefault("MusicSignServerUrl", "")
cfg.setdefault("Account", {"Uin": 0, "Protocol": "Linux", "AutoReconnect": True})
cfg.setdefault("Message", {"IgnoreSelf": True})
cfg.setdefault("QrCode", {"ConsoleCompatibilityMode": False})
impls = cfg.setdefault("Implementations", [])
if not isinstance(impls, list):
    impls = []
    cfg["Implementations"] = impls
reverse = next((x for x in impls if isinstance(x, dict) and x.get("Type") == "ReverseWebSocket"), None)
desired = {
    "Type": "ReverseWebSocket",
    "Host": "127.0.0.1",
    "Port": 8080,
    "Suffix": "/onebot/v11/ws",
    "ReconnectInterval": 5000,
    "HeartBeatInterval": 5000,
    "AccessToken": "",
}
if reverse is None:
    impls.append(desired)
else:
    reverse.update(desired)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
os.replace(tmp, path)
PY

# 3b. Install any enabled plugins recorded in the manifest (idempotent).
if [ -f "$DATA_DIR/plugins.json" ] && [ -x "$VENV_DIR/bin/python" ]; then
  mapfile -t PLUGIN_NAMES < <("$VENV_DIR/bin/python" - "$DATA_DIR/plugins.json" <<'PY'
import json, re, sys
plugin_re = re.compile(r"^nonebot[-_]plugin[-_][A-Za-z0-9_-]+$")
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    cfg = {"plugins": []}
for p in cfg.get("plugins", []):
    name = (p.get("name") or "").strip()
    if name and p.get("enabled", True) and plugin_re.match(name):
        print(name)
PY
)
  for name in "${PLUGIN_NAMES[@]:-}"; do
    [ -z "$name" ] && continue
    echo "[entrypoint] ensuring plugin installed: $name"
    "$VENV_DIR/bin/pip" install --no-cache-dir "$name" || echo "[entrypoint] WARN: failed to install $name"
  done
fi

# 4. Render supervisord config (only the whitelisted vars are substituted).
envsubst '${DATA_DIR} ${VENV_DIR} ${PORT} ${ADMIN_USER} ${ADMIN_PASS} ${STATIC_DIR}' \
  < "$TEMPLATES/supervisord.conf.template" \
  > "$DATA_DIR/manager/supervisord.conf"

# 5. Launch supervisord as PID 1.
echo "[entrypoint] starting supervisord on port $PORT ..."
exec supervisord -c "$DATA_DIR/manager/supervisord.conf"
