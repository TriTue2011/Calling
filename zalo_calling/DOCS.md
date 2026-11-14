# Zalo Calling — bản có giao diện

Gọi **thoại và video Zalo** từ Home Assistant. Add-on này chạy app Zalo (đăng nhập bằng mã QR) và hiện WebUI
ngay trong bảng bên của HA (mục **Zalo Calling**), không cần mở cổng hay tự dựng proxy.

> App không chính thức. **Dùng tài khoản Zalo phụ.**

## Cài đặt

1. **Cài đặt → Add-on → Cửa hàng → ⋮ → Kho lưu trữ** → thêm `https://github.com/TriTue2011/Zalo-calling`.
2. Cài **Zalo Calling**, bấm **Khởi động**. Có thể bật *Hiện trong thanh bên*.
3. Mở **Zalo Calling** ở thanh bên → chọn **Qua Web** (nhắn tin) hoặc **Qua PC** (cần cho gọi thoại/video) → quét QR bằng Zalo trên điện thoại.
4. Cài tích hợp **Zalo Call** bằng HACS (`https://github.com/TriTue2011/Zalo-calling`, loại *Integration*), khởi động lại HA, rồi
   **Thiết bị & Dịch vụ → Thêm tích hợp → Zalo Call** với địa chỉ `http://<IP máy HA>:8080` và tên đăng nhập/mật khẩu bên dưới.

## Tuỳ chọn (đều không bắt buộc)

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `username` | Tên đăng nhập app, mặc định `admin`. |
| `password` | Để trống: app tự sinh, in **một lần** trong tab *Nhật ký* và lưu ở `/data/THONG-TIN-DANG-NHAP.txt`. |
| `webhook_url` | Địa chỉ webhook ban đầu cho cả bốn loại (tin nhắn, sự kiện nhóm, biểu cảm, cuộc gọi). Chỉ dùng khi chưa có cấu hình; dùng tích hợp Zalo Call thì để trống. |

Mở bằng bảng bên của HA thì **không hỏi mật khẩu** (HA đã xác thực bạn). Mật khẩu chỉ dùng khi vào qua cổng 8080 và cho tích hợp.
Đổi mật khẩu trong WebUI hoặc bằng dịch vụ `zalo_call.set_app_password` thì giá trị đó được giữ, không bị tuỳ chọn ghi đè.

## Lưu ý

- Cổng **8080** để loa/camera và tích hợp gọi vào; đổi ở tab *Mạng* nếu trùng, nhớ đổi cả địa chỉ trong tích hợp.
- Dữ liệu (phiên Zalo, tin nhắn, cài đặt) nằm ở `/data` của add-on và đi theo bản sao lưu của HA.
- **Không cài đồng thời** hai bản (có và không giao diện) với cùng cổng 8080; muốn chạy cả hai thì đổi cổng một bản.
- Bản nhẹ, không giao diện: add-on **Zalo Calling (không giao diện)** cùng kho.
- Hướng dẫn đầy đủ, danh mục dịch vụ: <https://github.com/TriTue2011/Zalo-calling#readme>
