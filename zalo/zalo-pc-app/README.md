# Zalo PC-style app (Docker, Linux) — QR login + signaling

App dạng Zalo PC về cách dùng, chạy native trong Docker trên server
Linux, mở bằng trình duyệt: quét QR một lần → thấy danh bạ → bấm gọi.
Không chạy binary PC, không Wine, không QEMU.

Báo cáo đầy đủ (luồng QR, verdict, câu hỏi mở, quy trình test thật):
xem [bao-cao.md](bao-cao.md).

## Hai image: có giao diện (`:latest`) và KHÔNG giao diện (`:noui`)

Cùng một mã nguồn và một Dockerfile, hai đích build: `--target ui` (mặc định, có WebUI) và `--target noui` (xóa thư mục `static`, chỉ phục vụ API). CI đẩy cả hai
(`:latest`, `:vX.Y.Z`, `:noui`, `:vX.Y.Z-noui`). Compose: `docker-compose.yml` (có UI) và `docker-compose.noui.yml`.

**Mọi biến môi trường đều TÙY CHỌN** (xem `.env.example`; compose dùng dạng `${BIEN:-}` nên thiếu biến thì `docker compose up` không báo lỗi; biến rỗng = chưa đặt):

| Không đặt thì | Bản có UI | Bản không UI |
|---|---|---|
| `ZALO_PC_APP_USER` / `ZALO_PC_APP_PASSWORD` | tự sinh (user `admin`, mật khẩu ngẫu nhiên), in một lần trong log, lưu `/data/THONG-TIN-DANG-NHAP.txt` (0600); đổi trong WebUI | như bên cạnh; đổi bằng dịch vụ HA `zalo_call.set_app_password` hoặc `POST /api/app/password` |
| `ZALO_PC_WEBHOOK_URL` (hoặc `ZALO_PC_WEBHOOK_<MESSAGE\|GROUP_EVENT\|REACTION\|CALL>_URL`) | để trống; đặt trong WebUI, hoặc tích hợp HA tự điền | giá trị ban đầu từ biến (chỉ khi CHƯA có cấu hình, không bao giờ đè); sau đó dịch vụ HA `set_app_settings` / `POST /api/webhooks` |
| Các cài đặt khác (thiết bị, lưu trữ, proxy, bảo mật) | WebUI | dịch vụ HA `get_app_settings` / `set_app_settings`, hoặc curl `/api/settings/devices`, `/api/retention`, `/api/proxy`, `/api/security` |

Giá trị đặt trong `.env` (hoặc tùy chọn add-on) luôn thắng giá trị tự sinh; mật khẩu đổi sau đó trong WebUI/HA không bị biến môi trường đè lại.
Đăng nhập Zalo bằng QR (không UI): dịch vụ HA `zalo_call.login_qr` (mã hiện ở thực thể ảnh) hoặc `POST /api/qr/new` + `GET /api/qr/status`.
`GET /api/status` có cờ `ui` (true/false) cho biết đang chạy bản nào. Muốn tắt UI trên bản có giao diện: `ZALO_PC_UI=0` (đừng đặt `ZALO_PC_UI` rỗng trong compose).

```bash
# Ví dụ curl (bản không UI): đăng nhập app lấy cookie, rồi đọc/đặt cài đặt
curl -s -c /tmp/ck -H 'Content-Type: application/json' -d '{"username":"admin","password":"..."}' http://127.0.0.1:8080/api/app/login
curl -s -b /tmp/ck http://127.0.0.1:8080/api/webhooks
curl -s -b /tmp/ck -H 'Content-Type: application/json' -d '{"call_webhook_url":"http://ha:8123/api/webhook/<ma>"}' http://127.0.0.1:8080/api/webhooks
```

Lưu ý thật: image `:noui` KHÔNG nhẹ hơn đáng kể (đo: 815 MB cả hai, chênh ~0,7 MB) vì phần nặng là ffmpeg và Python; giá trị của nó là không mở bề mặt WebUI và cấu hình hoàn toàn bằng mã/biến.

## Đăng nhập app (user / mật khẩu) — cổng ngoài

Mở app phải đăng nhập bằng tài khoản do người quản trị cấp, rồi mới
tới bước quét mã QR Zalo (cổng trong). Trang đăng nhập ở `/login`
(kiểu framed-sheet, tiếng Việt, cùng font/chủ đề với app); sai thì
chỉ báo chung «Tên đăng nhập hoặc mật khẩu không đúng» — không lộ
user có tồn tại hay không. Nút «Đăng xuất» ở sidebar gọi
`POST /api/logout`: xóa cả phiên Zalo lẫn phiên app, rồi về `/login`.

