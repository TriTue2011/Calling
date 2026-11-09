FROM python:3.12-slim
WORKDIR /app
# ffmpeg: doi file ghi am cua trinh duyet (webm/opus, mp4/aac) sang
# MP3 truoc khi gui qua voicemp3 — giong zalobot (Node.js) cai ffmpeg
# trong image de doi tin thoai (voiceAac.js); chi khac dich (MP3 thay
# cho AAC) vi endpoint PC voicemp3 bat buoc MP3 (loi 133). Xem
# zalo_pc_app/voice_transcode.py. --no-install-recommends de image
# gon; khong co ffmpeg thi gui tin thoai loi ro, khong crash server.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*
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
