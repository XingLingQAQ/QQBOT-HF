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

# QQ stores its login session under $HOME/.config/QQ; HOME points into the
# persistent workdir so a scanned login survives container rebuilds.
exec /opt/QQ/qq --no-sandbox
