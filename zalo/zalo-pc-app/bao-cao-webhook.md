# Cài đặt webhook cho app Zalo kiểu PC — báo cáo

- Bản copy làm việc: `~/workspace/zalo-pc-qr-webhook/` (copy từ
  `~/workspace/zalo-pc-qr/` lúc 17:38 +07, bỏ `__pycache__`).
  **Không sửa workdir gốc, không sửa `~/workspace/calling-push/`,
  không push.**
- Phiên bản: `2026-11-05-webhook` (footer app / `GET /api/status`).
- Mô hình theo đúng addon: `~/workspace/zalo-addon-doc/bao-cao-addon-96-services.md`
  §4 + `~/workspace/has-addons/zalo_bot/services/webhookService.js` +
  `eventListeners.js` (chỉ đọc). UI theo hướng framed-sheet sẵn có
  (`design-taste-frontend` references/app-screens.md §8: label trên
  field, input 40px, một nút primary duy nhất là «Lưu cài đặt»,
  toggle phải, card 1px border không shadow).
- Đồng bộ giữa chừng (17:5x +07): bản gốc đã được agent sửa lỗi 114
  cập nhật SAU lúc copy (thêm `_normalize_call_id` + guard đơn điệu,
  `test_call_114.py`, mock kiểm contract requestcall, smoke test
  mới). Đã đồng bộ các file do agent 114 sở hữu sang bản copy
  (`server.py`, `__init__.py`, `tests/mock_server.py`,
  `tests/test_contacts.py`, `tests/test_flow_mock.py`,
  `tests/test_server_smoke.py`, `tests/test_call_114.py`,
  `bao-cao.md`, `bao-cao-doi-chieu-addon.md`) rồi gắn lại móc webhook
  lên `server.py` mới — **không đụng `signaling.py` / `protocol.py` /
  body requestcall**. Xem mục «Tích hợp» bên dưới.

## 1. File đã đổi / thêm (đường dẫn đầy đủ trong bản copy)

| File | Thay đổi |
|---|---|
| `~/workspace/zalo-pc-qr-webhook/zalo_pc_app/webhooks.py` | **MỚI** — toàn bộ logic webhook: store, validate, payload builders, dispatcher, hook points |
| `~/workspace/zalo-pc-qr-webhook/zalo_pc_app/server.py` | Chỉ thêm móc nối (ghi `WEBHOOK HOOK (webhooks.py)`): import, `AppState.webhook_store` + `webhook_dispatcher`, `GET /api/webhooks`, `POST /api/webhooks`, `POST /api/webhooks/test`, dispatch `call.sent` / `call.error` / `call.ended` trong `/api/call/request` và `/api/call/end` |
| `~/workspace/zalo-pc-qr-webhook/zalo_pc_app/static/app.html` | Nav «Webhook» + view `#view-webhooks` (4 card: tin nhắn / nhóm / cảm xúc / gọi) |
| `~/workspace/zalo-pc-qr-webhook/zalo_pc_app/static/app.js` | `view-webhooks` vào `VIEWS`, nav active, ẩn ô tìm kiếm ngoài Danh bạ/Cuộc gọi, `loadWebhooks` / `saveWebhooks` / `testWebhook` |
| `~/workspace/zalo-pc-qr-webhook/zalo_pc_app/static/style.css` | `.webhook-card`, `.field-label`, `.field-input`, `.toggle`, `.note-box`, `.saved-box`, `.test-result` (dùng token sẵn có) |
| `~/workspace/zalo-pc-qr-webhook/tests/test_webhooks.py` | **MỚI** — 15 test (14 unit/mock + 1 e2e qua server thật + mock Zalo) |
| `~/workspace/zalo-pc-qr-webhook/tests/run_tests.py` | Thêm `test_call_114.py` (đồng bộ từ gốc) + `test_webhooks.py` |
| `~/workspace/zalo-pc-qr-webhook/zalo_pc_app/__init__.py` | `VERSION = "2026-11-05-webhook"` |
| `~/workspace/zalo-pc-qr-webhook/.gitignore` | Thêm `webhooks.json` |
| `~/workspace/zalo-pc-qr-webhook/README.md` | Thêm mục «Cài đặt webhook» |
| `~/workspace/zalo-pc-qr-webhook/bao-cao-webhook.md` | File này |

