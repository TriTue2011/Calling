# Calling — gọi Tele + Zalo (chức năng mới)

Repo chứa code gọi cho Telegram và Zalo, chạy bằng Docker trên server.
Nhắn tin Zalo có sẵn vẫn dùng image `zalobot` của repo has-addons;
repo này chỉ chứa phần gọi mới.

## Cấu trúc

- `zalo/` — **toàn bộ phần Zalo**: app Zalo PC (gọi thoại/video, tin nhắn, WebUI) và client cũ.
  Cài đặt, cập nhật, thiết bị loa/mic/camera: xem **`zalo/README.md`**. Image: `ghcr.io/tritue2011/zalo-calling`.
- `custom_components/zalo_call/` — tích hợp Home Assistant cho phần Zalo (cài bằng HACS; phải ở gốc repo).
- `telegram-gateway/` — gateway Telegram chạy Docker: FastAPI + TDLib
  (tdjson 1.8.69) + NTgCalls, REST + web UI nội bộ, session bền qua restart.
  Xem chi tiết trong `telegram-gateway/README.md`.
- `.github/workflows/` — `ci.yml` (test), `release.yml` (tag `vX` → image `zalo-calling` + GitHub Release),
  cùng workflow build image test của telegram-gateway và zalo-call-client.

## Image test (tự build, không cần build tay)

GitHub Actions tự build và đẩy lên GHCR mỗi khi push lên `main` hoặc bất
kỳ nhánh `muse/*` nào, hoặc chạy tay (Run workflow). Các workflow nằm ở
gốc repo này nên mới chạy được — trước đây file workflow nằm lồng trong
`outbox/` của repo Giao nên GitHub không nhận.

| Thành phần | Image test |
| --- | --- |
| Telegram gateway | `ghcr.io/tritue2011/telegram-gateway-test:test` và `ghcr.io/tritue2011/telegram-gateway-test:test-<sha>` |
| Zalo call client | `ghcr.io/tritue2011/zalo-call-test:test` và `ghcr.io/tritue2011/zalo-call-test:test-<sha>` |

Lệnh pull trên server:

```sh
docker pull ghcr.io/tritue2011/telegram-gateway-test:test
docker pull ghcr.io/tritue2011/zalo-call-test:test
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
