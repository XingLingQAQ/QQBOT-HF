# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React/Vite frontend ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build          # output: /build/dist

# ---------- Stage 2: build the self-hosted SignServer ----------
# VincentZyu233/SignServer is Rust (edition 2024) + a tiny C shim. We build the
# `sign` binary and `libsymbols.so` here; at runtime they sit next to QQ's
# wrapper.node. The offset in sign.config.toml is set for QQ 3.2.23-44343 (see
# sign.config.toml.template for how that offset was derived).
FROM rust:1-slim-bookworm AS signserver
ARG SIGNSERVER_REPO="https://github.com/VincentZyu233/SignServer"
ARG SIGNSERVER_REF="a074cf09df8e6081b056a69b99e35f13f1df167c"
RUN apt-get update && apt-get install -y --no-install-recommends \
      git gcc ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone "$SIGNSERVER_REPO" . && git checkout "$SIGNSERVER_REF"
RUN gcc -std=c99 -shared -fPIC -o libsymbols.so symbols.c && \
    cargo build --release && \
    mkdir -p /out && \
    cp target/release/sign /out/sign && \
    cp libsymbols.so /out/libsymbols.so

# ---------- Stage 3: runtime ----------
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PORT=7860 \
    DATA_DIR=/data \
    STATIC_DIR=/app/static \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# Runtime deps:
#  - libicu-dev: required by the .NET self-contained Lagrange.OneBot binary
#  - gettext-base: provides `envsubst` used by the entrypoint
#  - procps/bash/curl/tar/gzip/unzip/ca-certificates: tooling & TLS
#  - GUI/Electron libs + xvfb + ffmpeg + fonts + dbus: required to run the
#    official Linux QQ (Electron) headless for NapCatQQ
#  - libgnutls30: provides libgnutls.so.30 preloaded by the sign server
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl bash procps libicu-dev tar gzip unzip gettext-base \
      libgnutls30 gnutls-bin \
      xvfb ffmpeg dbus dbus-x11 \
      libnss3 libnotify4 libsecret-1-0 libgbm1 libasound2 \
      libglib2.0-0 libdbus-1-3 libgtk-3-0 libxss1 libxtst6 libatspi2.0-0 \
      libx11-xcb1 fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# Pre-install runtime Python dependencies into the image. Do not run app
# processes from /data: some hosting runtimes mount persistent storage with
# execution restrictions, so /data is used only for persisted configs/plugins.
RUN pip install --no-cache-dir \
      supervisor \
      "fastapi>=0.110" "uvicorn[standard]>=0.29" "python-multipart>=0.0.9" \
      "itsdangerous>=2.1" "aiofiles>=23.2" "httpx>=0.27" "websockets>=12.0" \
      "nonebot2>=2.5.0" "nonebot-adapter-onebot>=2.4.6" \
      "playwright==1.60.0"

# Pre-install Playwright's Chromium (+ headless shell) and its OS deps into the
# image so browser-rendering plugins (e.g. nonebot-plugin-htmlrender, which
# nonebot-plugin-picstatus_ng depends on) work out of the box. Without this the
# plugin's startup hook fails ("Executable doesn't exist ... chrome-headless-shell")
# and takes the whole NoneBot process down. Browsers go to PLAYWRIGHT_BROWSERS_PATH
# (/opt/ms-playwright), a stable shared path; world-readable so appuser can launch.
# The system Playwright (pinned here) always wins over any overlay copy a plugin
# pulls into /data (see the overlay .pth below), so this baked Chromium build
# always matches the Playwright that actually runs.
RUN python -m playwright install --with-deps chromium && \
    chmod -R a+rX /opt/ms-playwright

# Make the persisted plugin dir (/data/python-packages) the LOWEST-priority entry
# on sys.path via a .pth file. .pth dirs are appended AFTER the system
# site-packages, so the image's own nonebot/pydantic/playwright/etc. always win,
# and only packages that exist solely in the overlay (the actual plugins) load
# from /data. This is the root fix for the recurring crashes where a plugin's
# `pip install --target` dropped a duplicate (often older/incomplete) nonebot
# core into the overlay and shadowed the system one carrying the OneBot adapter
# (ModuleNotFoundError: nonebot.adapters.onebot / ImportError: ASGIMixin).
# NOTE: site only adds the dir if it exists at interpreter start; the entrypoint
# creates /data/python-packages before launching any process.
RUN SP="$(python -c 'import site; print(site.getsitepackages()[0])')" && \
    printf '%s\n' '/data/python-packages' > "$SP/zzz_qqbot_overlay.pth" && \
    echo "[build] overlay path file -> $SP/zzz_qqbot_overlay.pth"

# Download Lagrange.OneBot (linux-x64, self-contained net9.0 nightly).
ARG LAGRANGE_URL="https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/Lagrange.OneBot_linux-x64_net9.0_SelfContained.tar.gz"
RUN mkdir -p /opt/lagrange /tmp/lg && \
    curl -fL -o /tmp/lagrange.tar.gz "$LAGRANGE_URL" && \
    tar -xzf /tmp/lagrange.tar.gz -C /tmp/lg && \
    BIN="$(find /tmp/lg -type f -name 'Lagrange.OneBot' | head -n1)" && \
    test -n "$BIN" && \
    cp "$BIN" /opt/lagrange/Lagrange.OneBot && \
    chmod +x /opt/lagrange/Lagrange.OneBot && \
    rm -rf /tmp/lagrange.tar.gz /tmp/lg