## 2. Lưu trữ cấu hình

- **Đường dẫn file lưu cấu hình:** `<DATA_DIR>/webhooks.json`
  (mặc định `./data/webhooks.json`, cùng chỗ `session.json`;
  `DATA_DIR` theo biến môi trường `ZALO_PC_DATA_DIR`).
- **Mode 0600**, ghi nguyên tử (file `.tmp` + `os.replace`, cùng mẫu
  `session.py`). Thư mục `data/` đã nằm trong `.gitignore`; thêm
  dòng `webhooks.json` riêng để chắc chắn khi `DATA_DIR` trỏ đi chỗ
  khác. Không có file mẫu nào chứa URL thật trong repo.
- **Nội dung file** (mặc định khi chưa lưu gì — toàn URL rỗng, toàn
  công tắc bật):
  ```json
  {
    "message_webhook_url": "",
    "message_enabled": true,
    "group_event_webhook_url": "",
    "group_event_enabled": true,
    "reaction_webhook_url": "",
    "reaction_enabled": true,
    "call_webhook_url": "",
    "call_enabled": true
  }
  ```
- Validate lúc lưu: chỉ nhận chuỗi rỗng hoặc URL `http://` /
  `https://` ≤ 2048 ký tự; sai → API trả 400, không ghi gì.
  Key lạ trong body bị bỏ. File hỏng JSON → đọc ra mặc định (trang
  Cài đặt vẫn mở được).

## 3. API

Tất cả cần đăng nhập — dùng chung `_require_login()` với
`/api/calls` (đã có sẵn trong `server.py`; **không** để route mở).
Chưa đăng nhập → `401 {"error": "chua_dang_nhap"}` (đã kiểm live).

| Route | Mô tả |
|---|---|
| `GET /api/webhooks` | Trả toàn bộ cấu hình hiện tại |
| `POST /api/webhooks` | Lưu cấu hình (body = object như mục 2). Trả `{"ok": true, "config": {...}}`; URL sai → 400 |
| `POST /api/webhooks/test` | Body `{"kind": "message" \| "group_event" \| "reaction" \| "call"}`. Gửi **đồng bộ** một payload thử tới URL của loại đó và trả `{"dispatched": bool, "status": int\|null, "error": str, "reason": "sent"\|"no_url"\|"disabled"\|"http_error"\|"error"}` để UI hiện HTTP status |

## 4. Định dạng payload JSON từng loại sự kiện

Envelope chung mọi loại: `{"event": <family>, "type": <family>.<name>,
"account_id": <uid tài khoản PC>, "sent_at": <unix seconds>, ...}`.
POST `Content-Type: application/json`, `User-Agent:
zalo-pc-qr-webhook/1.0`, timeout **5 giây** (ngắn hơn addon 10 s),
payload tối đa 2 MB (cùng mức addon). Tin **tự gửi (`is_self`)
mặc định KHÔNG đẩy** (chống lặp như addon); chỉ đẩy khi kèm
`self_reply=true` (lệnh từ khóa của chủ).

### 4.1 call — GỬI ĐƯỢC NGAY (đã nối vào `/api/call/request`, `/api/call/end`)

`call_id` là id **hiệu lực sau chuẩn hoá của agent 114** (số uint32;
chuỗi không phải số bị đổi thành epoch seconds) — webhook nhận đúng
id mà Calls UI đang hiện, không phải id thô user gõ.

```json
// type: call.sent | call.error | call.ended
{"event": "call", "type": "call.sent", "account_id": "10001",
 "sent_at": 1762345678, "call_id": "123456789", "thread_id": "20001",
 "peer": "Ban A", "call_type": "user", "status": "sent",
 "started_at": 1762345678, "ended_at": null}
// call.error thêm: "detail": "<lỗi, vd inner 114...>"
// call.ended: "status": "ended", "ended_at": <unix seconds>
```

- `call.sent`: requestcall được server chấp nhận (ghi log xong).
- `call.error`: requestcall lỗi (vd timeout, inner 114) — `detail`
  là đúng chuỗi lỗi Calls UI đang hiện, không chứa bí mật.
