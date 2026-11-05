# Zalo PC-style app (Docker, Linux) — QR login + signaling

App dạng Zalo PC về cách dùng, chạy native trong Docker trên server
Linux, mở bằng trình duyệt: quét QR một lần → thấy danh bạ → bấm gọi.
Không chạy binary PC, không Wine, không QEMU.

Báo cáo đầy đủ (luồng QR, verdict, câu hỏi mở, quy trình test thật):
xem [bao-cao.md](bao-cao.md).

## Chạy

```sh
docker compose up --build
# UI: http://127.0.0.1:8080
```

Chạy trực tiếp (không Docker):

```sh
ZALO_PC_DATA_DIR=./data python3 -m zalo_pc_app.server
```

## Test offline (không cần mạng Zalo)

```sh
python3 tests/run_tests.py
```

## Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `ZALO_PC_DATA_DIR` | `./data` | Thư mục volume chứa `session.json` (mode 0600) |
| `ZALO_PC_HOST` / `ZALO_PC_PORT` | `127.0.0.1` / `8080` | Bind của app server |
| `ZALO_PC_PARAM_CIPHER_KEY` | (trống) | Khóa mã hóa tham số API login, cấp lúc deploy, KHÔNG đưa vào repo. Không có nó, client dùng tham số trần + signkey (server chỉ chấp nhận nếu đã tắt mã hóa tham số) |
| `ZALO_PC_COOKIE_NAME` | `zpw_sek` | Tên cookie phiên gửi kèm API sau login |

## Trạng thái

- Giai đoạn 1 (xong, test offline pass): trang QR, phiên bền,
  danh bạ/nhóm, gọi đi qua signaling kiểu PC.
- Giai đoạn 2 (chưa): nhận cuộc gọi đến (kênh sync WebSocket),
  tiếng trực tiếp (engine gắn qua `zalo_pc_app/engine_seam.py`),
  QR new-format (trust-device, cần WASM — cố tình chưa làm).
- Chưa kiểm bằng chạy thật: cần probe `reqqr` không tài khoản và
  quét thật bằng tài khoản phụ (xem bao-cao.md mục 6 + 9).
