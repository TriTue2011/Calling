# Sửa nháy trang QR + load lại chậm — bản copy `zalo-pc-qr-view`

Bản copy riêng của `~/workspace/zalo-pc-qr-429/` (bản đã có sửa 429 +
số thành viên nhóm). Mọi sửa đổi CHỈ trong bản copy này. Không sửa
`~/workspace/zalo-pc-qr/`, `~/workspace/zalo-pc-qr-429/`,
`~/workspace/calling-push/`, không push, không đăng nhập thật,
không gọi thật bằng tài khoản nào (chỉ mock offline).

## 1. Lỗi (1) — load lại trang nháy trang QR dù đã đăng nhập

Nguyên nhân gốc (đã xác nhận bằng đọc code, khớp ảnh user 17:52):
`app.html` vẽ sẵn `view-login` (trang QR) là view duy nhất hiện lúc
tải trang, `view-main` ẩn sẵn; `app.js` chỉ gọi `loadMain()` ở cuối
file, mà `loadMain()` phải `await /api/status` rồi mới quyết định
đổi view. Trong khoảng chờ đó trình duyệt đã vẽ trang QR — dù phiên
vẫn còn. Sidebar `#who` mặc định cũng ghi sẵn «Chưa đăng nhập».

### Sửa (app.html / app.js / style.css)

- `app.html`: thêm `view-loading` — view DUY NHẤT hiện lúc tải trang,
  chỉ ghi «Đang mở Zalo PC… / Đang kiểm tra phiên đăng nhập…»
  (trung tính: không có mã QR, không khẳng định chưa đăng nhập).
  `view-login` thêm `style="display:none"` (ẩn sẵn); `#who` mặc định
  thành «Đang kiểm tra…».
- `app.js`: `VIEWS` thêm `"view-loading"`; `show()` ẩn ô tìm kiếm cả
  ở `view-loading`. Boot: `show("view-loading"); loadMain();` —
  view được quyết định theo phiên TRƯỚC khi vẽ view chính.
  `loadMain()` chỉ `show("view-login")` khi `/api/status` trả
  `login:false` (đã chứng minh chưa đăng nhập); đã đăng nhập thì
  sau khi tải danh bạ mới `show("view-main")`. Nếu `/api/status`
  lỗi mạng thì ở lại `view-loading` với câu «Không kết nối được máy
  chủ. Thử tải lại trang.» — cũng không hiện trang QR.

### Sơ đồ luồng load

```
tải trang → [view-loading: "Đang kiểm tra phiên…"] (view duy nhất hiện)
    │  GET /api/status
    ├─ lỗi mạng ──────────────→ ở lại view-loading + câu báo lỗi
    ├─ login:false ───────────→ view-login (trang QR) — đường duy nhất tới QR
    └─ login:true ────────────→ GET /api/contacts (+ /api/calls)
                                ├─ có cache/stale → hiện danh bạ NGAY
                                └─ chưa có cache → chờ tươi (xem §2)
                                → view-main (danh bạ)
```

## 2. Lỗi (2) — tải danh bạ sau refresh CHẬM (stale-while-revalidate)

Nguyên nhân gốc: bản 429 đã cache trong TTL, nhưng hết TTL là
`/api/contacts` lại gọi tươi lên Zalo và BẮT TRÌNH DUYỆT CHỜ
(Zalo chậm/429 → trang treo lâu). Log thật 17:53 ghi thêm 8 khối
`[contacts-shape]` giống hệt nhau — dội contacts vẫn tiếp diễn.

### Sửa (server.py — `AppState.get_contacts` + UI)

- Hết TTL nhưng CÓ cache + không force + không backoff → trả cache
  cũ NGAY (`source: "stale"`, `stale: true`, `cached: true`) và làm
  mới nền trong một thread daemon. Lần load sau thấy dữ liệu mới.
- Chỉ khi hoàn toàn CHƯA có cache mới chờ gọi tươi (đồng bộ như cũ).
- `?force=1` (nút «Tải lại» có chủ đích) vẫn gọi tươi đồng bộ,
  nhưng vẫn tôn trọng backoff 429 như cũ.
- Đang backoff 429 → trả `cache-after-429` như cũ, KHÔNG làm mới
  nền (không gọi Zalo thêm trong backoff).
- Làm mới nền dính 429 → chỉ đặt backoff (gấp đôi như cũ), cache cũ
  còn nguyên; lần load sau trả `cache-after-429`.