**Đặt tài khoản lúc deploy (Portainer):** vào Stack → mục
Environment variables, thêm 2 biến rồi redeploy (không ghi mật khẩu
thật vào `docker-compose.yml` hay bất cứ file nào trong repo):

| Biến | Giá trị |
|---|---|
| `ZALO_PC_APP_USER` | tên đăng nhập, ví dụ `viet` |
| `ZALO_PC_APP_PASSWORD` | mật khẩu (plain text, chỉ nằm trong env lúc deploy) |

Cách khác: thay `ZALO_PC_APP_PASSWORD` bằng
`ZALO_PC_APP_PASSWORD_HASH` — hash đã tính sẵn, để mật khẩu không
đi qua env dạng plain text. Tính hash trên máy của bạn (mật khẩu gõ
qua `getpass`, không lưu vào shell history):

```sh
python3 -m zalo_pc_app.app_auth
# in ra: ZALO_PC_APP_PASSWORD_HASH=$pbkdf2-sha256$210000$...
```

**Cách hash/phiên hoạt động:** mật khẩu lưu dạng hash PBKDF2-HMAC-SHA256
(210.000 vòng, salt 16 byte, hash 32 byte) — xem
`zalo_pc_app/app_auth.py`. Dùng `ZALO_PC_APP_PASSWORD`: salt + hash
được lưu vào `/data/app_auth.json` (mode 0600, cùng volume với
`session.json`); đổi mật khẩu qua env thì file này được ghi đè bằng
salt/hash mới. Dùng `ZALO_PC_APP_PASSWORD_HASH`: dùng thẳng hash đó,
không ghi file. Phiên là token ngẫu nhiên (`secrets.token_urlsafe`),
lưu phía server trong bộ nhớ (mất khi restart container), hạn 8 giờ
(đổi qua `ZALO_PC_APP_SESSION_HOURS`); cookie tên `zalo_pc_app`,
HttpOnly, SameSite=Lax, Path=/ (`Secure` chỉ khi
`ZALO_PC_APP_COOKIE_SECURE=1`, tức chạy sau HTTPS). Thiếu user hoặc
thiếu cả hai biến mật khẩu thì server từ chối khởi động (exit 2, báo
rõ biến nào thiếu) — không bao giờ tự chạy không mật khẩu. Quên mật
khẩu: đặt lại 2 biến env rồi redeploy; app không có tự đặt lại mật khẩu.

**Phạm vi bảo vệ:** mọi route `/api/*` (trừ `POST /api/app/login`
và `GET /api/app/status`) trả 401 khi chưa đăng nhập app; trang
`/` chuyển về `/login` khi chưa đăng nhập; `/app.js` cũng yêu cầu
đăng nhập. Ngoại lệ duy nhất: trang `/login` và tài nguyên của nó
(`/style.css`, `/fonts/*`) — vì trang đăng nhập cần chúng để hiển thị.

## Chạy

```sh
docker compose pull && docker compose up -d                              # bản có giao diện
docker compose -f docker-compose.noui.yml pull && docker compose -f docker-compose.noui.yml up -d   # bản không giao diện
# UI: http://127.0.0.1:8080
```

Trong Home Assistant OS/Supervised dùng add-on thay cho compose (hai add-on `zalo_calling` và `zalo_calling_noui` ở gốc repo,
cài theo README gốc, mục **Cài đặt**). Add-on có giao diện hiện WebUI ở thanh bên HA qua Ingress (`ZALO_PC_INGRESS=1`).

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

## Cài đặt webhook

Sidebar → **Webhook**: 4 địa chỉ nhận sự kiện (theo đúng mẫu addon
`set_account_webhook`, thêm loại gọi mới) — tin nhắn đến, sự kiện
nhóm, cảm xúc, cuộc gọi — mỗi loại có công tắc bật/tắt riêng, nút
«Gửi thử» (báo HTTP status trả về) và nút Lưu chung. Cấu hình lưu
tại `<DATA_DIR>/webhooks.json` (mode 0600, cùng chỗ `session.json`).

- **Sự kiện gọi gửi được ngay:** mỗi lần gọi đi (đã gửi / lỗi / kết
  thúc) server POST JSON tới `call_webhook_url` — không chặn cuộc
  gọi, lỗi webhook không phá thao tác gốc.
- **Tin nhắn / nhóm / cảm xúc:** đã có cấu hình + điểm móc sẵn
  (`dispatch_message` / `dispatch_group_event` / `dispatch_reaction`
  trong `zalo_pc_app/webhooks.py`), nhưng **chưa gửi được tin thật**
  vì app PC chưa có kênh đồng bộ tin nhắn đến (O3, giai đoạn 2).
  Chi tiết định dạng payload + giới hạn: xem
  [bao-cao-webhook.md](bao-cao-webhook.md).

