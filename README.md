# 📞 Zalo Calling

Gọi **thoại và video Zalo** từ Home Assistant: điện thoại đổ chuông, nghe máy xong tiếng bên kia ra **loa trong nhà**
(R1, loa camera, `media_player`), mic loa/camera gửi sang điện thoại, video phát hình từ **camera nhà**.

> ⚠️ App không chính thức, đăng nhập Zalo bằng mã QR. **Dùng tài khoản Zalo phụ.**
> Telegram: xem kho riêng [Telegram-calling](https://github.com/TriTue2011/Telegram-calling).

## Thêm nhanh vào Home Assistant

Cần **2 phần**: ① app Zalo (add-on hoặc Docker) và ② tích hợp **Zalo Call** (HACS). Bấm các nút (cần
[My Home Assistant](https://my.home-assistant.io) trỏ về HA của bạn):

| Bước | Nút |
|---|---|
| ① Thêm kho add-on (HAOS / Supervised) | [![Thêm kho add-on](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FTriTue2011%2Fhas-addons) |
| ② Mở tích hợp trong HACS | [![Mở trong HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TriTue2011&repository=Zalo-calling&category=integration) |
| ③ Thêm tích hợp (sau khi tải + khởi động lại HA) | [![Thêm tích hợp](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=zalo_call) |

**Không dùng được nút?** Làm tay:

1. **App:** Cài đặt → Add-on → Cửa hàng → ⋮ → Kho lưu trữ → `https://github.com/TriTue2011/has-addons` → cài **Zalo Calling**
   (hoặc chạy Docker: xem [hướng dẫn đầy đủ](https://github.com/TriTue2011/has-addons/blob/main/zalo_calling/README.md#docker)).
2. **Tích hợp (HACS 2.x):** HACS → **⋮ → Custom repositories** → dán `https://github.com/TriTue2011/Zalo-calling`,
   **Type = Integration** → **Add** → tìm **Zalo Call** trong HACS → **Download** → khởi động lại HA.
3. **Cài đặt → Thiết bị & Dịch vụ → Thêm tích hợp → Zalo Call**: địa chỉ app `http://<IP HA>:8080` + tài khoản WebUI.

Hướng dẫn từng bước, cách cấu hình loa/mic/camera, gọi bằng service, lỗi thường gặp:
**[zalo_calling/README.md](https://github.com/TriTue2011/has-addons/blob/main/zalo_calling/README.md)** (kho has-addons).

## Định dạng chữ, màu, emoji

`zalo_call.send_message` nhận `format: markdown` (**đậm**, *nghiêng*, gạch chân, gạch ngang, tiêu đề, danh sách, `{red}`/`{orange}`/`{yellow}`/`{green}`, `{big}`/`{small}`),
`auto_emphasis` (tự đổi màu + đậm cho số như 29°C, 75%), `emoji` (bảng chọn) và `auto_emoji`. Trả lời của AI tự trả lời cũng đi qua đây (ô/công tắc trên thiết bị).
Chi tiết và ví dụ: [README add-on](https://github.com/TriTue2011/has-addons/blob/main/zalo_calling/README.md).

## Kho này gồm

| Thư mục | Là gì |
|---|---|
| `custom_components/zalo_call/` | Tích hợp Home Assistant (HACS bắt buộc đặt ở gốc kho; **một tích hợp mỗi kho**) |
| `zalo/zalo-pc-app/` | App Zalo dạng PC chạy Docker: đăng nhập QR, gọi thoại/video, WebUI. Ảnh `ghcr.io/tritue2011/zalo-calling` |
| `tests/` | Test của tích hợp (bộ test của app nằm trong `zalo/zalo-pc-app/tests/`) |
| `.github/workflows/` | `ci.yml` (test), `release.yml` (thẻ `vX` → Release + `zalo_call.zip`), `image.yml` (thẻ `vX` → ảnh Docker) |

Phát hành: đẩy thẻ `vX.Y.Z.N` khớp `version` trong `custom_components/zalo_call/manifest.json`.
Chi tiết kỹ thuật của app: [`zalo/README.md`](zalo/README.md).