- Làm mới nền dính lỗi khác (vd 602) → không bẩn cache (như cũ).
- HAI KHÓA (sửa trong lúc test — lỗi thật do test đồng thời bắt
  được): `_contacts_lock` chỉ giữ trạng thái trong bộ nhớ
  (cache/backoff/cờ refreshing/init) trong các đoạn ngắn;
  `_contacts_fetch_lock` mới xâu chuỗi các lần gọi Zalo tươi.
  Trước đó một khóa giữ suốt lần fetch khiến các load stale đồng
  thời phải xếp hàng sau lần làm mới nền thay vì trả stale ngay.
  Phần fetch tách thành `_contacts_do_fetch` (gọi Zalo, không giữ
  khóa nào) + `_contacts_apply_fetch_result_locked` (ghi cache /
  đặt backoff dưới khóa trạng thái) + `_contacts_serve_from_state_locked`
  (backoff / cache tươi / stale + khởi động làm mới nền) — dùng
  chung cho foreground và background. Tải tươi vẫn tiêu cờ `init=1`
  sau khi friends thành công (giữ hành vi cũ).
- Chống dội: cờ `_contacts_refreshing` + token — nhiều load stale
  cùng lúc chỉ chia nhau MỘT lần làm mới nền. Thread nền kiểm tra
  lại trạng thái sau khi lấy được khóa fetch (backoff vừa đặt /
  cache vừa tươi thì thôi không gọi nữa).
- An toàn phiên: kết quả nền chỉ ghi cache khi `STATE.session`
  vẫn là cùng uid; đăng xuất / đăng nhập mới trong lúc nền đang
  chạy thì kết quả bị bỏ, không hồi sinh cache phiên cũ.
- UI (`app.js`): dữ liệu stale thì render danh bạ cũ ngay, dòng
  meta ghi «Danh bạ đã lưu lúc HH:MM:SS — đang tải bản mới…» và
  hẹn `loadMain()` lại sau 3 giây (`scheduleStaleRefresh`, hủy
  mỗi lần `loadMain()` chạy lại) để lấy bản mới. Không hẹn khi dữ
  liệu đã tươi / còn trong TTL.

### Khi nào trả gì (GET /api/contacts thường, không force)

| Trạng thái | Trả về | Gọi Zalo? |
|---|---|---|
| Cache còn trong TTL 120s | `cache` ngay | Không |
| Cache hết TTL, có cache, không backoff | `stale` ngay + làm mới nền | Có, ở nền |
| Chưa có cache | Chờ tươi → `fresh` | Có, đồng bộ |
| Đang backoff 429, có cache | `cache-after-429` + chờ | Không |
| Đang backoff 429, chưa có cache | 429 + `retry_after_seconds` | Không |
| `?force=1` | Chờ tươi → `fresh` (trừ khi backoff) | Có, đồng bộ |

## 3. File đã đổi / thêm (trong bản copy)

- `zalo_pc_app/server.py` — SWR + hai khóa (xem §2); không đụng
  `signaling.py` hay body requestcall; `VERSION` không đổi.
- `zalo_pc_app/static/app.js` — `view-loading` trong `VIEWS`,
  boot `show("view-loading")` rồi mới `loadMain()`, `loadMain()`
  try/catch `/api/status` (lỗi mạng → ở lại loading, không hiện
  QR), `updateContactsMeta` nhánh `stale`, `scheduleStaleRefresh`
  / `clearStaleRefresh` (tải lại sau 3 giây khi stale).
- `zalo_pc_app/static/app.html` — section `view-loading` hiện sẵn,
  `view-login` ẩn sẵn, `#who` mặc định «Đang kiểm tra…».
- `zalo_pc_app/static/style.css` — `.loading-wrap` / `.lede`.
- `tests/mock_server.py` — `slow_seconds`: làm Zalo trả chậm trên
  3 endpoint danh bạ (để pin «stale trả ngay»), mặc định 0.
- `tests/test_contacts_stale_swr.py` (MỚI) — 7 test SWR qua HTTP
  API thật với MockZalo.
- `tests/test_contacts_cache_429.py` — `test_ttl_expiry_refetches`
  đổi theo contract mới (hết TTL → stale ngay + nền làm mới, thay
  vì fresh đồng bộ); thêm chú thích float-vs-int ở
  `fetched_at` (payload là int, cache lưu float).
- `tests/view_decision_harness.js` (MỚI) — chạy app.js THẬT với
  DOM + fetch giả lập (node, không cần trình duyệt), ghi lại chuỗi
  view hiện theo thời gian, 3 kịch bản.
- `tests/test_view_decision.py` (MỚI) — 5 test: 2 assert tĩnh trên
  app.html/app.js + 3 kịch bản qua harness.
- `tests/run_tests.py` — thêm 2 file test mới vào danh sách.

## 4. Kết quả test (trong bản copy, mock offline)

`python3 tests/run_tests.py` → **ALL TEST SUITES PASSED** (10 file,
exit 0), gồm:

