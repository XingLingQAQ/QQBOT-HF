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

# Create the overlay dir before any Python process starts: the image ships a
# `.pth` file that appends this dir to sys.path (see Dockerfile), but `site`
# only honors it if the dir exists at interpreter startup.
mkdir -p "$PYTHON_PACKAGES_DIR"
export DATA_DIR PYTHON_BIN PYTHON_PACKAGES_DIR PORT ADMIN_USER ADMIN_PASS STATIC_DIR
# NOTE: we deliberately do NOT prepend $PYTHON_PACKAGES_DIR to PYTHONPATH.
# PYTHONPATH would outrank the system site-packages and let a plugin's
# duplicated nonebot/pydantic/playwright core shadow the image's own (crashing
# NoneBot with "No module named 'nonebot.adapters.onebot'"/"ASGIMixin"). Instead
# the overlay is added at LOWEST priority via the .pth, so the system packages
# always win and only genuine plugin packages load from /data.

# Persist pip installs to /data. The image ships read-only layers that do NOT
# survive a rebuild/redeploy, and on Hugging Face only /data persists. We point
# pip at the overlay dir (the same one the .pth adds to sys.path) via a config
# file written at RUNTIME (so the Docker *build*'s own pip installs into the
# image are untouched). `target` makes every `pip install` land in /data.
#
# We deliberately do NOT set `upgrade = true`: combined with `--target`, pip's
# upgrade path `shutil.rmtree()`s the pre-existing package dir before replacing
# it, and on HF's /data (overlay/fuse) `os.rmdir` of a freshly-emptied dir
# raises `OSError: [Errno 39] Directory not empty`, aborting the install AFTER
# packages are downloaded — leaving transitive deps (e.g. nonebot_plugin_alconna)
# half-installed and crashing dependent plugins. Without `upgrade`, pip skips
# already-present packages (warning only) but still fills in MISSING deps, and
# never takes the destructive rmtree path. Clean upgrades go through the
# install-to-tempdir-then-merge path used by the entrypoint loop and the panel.
# The .pth still keeps system core packages winning, so this cannot reintroduce
# the nonebot/pydantic shadowing crashes.
PIP_CONFIG_FILE="$DATA_DIR/manager/pip.conf"
mkdir -p "$DATA_DIR/manager"
_write_pip_conf() {
  # $1 = destination path. Keep `target` under [install] (NOT [global]/PIP_TARGET)
  # so it applies only to `pip install` — putting it globally would make
  # `pip uninstall`, `pip show` and `pip list` choke on an unsupported --target
  # option.
  cat > "$1" <<PIPCONF
[global]
no-cache-dir = true

[install]
target = $PYTHON_PACKAGES_DIR
PIPCONF
}
_write_pip_conf "$PIP_CONFIG_FILE"
export PIP_CONFIG_FILE
# Also drop it at pip's per-user default location so an interactive shell that
# does NOT inherit PIP_CONFIG_FILE (e.g. a plain `docker exec` login) still
# installs to the persistent overlay.
if [ -n "${HOME:-}" ]; then
  mkdir -p "$HOME/.config/pip" 2>/dev/null && _write_pip_conf "$HOME/.config/pip/pip.conf" 2>/dev/null || true
fi

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

# bot.py is a MANAGED file: it carries the OneBot connect/disconnect hooks that
# write the panel's login state (/data/manager/bot_login.json). A deployment
# that first booted before those hooks existed keeps a stale bot.py forever
# under a persistent /data, so NapCat/Lagrange would connect but the panel would
# never see "online"/uin/nickname. We embed a `# qqbot-managed-file: bot.py
# rev=N` marker in the template and auto-upgrade an older/markerless managed
# copy on boot, backing up the previous file first.
_bot_py="$DATA_DIR/nonebot/bot.py"
_bot_tmpl="$TEMPLATES/bot.py.template"
_rev_of() { sed -n 's/^# qqbot-managed-file: bot.py rev=\([0-9][0-9]*\).*/\1/p' "$1" 2>/dev/null | head -n1; }
if [ ! -f "$_bot_py" ]; then
  cp "$_bot_tmpl" "$_bot_py"
  echo "[entrypoint] created managed bot.py (rev $(_rev_of "$_bot_tmpl"))"
else
  _tmpl_rev="$(_rev_of "$_bot_tmpl")"; _tmpl_rev="${_tmpl_rev:-0}"
  _cur_rev="$(_rev_of "$_bot_py")"; _cur_rev="${_cur_rev:-0}"
  if [ "$_cur_rev" -lt "$_tmpl_rev" ]; then
    cp "$_bot_py" "$_bot_py.bak.$(date +%s)" 2>/dev/null || true
    cp "$_bot_tmpl" "$_bot_py"
    echo "[entrypoint] upgraded managed bot.py (rev $_cur_rev -> $_tmpl_rev; old copy backed up)"
  fi
fi

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
    # No --upgrade: that would trigger pip's destructive rmtree on /data (Errno
    # 39). Without it pip skips packages already present and only installs the
    # missing ones (including transitive deps), which is exactly the
    # "ensure installed" semantics we want here and is crash-free.
    "$PYTHON_BIN" -m pip install --no-cache-dir --target "$PYTHON_PACKAGES_DIR" "$name" || echo "[entrypoint] WARN: failed to install $name"
  done
fi

# 3c. Belt-and-suspenders: also delete the duplicated NoneBot core that
# `pip install --target $PYTHON_PACKAGES_DIR` drops into the overlay. The .pth
# above already makes the system nonebot win regardless, but removing the dead
# overlay copy keeps /data lean and self-heals deployments that predate the .pth.
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
