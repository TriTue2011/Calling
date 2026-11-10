FROM python:3.12-slim
WORKDIR /app

# Thu vien he thong can khi CHAY (khong can cai gi them tren may chu):
#  - ffmpeg (co libx264): phat hinh camera (RTSP/go2rtc) va mic tu nguon bat ky len cuoc
#    goi, doi ghi am cua trinh duyet sang MP3 de gui tin thoai;
#  - libopus0: ma hoa/giai ma tieng cuoc goi (Opus 16 kHz);
#  - OpenSSL (libcrypto) da di kem python:slim: AES-CTR nhanh cho SRTP;
#  - ca-certificates: goi HTTPS toi Zalo.
# --no-install-recommends de image gon.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY zalo_pc_app/ ./zalo_pc_app/
COPY docker-entrypoint.py /usr/local/bin/docker-entrypoint.py

# Build THAT BAI ngay neu thieu thu vien bat buoc (ffmpeg+libx264, libopus, libcrypto):
# an toan hon la cuoc goi chay cham hoac khong tieng luc dang dung.
RUN python3 -m zalo_pc_app.deps

RUN useradd -m app && mkdir -p /data && chown app:app /data
# No USER app here on purpose: the container starts as root so the
# entrypoint can chown a host-path data volume to app:app, then drops
# privileges and runs the server as app (never as root).

# APP_VERSION: tag phat hanh (vd v2026.11.10.1) hoac commit sha, do CI truyen vao; app bao
# no o /api/status va chan trang UI de doi chieu ban dang chay voi ma da day.
ARG APP_VERSION=""
ENV ZALO_PC_VERSION=${APP_VERSION}
ENV ZALO_PC_DATA_DIR=/data ZALO_PC_HOST=0.0.0.0 ZALO_PC_PORT=8080 PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.source="https://github.com/TriTue2011/Zalo-calling" \
      org.opencontainers.image.description="Zalo PC app: goi thoai/video, tin nhan, WebUI" \
      org.opencontainers.image.version="${APP_VERSION}"
EXPOSE 8080
# Trang dang nhap la cong khai: 200 nghia la server song.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:8080/login', timeout=4).status == 200 else 1)"
ENTRYPOINT ["python3", "/usr/local/bin/docker-entrypoint.py"]
CMD ["python3", "-m", "zalo_pc_app.server"]
