# Sửa lỗi 429 danh bạ + số thành viên nhóm hiện 0 — bản copy `zalo-pc-qr-429`

Bản copy riêng của `~/workspace/zalo-pc-qr/` (chụp lúc 17:38 05/11/2026,
bỏ `__pycache__`). Mọi sửa đổi CHỈ trong bản copy này. Không sửa workdir
gốc, không chạm `~/workspace/calling-push/`, không push, không đăng nhập
thật, không gọi thật bằng tài khoản nào (chỉ mock offline).

## 1. Lỗi 429 danh bạ — nguyên nhân gốc đã xác nhận bằng log thật

Bằng chứng (user gửi log server 17:37 +07 ngày 05/11/2026): log có **7 khối
`[contacts-shape]` GIỐNG HỆT NHAU LIÊN TIẾP** — mỗi khối đều gọi lại
friends (len=60) + groups v4 (len=6) + getmg-v2 (len=6) từ Zalo. Nghĩa là
`/api/contacts` gọi lại Zalo tươi **mỗi lần load, không có cache**, và đã
bị dội **7 lần liên tiếp** → Zalo trả 429 cho friends (banner trên UI:
«Lỗi tải danh bạ: friends: GET https://profile-wpa.zalo.me/api/social/friend/getfriends network status=429»;
danh sách vẫn hiện nhờ dữ liệu đã tải trước). Đây là nguyên nhân gốc, đã
xác nhận bằng log thật — không còn là giả thuyết.

### Sửa (server.py — `AppState.get_contacts`, cache trong bộ nhớ server)

- **TTL = 120 giây** (`CONTACTS_TTL_SECONDS`). Lý do: danh bạ đổi chậm
  theo ngày/giờ, không theo giây; 120s đủ để một phiên duyệt (chuyển tab,
  bấm xem lại, gọi xong quay về) chỉ tốn TỐI ĐA 1 lần gọi tươi, vẫn đủ mới
  khi có bạn/nhóm mới (60s vẫn dội gấp đôi khi bấm qua lại; 300s thì nhóm
  mới tạo phải chờ tới 5 phút mới thấy). User luôn có thể bấm «Tải lại»
  để lấy tươi ngay (trừ khi đang backoff).
- **Backoff sau 429: 60 giây, gấp đôi mỗi lần 429 liên tiếp, tối đa
  300 giây** (`CONTACTS_BACKOFF_BASE_SECONDS` / `..._MAX_SECONDS`). Zalo
  không công bố Retry-After cho getfriends; 60s là khoảng chờ an toàn,
  cấp số nhân ngăn bấm tải lại liên tục kéo dài cơn 429. Thành công bất
  kỳ lần nào reset backoff về 60s.
- Load thường trong TTL → trả cache, **không gọi Zalo** (1 lần tải tươi
  thay cho 7 lần dội). `?force=1` (nút «Tải lại» có chủ đích) → bỏ qua
  TTL nhưng **không bỏ qua backoff**. Trong backoff, mọi lần tải (kể cả
  force) đều không gọi Zalo.
- Gặp 429 **có cache** → trả 200 với danh bạ cũ + `source:
  "cache-after-429"`, `rate_limited: true`, `retry_after_seconds`
  (60/120/…) thay vì báo lỗi khô. Gặp 429 **không cache** → trả 429 kèm
  `retry_after_seconds` + câu tiếng Việt có thời gian chờ.
- Chỉ fetch nào **cả friends lẫn groups đều thành công** mới được cache;
  lỗi không phải 429 (vd 602) vẫn trả 502 với tên endpoint
  («friends: …» / «groups: …») và không làm bẩn cache. Friends thành
  công vẫn tiêu cờ `init=1` dù groups sau đó lỗi (giữ hành vi cũ).
- Cache theo phiên Zalo hiện tại (khóa theo `uid`): đổi phiên/đăng nhập
  mới/đăng xuất → xóa cache + backoff. Fetch chạy dưới một
  `_contacts_lock` riêng nên các load đồng thời xếp hàng sau một lần
  tải tươi thay vì mỗi load tự dội Zalo một lần.
- Log `[contacts-shape]` giữ nguyên (không thêm request, không đổi cách
  parse friends/groups); thêm dòng `[contacts-cache]` ghi marker
  `fresh` / `cache-hit age=…s` / `backoff cache-hit` / `429 at … backoff=…s`
  để chẩn đoán. Không ghi giá trị cá nhân.
