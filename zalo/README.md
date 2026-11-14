# Zalo — gọi thoại/video, tin nhắn, WebUI

Thư mục này gom **toàn bộ phần Zalo** của repo Zalo-calling:

- `zalo-pc-app/` — app Zalo dạng PC (đăng nhập QR, tin nhắn, **gọi thoại và video có tiếng thật**, WebUI). Chi tiết, bảng biến môi trường: [`zalo-pc-app/README.md`](zalo-pc-app/README.md); báo cáo kỹ thuật `zalo-pc-app/bao-cao.md`.
- Tích hợp Home Assistant **`zalo_call`** ở `../custom_components/zalo_call` (HACS bắt buộc `custom_components/` ở gốc repo).
- Hai add-on HA (có WebUI hiện ở thanh bên qua Ingress; không giao diện) ở kho [has-addons](https://github.com/TriTue2011/has-addons); app tự bật Ingress khi chạy dưới add-on (`ZALO_PC_INGRESS=1`).

Image Docker: `ghcr.io/tritue2011/zalo-calling` — `:latest` / `:vX.Y.Z` / `:X.Y.Z` có giao diện; `:noui` / `:vX.Y.Z-noui` / `:X.Y.Z-noui` không giao diện (amd64 + arm64).

## Cài đặt và cập nhật

Hướng dẫn cài từng bước theo thứ tự Docker → Docker Compose → Portainer → tích hợp HACS → kết nối → dịch vụ → automation: [README gốc](../README.md#1-cài-đặt-app-bằng-docker-docker-compose-và-portainer);
add-on HAOS ở kho [has-addons](https://github.com/TriTue2011/has-addons): [có giao diện](https://github.com/TriTue2011/has-addons/blob/main/zalo_calling/DOCS.md), [không giao diện](https://github.com/TriTue2011/has-addons/blob/main/zalo_calling_noui/DOCS.md). Tóm tắt:

- **Add-on** (HAOS/Supervised): thêm kho `https://github.com/TriTue2011/Zalo-calling`, cài *Zalo Calling* hoặc *Zalo Calling (không giao diện)*; bản không giao diện **bắt buộc** điền `username` và `password` (≥ 8 ký tự).
- **Docker:** `docker-compose.yml` (có giao diện) hoặc `docker-compose.noui.yml`; `.env` là tuỳ chọn — không đặt thì app tự sinh tài khoản và in một lần trong log.
  Cập nhật: `docker compose pull && docker compose up -d` (hoặc Watchtower kéo `:latest`). Bản đang chạy: `GET /api/status` (`version`, `deps`, `ui`).
- **Tích hợp:** HACS → Custom repositories → repo này (*Integration*) → tải **Zalo Call** → khởi động lại HA → Thêm tích hợp (địa chỉ app `http://<IP>:8080` + tài khoản app).

Mỗi thẻ `vX.Y.Z.N` (khớp `version` trong manifest) tự tạo GitHub Release (`zalo_call.zip` cho HACS) và dựng hai image; phiên bản add-on theo cùng số đó.

### Thiết bị cuộc gọi (loa, mic, camera)

Không có loa/mic/camera «mặc định» toàn cục: thiết bị chỉ được dùng khi **quy tắc** của người đó (`set_rule`) hoặc **chính cuộc gọi** (`make_call`, `answer_call`) chọn
và tích ô `connect` / `connect_now`. Chưa chọn là không dùng, AI cũng không tự dùng.

- **Loa**: bất kỳ `media_player` (app phát WAV liên tục, HA bảo loa phát).
- **Mic**: `camera` (tiếng của luồng camera), `assist_satellite`, hoặc URL bất kỳ (`mic_url`: rtsp/http/rtmp). HA chỉ phân giải ra URL, **app tự dùng ffmpeg đọc** và phát lên cuộc gọi.
- **Camera**: bất kỳ `camera` có stream (go2rtc/RTSP): app mã hoá H.264 bằng ffmpeg và phát hình lên cuộc gọi video.
- Các chế độ tự động chung (`auto_mic`, `auto_video`, `echo_guard`, `call_volume`…) đặt bằng `set_default_devices`.

**Gọi thoại rồi chuyển sang video** khi đang nói: dịch vụ `zalo_call.upgrade_to_video`, nút *Chuyển sang video* của tích hợp, hoặc nút trong WebUI.
Video của bên kia (H.264 hoặc H.265) hiện ở WebUI; cuộc gọi có thể tách thành cửa sổ riêng (`/call`). Gọi nhóm: có tín hiệu và danh sách người tham gia, nhưng hình/tiếng nhóm (máy chủ SFU của Zalo) chưa được hỗ trợ.

### WebUI

> **Giới hạn đã biết:** tin 1-1 chỉ có từ lúc app bắt đầu lưu tin xuống DB của app (Zalo không có API lấy lịch sử 1-1); tin mới vẫn hiện tức thì. WebUI không còn hiện dòng cảnh báo này (chi tiết: [README app](zalo-pc-app/README.md#lịch-sử-tin-nhắn-1-1-giới-hạn-đã-biết)).

`http://<máy chủ>:8080` (hoặc thanh bên của HA khi dùng add-on có giao diện): danh bạ (nút *Gọi* và *Video*), khung cuộc gọi (nghe bên kia ngay trên trình duyệt,
mic trình duyệt, *Chuyển sang video*, tắt hình/mic, *Tách cửa sổ*) và trang **Thiết bị**. Trong cuộc gọi có **Mic máy này** / **Nghe trên máy này** (mic và loa của máy đang mở WebUI, mic cần HTTPS hoặc localhost) và **Mic/Loa/Camera nhà** (thiết bị trong nhà); xem README gốc, mục 8.
**Trên điện thoại** (màn ≤ 900 px quy đổi) WebUI chuyển sang bố cục kiểu Zalo di động: thanh đầu gradient xanh, thanh tab dưới có nhãn, soạn tin một hàng (nút ít dùng gom vào «…»), nút ≡ mở trang **Thông tin** toàn màn hình. `tests/test_phone_layout.py` đo bố cục bằng Chrome thật ở 390 px và 320 px.
Đăng nhập Zalo ở màn hình đầu: **Qua PC** (gọi thoại/video) hoặc **Qua Web** (chỉ nhắn tin). Bản không giao diện không có các trang này: cấu hình bằng `.env` / tuỳ chọn add-on,
dịch vụ HA `get_app_settings` / `set_app_settings` hoặc `curl`.
