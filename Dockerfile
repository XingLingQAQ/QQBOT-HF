# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React/Vite frontend ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build          # output: /build/dist

# ---------- Stage 2: runtime ----------
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PORT=7860 \
    DATA_DIR=/data \
    STATIC_DIR=/app/static \
    PYTHONUNBUFFERED=1

# Runtime deps:
#  - libicu-dev: required by the .NET self-contained Lagrange.OneBot binary
#  - gettext-base: provides `envsubst` used by the entrypoint
#  - procps/bash/curl/tar/gzip/ca-certificates: tooling & TLS for sign server
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl bash procps libicu-dev tar gzip gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Pre-install runtime Python dependencies into the image. Do not run app
# processes from /data: some hosting runtimes mount persistent storage with
# execution restrictions, so /data is used only for persisted configs/plugins.
RUN pip install --no-cache-dir \
      supervisor \
      "fastapi>=0.110" "uvicorn[standard]>=0.29" "python-multipart>=0.0.9" \
      "itsdangerous>=2.1" "aiofiles>=23.2" "websockets>=12.0" \
      "nonebot2>=2.5.0" "nonebot-adapter-onebot>=2.4.6"

# Download Lagrange.OneBot (linux-x64, self-contained net9.0 nightly).
# URL fetched/verified via MCP (LagrangeDev/Lagrange.Core nightly release).
ARG LAGRANGE_URL="https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/Lagrange.OneBot_linux-x64_net9.0_SelfContained.tar.gz"
RUN mkdir -p /opt/lagrange /tmp/lg && \
    curl -fL -o /tmp/lagrange.tar.gz "$LAGRANGE_URL" && \
    tar -xzf /tmp/lagrange.tar.gz -C /tmp/lg && \
    BIN="$(find /tmp/lg -type f -name 'Lagrange.OneBot' | head -n1)" && \
    test -n "$BIN" && \
    cp "$BIN" /opt/lagrange/Lagrange.OneBot && \
    chmod +x /opt/lagrange/Lagrange.OneBot && \
    rm -rf /tmp/lagrange.tar.gz /tmp/lg

WORKDIR /app
COPY backend/ /app/backend/
COPY --from=frontend /build/dist /app/static
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Non-root user; /data is the persistent mount.
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data && \
    chown -R appuser:appuser /data /app /opt/lagrange
USER appuser

EXPOSE 7860
ENTRYPOINT ["/app/docker-entrypoint.sh"]