- `call.ended`: `/api/call/end` thành công và có bản ghi live khớp
  `call_id` (id lạ không có bản ghi → không gửi gì).

### 4.2 message — CẤU HÌNH + MÓC SẴN, CHƯA CÓ NGUỒN SỰ KIỆN (xem §6)

```json
// type: message.received
{"event": "message", "type": "message.received", "account_id": "10001",
 "sent_at": 1762345678, "thread_id": "20001", "thread_type": 0,
 "sender_id": "20002", "message_id": "m1",
 "content": "<nội dung tin>", "is_self": false}
// tin tự gửi có từ khóa (hiếm): thêm "self_reply": true, "tag_khop": "@ha"
```

`content` **có** trong payload — bên nhận là webhook của chính user
(HA/n8n), đúng như addon forward nguyên object `msg`. Nội dung tin
không bao giờ ghi vào log server (log chỉ có đích + status, xem §5).

### 4.3 group_event — CẤU HÌNH + MÓC SẴN, CHƯA CÓ NGUỒN SỰ KIỆN

```json
// type: group_event.<loại trong dữ liệu, vd group_event.join>
//       (không rõ loại: group_event.received)
{"event": "group_event", "type": "group_event.join", "account_id": "10001",
 "sent_at": 1762345678, "thread_id": "30001",
 "group_event": {<toàn bộ dict sự kiện gốc, giữ nguyên>}
}
```

### 4.4 reaction — CẤU HÌNH + MÓC SẴN, CHƯA CÓ NGUỒN SỰ KIỆN

```json
// type: reaction.received
{"event": "reaction", "type": "reaction.received", "account_id": "10001",
 "sent_at": 1762345678, "thread_id": "20001", "thread_type": 0,
 "message_id": "m1", "sender_id": "20002", "icon": "heart"}
```

### 4.5 Payload «Gửi thử» (nút «Gửi thử» từng loại)

Envelope như sự kiện thật của loại đó + `"test": true`, không chứa
dữ liệu thật (`call_id: "test"`, tin nhắn `"Tin nhan thu"`,
reaction `icon: "like"`, `group_event: {}`). Ví dụ loại gọi:
`{"event": "call", "type": "call.test", "test": true, "message":
"Gui thu webhook tu Zalo PC", "call_id": "test", "thread_id": "",
"peer": "", "call_type": "user", "status": "sent", ...}`.

**Khác addon ở đâu (để bên nhận khỏi hiểu lầm):** payload ở đây là
shape riêng của app PC (đã ghi trong `webhooks.py`), KHÔNG phải
object zca-js thô mà addon forward (`{...msg, _accountId}`).
`account_id` ở đây = uid PC (vai trò tương đương `_accountId` của
addon). Tên field URL giữ nguyên 3 tên addon
(`message_webhook_url`, `group_event_webhook_url`,
`reaction_webhook_url`) + thêm `call_webhook_url` mới (addon không
có vì zca-js không gọi được).

## 5. Hành vi gửi + an toàn

- Dispatch sự kiện gọi là **fire-and-forget** (daemon thread):
  không chặn response của `/api/call/request` / `/api/call/end`.
- Không gửi khi: loại đang tắt (`reason: disabled`) hoặc chưa có URL
  (`reason: no_url`). Tắt công tắc giữ nguyên URL để bật lại sau.
- Webhook lỗi (timeout 5 s, refused, HTTP 4xx/5xx) → ghi nhận trong
  bộ nhớ (`dispatcher.last_deliveries()`, tối đa 20 lần, chỉ có
  kind/type/status/error — không chứa payload), **không ném lỗi ra
  ngoài, không phá thao tác gốc** (đã test: endpoint chết → cuộc gọi
  vẫn trả `ok: true`).
- Log server mỗi lần gửi chỉ có: `[webhook] kind=... type=...
  dest=<scheme://host/path, query đã lược> status=...` — query bị
  lược để token trong URL không lọt vào log; không log nội dung
  payload (không tên, không nội dung tin).

## 6. GIỚI HẠN — NÓI RÕ

