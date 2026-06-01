#!/usr/bin/env bash
#
# NapCatQQ launcher (supervisord [program:napcat]).
#
# NapCat injects into the official Linux QQ (an Electron app), so it needs a
# virtual X display. We start Xvfb on :1, then exec the patched QQ binary which
# loads NapCat via /opt/QQ/resources/app/loadNapCat.js. NapCat reads its config
# (onebot11.json) and writes logs/cache/qrcode.png under $NAPCAT_WORKDIR.
set -euo pipefail

NAPCAT_WORKDIR="${NAPCAT_WORKDIR:-/data/napcat}"
export NAPCAT_WORKDIR
mkdir -p "$NAPCAT_WORKDIR/config" "$NAPCAT_WORKDIR/cache" \
         "$NAPCAT_WORKDIR/logs" "$NAPCAT_WORKDIR/home"

# Start a fresh virtual display. The lock may be stale after a restart since
# supervisord kills the whole process group (killasgroup), so clear it first.
rm -f /tmp/.X1-lock
Xvfb :1 -screen 0 1080x760x16 +extension GLX +render >/dev/null 2>&1 &
sleep 2

export DISPLAY=:1
export FFMPEG_PATH="${FFMPEG_PATH:-/usr/bin/ffmpeg}"

# Quick login: when config/quick_login.json has {"enabled":true,"qq":"<uin>"},
# launch QQ with `-q <uin>` so a previously scanned session auto-logs in without
# showing the QR again. The QQ uin is validated to be digits before use.
QUICK_CFG="$NAPCAT_WORKDIR/config/quick_login.json"
QUICK_QQ=""
if [ -f "$QUICK_CFG" ] && grep -q '"enabled"[[:space:]]*:[[:space:]]*true' "$QUICK_CFG"; then
  QUICK_QQ=$(sed -n 's/.*"qq"[[:space:]]*:[[:space:]]*"\{0,1\}\([0-9]\{1,\}\).*/\1/p' "$QUICK_CFG" | head -n1)
fi

# QQ stores its login session under $HOME/.config/QQ; HOME points into the
# persistent workdir so a scanned login survives container rebuilds.
if [ -n "$QUICK_QQ" ]; then
  echo "[napcat] quick login enabled for QQ $QUICK_QQ"
  exec /opt/QQ/qq --no-sandbox -q "$QUICK_QQ"
fi
exec /opt/QQ/qq --no-sandbox
