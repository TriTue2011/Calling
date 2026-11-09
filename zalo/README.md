# Zalo — gọi thoại/video, tin nhắn, WebUI

Thư mục này gom **toàn bộ phần Zalo** của repo Calling:

- `zalo-pc-app/` — app Zalo dạng PC chạy Docker (đăng nhập QR kiểu PC, tin nhắn, **gọi thoại và video có tiếng thật**, WebUI). Chi tiết: `zalo-pc-app/README.md`, báo cáo kỹ thuật `zalo-pc-app/bao-cao.md`.
- `zalo-call-client/` — client gọi Zalo bằng Python (bản cũ theo APK mobile, chỉ ở mức signaling; app PC ở trên đã thay thế).
- Tích hợp Home Assistant **`zalo_call`** nằm ở `../custom_components/zalo_call` (HACS bắt buộc `custom_components/` ở gốc repo).

Image Docker: `ghcr.io/tritue2011/zalo-calling` (tag `vX.Y.Z` và `latest`).

## Cài đặt và cập nhật

**1. App Zalo PC (Docker).** Image dựng sẵn, đã kèm ffmpeg (libx264), libopus và OpenSSL — không cài thêm gì:

```sh
mkdir zalo && cd zalo
curl -LO https://github.com/TriTue2011/Calling/releases/latest/download/docker-compose.yml
printf 'ZALO_PC_APP_USER=ten\nZALO_PC_APP_PASSWORD=mat-khau-dai\n' > .env
docker compose up -d          # mở http://<máy chủ>:8080, quét QR Zalo
docker compose pull && docker compose up -d   # cập nhật bản mới
```

Mỗi tag `vX.Y.Z` tự dựng image `ghcr.io/tritue2011/zalo-calling:vX.Y.Z` và `:latest` (amd64 + arm64), rồi tạo
GitHub Release. Kiểm tra bản đang chạy ở `GET /api/status` (`version`, `deps`). Có Watchtower thì tự kéo `:latest`.

**2. Tích hợp Home Assistant (HACS).** HACS → ⋮ → Kho tùy chỉnh → `https://github.com/TriTue2011/Calling`
(loại *Integration*) → tải **Zalo Call** → khởi động lại HA → Cài đặt → Thiết bị & dịch vụ → Thêm tích hợp →
*Zalo Call* (địa chỉ app, tài khoản app). Cập nhật: HACS báo khi có release mới.

### Thiết bị cuộc gọi (loa, mic, camera)

Cài đặt **ngay trên thiết bị Zalo Call** (không cần bánh răng): các thực thể *Loa mặc định*, *Mic mặc định*,
*Camera mặc định*, *Mic URL*, hai công tắc *Tự phát mic khi nghe máy* và *Tự đồng ý khi bên kia xin gọi video*, và các nút
*Chuyển sang video*, *Tắt hình*, *Tắt mic cuộc gọi*. Mỗi cuộc gọi vẫn ghi đè được bằng trường `speaker`, `mic`, `mic_url`,
`camera` của service `make_call` / `answer_call` (để rỗng = tắt thiết bị đó cho cuộc này).

- **Loa**: bất kỳ `media_player` (app phát WAV liên tục, HA bảo loa phát).
- **Mic**: `camera` (tiếng của luồng camera), `assist_satellite` của camera Imou/Dahua (dùng `mic_url` của dahua_talk)
  hoặc của loa R1 (luồng PCM 16 kHz `/api/r1_speaker/mic/<entry>?k=<khoá>` của r1_speaker), hoặc URL bất kỳ
  (rtsp/http/rtmp). HA chỉ phân giải ra URL, **app tự dùng ffmpeg đọc** và phát lên cuộc gọi.
- **Camera**: bất kỳ `camera` có stream (go2rtc/RTSP): app mã hoá H.264 bằng ffmpeg và phát hình lên cuộc gọi video.

**Gọi thoại rồi chuyển sang video** khi đang nói: service `zalo_call.upgrade_to_video` (hoặc nút, hoặc nút
*Chuyển sang video* trong WebUI). Bên kia xin chuyển sang video thì app tự đồng ý và phát camera mặc định (tắt bằng công tắc).

Service mới: `upgrade_to_video`, `start_call_video`, `stop_call_video`, `start_call_mic`, `stop_call_mic`,
`set_default_devices`; `make_call` thêm `type: video` và chọn thiết bị bằng bộ chọn thực thể.

### WebUI

`http://<máy chủ>:8080`: danh bạ (nút *Gọi* và *Video*), khung cuộc gọi (nghe bên kia ngay trên trình duyệt, mic mặc định /
âm 440 Hz / mic trình duyệt, *Chuyển sang video*, camera mặc định / hình thử, tắt hình/mic) và trang **Thiết bị** (nguồn mic,
nguồn camera, thông số hình, hai công tắc tự động). Mic trình duyệt cần HTTPS hoặc localhost.

