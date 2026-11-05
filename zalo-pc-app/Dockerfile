FROM python:3.12-slim
WORKDIR /app
COPY zalo_pc_app/ ./zalo_pc_app/
RUN useradd -m app && mkdir -p /data && chown app:app /data
USER app
ENV ZALO_PC_DATA_DIR=/data ZALO_PC_HOST=0.0.0.0 ZALO_PC_PORT=8080
EXPOSE 8080
CMD ["python3", "-m", "zalo_pc_app.server"]
