# Calling — gọi Tele + Zalo (chức năng mới)

Repo chứa code gọi cho Telegram và Zalo, chạy bằng Docker trên server.
Nhắn tin Zalo có sẵn vẫn dùng image `zalobot` của repo has-addons;
repo này chỉ chứa phần gọi mới.

## Cấu trúc

- `telegram-gateway/` — gateway Telegram chạy Docker: FastAPI + TDLib
  (tdjson 1.8.69) + NTgCalls, REST + web UI nội bộ, session bền qua restart.
  Xem chi tiết trong `telegram-gateway/README.md`.
- `zalo-call-client/` — client gọi Zalo bằng Python (signaling theo phân tích
  từ APK Zalo 26.10.02, Opus thật qua libopus, audio I/O trừu tượng).
  Xem chi tiết trong `zalo-call-client/README.md`. Lưu ý trung thực: client
  hiện ở mức signaling đã test offline (40/40); SRTP thật, phiên socket
  mobile thật và kiểm thử bằng tài khoản phụ vẫn là việc tiếp theo.
- `zalo-pc-app/` — app Zalo dạng PC chạy Docker: đăng nhập bằng QR kiểu
  PC (old-format, không WASM), phiên bền qua restart, danh bạ/nhóm,
  gọi đi qua API voicecall HTTPS. Xem chi tiết trong
  `zalo-pc-app/README.md` và báo cáo `zalo-pc-app/bao-cao.md`. Lưu ý
  trung thực: giai đoạn 1 đã test offline (mock server + openssl
  cross-check); nhận cuộc gọi đến (kênh sync) và tiếng trực tiếp
  (engine) là giai đoạn 2; chưa kiểm bằng quét thật.
- `.github/workflows/` — 3 workflow tự build image test (xem dưới).

## Cài đặt và cập nhật (bản phát hành)

**1. App Zalo PC (Docker).** Image dựng sẵn, đã kèm ffmpeg (libx264), libopus và OpenSSL — không cài thêm gì:

```sh
mkdir zalo && cd zalo
curl -LO https://github.com/TriTue2011/Calling/releases/latest/download/docker-compose.yml
printf 'ZALO_PC_APP_USER=ten\nZALO_PC_APP_PASSWORD=mat-khau-dai\n' > .env
docker compose up -d          # mở http://<máy chủ>:8080, quét QR Zalo
docker compose pull && docker compose up -d   # cập nhật bản mới
```

Mỗi tag `vX.Y.Z` tự dựng image `ghcr.io/tritue2011/zalo-pc-app:vX.Y.Z` và `:latest` (amd64 + arm64), rồi tạo
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

## Image test (tự build, không cần build tay)

GitHub Actions tự build và đẩy lên GHCR mỗi khi push lên `main` hoặc bất
kỳ nhánh `muse/*` nào, hoặc chạy tay (Run workflow). Hai workflow nằm ở
gốc repo này nên mới chạy được — trước đây file workflow nằm lồng trong
`outbox/` của repo Giao nên GitHub không nhận.

| Thành phần | Image test |
| --- | --- |
| Telegram gateway | `ghcr.io/tritue2011/telegram-gateway-test:test` và `ghcr.io/tritue2011/telegram-gateway-test:test-<sha>` |
| Zalo call client | `ghcr.io/tritue2011/zalo-call-test:test` và `ghcr.io/tritue2011/zalo-call-test:test-<sha>` |
| Zalo PC app | `ghcr.io/tritue2011/zalo-pc-app-test:test` và `ghcr.io/tritue2011/zalo-pc-app-test:test-<sha>` |

Lệnh pull trên server:

```sh
docker pull ghcr.io/tritue2011/telegram-gateway-test:test
docker pull ghcr.io/tritue2011/zalo-call-test:test
docker pull ghcr.io/tritue2011/zalo-pc-app-test:test
```

Build đa kiến trúc `linux/amd64,linux/arm64` trong 1 job bằng QEMU
(giống 2 file workflow đã chuẩn bị trước đó). Nếu build arm64 bằng QEMU
quá chậm thì tách job arm64 sang runner ARM thật sau.

Chạy Telegram gateway trên server: vào `telegram-gateway/`, copy
`.env.example` thành `.env` (sinh `GATEWAY_TOKEN` mới bằng
`openssl rand -hex 32`, không copy `.env` từ máy khác), rồi
`docker compose up -d`. Cổng 3333 chỉ bind loopback/LAN — tuyệt đối
không mở ra Internet.

## Phân biệt rõ

- Patch module `telegram-user` cho web2api KHÔNG nằm trong repo này.
  Patch đó vẫn nằm ở outbox repo Giao (nhánh `muse/telegram-p1`), chờ
  gộp vào repo web2api.
- Repo này chỉ chứa 3 thành phần chạy Docker độc lập: gateway Telegram,
  client gọi Zalo (đường mobile) và app Zalo kiểu PC (đường QR PC).

## Ràng buộc an toàn

- Mọi thử nghiệm gọi chỉ dùng tài khoản phụ, tuyệt đối không dùng tài
  khoản chính.
- Một tài khoản MTProto Telegram không chạy cùng lúc ở cả module web2api
  lẫn gateway Docker — mỗi đường một tài khoản phụ riêng, hoặc chỉ chạy
  một đường tại một thời điểm.
- Không có bí mật, token, OTP, mật khẩu, cookie hay phiên thật nào trong
  repo này — mọi bí mật đều cấp qua biến môi trường trên server.
