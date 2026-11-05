FROM python:3.12-slim
WORKDIR /app
COPY zalo_pc_app/ ./zalo_pc_app/
COPY zalobot-embedded/ ./zalobot-embedded/
COPY docker-entrypoint.py /usr/local/bin/docker-entrypoint.py
# Node 20 for the embedded zalobot sidecar (zca-js 2.1.2) + ffmpeg
# (video thumbnails + voice AAC conversion, API-MAP §0.1) + jq
# (entrypoint secret handling, same as the zalobot entrypoint.sh).
# Debian bookworm slim has no `node` package new enough, so Node
# comes from the official NodeSource setup (nodesource.com) — the
# documented install path for Debian; the alternative (official
# linux-x64 tarball) needs the same ca-certificates/curl below.
# A real `docker build` can only be verified on the user's server
# (this machine cannot run containers) — see
# HUONG-DAN-BUILD-TREN-SERVER.md.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg ffmpeg jq \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && node --version && npm --version \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && npm ci --omit=dev --no-audit --no-fund \
        --prefix ./zalobot-embedded
RUN useradd -m app && mkdir -p /data && chown app:app /data
# No USER app here on purpose: the container starts as root so the
# entrypoint can chown a host-path data volume to app:app, then drops
# privileges and runs the server as app (never as root). The sidecar
# is started by the entrypoint AFTER the drop, so it runs as app too.
# APP_VERSION is the git commit sha, passed by CI (see the workflow):
# the app reports it in /api/status and the UI footer, so a deploy can
# be verified against the pushed code. Without it, the code's own
# VERSION tag applies.
ARG APP_VERSION=""
ENV ZALO_PC_VERSION=${APP_VERSION}
ENV ZALO_PC_DATA_DIR=/data ZALO_PC_HOST=0.0.0.0 ZALO_PC_PORT=8080
EXPOSE 8080 3000
ENTRYPOINT ["python3", "/usr/local/bin/docker-entrypoint.py"]
CMD ["python3", "-m", "zalo_pc_app.server"]
