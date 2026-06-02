#!/usr/bin/env bash
#
# Container entrypoint. Prepares the persistent /data layout on first boot
# (configs, manifest, persisted plugin packages), renders the supervisord config, then hands
# off to supervisord as PID 1 to supervise backend / lagrange / nonebot.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
PYTHON_BIN="${PYTHON_BIN:-/usr/local/bin/python}"
PYTHON_PACKAGES_DIR="${PYTHON_PACKAGES_DIR:-$DATA_DIR/python-packages}"
PORT="${PORT:-7860}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin123}"
STATIC_DIR="${STATIC_DIR:-/app/static}"
TEMPLATES="/app/backend/app/templates"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "[entrypoint] WARN: invalid PORT=$PORT, falling back to 7860"
  PORT=7860
fi

mkdir -p "$PYTHON_PACKAGES_DIR"
export DATA_DIR PYTHON_BIN PYTHON_PACKAGES_DIR PORT ADMIN_USER ADMIN_PASS STATIC_DIR
export PYTHONPATH="$PYTHON_PACKAGES_DIR${PYTHONPATH:+:$PYTHONPATH}"

echo "[entrypoint] preparing $DATA_DIR ..."

# 1. Directory layout
mkdir -p "$DATA_DIR/lagrange" \
         "$DATA_DIR/nonebot/data" \
         "$DATA_DIR/manager" \
         "$DATA_DIR/napcat/config" \
         "$DATA_DIR/napcat/cache" \
         "$DATA_DIR/napcat/logs" \
         "$DATA_DIR/napcat/home"

# 2. Runtime dependencies are installed in the image. Plugins are persisted as
# importable packages under /data/python-packages so no script in /data needs to
# be executed (compatible with noexec persistent volumes).

# 3. First-run config files (never overwrite user edits / persisted state)
[ -f "$DATA_DIR/nonebot/bot.py" ]            || cp "$TEMPLATES/bot.py.template"          "$DATA_DIR/nonebot/bot.py"
[ -f "$DATA_DIR/nonebot/.env" ]              || cp "$TEMPLATES/env.template"             "$DATA_DIR/nonebot/.env"
[ -f "$DATA_DIR/lagrange/appsettings.json" ] || cp "$TEMPLATES/appsettings.json.template" "$DATA_DIR/lagrange/appsettings.json"
[ -f "$DATA_DIR/napcat/config/onebot11.json" ] || cp "$TEMPLATES/onebot11.json.template" "$DATA_DIR/napcat/config/onebot11.json"
[ -f "$DATA_DIR/plugins.json" ]              || echo '{"plugins":[]}' > "$DATA_DIR/plugins.json"

# NapCat WebUI config (first run only). Listen on loopback so it is never
# exposed directly; the backend reverse-proxies it at /napcat/* on $PORT. A
# random token is generated once and persisted so the panel can pre-fill login.
WEBUI_JSON="$DATA_DIR/napcat/config/webui.json"
if [ ! -f "$WEBUI_JSON" ]; then
  "$PYTHON_BIN" - "$WEBUI_JSON" "${NAPCAT_WEBUI_PORT:-6099}" <<'PY'
import json, secrets, sys
path, port = sys.argv[1], int(sys.argv[2])
cfg = {
    "host": "127.0.0.1",
    "port": port,
    "token": secrets.token_hex(16),
    "loginRate": 10,
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False, indent=2)
PY
  echo "[entrypoint] generated NapCat WebUI config at $WEBUI_JSON"
fi

# Keep first-run and old persisted Lagrange configs aligned with the current
# in-container NoneBot reverse-WS wiring, without overwriting custom sign URLs
# unless they are empty or known legacy defaults. The default points at the
# self-hosted SignServer (127.0.0.1:8087); legacy official URLs are migrated to
# it since the central sign server is offline.
"$PYTHON_BIN" - "$DATA_DIR/lagrange/appsettings.json" "${LAGRANGE_SIGN_SERVER_URL:-http://127.0.0.1:${SIGNSERVER_PORT:-8087}}" <<'PY'
import json, os, sys

path, default_sign = sys.argv[1], sys.argv[2]
old_sign_urls = {
    "",
    "https://sign.lagrangecore.org/api/sign",
    "https://sign.lagrangecore.org/api/sign/30366",
    "https://sign.lagrangecore.org/api/sign/39038",
}
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

# 3a. QQ protocol backend selection (persisted). Defaults to lagrange so the
# existing behaviour is unchanged; napcat starts disabled.
[ -f "$DATA_DIR/manager/protocol.json" ]     || echo '{"protocol":"lagrange"}' > "$DATA_DIR/manager/protocol.json"
PROTOCOL=$(sed -n 's/.*"protocol"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p' "$DATA_DIR/manager/protocol.json")
[ "$PROTOCOL" = "napcat" ] || PROTOCOL="lagrange"
if [ "$PROTOCOL" = "napcat" ]; then
  AUTOSTART_LAGRANGE="false"; AUTOSTART_SIGNSERVER="false"; AUTOSTART_NAPCAT="true"
else
  AUTOSTART_LAGRANGE="true";  AUTOSTART_SIGNSERVER="true";  AUTOSTART_NAPCAT="false"
fi
export AUTOSTART_LAGRANGE AUTOSTART_SIGNSERVER AUTOSTART_NAPCAT
echo "[entrypoint] QQ protocol backend: $PROTOCOL"

# 3b. Install any enabled plugins recorded in the manifest (idempotent).
if [ -f "$DATA_DIR/plugins.json" ]; then
  mapfile -t PLUGIN_NAMES < <("$PYTHON_BIN" - "$DATA_DIR/plugins.json" <<'PY'
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
    "$PYTHON_BIN" -m pip install --no-cache-dir --upgrade --target "$PYTHON_PACKAGES_DIR" "$name" || echo "[entrypoint] WARN: failed to install $name"
  done
fi

# 3c. Strip the duplicated NoneBot core from the plugin overlay dir.
# `pip install --target $PYTHON_PACKAGES_DIR` also drops a full copy of nonebot2
# (a hard dependency of every plugin) into the overlay. Since that dir is
# prepended to PYTHONPATH, the duplicate `nonebot/` package shadows the image's
# system install — the one carrying the OneBot v11 adapter — so NoneBot crashes
# on boot with "No module named 'nonebot.adapters.onebot'". The image already
# ships a complete nonebot core + onebot adapter, so remove the overlay copy;
# real plugin packages (nonebot_plugin_*) stay and import nonebot from the
# system. Runs every boot, so it also self-heals deployments already broken.
if [ -d "$PYTHON_PACKAGES_DIR" ]; then
  rm -rf "$PYTHON_PACKAGES_DIR/nonebot" \
         "$PYTHON_PACKAGES_DIR"/nonebot2-*.dist-info \
         "$PYTHON_PACKAGES_DIR"/nonebot2-*.data 2>/dev/null || true
fi

# 4. Render supervisord config (only the whitelisted vars are substituted).
envsubst '${DATA_DIR} ${PYTHON_BIN} ${PORT} ${AUTOSTART_LAGRANGE} ${AUTOSTART_SIGNSERVER} ${AUTOSTART_NAPCAT}' \
  < "$TEMPLATES/supervisord.conf.template" \
  > "$DATA_DIR/manager/supervisord.conf"

# 5. Launch supervisord as PID 1.
echo "[entrypoint] starting supervisord on port $PORT ..."
exec supervisord -c "$DATA_DIR/manager/supervisord.conf"