## Lịch sử tin nhắn 1-1 (giới hạn đã biết)

Zalo không có API HTTPS lấy lịch sử chat 1-1; client PC thật đọc từ DB local và đồng bộ từ điện thoại. App này **chỉ có tin 1-1 từ lúc bắt đầu lưu tin xuống
DB của app** (tin cũ hơn chưa có); tin đến mới vẫn hiện tức thì qua kênh đồng bộ. Nhóm lấy được lịch sử qua API. WebUI **không còn hiện dòng cảnh báo**
này trong khung chat (cho gọn); API `GET /api/thread/<id>/history` vẫn trả trường `notice` để người viết automation biết.

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

**Tất cả đều TÙY CHỌN** (xem `.env.example`; compose dùng dạng `${BIEN:-}`, biến rỗng = chưa đặt). Add-on HA không đặt biến: dùng tuỳ chọn add-on
(`username`, `password`, `webhook_url`) và entrypoint đổi chúng thành các biến dưới đây.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `ZALO_PC_APP_USER` | tự sinh `admin` | Tên đăng nhập app |
| `ZALO_PC_APP_PASSWORD` | tự sinh, ngẫu nhiên | Mật khẩu app dạng plain text lúc deploy; server hash PBKDF2 rồi lưu salt+hash vào `/data/app_auth.json` (0600). Không đặt: in một lần trong log và lưu `/data/THONG-TIN-DANG-NHAP.txt` (0600). Mật khẩu đổi sau đó trong WebUI / `zalo_call.set_app_password` được giữ, không bị biến này đè |
| `ZALO_PC_APP_PASSWORD_HASH` | (không có) | Thay cho PASSWORD: hash `$pbkdf2-sha256$...` tính bằng `python3 -m zalo_pc_app.app_auth`; ưu tiên hơn PASSWORD. Đặt hash thì KHÔNG đổi được mật khẩu từ WebUI/HA |
| `ZALO_PC_APP_SESSION_HOURS` | `8` | Hạn phiên đăng nhập app (giờ, số > 0) |
| `ZALO_PC_APP_COOKIE_SECURE` | (trống = 0) | Đặt `1` khi chạy sau HTTPS để cookie có cờ Secure |
| `ZALO_PC_APP_PIN` / `ZALO_PC_APP_PIN_HASH` / `ZALO_PC_APP_PIN_MINUTES` | (tắt) / (tắt) / `10` | Mã PIN riêng tư (4–32 ký tự, hoặc hash tính bằng `python3 -m zalo_pc_app.privacy`) và số phút không dùng thì tự khoá lại |
| `ZALO_PC_WEBHOOK_URL` | (trống) | Webhook ban đầu cho cả bốn loại; chỉ dùng khi CHƯA có cấu hình (không bao giờ đè). Từng loại: `ZALO_PC_WEBHOOK_MESSAGE_URL`, `ZALO_PC_WEBHOOK_GROUP_EVENT_URL`, `ZALO_PC_WEBHOOK_REACTION_URL`, `ZALO_PC_WEBHOOK_CALL_URL` |
| `ZALO_PC_UI` | (bật nếu có `static/`) | `0` / `false` / `no` / `off` tắt WebUI trên bản có giao diện. Image `:noui` không có thư mục `static` nên luôn không giao diện. Đừng đặt rỗng trong compose |
| `ZALO_PC_INGRESS` | (tắt) | `1` bật chế độ Ingress của HA: tin yêu cầu từ Supervisor (172.30.32.2) có `X-Ingress-Path`, không hỏi mật khẩu, viết lại đường dẫn giao diện. Add-on tự đặt; Docker thường để tắt |
| `ZALO_PC_DATA_DIR` | `./data` (image: `/data`) | Thư mục volume chứa `session.json` (mode 0600) và dữ liệu app |
| `ZALO_PC_HOST` / `ZALO_PC_PORT` | `127.0.0.1` / `8080` | Bind của app server (compose đặt `0.0.0.0` / `8080`) |
| `ZALO_PC_PARAM_CIPHER_KEY` | (trống) | Khóa mã hóa tham số API login, cấp lúc deploy, KHÔNG đưa vào repo. Không có nó, client dùng tham số trần + signkey (server chỉ chấp nhận nếu đã tắt mã hóa tham số) |
| `ZALO_PC_COOKIE_NAME` | `zpw_sek` | Tên cookie phiên gửi kèm API sau login |
| `ZALO_PC_VERSION` | (CI đặt lúc build) | Phiên bản hiển thị ở `GET /api/status`; image tự mang theo (build-arg `APP_VERSION`), không cần đặt |

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
