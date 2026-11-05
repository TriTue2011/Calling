FROM python:3.12-slim
WORKDIR /app
COPY zalo_pc_app/ ./zalo_pc_app/
COPY docker-entrypoint.py /usr/local/bin/docker-entrypoint.py
RUN useradd -m app && mkdir -p /data && chown app:app /data
# No USER app here on purpose: the container starts as root so the
# entrypoint can chown a host-path data volume to app:app, then drops
# privileges and runs the server as app (never as root).
# APP_VERSION is the git commit sha, passed by CI (see the workflow):
# the app reports it in /api/status and the UI footer, so a deploy can
# be verified against the pushed code. Without it, the code's own
# VERSION tag applies.
ARG APP_VERSION=""
ENV ZALO_PC_VERSION=${APP_VERSION}
ENV ZALO_PC_DATA_DIR=/data ZALO_PC_HOST=0.0.0.0 ZALO_PC_PORT=8080
EXPOSE 8080
ENTRYPOINT ["python3", "/usr/local/bin/docker-entrypoint.py"]
CMD ["python3", "-m", "zalo_pc_app.server"]
