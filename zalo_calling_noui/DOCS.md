# Zalo Calling — bản KHÔNG giao diện

Cùng mã nguồn với bản có giao diện nhưng nhỏ hơn, hợp máy cấu hình yếu. **Không có WebUI**: mọi cài đặt đặt bằng
tuỳ chọn add-on, dịch vụ Home Assistant hoặc `curl`.

> App không chính thức. **Dùng tài khoản Zalo phụ.**

## Cài đặt

1. **Cài đặt → Add-on → Cửa hàng → ⋮ → Kho lưu trữ** → thêm `https://github.com/TriTue2011/Zalo-calling`.
2. Cài **Zalo Calling (không giao diện)**. Ở tab *Cấu hình* điền **`username`** và **`password`** (từ 8 ký tự) — **bắt buộc**,
   thiếu thì Supervisor không cho khởi động. Khởi động add-on.
3. Cài tích hợp **Zalo Call** bằng HACS, khởi động lại HA, **Thêm tích hợp → Zalo Call** với địa chỉ `http://<IP máy HA>:8080`
   và đúng cặp `username`/`password` ở bước 2.
4. Đăng nhập Zalo: gọi dịch vụ **`zalo_call.login_qr`** (`type: pc` để gọi thoại/video, `web` chỉ nhắn tin) rồi mở thực thể ảnh
   **Mã QR đăng nhập**, quét bằng Zalo trên điện thoại. Cảm biến **Trạng thái Zalo** cho biết đã đăng nhập hay chưa.

## Tuỳ chọn

| Tuỳ chọn | Bắt buộc | Ý nghĩa |
|---|---|---|
| `username` | **có** | Tên đăng nhập app. |
| `password` | **có**, ≥ 8 ký tự | Mật khẩu app. Đổi lúc đang chạy bằng `zalo_call.set_app_password` thì giá trị đó được giữ. |
| `webhook_url` | không | Webhook ban đầu cho cả bốn loại; chỉ dùng khi chưa có cấu hình webhook. |

## Đọc / đổi cài đặt lúc đang chạy (không cần WebUI)

Dịch vụ Home Assistant (cũng dùng được trong blueprint/automation):

- `zalo_call.get_app_settings` — đọc webhook, thiết bị, lưu giữ, proxy, bảo mật (`sections`, `reveal_secrets`).
- `zalo_call.set_app_settings` — đổi một mục: `section: webhooks | devices | retention | proxy | security` + `values`.
- `zalo_call.set_app_password`, `zalo_call.test_webhook`, `zalo_call.logout`.

Hoặc `curl`: đăng nhập `POST /api/app/login` (`{"username":…, "password":…}`) lấy cookie, rồi `GET/POST /api/webhooks`,
`/api/settings/devices`, … Kiểm tra sống: `GET /api/app/status` (không cần đăng nhập).

## Lưu ý

- Cổng **8080** để tích hợp và loa/camera gọi vào.
- Dữ liệu ở `/data` của add-on, đi theo bản sao lưu HA.
- **Không cài đồng thời** với bản có giao diện trên cùng cổng 8080.
- Hướng dẫn đầy đủ: <https://github.com/TriTue2011/Zalo-calling#readme>