# Install ONE official Linux QQ build, 3.2.23-44343, shared by BOTH backends:
#   * NapCatQQ runs this QQ's Electron app. NapCat 4.18.4's PacketBackend requires
#     QQ build >= 40768 and explicitly rejects older builds like 3.2.19-39038
#     ("PacketBackend 不支持当前QQ版本架构：3.2.19-39038-x64"), so 3.2.23-44343 is
#     the minimum that works. URL/version per the NapCat v4.18.4 release notes.
#   * The self-hosted SignServer dlopen()s this same QQ's wrapper.node (it never
#     runs the Electron app). The SignServer supports any QQ build via its
#     offset/version config — we located the sign-function offset for 3.2.23-44343
#     and ship a matching appinfo, so a single QQ serves both (see
#     sign.config.toml.template). This keeps the image to one QQ install.
ARG QQ_DEB_URL="https://dldir1.qq.com/qqfile/qq/QQNT/94704804/linuxqq_3.2.23-44343_amd64.deb"
ARG QQ_DEB_SHA512="acb42d676bdb9c64da4aa3f8ed1a2a4eaac73de75eac45928923f734fd34a2da00e90829b9a91d9d4c18fca3ee459c168b4217a2a462ce6aa32f95712cee87fe"
RUN for i in 1 2 3 4 5; do \
        curl --retry 3 --retry-delay 5 --connect-timeout 30 --max-time 900 -fL -o /tmp/linuxqq.deb "$QQ_DEB_URL" && break || \
        (echo "QQ download attempt $i failed, retrying in 10s..." && sleep 10); \
    done && \
    echo "${QQ_DEB_SHA512}  /tmp/linuxqq.deb" | sha512sum -c - && \
    dpkg -i --force-depends /tmp/linuxqq.deb && \
    rm -f /tmp/linuxqq.deb

# Place the sign server next to QQ's wrapper.node (its required CWD) + config +
# the 3.2.23-44343 appinfo (served at /appinfo; the upstream build only embeds
# 3.2.19-39038, and service.rs reads {version}.json from CWD before the embed).
COPY --from=signserver /out/sign /opt/QQ/resources/app/sign
COPY --from=signserver /out/libsymbols.so /opt/QQ/resources/app/libsymbols.so
COPY backend/app/templates/sign.config.toml.template /opt/QQ/resources/app/sign.config.toml
COPY backend/app/templates/3.2.23-44343.json /opt/QQ/resources/app/3.2.23-44343.json
RUN chmod +x /opt/QQ/resources/app/sign

# Install NapCatQQ (Shell) and patch QQ to load it on startup.
ARG NAPCAT_URL="https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.4/NapCat.Shell.zip"
RUN mkdir -p /opt/napcat && \
    curl -fL -o /tmp/napcat.zip "$NAPCAT_URL" && \
    unzip -q /tmp/napcat.zip -d /opt/napcat && \
    rm -f /tmp/napcat.zip && \
    echo "(async () => {await import('file:///opt/napcat/napcat.mjs');})();" > /opt/QQ/resources/app/loadNapCat.js && \
    sed -i 's|"main": "[^"]*"|"main": "./loadNapCat.js"|' /opt/QQ/resources/app/package.json

# Re-base the NapCat WebUI static bundle so it can be reverse-proxied under
# /napcat/* on the single public port. NapCat dropped `prefix` support in v4.4+,
# so its frontend hardcodes absolute paths: assets/router under `/webui/` and its
# backend under `/api/` (incl. the WS endpoints `/api/Debug/ws`, `/api/ws/terminal`,
# built via template literals, not just quoted strings). We rewrite `/webui/`->
# `/napcat/webui/`, `/api/`->`/napcat/api/` and the bare base `/api"`->`/napcat/api"`
# in the served HTML/JS/CSS; the backend proxy strips `/napcat` before forwarding to
# 6099. The `/api/` form is precise: external refs like `api.github.com`/`api.iowen.cn`
# use `/api.` (a dot, not a slash) and are left untouched.
RUN set -e; \
    WEBUI_STATIC=/opt/napcat/static; \
    if [ -d "$WEBUI_STATIC" ]; then \
      find "$WEBUI_STATIC" -type f \( -name '*.html' -o -name '*.js' -o -name '*.css' \) -print0 \
        | xargs -0 sed -i -e 's#/webui/#/napcat/webui/#g' -e 's#/api/#/napcat/api/#g' -e 's#/api"#/napcat/api"#g'; \
      echo "[build] patched NapCat WebUI base paths under $WEBUI_STATIC"; \
    else \
      echo "[build] WARN: $WEBUI_STATIC not found; WebUI base paths not patched"; \
    fi

COPY scripts/napcat-run.sh /opt/napcat/napcat-run.sh
RUN chmod +x /opt/napcat/napcat-run.sh

WORKDIR /app
COPY backend/ /app/backend/
COPY --from=frontend /build/dist /app/static
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Non-root user; /data is the persistent mount. /opt/QQ must be writable by the
# runtime user (QQ writes its profile/cache, the sign server appends a log).
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data && \
    chown -R appuser:appuser /data /app /opt/lagrange /opt/napcat /opt/QQ
USER appuser

EXPOSE 7860
ENTRYPOINT ["/app/docker-entrypoint.sh"]