- **Webhook tin nhắn đến / nhóm / reaction CHƯA chạy end-to-end.**
  Đã có: trang Cài đặt lưu được 3 URL đó, nút «Gửi thử» gửi được
  payload mẫu tới URL đã cấu hình, hàm `dispatch_message()` /
  `dispatch_group_event()` / `dispatch_reaction()` trong
  `webhooks.py` đã sẵn. **Chưa có:** nguồn sự kiện đến. App PC hiện
  không có kênh đồng bộ tin nhắn (kênh sync O3 / WebSocket, giai
  đoạn 2, chưa làm) nên không có process nào gọi 3 hàm đó — không
  có tin nhắn/nhóm/reaction thật nào được đẩy đi. Đừng claim 3 loại
  này đã chạy khi chưa có O3.
- **Riêng sự kiện gọi đi bắn được ngay**, vì chính app là nguồn:
  mọi lần bấm gọi trên UI đều qua `/api/call/request` / `/api/call/end`
  đã nối webhook. Đã kiểm bằng mock endpoint thật (xem §7).
- Chưa có: gọi đến (O3), chữ ký/HMAC xác thực webhook, retry khi
  webhook lỗi (chỉ gửi 1 lần), giao diện xem lịch sử gửi (chỉ có
  `last_deliveries()` trong bộ nhớ, chưa lộ ra API).

## 7. Kết quả test

`python3 tests/run_tests.py` trong bản copy: **ALL TEST SUITES
PASSED — 9/9 suite** (test_aes, test_crypto, test_flow_mock,
test_logininfo, test_contacts, test_calls, test_call_114 7/7,
test_webhooks 15/15, test_server_smoke).

`tests/test_webhooks.py` (15 test, không đăng nhập thật, không gọi
thật, không URL thật — endpoint mock duy nhất là
`http://127.0.0.1:<cổng tạm>` + `https://example.invalid/...` làm
dữ liệu giả):
- Mặc định / lưu-đọc round-trip / mode 0600 / key lạ bị bỏ.
- URL sai bị từ chối (`ftp:`, `javascript:`, không scheme, quá dài,
  không phải chuỗi) và không ghi đè cấu hình cũ; file hỏng → mặc
  định.
- Shape payload call (sent/error/ended, `detail` chỉ ở error),
  message, group_event, reaction.
- Dispatch `call.sent` tới mock HTTP endpoint thật, nhận đúng
  payload + `Content-Type: application/json`.
- Tắt công tắc / URL rỗng → không gửi gì.
- Endpoint trả 500 → `dispatched: false, status: 500`, không raise;
  endpoint chết (connection refused) → `reason: error`, không raise;
  dispatch async cũng nuốt lỗi.
- Tin tự gửi không đẩy; chỉ đẩy khi `self_reply=true`.
- Payload «Gửi thử» đúng shape; `safe_url_for_log` lược query;
  `last_deliveries()` không chứa nội dung tin.
- **E2E qua server thật + mock Zalo** (`test_api_webhooks_e2e`):
  chưa đăng nhập → `GET /api/webhooks` 401; đăng nhập mock QR xong
  → GET mặc định, POST URL sai → 400, POST lưu → 200 + file
  `webhooks.json` mode 0600, «Gửi thử» → `dispatched: true,
  status: 200` + mock endpoint nhận `call.test`, gọi thật qua mock
  (`/api/call/request` call_id số hợp lệ) → `ok: true` + mock
  endpoint nhận `call.sent` đúng `call_id`/`thread_id`, đổi webhook
  sang endpoint chết → cuộc gọi vẫn `ok: true`.

Kiểm thêm ngoài suite: `node --check` app.js OK; `py_compile`
webhooks/server OK; chạy server thật với data rỗng: trang chủ chứa
`#view-webhooks` + `#nav-webhooks`, `GET /api/webhooks` khi chưa
đăng nhập → 401, footer version `2026-11-05-webhook`. Quét bí mật:
không URL webhook thật nào trong code/test (chỉ `127.0.0.1` mock và
`example.invalid` giả; 2 dòng `http://` trong `webhooks.py` là chữ
trong comment/thông báo lỗi).

## 8. Tích hợp — chỗ agent tích hợp cần chú ý khi gộp

