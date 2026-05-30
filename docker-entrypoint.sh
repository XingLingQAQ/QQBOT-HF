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

# 3b. Install any enabled plugins recorded in the manifest (idempotent).
if [ -f "$DATA_DIR/plugins.json" ] && [ -x "$VENV_DIR/bin/python" ]; then
  mapfile -t PLUGIN_NAMES < <("$VENV_DIR/bin/python" - "$DATA_DIR/plugins.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    cfg = {"plugins": []}
for p in cfg.get("plugins", []):
    name = (p.get("name") or "").strip()
    if name and p.get("enabled", True):
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