- Response `/api/contacts` thêm: `cached`, `source`
  (`"fresh"|"cache"|"cache-after-429"`), `fetched_at`,
  `age_seconds`, `retry_after_seconds`, `rate_limited`. Khi 429 không
  cache: `source: "rate-limited"`.

### UI (app.html / app.js / style.css)

- Nút «Tải lại» mới ở đầu trang Danh bạ + nút «Tải lại» cũ trong hộp lỗi:
  khi đang backoff thì **khóa tạm + hiện đếm ngược** («Tải lại (42 giây)»),
  bấm cũng không gửi request (guard cả ở `disabled` lẫn handler). Hết
  backoff tự mở lại (tick 1 giây).
- Dòng trạng thái dưới tiêu đề Danh bạ (`#contacts-meta`):
  - tươi: «Vừa cập nhật lúc HH:MM:SS.»
  - cache: «Danh bạ đã lưu lúc HH:MM:SS — sẽ tải mới sau N giây (bấm
    “Tải lại” để lấy mới ngay).»
  - 429: «Zalo đang giới hạn (429) — đang hiển thị danh bạ đã lưu lúc
    HH:MM:SS, thử lại sau N giây.» (màu cảnh báo, đếm ngược từng giây).
  - 429 không cache: hộp lỗi ghi rõ lỗi + «thử lại sau N giây».
- Mọi `loadMain()` thường (chuyển tab, quay lại từ cuộc gọi, kết thúc
  gọi) đều là load thường → hưởng cache; chỉ bấm «Tải lại» mới gửi
  `?force=1`. (Nhân tiện sửa hai chỗ `onclick = loadMain` cũ: click
  event rơi vào tham số `force` thành truthy → vô tình thành tải cưỡng
  bức; giờ đều là `() => loadMain()`.)

## 2. Số thành viên nhóm hiện 0 — sai

Bằng chứng (user gửi ảnh 17:45 +07): tab Nhóm hiện đủ 6 nhóm có tên đúng
nhưng mỗi nhóm đều ghi «0 thành viên» — sai, các nhóm này có thành viên.
Bằng chứng từ log `[contacts-shape]` thật lúc 17:32: item nhóm trong
`gridInfoMap` có sẵn các trường `memberIds`, `currentMems`,
`totalMember`.

Nguyên nhân gốc: hàng nhóm đếm `len(topMember)` (`app.js` hiển thị
`r.members.length + " thành viên"`) — mà `topMember` chỉ là danh sách
thành viên HIỂN THỊ, server có thể trả rỗng (hoặc chỉ một phần) dù nhóm
đông. Live: topMember rỗng → 0 cho mọi nhóm.

### Sửa

- `contacts.py` — `_group_row` thêm `member_count`, thứ tự ưu tiên:
  1. `totalMember` (số, kể cả dạng chuỗi số) khi > 0 — tổng số thành
     viên, đáng tin nhất;
  2. `len(memberIds)` khi totalMember thiếu/bằng 0;
  3. `len(currentMems)` khi cả hai trên đều thiếu;
  4. `len(members)` từ topMember — đường lui cuối cùng.
- `members` (topMember userIds) **giữ nguyên**, CHỈ dùng cho `partners`
  khi gọi nhóm, không dùng để đếm nữa.
- `app.js` render: hiển thị `r.member_count` (fallback `members.length`
  nếu thiếu); `partners: peer.members` khi gọi nhóm không đổi.

## 3. File đã đổi (trong bản copy `~/workspace/zalo-pc-qr-429/`)

- `zalo_pc_app/server.py` — cache TTL 120s + backoff 429 (60s, gấp đôi,
  tối đa 300s) trong `AppState.get_contacts`; `/api/contacts` nhận
  `?force=1`; xóa cache khi đăng nhập mới/đăng xuất; không đụng
  `signaling.py` hay body requestcall.
- `zalo_pc_app/contacts.py` — `_group_row` thêm `member_count` qua
  `_member_count` (totalMember > memberIds > currentMems > topMember);
  không đổi cách parse friends/groups.
- `zalo_pc_app/static/app.js` — nút «Tải lại» + đếm ngược backoff, dòng
  trạng thái cache/429, hiển thị `member_count`, `loadMain(force)`.