Móc nối webhook trong `server.py` được đánh dấu
`# WEBHOOK HOOK (webhooks.py)` ở 7 chỗ (import, `AppState.__init__`,
`GET /api/webhooks`, 3 điểm dispatch trong `/api/call/request` +
`/api/call/end`, `POST /api/webhooks` + `POST /api/webhooks/test`).
Khi gộp với các phần khác cùng sửa `server.py`:

1. **Đăng nhập app (agent làm song song):** route webhook dùng
   chung `_require_login()` đã có — nếu agent đăng nhập đổi cơ chế
   kiểm tra phiên (vd token/cookie app), chỉ cần `_require_login()`
   vẫn giữ nguyên tên + ngữ nghĩa (trả `None` khi chưa đăng nhập)
   là route webhook tự theo. **Không mở route webhook khi chưa có
   auth** — URL webhook là bí mật của user (có thể chứa token).
   Không có gì trong code webhook tự tạo auth riêng.
2. **Chat (agent làm song song):** khi chat/sync có dữ liệu đến, gọi
   đúng 1 dòng mỗi loại trong `webhooks.py`, với `account_id` =
   `session uid`:
   `webhooks.dispatch_message(STATE.webhook_dispatcher, msg, uid)`,
   `dispatch_group_event(...)`, `dispatch_reaction(...)` — `msg`
   theo shape §4.2 (có `threadId`, `type`, `uidFrom`, `data.content`,
   `isSelf`). Tin tự gửi đã được lọc sẵn trong
   `dispatch_message`. Khi đó §6 hết hiệu lực cho loại đó — cập
   nhật báo cáo này, đừng để câu «chưa chạy» cũ.
3. **Sửa 429 (cache contacts):** không liên quan webhook — webhook
   không gọi Zalo, không chạm `/api/contacts`. Chỉ lưu ý: đừng cache
   hay chia sẻ `STATE.webhook_dispatcher` qua tiến trình khác; nó
   giữ `WebhookStore` đọc file mỗi lần gửi nên cấu hình mới lưu là
   có hiệu lực ngay, không cần restart.
4. **Sửa lỗi gọi 114 (đã đồng bộ ở trên):** webhook lấy `call_id`
   **hiệu lực sau chuẩn hoá** từ giá trị `record_start` /
   `record_error` trả về — nếu agent 114 đổi tiếp cách chuẩn hoá,
   webhook vẫn đúng vì nó không tự tính `call_id`. Nhưng nếu họ đổi
   `CallLog.record_*` không trả về entry nữa thì móc dispatch sẽ
   nhận `None` → `dispatch_call_event` bỏ qua lặng lẽ (không crash,
   nhưng webhook gọi sẽ im lặng — kiểm tra lại bằng
   `test_api_webhooks_e2e`).
5. **Thứ tự gộp gợi ý:** lấy `server.py` mới nhất của gốc (đã có
   114-fix + guard) làm nền, áp lại đúng 7 móc webhook (đều có
   marker), giữ nguyên `zalo_pc_app/webhooks.py`,
   `static/{app.html,app.js,style.css}` (phần webhook),
   `tests/test_webhooks.py`, `VERSION = "2026-11-05-webhook"`.
   **Không gộp file `data/webhooks.json`** (nếu có lọt vào đâu đó)
   — cấu hình là dữ liệu runtime của từng máy, không phải code.
6. **Xung đột đã biết cần tránh:** bản copy được đồng bộ từ gốc lúc
   ~17:5x +07; nếu gốc tiếp tục đổi `server.py` / `test_server_smoke.py`
   / `app.js` sau thời điểm đó (vd agent sửa 429, agent chat), phải
   diff lại trước khi gộp — đừng gộp mù. **Ghi nhận lúc kết thúc
   (~18:0x +07): gốc đã đi tiếp — agent điều tra luồng gọi thêm
   bước `request` 11301 / `group/request` 12434
   (`media_endpoints.py` mới, `vc_request_group`,
   `signaling.send_request_group`). Bản copy này KHÔNG có phần đó
   (đúng phạm vi: không đụng signaling); khi gộp, lấy gốc mới nhất
   làm nền rồi áp lại 7 móc webhook — webhook không chạm các hàm
   đó nên không xung đột trực tiếp, chỉ cần kiểm lại
   `test_api_webhooks_e2e` sau gộp.