- SWR (mới, 7 test): stale trả ngay khi Zalo chậm 2s/endpoint
  (< 1,5s thay vì ~6s chờ tươi), rồi load sau thấy cache mới;
  chưa có cache thì vẫn chờ tươi; force đồng bộ; hết TTL trong
  backoff thì `cache-after-429`, không làm mới nền; nền dính 429
  thì giữ cache + đặt backoff; đăng xuất giữa lúc nền chạy thì
  cache không hồi sinh; 3 load stale đồng thời chỉ gây 1 lần làm
  mới nền.
- View (mới, 5 test): đã đăng nhập → chuỗi
  `view-loading -> view-main`, không qua QR; chưa đăng nhập →
  `view-loading -> view-login`, không gọi `/api/contacts`;
  stale → `view-loading -> view-main` + tự tải lại lần 2.
- Toàn bộ suite cũ xanh (aes/crypto/flow/logininfo/contacts/
  cache-429/calls/server-smoke), kể cả test 429 cũ sau khi đổi
  contract TTL.

## 5. Giới hạn còn lại

- Chưa kiểm chứng trên trình duyệt/server thật: chỉ mock offline.
  Cần kiểm live sau gộp + redeploy: làm mới trang khi đã đăng nhập
  → không thấy trang QR dù chỉ một khung hình, danh bạ cũ hiện
  ngay rồi tự mới sau ~3 giây; làm mới khi chưa đăng nhập → vẫn
  thấy trang QR bình thường.
- Lần tải ĐẦU TIÊN sau khi đăng nhập (chưa có cache) vẫn phải chờ
  gọi tươi — SWR không làm nhanh được ca này (không có gì để trả
  ngay); chỉ các lần sau mới nhanh.
- `?force=1` khi đang có lần làm mới nền chạy: lần force chờ khóa
  fetch rồi gọi tươi thêm một lần nữa (tốn 1 cuộc gọi thừa). Hiếm
  (chỉ khi user bấm «Tải lại» đúng lúc nền đang chạy) — chấp nhận.
- Meta «đang tải bản mới…» dựa vào lần hẹn 3 giây của UI, không
  phải push từ server: nếu nền thất bại (429) thì lần tải lại sau
  3 giây trả `cache-after-429` + đếm ngược backoff (đúng), nhưng
  UI không phân biệt được «nền đang chạy» với «nền vừa xong» ngoài
  cờ `stale` ở response.
- Cache vẫn chỉ trong bộ nhớ tiến trình: restart server là mất
  (tải tươi lại 1 lần) — như bản 429.

## 6. Chỗ agent tích hợp cần chú ý khi gộp

- **Bản copy này dựa trên bản 429 — khi gộp lấy phía
  `server.py` / `contacts.py` / `app.js` từ bản này làm phía
  «429+view», đừng gộp đè bản 429 cũ.** Nhưng KHÔNG được lấy
  nguyên bản copy này đè lên gốc: gốc đã đi tiếp sau lúc copy
  bản 429 (17:38).
- **Gốc đã có thêm 2 phía gọi điện sau lúc copy:** sửa 114
  (commit 01f7ee7: `_normalize_call_id` + guard đơn điệu,
  `protocol.py` hằng `CALL_TYPE_*`, `app.js` sinh callId số,
  `tests/test_call_114.py`) và bước request sau requestcall
  11301/12434 (commit 4f40c7e lúc 18:02: `media_endpoints.py`
  mới, call log thêm `request_sent`, `tests/test_call_11301.py`,
  version `2026-11-05-call-11301`). Bản copy này KHÔNG có cả hai.
  Gộp cần 3 phía: (a) 429+view này (`server.py` phần contacts +
  `app.js` phần view/stale + `app.html`/`style.css` + test SWR/
  view); (b) 114; (c) 11301. Điểm chạm: `server.py`
  (`_contacts_*` của phía này vs `_normalize_call_id` /
  `request_call` + bước request của phía gọi — khác hàm, ít
  xung đột trực tiếp) và `app.js` (phía này đổi đầu file +
  `loadMain` + meta; phía gọi đổi `startCall`/callId — khác vùng).
- **Contract mới phía này mà phía gộp phải giữ:** response
  `/api/contacts` thêm `source: "stale"` + `stale: true/false`
  (mọi response đều có `stale`, mặc định false); `test_429`
  cũ đã đổi theo contract này (hết TTL → stale, không còn fresh
  đồng bộ). `VERSION` trong bản copy chưa đổi — agent tích hợp
  đặt version mới khi gộp.
- Không có thay đổi nào ở `signaling.py`, body requestcall,
  QR login, hay `contacts.py` (số thành viên nhóm của bản 429
  giữ nguyên).