- `zalo_pc_app/static/app.html` — nút `#btn-reload-contacts` + dòng
  `#contacts-meta`.
- `zalo_pc_app/static/style.css` — `.title-row` flex + `.contacts-meta`
  (`.warn` khi 429).
- `tests/mock_server.py` — chế độ `friends_mode/groups_mode =
  "rate429"` (HTTP 429 thật, đúng dạng log live); group mock thêm
  `memberIds`/`currentMems`; Nhom Y là ca phân biệt: topMember chỉ 1/5
  người, `totalMember` = 5.
- `tests/test_contacts_cache_429.py` (MỚI) — 9 test cache/429 qua HTTP
  API thật với MockZalo.
- `tests/test_contacts.py` — ca lỗi nhóm trong
  `test_contacts_error_attribution` dùng `?force=1` (load thường giờ
  trả cache nên không lộ lỗi groups nữa — đúng hành vi mới); cập nhật
  `_group_row` theo `member_count`; thêm
  `test_group_member_count_not_from_topmember` (topMember rỗng nhưng
  totalMember=7 → 7; totalMember thiếu → đếm memberIds; totalMember=0 →
  đếm currentMems; chuỗi số; không có gì → 0) và assert hợp đồng
  `member_count == [2, 5]`.
- `tests/test_server_smoke.py` — thích ứng với contract call_id uint32
  của agent sửa 114 (§7k, xem §5): gửi call_id số `9001`/`9002` thay
  cho `"c9"`/`"g9"`, dùng `call_id` hiệu lực server trả về cho
  `/api/call/end` và assert; thêm assert `member_count == [2, 5]` qua
  API thật.
- `tests/run_tests.py` — thêm `test_contacts_cache_429.py` vào danh sách.

## 4. Kết quả test (trong bản copy, mock offline, không đăng nhập/gọi thật)

`python3 tests/run_tests.py` → **ALL TEST SUITES PASSED, 48 dòng PASS**,
gồm:

- Cache/429 (mới, 9 test): cache-hit không gọi Zalo lần 2 trong TTL;
  force bỏ qua TTL; hết TTL gọi tươi lại; 429 có cache → trả cache +
  chờ 60s; 429 ở groups → trả cache (không trộn nửa tươi nửa cũ); 429
  không cache → 429 + chờ 60s, trong backoff không gọi Zalo thêm, hết
  backoff gọi lại được; 429 liên tiếp → chờ gấp đôi 60 → 120s; lỗi 602
  vẫn đúng endpoint + không bẩn cache; logout xóa cache + backoff.
- Số thành viên: `test_group_member_count_not_from_topmember` PASS;
  hợp đồng mock `member_count == [2, 5]` PASS; smoke test
  `member_count == [2, 5]` qua API thật PASS.
- Toàn bộ suite cũ (aes/crypto/flow/logininfo/contacts/calls/server)
  xanh, kể cả `test_server_smoke.py` sau thích ứng §5.

## 5. Lưu ý về test smoke + bản copy lệch thời gian với workdir gốc

- Lúc copy (17:38) suite trong bản copy đỏ ở `test_server_smoke.py` —
  KHÔNG phải do sửa 429: agent sửa 114 (chạy song song) đã đổi
  `server.py::_normalize_call_id` (§7k: call_id phải là số uint32;
  `"c9"`/`"g9"` không phải số → rơi về epoch seconds, hai cuộc gọi
  cùng 1 giây trùng id → assert `active.call_id == "g9"` fail). Sửa
  test cho đúng contract mới (mục 3) thay vì đụng code gọi của agent
  kia; không sửa `signaling.py` hay body requestcall.
- Workdir gốc đã đi tiếp SAU lúc copy: push sửa 114 lúc 17:48
  (commit 01f7ee7 — `_normalize_call_id` thêm guard đơn điệu
  `_LAST_CALL_ID` chống trùng id trong cùng 1 giây, `app.js` sinh
  callId số epoch seconds, thêm `tests/test_call_114.py`,
  `tests/test_flow_mock.py` đổi theo contract mới, thêm
  `bao-cao-doi-chieu-addon.md`). **Bản copy này KHÔNG có các đổi mới
  đó** — agent tích hợp phải gộp cả hai phía (xem §7), không được lấy
  bản copy này đè lên gốc.

