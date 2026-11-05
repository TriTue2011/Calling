# Zalo PC-style app (Docker, Linux) — QR login + signaling

App dạng Zalo PC về cách dùng, chạy native trong Docker trên server
Linux, mở bằng trình duyệt: quét QR một lần → thấy danh bạ → bấm gọi.
Không chạy binary PC, không Wine, không QEMU.

Báo cáo đầy đủ (luồng QR, verdict, câu hỏi mở, quy trình test thật):
xem [bao-cao.md](bao-cao.md).

## Chạy

```sh
docker compose pull && docker compose up -d
# UI: http://127.0.0.1:8080
```

> Dùng host path làm volume (ví dụ `/opt/zalo:/data`) hay named volume
> đều không cần bước chown tay nào: entrypoint của image chown thư mục
> data về user `app` (UID 1000) khi khởi động, rồi hạ quyền và chạy
> server bằng user `app` (server không bao giờ chạy bằng root).

## Giao diện + gọi ngay trên UI

Giao diện mới (framed-sheet, font IBM Plex Sans/Mono tự host — xem
bao-cao.md 7j): sidebar trái (Danh bạ / Cuộc gọi), ô tìm kiếm, thẻ
đếm Tất cả / Bạn bè / Nhóm, danh sách thread, rail Cuộc gọi bên phải.

**Gọi ngay trên UI, không cần chờ service HA:** bấm một hàng danh bạ
(hoặc nút «Gọi») là gọi được ngay theo threadID — bạn bè đi
requestcall 11300, nhóm đi group/requestcall 12433 với partners là
thành viên nhóm. Service HA `make_call` làm sau, không chặn việc này.

**Theo dõi calling:** mục Cuộc gọi (sidebar, hoặc rail bên phải danh
bạ) hiện cuộc gọi đang diễn ra (đang đổ chuông + đồng hồ đếm thời
gian) và lịch sử các lần gọi (thời gian, đối phương, threadId, loại
Cá nhân/Nhóm, kết quả: Đang đổ chuông / Đã kết thúc / Lỗi). Lịch sử
lưu trong bộ nhớ server (tối đa 50 lần gọi gần nhất, mất khi restart
container) — xem qua `GET /api/calls` (cần đăng nhập). Không lưu bí
mật, không lưu nội dung thoại.

## Kiểm tra phiên bản đang chạy

Sau khi redeploy, mở trang app và đọc dòng "Phiên bản:" ở cuối trang
(hoặc `GET /api/status` và xem trường `version`): nó phải trùng với
commit/tag được báo cho lần sửa đó (image do CI build có sẵn commit
sha đầy đủ). Nếu không trùng, tức là image `:test` cũ vẫn đang chạy
— chạy `docker compose pull` rồi mới `docker compose up -d`.

## Log `ConnectionResetError` (không phải lỗi)

Thỉnh thoảng log có traceback `ConnectionResetError: [Errno 104]
Connection reset by peer` — đó chỉ là trình duyệt/proxy đóng kết
nối trước khi gửi request; server vẫn chạy bình thường. Từ bản
`2026-11-05-groups-zpwtype30` trở đi, server tắt tiếng đúng loại
lỗi này (mọi lỗi khác vẫn in ra như cũ).

## Log chẩn đoán danh bạ (`[contacts-shape]`)

Mỗi lần mở trang danh bạ, server in một dòng cho mỗi endpoint vào
log (stdout — xem bằng `docker logs <container>` hoặc Portainer →
Logs). Dòng này chỉ ghi DẠNG dữ liệu (kiểu, độ dài, tên key) — tuyệt
đối không ghi tên, id, số điện thoại hay nội dung, nên cứ copy
nguyên dòng gửi lại khi cần chẩn đoán:

```text
[contacts-shape] friends raw=list len=3 first_item_keys=['avatar', 'displayName', 'userId'] rows=3
[contacts-shape] groups v4 raw=dict keys=['gridVerMap', 'version'] gridVerMap len=2 rows=2
[contacts-shape] groups info raw=dict keys=['gridInfoMap', 'removedsGroup', 'unchangedsGroup'] gridInfoMap len=2 first_item_keys=['avt', 'creatorId', 'fullAvt', 'groupId', 'name', 'topMember', 'totalMember', 'type'] rows=2
```

Nếu số `rows=` khác số trên tab (hoặc khác số trên app Zalo điện
thoại cùng tài khoản), hai dòng này cho biết server thật trả về
dạng gì.

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
  danh bạ/nhóm, gọi đi qua signaling kiểu PC. Tab danh bạ hiện số
  lượng «Bạn bè (N)» / «Nhóm (M)» — số 0 nghĩa là tài khoản thật sự
  không có bạn/nhóm (xem bao-cao.md 7f).
- Giao diện mới (xem bao-cao.md 7j): gọi ngay trên UI theo threadID
  + mục theo dõi Cuộc gọi. Chưa kiểm trực quan bằng trình duyệt thật
  (VM không chạy được Chrome) — kiểm sau deploy trên server.
- Giai đoạn 2 (chưa): nhận cuộc gọi đến (kênh sync WebSocket),
  tiếng trực tiếp (engine gắn qua `zalo_pc_app/engine_seam.py`),
  QR new-format (trust-device, cần WASM — cố tình chưa làm).
- Chưa kiểm bằng chạy thật: cần probe `reqqr` không tài khoản và
  quét thật bằng tài khoản phụ (xem bao-cao.md mục 6 + 9).