## 6. Giới hạn còn lại

- Chưa kiểm chứng trên trình duyệt/server thật: chỉ mock offline.
  Cần kiểm live sau gộp + redeploy: tải trang 2–3 lần liên tiếp → log
  server chỉ có 1 khối `[contacts-shape]` tươi + các lần sau
  `[contacts-cache] cache-hit`; bấm «Tải lại» liên tục khi 429 → không
  thêm request Zalo; tab Nhóm hiện số thành viên đúng với Zalo trên
  điện thoại (ground truth 6 nhóm).
- TTL 120s: bạn/nhóm mới thêm trong vòng 120s chưa hiện nếu không bấm
  «Tải lại» — đánh đổi có chủ ý (mục 1).
- Backoff 60s là ước lượng (Zalo không công bố Retry-After cho
  getfriends); nếu live vẫn 429 sau 60s, backoff tự gấp đôi lên 120s,
  240s, tối đa 300s.
- `member_count` tin `totalMember` của server; nếu một nhóm nào đó
  server trả `totalMember` sai/thiếu thì rơi về đếm `memberIds` /
  `currentMems` / topMember — vẫn có thể lệch nếu cả ba đều thiếu.
  Chưa có nguồn độc lập để đối chiếu `totalMember` với số thật trên
  điện thoại ngoài mắt user.
- Cache chỉ trong bộ nhớ tiến trình: restart server là mất (tải tươi
  lại 1 lần) — đúng thiết kế, không lưu disk.
- Lỗi 429 ở endpoint khác (QR, gọi) không thuộc phạm vi sửa này.

## 7. Chỗ agent tích hợp cần chú ý khi gộp

- **Gộp 3 phía cùng sửa `server.py` / `contacts.py` / `app.js`:**
  (a) sửa 429 + số thành viên này; (b) sửa gọi 114 của agent kia
  (đã push 01f7ee7: `_normalize_call_id` + guard `_LAST_CALL_ID`,
  `protocol.py` hằng `CALL_TYPE_*`, `signaling.py` mặc định
  typeRequest 1/5, `app.js` sinh callId epoch seconds,
  `tests/test_call_114.py` + `tests/test_flow_mock.py` mới); (c) các
  phần đăng nhập app / webhook / chat cùng sửa `server.py` /
  `contacts.py` / `app.js`. **Không lấy file nào đè file nào**: giữ
  guard `_LAST_CALL_ID` + hằng `CALL_TYPE_*` của (b), giữ cache/backoff
  + `member_count` của (a); `test_flow_mock.py` và `test_call_114.py`
  của (b) phải được mang sang cùng.
- `app.js` có điểm chạm: (a) thêm `loadMain(force)` + nút tải lại +
  `member_count`; (b) đổi `startCall` sinh callId số epoch seconds.
  Hai đổi này không xung đột logic nhưng cùng sửa một file — gộp tay.
- **Vấn đề đã thấy, ngoài phạm vi bản này, cần agent gọi xem lại:**
  `app.js` `startCall` cũ dùng `String(Date.now())` làm callId cho cả
  `/api/call/end`, trong khi server (§7k) chuẩn hoá callId và trả
  `call_id` hiệu lực về — UI phải dùng id server trả về thì
  `/api/call/end` mới khớp (smoke test đã làm đúng như vậy). Nếu phía
  (b) đã sửa `app.js` sinh callId epoch seconds thì điểm này có thể đã
  xong — kiểm tra khi gộp, đừng giả định.
- Thứ tự kiểm sau gộp: chạy `tests/run_tests.py` trong bản gộp phải
  xanh hết (gồm `test_call_114.py` + `test_contacts_cache_429.py`);
  redeploy rồi kiểm live 3 điểm ở §6 (1 khối tươi + cache-hit; backoff
  không dội thêm; số thành viên nhóm khớp điện thoại).
- Không gộp phần chat/webhook/đăng nhập app vào bản này: các phần đó
  chưa xong và có thể thay đổi `server.py` `/api/contacts` (vd thêm
  trường) — nếu chúng thêm field vào response contacts thì giữ nguyên
  các field cache (`cached`, `source`, `fetched_at`, `age_seconds`,
  `retry_after_seconds`, `rate_limited`) và `member_count`.
