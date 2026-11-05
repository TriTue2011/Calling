# Đăng nhập Zalo kiểu PC bằng QR cho client native Linux — báo cáo

Ngày: 05/11/2026. Nguồn phân tích: Zalo PC 26.11.10 (file cài
`ZaloSetup-26.11.10.exe`, asar đã giải tại
`~/workspace/zalo-pc-reverse/extracted/asar/`).
Phương pháp: đọc code tĩnh, KHÔNG chạy app, KHÔNG đăng nhập thật bằng
bất kỳ tài khoản nào. Mọi kết luận về hành vi server đều là suy luận từ
code client, chưa kiểm bằng chạy thật (xem mục 8).

## Verdict: GO (có điều kiện) — cho giai đoạn 1

**Làm được ngay (giai đoạn 1, đã implement + test offline):**
trang QR → quét → phiên bền → danh bạ/nhóm → gọi đi qua signaling
kiểu PC. Không cần WASM, không cần binary PC, không Wine, không QEMU.

**Điều kiện GO dựa trên 2 cột trụ đã xác minh bằng code:**

1. **Đường QR old-format là đường mặc định cho client mới.**
   Client mới (chưa có auth lưu sẵn) có `serverConfig` mặc định
   `{self_g: false, qr_format_trust_device: false, logo_qr: true}` nên
   gọi `reqqr` với `self_g=0, qr_form=0` và nhận ảnh QR base64 do server
   cấp — không tạo linking state, không chạm tới WASM trust protocol.
   Các cờ trust chỉ bật khi một lần đăng nhập trước đó đã lưu
   `authentication.trusted_device` (xem mục 1, bước 0).
2. **Mọi crypto cần thiết đều tái tạo được mà không cần bí mật tài khoản:**
   - ParamCipher cho API login: AES-256-CBC, IV 0, đã map đủ công thức
     (mục 4.1). Chỉ cần thêm một khóa cố định nhúng trong app PC
     (xem quyết định bí mật ở mục 4.4 — khóa này KHÔNG có trong repo,
     cấp lúc deploy; nếu server tắt mã hóa tham số thì không cần nó).
   - Chữ ký request: MD5(salt cố định + tên API + giá trị theo thứ tự
     key) — tái tạo được.
   - AES cho API sau login (voicecall, danh bạ...): khóa `zpw_enk` do
     **server cấp theo từng phiên** qua `getLoginInfo`, không cần khóa
     nhúng nào.

**Chưa làm được trong giai đoạn 1 (giai đoạn 2, nói rõ ở mục 6):**
nhận cuộc gọi đến (cần map tiếp kênh sync WebSocket), tiếng trực tiếp
(cần engine của agent song song gắn vào seam), và đường QR new-format
(trust-device, cần WASM — cố tình từ chối thay vì làm dở).

---

## 1. Luồng QR PC từng bước (kèm chứng cứ)

### Bước 0 — Cờ serverConfig (quyết định old hay new format)

- File: `pc-dist/lazy/login-startup.*.js`, class singleton quản lý
  linking (`serverConfig`, `mergeServerConfig`, `genFirstQR`).
- Mặc định: `serverConfig = {self_g: false, qr_format_trust_device:
  false, logo_qr: true}`.
- `mergeServerConfig` chỉ đọc từ **auth đã lưu** của lần đăng nhập trước
  (`authentication.trusted_device.{self_g, qr_format_trust_device,
  logo_qr}`), gọi 2 lần lúc khởi động (lần 2 sau `getServerInfoCheck`).
  Không có lần fetch cờ nào khác từ server lúc tạo QR.
- Hệ quả: client mới tinh → old-format. Client đã từng đăng nhập và
  server từng bật trust → new-format ở lần sau.

### Bước 1 — Xin mã QR: `reqqr`

- Hàm: API client `getQRCode(deviceId, loggedUids, language, self_g,
  qr_form)` trong `pc-dist/compact-app-pc.*.js`.
- Endpoint: `GET https://wpa.zalo.me/api/login/reqqr` (mã API 11133;
  `authDomain = https://wpa.zalo.me`).
- Tham số (trước mã hóa): `language`, `client_time` (unix giây),
  `imei` = device ID, `computer_name` = hostname máy,
  `logged_uids` = các uid từng đăng nhập (để server nhận relink),
  `self_g` (mặc định 0), `qr_form` (mặc định 0).
- Gói tham số: qua `encryptParam(params, "reqqr")` nếu bật mã hóa
  (mục 4.1), nếu không thì tham số trần + `type`, `client_version`,
  `signkey`. **Không gửi `zpw_ver/zpw_type`** ở API login (chúng chỉ
  thuộc về common params của API sau login). `enk` (khóa phiên) KHÔNG
  gửi lên mạng — client giữ lại để giải mã response.
- Response `data` (parser `Qe` trong login-startup):
  `base64_qr`, `chk_wait_scan`, `chk_wait_cfirm`, `qr_retry`,
  `qr_timeout`, `token_id`, `ntk`, `qr_cnt`, `uid`, `master_id`,
  `regen_qr`.
- Hiển thị old-format: `genFirstQR` trả `data:image/png;base64,...`
  từ `base64_qr` khi `self_g` tắt; khi `self_g` bật nhưng
  `qr_format_trust_device` tắt thì tự render từ chuỗi token bằng bộ mã
  QR ZQR (ECC LOW, minVersion 9) — client tự viết dùng thư viện QR
  bất kỳ, nội dung chuỗi mới là điều quan trọng.
- Rate limit: tạo QR quá nhanh → mã `GEN_QR_EXCEED_RATE_LIMIT` kèm
  `time_left` (ms); client đếm ngược mặc định 89 giây (làm tròn lên
  bội số 5, tối thiểu 20 giây).

### Bước 2 — Chờ quét: long-poll `chk_wait_scan`

- Hàm: `getStatusQRCode(url, qrTimeout)` = `GET` URL đó, timeout =
  `qr_timeout × 1000` ms (long-poll, server giữ request tới khi có sự
  kiện hoặc hết timeout). Lặp tối đa `qr_retry` lần (hàm `ar`).
- Mã kết quả: `0` = có sự kiện (parser `je`: `avatar`, `display_name`,
  `link_data.{enc_link_data, enc_link_hmac}`); `-20` = quét lần đầu
  xong nhưng cần renew QR2 (multi-layer, thuộc trust flow);
  `-21` = lỗi relink QR2 (xóa link history theo uid, tạo QR mới);
  `18010` = user từ chối trên điện thoại.
- Old-format: `link_data` rỗng → bỏ qua bước verify, đi thẳng sang
  bước 3. `link_data` không rỗng → trust flow (giai đoạn 1 từ chối
  bằng lỗi rõ ràng `TrustFlowRequired`, không giả vờ đăng nhập được).

### Bước 3 — Chờ xác nhận: long-poll `chk_wait_cfirm`

- Cùng cơ chế long-poll/retry như bước 2.
- Khi user bấm chấp nhận trên điện thoại, server trả: `uid`, `dkey`,
  `profile.phonenum`, `needSyncMsg`/`sync_msg_info`, `cptch_cert`,
  `zpw_sek`, `zpw_kt`, `devices`.
- Client làm ngay (hàm xử lý confirm trong login-startup):
  `setAppCookie(zpw_sek)` (cookie phiên PC), lưu `captcha_cert`,
  đặt cờ `FORCE_GET_FRIEND_LIST=1`, rồi `Dr()`: đường trust thì
  `completeLinkingDevice(devices, uid)` (kiểm tra uid khớp khi relink),
  đường không trust thì bỏ qua; nếu có `zpw_kt` thì lưu renew-session
  `{encK: "", refreshToken: zpw_kt}` với timeout 30 giây.

### Bước 4 — Lấy thông tin phiên: `getLoginInfo`

- Endpoint: `GET https://wpa.zalo.me/api/login/getLoginInfo`
  (mã API 11134), xác thực bằng cookie phiên `zpw_sek`.
- Response `data` (wrapper trong compact-app-pc):
  `config` (gồm `zpw_chts_new`, `zpw_ctrs_new`,
  `zpw_service_map_new`, `zpw_service_map_v3`, `zpw_conf`, `zpw_ws`,
  `phone_number`, `current_time`), `dkey` (= UIN cho `setUIN`),
  **`zpw_enk`** (= khóa AES cho mọi API sau login, xem mục 4.3),
  `settings.authen` (merge vào auth đã lưu — đây là đường mà cờ
  `trusted_device` đi vào auth cho lần đăng nhập sau).
- Client sau đó: `setEndpoints(...)` (đặt domain map + endpoint
  WebSocket `zpw_ws`), `setUIN(dkey)`, `setDecryptKey(zpw_enk)`.
- Request chi tiết (ĐÃ XÁC NHẬN từ code client thật, sửa sau lỗi 102
  ở lần quét thật đầu tiên 2026-11-05): `getLoginInfo` là API
  *login*, không dùng common params `zpw_ver`/`zpw_type`. Nó gửi
  login envelope — `imei`, `computer_name`, `language`, `ts` (ms) +
  `type`/`client_version`/`signkey` (api name `"getlogininfo"`, mã hóa
  ParamCipher khi có key) — kèm cookie phiên `zpw_sek`. Tên cookie
  này cũng đã xác nhận: `setAppCookie` trong main.js đặt cookie tên
  `zpw_sek` cho các domain zalo.me/zaloapp.com/chat.zalo.me.
  `zpw_sek` trong payload confirm nằm top-level của `data`
  (`data.data.zpw_sek` ở cả đường QR confirm lẫn đường password).
  Bản client cũ chỉ gửi `zpw_ver`/`zpw_type` + cookie nên server trả
  102; bản sửa gửi đúng envelope và validate `zpw_sek` rỗng thì báo
  lỗi nêu tên field thay vì gửi request không cookie (xem
  `tests/test_logininfo.py`; mock nay bắt buộc đúng contract này).

### Bước 5 — Phiên bền qua restart

- File phiên của app này: `data/session.json`, mode `0600`,
  gitignored (xem mục 2). Mở app lên: nếu file có `zpw_sek` thì dùng
  ngay, không quét lại; gọi lại `getLoginInfo` để làm mới `zpw_enk` +
  service map. Hết hạn/kickout → quay về trang QR.
- Tương đương phía PC: uid + dkey + cookie + refresh token + cờ
  `trusted_device` cho lần sau (client tự viết không cần sao chép
  schema DB của Zalo).

---

## 2. Danh mục phiên / tài liệu sau login

| Tài liệu | Nguồn | Dùng để | Lưu |
|---|---|---|---|
| `device_id` | client tự sinh: `UUID + "-" + MD5(user-agent)` (`getZaloClientID`, lưu local storage) | `imei` mọi request, nhận diện thiết bị | session file, ổn định |
| `computer_name` | hostname máy (`$znode.os.hostname()`) | tham số `reqqr` | suy ra lúc chạy |
| `uid`, `dkey` | confirm QR | định danh tài khoản + thiết bị | session file |
| `zpw_sek` | confirm QR | cookie phiên cho mọi API sau login | session file (0600) |
| `zpw_kt` | confirm QR | refresh token, renew phiên | session file (0600) |
| `cptch_cert` | confirm QR | chứng chỉ captcha (nếu cần) | session file |
| `zpw_enk` | `getLoginInfo` | khóa AES tham số API sau login | session file (0600) |
| service map + `zpw_ws` | `getLoginInfo.config` | domain API + endpoint WebSocket sync/control | session file |
| `trusted_device` flags | `getLoginInfo.settings.authen` → auth lưu | quyết định old/new format lần sau | session file |
| `qr_timeout`, `qr_retry` | `reqqr` | long-poll + regen | chỉ trong bộ nhớ lúc login |

Không có tài liệu nào trong bảng này là bí mật tài khoản dạng
mật khẩu/TOTP; tất cả đều do server cấp sau một lần quét QR hợp lệ.

---

## 3. Signaling kiểu PC (gọi đi — đã map đủ, đã implement)

Mọi lệnh là `HTTPS GET`:
`https://voicecall-wpa.zalo.me/api/voicecall/<path>?zpw_ver=695&zpw_type=30&params=<AES JSON base64>`
(khóa AES = `zpw_enk` của phiên, mục 4.3). Mã API trong ngoặc.

| Lệnh | Path (mã) | Body JSON (đủ trường) |
|---|---|---|
| Gọi đi, bước 1 | `requestcall` (11300) | `calleeId, callId, codec ("[]" nếu null), typeRequest, imei` |
| Gọi đi, bước 2 (gửi địa chỉ media) | `request` (11301) | `calleeId, rtcpAddress, rtpAddress, codec, session, callId, imei` + `extendData, subCommand=3` nếu có extendData |
| Báo chuông phía nhận | `ringring` (11302) | `callerId, callId, status=0, imei` |
| Trả lời | `answer` (11303) | `callerId, callId, status, codec ("" nếu null), rtcpAddress, rtpAddress, session_id` + `extendData, subCommand=3` |
| Xác nhận đã trả lời | `answerack` (11304) | `calleeId, callId, status=0, imei` |
| Hủy | `cancel` (11305) | `callerId, callId, callType, status=0, imei` |
| Kết thúc | `endcall` (11306) | `uidTo, callId, status=3, imei` |
| Giữ / tiếp tục giữ | `holdreq` (11307) / `holdresp` (11308) | `toId` |
| Bỏ giữ / xác nhận bỏ giữ | `unholdreq` (11309) / `unholdresp` (11310) | `toId` |

Ánh xạ với cầu nối native của PC (`handleSendSignal`): 401→requestcall,
416→request, 407→ringring, 402→answer, 408→answerack, 405→cancel,
409→endcall, 411/412/413/414→hold. Các trường `rtcpAddress`,
`rtpAddress`, `session`, `extendData` là đầu vào cho engine tiếng
(relay + khóa media) — xem seam ở mục 5.

**Chiều nhận cuộc gọi:** server đẩy sự kiện qua kênh sync/control
(WebSocket tại `zpw_ws` + các endpoint `zpw_chts_new`/`zpw_ctrs_new`
từ config login). Khung message sync-v2 cho sự kiện gọi chưa map xong
— đây là việc giai đoạn 2 (mục 6, O3). UI đã có sẵn ô banner “cuộc gọi
đến” để gắn vào khi xong.

---

## 4. Crypto (đã map đủ để implement)

### 4.1 ParamCipher — API login (reqqr, ...)

Class `O` trong compact-app-pc (module `fBUP`):

```
zcid     = AES-256-CBC(key=S, iv=0, "apiType,deviceId,firstLaunchTimeMs")
           -> hex VIẾT HOA
zcid_ext = chuỗi ngẫu nhiên 6..12 ký tự (gửi trần)
enk      = even(MD5(zcid_ext).hex.upper)[0:8]
         + even(zcid)[0:12]
         + reverse(toàn bộ odd(zcid))[0:12]        (32 ký tự)
params   = AES-256-CBC(key=enk, iv=0, JSON) -> base64
```

Request gửi: `{zcid, zcid_ext, enc_ver:"v2", params, type, client_version,
signkey}`. Response `data` (nếu là chuỗi base64) được giải bằng cùng
`enk`, IV 0. IV 0 đã xác minh từ preload chính:
`encrypt(..., iv = Buffer.alloc(16, 0))` trong
`main-dist/compact-app-preload.js`. Lỗi `19000` → tắt mã hóa tham số và
thử lại một lần bằng tham số trần (client này đã implement fallback đó).

### 4.2 signkey — chữ ký request API login

```
signkey = MD5(salt_cố_định + tên_api + nối_các_giá_trị_theo_thứ_tự_key)
```

Không có dấu phân cách giữa các giá trị. Salt là hằng số giao thức
ngắn nhúng trong client PC (giống class với URL endpoint và mã API —
cùng cho mọi client), được giữ trong code dưới tên hằng `SIGN_SALT`
(xem quyết định ở mục 4.4).

### 4.3 Session AES — API sau login (voicecall, danh bạ, nhóm)

```
params = AES-CBC(key=base64decode(zpw_enk), iv=0, JSON) -> base64
```

(CryptoJS `AES.encrypt` với `iv = 0x00*16`, mode CBC, padding Pkcs7,
key = Base64-parse của `zpw_enk`.) Khóa do server cấp theo phiên nên
không cần khóa nhúng. Cùng một cách mã hóa dùng cho danh bạ
(`GET profile-wpa.zalo.me/api/social/friend/getfriends`, mã 11137,
body `{incInvalid:1, page:1, count:20000, actiontime:0, imei}`) và nhóm
(`GET group-wpa.zalo.me/api/group/getlg/v3`, mã 11161 — xem 7c: bản
v1 `/api/group/getlg` không có caller thật và server từ chối bằng
602).

### 4.4 Quyết định về bí mật (quan trọng, đã áp dụng vào code)

- **KHÔNG có trong repo, trong báo cáo này, hay trong log:**
  khóa mã hóa tham số `S` của ParamCipher (một khóa AES cố định nhúng
  trong app PC), khóa AES pipe nội bộ của PC, token/phiên/cookie thật,
  p/q, mật khẩu. Test dùng khóa test riêng (`TEST_PARAM_KEY...`).
- `S` được cấp lúc deploy qua biến môi trường
  `ZALO_PC_PARAM_CIPHER_KEY` (xem `docker-compose.yml`). Không có `S`,
  client tự chuyển sang tham số trần + signkey — server chỉ chấp nhận
  nếu phía server đã tắt mã hóa tham số (câu hỏi mở O2).
- Hằng `SIGN_SALT` trong code là hằng số giao thức (không phải bí mật
  tài khoản), bắt buộc phải có thì mới ký request được; nó được ghi rõ
  là hằng số giao thức trong comment code để người soát có thể gạch bỏ
  nếu không đồng ý cho push.
- File phiên thật (`data/session.json`) không bao giờ vào git
  (`.gitignore`) và API của app không bao giờ trả `zpw_sek`/`zpw_kt`/
  `zpw_enk`/`dkey` ra ngoài (test server kiểm tra điều này).

---

## 5. Thiết kế app (theo định hướng 08:39 — giống app PC về cách dùng)

Chạy trong Docker trên server Linux, mở bằng trình duyệt (và dùng qua
HA sau này). Không cài app Windows thật.

```
trình duyệt ──HTTP──> app service (Python, stdlib, không cần pip)
  ├─ trang QR: ảnh QR + đếm ngược + trạng thái (chưa quét/đã quét/
  │   hết hạn/bị từ chối/giới hạn tốc độ)
  ├─ trang chính: danh bạ / nhóm (tìm kiếm, bấm tên → gọi)
  ├─ màn hình gọi: trạng thái gọi, kết thúc; ô banner cuộc gọi đến
  │   (gắn kênh sync ở giai đoạn 2)
  ├─ backend: qr_login (state machine) + session (file 0600) +
  │   signaling (mục 3) + contacts
  └─ seam engine tiếng (zalo_pc_app/engine_seam.py): engine gắn vào
      qua attach(call_info) với rtcp/rtp/session/extendData/codec từ
      signaling; audio PCM 16 kHz mono cho HA/R1. Giai đoạn 1 chưa có
      engine nên màn gọi signaling được nhưng báo rõ "chưa có tiếng".
```

Chạy:

```
docker compose up --build        # UI ở http://127.0.0.1:8080
python3 tests/run_tests.py       # test offline (không cần mạng Zalo)
python3 -m zalo_pc_app.server    # chạy trực tiếp (cần ZALO_PC_DATA_DIR)
```

Biến môi trường: `ZALO_PC_DATA_DIR` (mặc định `./data`),
`ZALO_PC_HOST`/`ZALO_PC_PORT`, `ZALO_PC_PARAM_CIPHER_KEY` (tùy chọn),
`ZALO_PC_COOKIE_NAME` (mặc định `zpw_sek` — xem O5).

---

## 6. Câu hỏi mở + cách kiểm chứng (theo thứ tự)

- **O1 — Server hiện còn phục vụ QR old-format không?**
  Code client mới nhất vẫn lấy old-format làm mặc định, nhưng quyết
  định cuối thuộc về server. Cách kiểm: probe `reqqr` **không tài
  khoản** (chỉ device ID tự sinh + hostname, chưa quét, chưa đăng
  nhập): nếu trả về `base64_qr` + 2 URL poll thì old-format còn sống.
  Probe này không phải đăng nhập và không dùng tài khoản nên nằm trong
  phạm vi cho phép của task. Nếu server bắt buộc trust-format thì dừng
  ở báo cáo giai đoạn 2 (cần quyết định về việc tái dùng blob WASM).
- **O2 — `reqqr` có bắt buộc tham số mã hóa không?**
  Cùng một probe trên, thử bản trần trước: nếu server trả lỗi mã hóa
  (hoặc 19000 ngược lại) thì biết cần `S` lúc deploy.
- **O3 — Khung message sync cho cuộc gọi đến.**
  Cần map tiếp sync-v2 WebSocket (`zpw_ws`): subscribe + nhận diện
  event gọi đến + ánh xạ sang answer/ringring. Đây là việc lớn thứ hai
  sau O1/O2.
- **O4 — Engine tiếng gắn vào signaling.**
  Agent song song đang làm SRTP/Opus (đã có primitive, chưa nối đường
  media, chưa chốt payload relay ZRTP). Seam đã định nghĩa (mục 5);
  khi engine xong, gắn qua `engine_seam.SEAM.attach(...)`.
- **O5 — ĐÃ XÁC NHẬN + SỬA (lỗi 102 ở lần quét thật đầu tiên
  2026-11-05):** tên cookie phiên là `zpw_sek` (xác nhận từ
  `setAppCookie` trong main.js); tham số `getLoginInfo` là login
  envelope `imei`/`computer_name`/`language`/`ts` +
  `type`/`client_version`/`signkey` (không phải `zpw_ver`/`zpw_type`);
  `zpw_sek` nằm top-level trong payload confirm. Nguyên nhân 102:
  bản cũ gửi thiếu envelope (và không validate `zpw_sek` rỗng).
  Bản sửa + test hồi quy ở `tests/test_logininfo.py`. Còn lại duy
  nhất điểm nhỏ: domain thực tế sau khi service map override (mặc
  định đã có trong mục 3) — chưa dùng service map để đổi domain,
  không chặn lần quét lại.

---

## 7. Test offline đã chạy (không cần mạng Zalo)

`python3 tests/run_tests.py` — **tất cả pass**:

- `test_aes.py`: vector FIPS-197 AES-128 + AES-256; AES của client
  (thuần Python, tự sinh S-box từ định nghĩa GF) giải/mã chéo được với
  `openssl enc` cả hai chiều; round-trip mọi độ dài 0/1/15/16/17/100.
- `test_crypto.py`: signkey khớp MD5 tính độc lập; ParamCipher
  round-trip; công thức `enk` khớp đặc tả từng bước; session AES
  round-trip; dạng device ID.
- `test_flow_mock.py`: full flow qua **mock server độc lập** (AES qua
  openssl, signkey/enk tính lại bằng hashlib — không dùng chung code
  với client): QR mã hóa, QR trần, quét → xác nhận → gọi đi
  (requestcall, body giải ra đúng trường), danh bạ, nhóm; các nhánh
  lỗi: bị từ chối (18010), hết hạn poll, rate limit, trust flow bị từ
  chối đúng cách, fallback 19000 → trần. (Mock đã bắt được một lỗi
  thật trong công thức `enk` của client trước khi sửa — xem ghi chú
  trong code.)
- `test_logininfo.py` (mới, hồi quy lỗi 102): contract `getLoginInfo`
  đúng client thật — envelope plaintext và mã hóa đều qua mock (mock
  tự verify signkey/envelope bằng openssl + hashlib, giải response
  mã hóa); confirm thiếu `zpw_sek` thì lỗi nêu tên field và KHÔNG
  gửi request; server trả 102 thì client báo đúng mã 102.
- `test_server_smoke.py`: chạy thật app server qua HTTP API: QR →
  done, file phiên mode `0600`, `/api/status` không rò rỉ bí mật,
  contacts + call request + logout đều chạy.
- `test_contacts.py` (mới, hồi quy lỗi 602): contract danh bạ đúng
  client thật — friends body có `avatar_size:160`, `init=1` ở lần tải
  đầu; groups body `{avatar_size, member_avatar_size}` không `imei`;
  giá trị `params` mã hóa URL đầy đủ (không còn `/` thô); mock
  bắt buộc đúng contract nên request kiểu cũ (thiếu `avatar_size`,
  body nhóm `{imei}`, `params` có `/` thô) đều bị mock từ chối 500;
  lỗi 602 mô phỏng từ friends vs groups được `/api/contacts` báo
  nêu tên đúng endpoint, và cờ `init` không bị tiêu sau lần friends
  lỗi.

---

## 7b. Sửa lỗi sau chạy thật 2026-11-05 (danh bạ 602 + chown tay)

Chạy thật trên server (quét QR bằng tài khoản phụ, đăng nhập thành
công, phiên đã lưu) lộ 2 lỗi; cả 2 đã sửa trong cùng lần này.

### Lỗi 602 ở danh bạ — nguyên nhân gốc

Server trả `error_code=602 "zpw_type bị thiếu hoặc không đúng"` khi
tải danh bạ. Đối chiếu code client PC thật trong `app.asar` đã giải
(`main-dist/main.js`, `ZaloAPIServices.js`, `ServiceAPI.js`) đã
**loại trừ**: `zpw_ver=695`/`zpw_type="embed"` đúng theo config mặc
định của bundle (`apiVersion:695`, `apiType:"embed"`, probe
`getServerInfo` không override) — **ĐÍNH CHÍNH ở 7d: kết luận này
SAI, do đọc nhầm biểu thức `apiType:"embed"===__ZaBUNDLENAME__?31:30`
thành `apiType="embed"`; giá trị đúng là số 30, và chính nó là nguyên
nhân gốc của lỗi 602 ở nhóm**; domain `profile-wpa`/`group-wpa`
đúng; cookie `zpw_sek` gắn đúng; khóa phiên AES đúng
(`decryptKey = data.zpw_enk`, `UIN = data.dkey` trong handler
`getLoginInfo` của bundle); AES-CBC/IV0/Pkcs7/base64 khớp.

Còn lại 3 sai khác thật so với client (đây là nguyên nhân gốc — một
trong 3 khiến server từ chối request, và bản sửa khớp cả 3):

1. **Friends body thiếu `avatar_size:160`** — client thật gửi
   `{incInvalid:1, page:1, count:20000, avatar_size:160,
   actiontime:0, imei}` + `init=1` (query) ở lần tải đầu
   (`getFriendsList(this._isFirstReq(), ...)`).
2. **Groups body sai hoàn toàn** — code cũ gửi `{imei}`, client thật
   (`getGroupList`) gửi `{avatar_size:160, member_avatar_size:160}`,
   cùng path `/api/group/getlg`. — ĐÍNH CHÍNH ở 7c: kết luận này chỉ
   đúng với hàm `getGroupList()` v1 trong bundle, nhưng không có
   caller thật nào dùng v1 cho danh sách chính; client thật dùng
   `getGroupListV3` (`/api/group/getlg/v3`, body có thêm
   `page`/`count`/`imei`, phân trang).
3. **`params` không mã hóa URL đầy đủ** — `urllib.parse.quote`
   mặc định giữ `/` thô trong giá trị base64 (đã đo thực tế: giá trị
   `params` có `/` thô), còn client dùng `encodeURIComponent` mã hóa
   thành `%2F`. Sửa bằng `quote(enc, safe="")` — cùng sửa cả
   `protocol.voicecall_params` (cùng lỗi).

Cách sửa: `protocol.friends_params`/`groups_params` đúng body thật
(+ hằng `AVATAR_SIZE = 160`), `contacts._url_with_params` nhận
`extra_query` và mã hóa đầy đủ, `Contacts.friends(init=...)`,
`server.py /api/contacts` báo lỗi nêu tên endpoint
(`friends: ...` / `groups: ...`) thay vì gộp chung, và cờ
`_contacts_init_pending` gửi `init=1` ở lần friends đầu sau
start/login, chỉ tiêu sau khi friends thành công. Mock siết chặt:
kiểm `zpw_ver`/`zpw_type`, cookie, `params` không `/`/`+` thô,
body friends/groups đúng contract, `init=1` bắt buộc ở lần đầu.

Kiểm chứng cuối (chưa làm được ở VM này): user pull image mới,
deploy lại stack cũ (giữ volume `/opt/zalo`), quét lại bằng tài khoản
phụ, tải danh bạ phải ra danh sách (không còn 602).

### 7c. Nhóm vẫn 602 sau bản 8397d18: client thật dùng getlg/v3

Sau khi user redeploy bản 8397d18: friends ĐÃ QUA, chỉ groups còn
`error_code=602 zpw_type` — lỗi nêu tên endpoint (`groups:`) nên biết
chắc friends qua rồi. Lần lại bundle với con mắt mới, kết luận ở 7b
mục 2 là **sai chỗ dùng**: hàm `getGroupList()` v1
(`/api/group/getlg`, body `{avatar_size, member_avatar_size}`, không
imei) chỉ là định nghĩa trong bundle, không có caller thật nào lần
được dùng nó cho danh sách chính. Các đường gọi danh sách nhóm lần
được trong các luồng UI/data của bundle đều dùng `getGroupListV3`:

- `_fetchAllGroups` gọi `getGroupListV3(page, 100)`;
- helper fetch-by-page (`_callApi`, `callFetchGroupListByPage`) gọi
  `getGroupListV3(page, 100, ...)` và lặp khi `hasMore` (dừng khi đủ
  `total` hoặc quá 100 trang);
- `getGroupListV4` (`/api/group/getlg/v4`, không body) chỉ dùng để
  kiểm version nhóm, không phải để lấy danh sách;
- bảng command của bundle: `11161 -> /api/group/getlg/v3`.

Contract đúng của V3 (đã sửa vào code): `GET
group-wpa.zalo.me/api/group/getlg/v3`, common params
`zpw_ver=695`/`zpw_type=30` + cookie `zpw_sek` như cũ — **ĐÍNH CHÍNH
ở 7d: bản 7c ghi `zpw_type="embed"` là sai; giá trị đúng là số 30**,
body `{page, count:100, avatar_size:160, member_avatar_size:160, imei}`,
params AES mã hóa URL đầy đủ; response `{groups, hasMore, total}`,
client lặp các trang cho tới khi hết `hasMore`. Các tham số `_get`
thừa trong lời gọi V3 (`0, ae, 0, void 0, {}, n`) chỉ là timeout /
retry / cancel token nội bộ, không lên dây. Mock siết chặt theo:
đường v1 cũ trả 602 như server thật (test tái hiện lỗi), đường v3
bắt buộc đúng body phân trang (test 2 trang gộp lại).

Kiểm chứng cuối (chưa làm được ở VM này): user pull image mới,
deploy lại stack cũ (giữ volume `/opt/zalo`), mở lại trang — danh
bạ phải hiện cả bạn bè lẫn nhóm, không còn 602, không cần quét lại
(phiên cũ còn trong volume).

### 7d. Nhóm VẪN 602 sau bản 7bc97bf: `zpw_type` phải là số 30, không phải chuỗi "embed"

Sau khi user redeploy bản 7bc97bf (16:24 ngày 05/11): friends ĐÃ QUA,
chỉ groups còn `error_code=602 zpw_type bị thiếu hoặc không đúng`.
Lần này lỗi ghi rõ `zpw_type` — và điều tra lại từ đầu cho thấy cả
hai lần sửa trước đều giữ một giá trị `zpw_type` SAI mà không ai
nghi ngờ, vì nó nằm trong phần "đã loại trừ" của 7b.

**Nguyên nhân gốc — đọc nhầm biểu thức config trong bundle.**
Config mặc định của bundle (compact-app-pc, Zalo PC 26.11.10) là:

```
apiVersion:695, apiType:"embed"===__ZaBUNDLENAME__?31:30
```

Đây là toán tử ba ngôi: giá trị của `apiType` là `31` nếu
`__ZaBUNDLENAME__ === "embed"`, ngược lại là `30`. `__ZaBUNDLENAME__`
của bundle này là `"compact-app-pc"` — chứng minh bằng guard khởi
động `if(!("compact-app-pc"===__ZaBUNDLENAME__))return;` ngay trước
log "Starting compact application" (không phải tên đó thì app đã
không chạy). `"embed" === "compact-app-pc"` là sai, nên
**`apiType = 30` (số)**. Common params của mọi API sau login được
build đúng một chỗ: `re={zpw_ver:r.default.apiVersion,
zpw_type:r.default.apiType}`, tức `zpw_ver=695&zpw_type=30` — cho
friends, groups và voicecall giống nhau, và `type=30` trong cả
envelope login (`encryptParam`: `n.type=r.default.apiType`).

Probe `getServerInfo` chạy lại ngày 05/11 (không tài khoản, không
phiên): `error_code 0`, nhưng `data` KHÔNG có key `type` /
`client_version` ở tầng cao nhất — nên không có gì override giá trị
mặc định 695/30. (Code client có đọc `a.type`/`a.client_version`
nhưng `a` ở đó là tham số khởi động của app, không phải response
HTTP này.)

**Vì sao friends qua mà groups 602 với cùng một giá trị sai?**
`profile-wpa` (friends) chấp nhận cả `zpw_type="embed"` — quan sát
chạy thật hai lần đều vậy — còn `group-wpa` kiểm tra `zpw_type`
nghiêm ngặt và trả đúng thông báo "zpw_type bị thiếu hoặc không
đúng". Hai lần sửa trước chỉ đổi path/body của groups (v1 → v3) mà
giữ nguyên `zpw_type="embed"` nên đều gãy ở cùng một chỗ. V3 là đúng
(có caller thật: `_fetchAllGroups`, `_callApi`,
`callFetchGroupListByPage`); sai chỉ còn ở `zpw_type`.

**Đã kiểm thêm và loại trừ trong lần này:** domain mặc định đúng
(`apiGroupDomain: https://group-wpa.${Xe}` → `group-wpa.zalo.me`,
`apiProfileDomain` tương tự); `getGroupListV3` và `getFriendsList`
dùng chung `_getCommonParamsObj()` và cùng `_get` (chỉ khác domain /
path / body), nên không có tham số/query/header/cookie riêng nào cho
nhóm bị bỏ sót; `_constructUrlParams` chỉ là `k=encodeURIComponent(v)`
nối bằng `&`; `avatar_size` (`se`) = 160; `imei` dùng chung
`getZaloClientID()` cho cả hai (friends qua nên imei đúng); mã hóa
params AES giống nhau cho cả hai (friends qua nên khóa đúng).

**Cách sửa:** `protocol.API_TYPE = 30` (số nguyên). Kéo theo tự động:
`common_params()` → `zpw_type=30` cho friends/groups/voicecall;
`type=30` trong envelope login (reqqr/getLoginInfo) và `ParamCipher`;
probe `getServerInfo` gửi `type=30`. Mock siết theo đúng server
thật: groups với `zpw_type="embed"` → 602 (test tái hiện lỗi cũ),
groups với `30` → qua; friends chấp nhận cả hai (ghi lại đúng độ
lệch đã quan sát). Test mới: `test_groups_zpwtype_embed_rejected`,
`test_friends_zpwtype_embed_accepted`; assertion cũ
`zpw_type == "embed"` đổi thành `"30"` (contacts, logininfo,
envelope trong mock).

### 7e. Version marker + tắt tiếng log ConnectionResetError

**Version marker (để loại trừ khả năng Portainer giữ image `:test`
cũ):** `GET /api/status` trả thêm `version`; footer của UI hiện
"Phiên bản: ...". Nguồn version: biến môi trường `ZALO_PC_VERSION`
— CI truyền đúng commit sha vào lúc build (`build-args:
APP_VERSION=${{ github.sha }}`, Dockerfile `ARG APP_VERSION` →
`ENV ZALO_PC_VERSION`) — nếu không có thì dùng tag trong code
(`zalo_pc_app.VERSION`, ví dụ `2026-11-05-groups-zpwtype30`, bump
mỗi lần sửa). Cách kiểm tra sau khi redeploy: mở trang app, đọc
dòng phiên bản ở cuối trang (hoặc `GET /api/status` và xem trường
`version`) — phải trùng với commit/tag được báo, nếu không tức là
image cũ vẫn đang chạy (cần `docker compose pull` rồi mới `up -d`).

**Log `ConnectionResetError: [Errno 104] Connection reset by peer`:**
user dán log thấy nhiều traceback từ client LAN 172.16.10.1 ở
`socketserver.py process_request_thread` → `rfile.readline`. Đây
chỉ là client (trình duyệt/proxy) đóng kết nối trước khi gửi
request — server vẫn chạy bình thường, KHÔNG phải nguyên nhân lỗi
groups 602. Đã tắt tiếng bằng `QuietServer(ThreadingHTTPServer)`
trong `server.py`: override `handle_error` để bỏ qua đúng
`ConnectionResetError`/`BrokenPipeError`, mọi lỗi khác vẫn in
traceback như cũ. Test `test_connection_reset_silenced` kiểm cả hai
mức (gọi trực tiếp `handle_error` + RST thật vào server đang chạy:
không còn traceback, server vẫn trả `/api/status`).

### 7f. Danh bạ hiện TRỐNG sau bản bd380d1: dạng thật của friends/groups + số đếm trên tab

**Chạy thật (16:44 ngày 05/11):** user redeploy bd380d1, footer
version khớp, đã đăng nhập, `/api/contacts` KHÔNG trả error nữa —
nhưng cả hai tab đều trống, bấm tab vẫn «Chưa có gì». Chưa rõ tài
khoản phụ có bạn/nhóm thật hay không, nên không giả định hướng nào.

**Dạng thật (lần lại bundle `compact-app-pc`, lần này tới tận hàm
parse của client):**
- Friends (getfriends): `data` là MẢNG TRẦN các profile
  `{userId, displayName|zaloName, avatar}`. Bằng chứng:
  `FriendListManager._callApi` — `.then(s.a)` unwrap envelope rồi
  `_preFormatData` trả `{data: e}` và code sau kiểm
  `Array.isArray(e)`; tên hiển thị trong UI contacts được giải quyết
  bằng `getDName(userId) || displayName || zaloName`;
  `reformatConversationFromFriend` chấp nhận cả snake_case
  (`uid` / `zalo_name` / `display_name`); `_normalizeMiniProfileData`
  đặt `displayName = zaloName` khi thiếu.
- Groups (getlg/v3): `data` là `{groups: [...], hasMore, total}`;
  mỗi item là group THÔ `{groupId, name, avt, fullAvt, creatorId,
  ...}`. Bằng chứng: `GroupListManager._callApi` +
  `_fetchAllGroups` đọc `r.groups`/`r.hasMore`/`r.total`;
  `_preFormatItemGroup` map `groupId -> userId` ("group"+groupId),
  `name -> displayName`, `avt -> avatar`, `fullAvt -> bgavatar`;
  `callFetchGroupListByPage` cũng format từng item qua
  `_preFormatItemGroup`. `_formatDataAGroup` (gridInfoMap) xác nhận
  cùng dạng thô.
- Không có bằng chứng item lồng «profile» trong hai hàm parse này
  (grep `.profile` trong cả hai manager = 0) — chỉ giữ làm fallback
  phòng thủ trong code, không coi là dạng thật.

**Lỗ hổng `_extract_rows` cũ (đã sửa):** không đọc `groupId` (nhóm
bị id rỗng → bấm vào gọi với peer id rỗng), không đọc
`avt`/`fullAvt` (avatar nhóm luôn rỗng), không đọc
`zaloName`/`zalo_name`/`display_name` (bạn chỉ có zaloName thì hiện
số id thay vì tên). Lưu ý trung thực: với dạng thô này, tên nhóm vẫn
trích được qua field `name` và bạn bè vẫn trích được qua
`userId`+`displayName` — nên các lỗ hổng trên GIẢI THÍCH được nút
gọi nhóm gãy và tên hiển thị sai, nhưng KHÔNG giải thích được danh
sách hoàn toàn trống. Khả năng còn lại là tài khoản phụ vốn trống —
chưa chứng minh được từ đây.

**Mock sai dạng thật (đã sửa):** mock cũ trả
`data = {"friends": [...]}` với item đã format sẵn
`{userId, displayName, avatar}` cho cả hai endpoint — server thật
không trả như vậy, nên test offline không bắt được các lỗ hổng trên.
Mock mới trả đúng dạng thật (friends: mảng trần, có 1 bạn chỉ có
`zaloName` và 1 bạn chỉ có snake_case; groups: item thô
`{groupId, name, avt, ...}` phân 2 trang), thêm chế độ
`friends_mode`/`groups_mode = "empty"` (friends `[]`, groups
`{groups: [], hasMore: False, total: 0}`).

**Số đếm trên tab (để lần sau phân biệt ngay):** `app.js renderList`
đặt nhãn tab theo tổng số rows đã trích — «Bạn bè (N)» /
«Nhóm (M)». «Bạn bè (0)» / «Nhóm (0)» nghĩa là tài khoản thật sự
trống; số > 0 mà không thấy tên mới là lỗi trích tên.

**Test mới:** `test_extract_rows_real_shapes` (dạng thật trích đủ
id/tên/avatar; fallback "rows"/"profile"; tài khoản trống → rows
rỗng), `test_empty_account` (mock "empty" → contacts trả rows rỗng,
không lỗi); `test_friends_groups_contract` assert thêm id nhóm =
groupId và avatar nhóm = avt; `test_friends_zpwtype_embed_accepted`
sửa theo dạng thật (data là mảng).

**Kiểm chứng cuối:** user pull image mới, up lại stack cũ (giữ
volume, không chown, không quét lại trừ khi trang hiện lại QR) — đọc
số trên tab: nếu «Bạn bè (0)» / «Nhóm (0)» thì tài khoản phụ trống
thật (cần thêm bạn cho nó mới thử gọi được); nếu số > 0 thì tên phải
hiện; nếu số > 0 mà vẫn không thấy tên thì báo lại — đó mới là lỗi
trích tên còn sót.

### 7g. Danh bạ vẫn 0/0 dù tài khoản có 60 bạn / 6 nhóm: response là envelope HAI LỚP có mã hóa

**Ground truth CHỐT (user xác nhận 17:00 ngày 05/11, đối chiếu app
Zalo thật trên điện thoại — chuẩn «zalo cũ», số liệu điện thoại
thắng nếu mâu thuẫn với phân tích bundle):** tài khoản phụ có
«Bạn bè (60)» và «Nhóm đang tham gia (6)». App PC đăng nhập cùng
tài khoản phải hiện đúng 60/6. Giả thuyết «tài khoản trống» ở 7f là
SAI. Ảnh gọi cho «BenBap» là tài khoản phụ trên điện thoại gọi đi
tới một người bạn trong 60 bạn đó — KHÔNG liên quan tới lỗi số
đếm; và app PC không đổ chuông/hiện gì khi có cuộc gọi đến là ĐÚNG
với bản hiện tại, vì nhận cuộc gọi đến là O3/giai đoạn 2, chưa làm.

**Nguyên nhân gốc — envelope HAI LỚP, đã xác nhận từ bundle:**
mọi API sau login đều trả response bọc hai lớp, và lớp ngoài KHÔNG
phải payload:
- Lớp ngoài: HTTP 200, JSON `{error_code: 0, data: "<chuỗi base64>"}`
  — `data` là CHUỖI đã mã hóa AES, không phải dữ liệu.
- Lớp trong: AES-giải mã `data` bằng khóa phiên (zpw_enk, AES-CBC,
  IV 0, PKCS7 — hàm `decodeAES` của client, khóa lấy từ
  `getSecretKey()`, được `setDecryptKey()` gán từ `zpw_enk` của
  getLoginInfo), rồi JSON-parse thành `{error_code, data}` — `data`
  trong mới là payload thật (friends: mảng trần; groups:
  `{groups, hasMore, total}`).
- Bằng chứng bundle (`compact-app-pc`, Zalo PC 26.11.10): hàm unwrap
  `o` ở module `kCOK` — `if(200==e.status&&e.data){
  0==e.data.error_code && e.data.data && (a=decodeAES(e.data.data),
  r=JSON.parse(a), 0==r.error_code ? t(r.data) : n(r)) }`;
  `decodeAES`/`encodeAES`/`getSecretKey`/`setDecryptKey` ở crypto
  util (`decodeAES`: `AES.decrypt(Base64.parse(e),
  Base64.parse(this.getSecretKey()), {iv: 0, mode: CBC, padding:
  Pkcs7})`); config `secretKey:"zpw_enk"`; getLoginInfo lưu
  `decryptKey: e.data.data.zpw_enk`. Cùng mẫu
  `JSON.parse(decodeAES(e.data.data))` + kiểm `error_code` trong rồi
  mới lấy `.data` xuất hiện ở hàng chục chỗ khác (getMe,
  getUserByPhone, sendChunk, ...). `s.a` (chính là hàm unwrap này)
  được gọi sau cả getFriendsList lẫn getGroupListV3.

**Vì sao cả hai endpoint cùng 0 mà không báo lỗi:** code cũ
(`contacts.py::_get`) trả `payload["data"]` thẳng — tức trả CHUỖI
mã hóa. `_extract_rows(chuỗi)` không phải list/dict nên ra `[]`;
`groups()` ép chuỗi thành `{}` nên ra 0 rows; outer `error_code`
vẫn là 0 nên không exception nào được ném — UI hiện tab trống mà
không báo lỗi, khớp đúng hiện tượng chạy thật. Cùng lỗi này có
trong `signaling.py::_call` (voicecall cũng dùng envelope hai lớp)
— đã sửa luôn, nếu không lần gọi thật đầu tiên sẽ trả về chuỗi mã
hóa thay vì kết quả.

**Các hướng khác đã kiểm và loại trừ trong lần này:**
- (a) Key parse của V3: `r.groups`/`r.hasMore`/`r.total` là đúng
  (đọc trong `_fetchAllGroups` và `_callApi` của GroupListManager).
- (b) Tab Nhóm đọc từ cache GroupWorker nạp bằng V3 lúc khởi động
  (`_callApi` → `_handleSucess` → `_preFormatItemGroup` →
  `_signalCallback`) — V3 đúng là nguồn danh sách, không phải danh
  sách hội thoại.
- (c) V3 KHÔNG phải API đồng bộ tăng dần: `getGroupListV3(page,
  count)` không có tham số version nào; API đồng bộ theo version là
  V4 (`getlg/v4`, code 12027, không body).
- (d) Page bắt đầu từ 1 (`i(1)` trong cả `_fetchAllGroups` và
  `_callApi`), count mặc định 100, vòng lặp dừng ở `++e>=100 ||
  !hasMore || collected>=total` — khớp vòng lặp trong
  `contacts.py::groups()`, không bỏ sót trang.
- (e) Item nhóm dạng thô `{groupId, name, avt, fullAvt, creatorId}`
  — đã khớp từ 7f, không có dạng lồng khác trong hai manager này.

**Đã sửa:**
- `crypto.py`: thêm `decode_postlogin_data(payload, zpw_enk)` —
  giải mã đúng unwrap của client (chuỗi → giải mã AES → JSON →
  kiểm inner error_code → trả inner data; data đã là dict/list thì
  giữ nguyên; thiếu data → None).
- `contacts.py::_get` và `signaling.py::_call`: dùng hàm trên thay
  cho `payload.get("data")`.
- `contacts.py`: thêm `describe_shape(data)` + log chẩn đoán
  `[contacts-shape]` — MỘT dòng cho mỗi endpoint mỗi lần tải
  (friends: 1 dòng; groups: 1 dòng cho mỗi trang), chỉ ghi SHAPE:
  kiểu dữ liệu, độ dài/số lượng, tên key tầng ngoài, tên key của
  item đầu tiên, `total`/`hasMore`. TUYỆT ĐỐI KHÔNG ghi tên, id,
  số điện thoại hay nội dung. Ví dụ dòng log thật (từ test):
  `[contacts-shape] friends raw=list len=3
  first_item_keys=['avatar', 'displayName', 'userId'] rows=3` và
  `[contacts-shape] groups page=1 raw=dict keys=['groups',
  'hasMore', 'total'] groups len=1 first_item_keys=['avt',
  'creatorId', 'fullAvt', 'groupId', 'name'] total=2 hasMore=True
  rows=1`. Sau redeploy, user copy 2 dòng `[contacts-shape]` trong
  log container (`docker logs <container>` / Portainer → Logs) gửi
  lại nếu số đếm vẫn sai — hai dòng đó cho biết server thật trả về
  dạng gì mà không lộ dữ liệu cá nhân.
- `tests/mock_server.py`: thêm `_postlogin_envelope()` — mock giờ
  trả đúng dạng hai lớp cho friends/groups/voicecall (outer data là
  chuỗi AES của inner `{error_code:0, data:...}` bằng openssl +
  TEST_SESSION_KEY); đường lỗi 602 vẫn là outer error thuần như
  server thật. Mock cũ trả inner data trực tiếp nên test offline
  không bắt được lỗi 0/0 — đó là lý do bug này lọt qua 6 suite
  xanh trước đó.
- Test mới trong `test_contacts.py`: `test_double_envelope_decrypted`
  (outer data là chuỗi mã hóa; client giải mã ra đủ rows — test này
  FAIL ở code cũ), `test_inner_error_raises` (inner error_code != 0
  phải raise kèm mã), `test_missing_outer_data_empty` (thiếu data →
  rows rỗng, không crash), `test_describe_shape_no_values` (log
  shape không chứa tên/id nào), `test_shape_log_printed` (mỗi
  endpoint in đúng một dòng shape, không lộ giá trị cá nhân);
  `test_friends_zpwtype_embed_accepted` sửa theo dạng hai lớp.
  Toàn bộ suite `tests/run_tests.py` xanh 6/6.
- `VERSION` bump thành `2026-11-05-contacts-double-envelope`.

**Kiểm chứng cuối:** user pull image mới, up lại stack cũ (giữ
volume `/opt/zalo`, không chown, không quét lại trừ khi trang hiện
lại QR) — tab phải hiện «Bạn bè (60)» / «Nhóm (6)» như trên điện
thoại. Nếu vẫn sai, gửi lại 2 dòng log `[contacts-shape]` (xem
trên) — không cần gửi tên hay id nào.

### Không cần chown tay nữa — cách đã chọn

Image cũ chạy bằng user `app` (UID 1000) nên mount host path thuộc
root (`/opt/zalo:/data`) thì không ghi được `session.json` → user
phải `sudo chown -R 1000:1000 /opt/zalo` tay. Cách chọn: **entrypoint
chạy bằng root, chown thư mục data, hạ quyền rồi chạy server**
(`docker-entrypoint.py`, thuần stdlib — không phụ thuộc `su`/`setpriv`
vì `python:3.12-slim` không đảm bảo có các công cụ đó):

- Container khởi động bằng root (bỏ `USER app` khỏi Dockerfile),
  entrypoint `mkdir -p $ZALO_PC_DATA_DIR` (mặc định `/data`), chown
  **chỉ đúng thư mục data** (không đệ quy) về `app:app` khi khác
  ownership, rồi `setgroups([])` → `setgid` → `setuid` xuống `app`
  và `exec` server — server không bao giờ chạy bằng root.
- `session.json` vẫn mode 0600 (server tự enforce khi lưu); named
  volume không đổi hành vi (chown là no-op vì Docker đã copy
  ownership của `/data` trong image).
- Entrypoint chạy không phải root (ví dụ `--user`) hoặc thiếu user
  `app` thì chỉ exec như cũ; chown lỗi (ví dụ mount read-only) chỉ
  cảnh báo, server sẽ lỗi rõ nếu không ghi được.

Đã kiểm trên VM này (chạy bằng root, tạo user `app` UID 1000 để
mô phỏng image): thư mục root-owned → `app:app` sau entrypoint,
tiến trình server chạy uid/gid 1000, `/api/status` trả `login: false`,
chạy lại khi thư mục đã thuộc `app` (no-op) và chạy bằng chính user
`app` đều đúng. **VM không chạy được container Docker nên deploy
trên server của user là bước kiểm chứng cuối**: pull image mới,
`docker compose up -d` với volume host path cũ, không còn bước chown
tay nào; server phải khởi động và ghi được phiên.

README + `docker-compose.yml` đã bỏ hướng dẫn chown tay.

---

## 8. Những gì CHƯA kiểm bằng chạy thật (ghi rõ, không suy đoán)

- Danh bạ trống sau bản bd380d1 (xem 7f) — lỗi 602 đã hết nhưng
  chưa rõ tài khoản phụ có bạn/nhóm thật hay không; bản sửa 7f thêm
  số đếm «Bạn bè (N)» / «Nhóm (M)» lên tab để phân biệt trống thật
  hay lỗi trích tên — cần user pull image mới, deploy lại stack cũ
  (giữ volume, không quét lại trừ khi trang hiện lại QR) và đọc số
  trên tab.
- Entrypoint chown/hạ quyền trong container thật (xem 7b) — VM này
  không chạy được container Docker; đã kiểm logic entrypoint bằng
  user `app` thật trên VM, còn deploy trên server là bước cuối.
- Server có trả QR old-format và chấp nhận tham số trần/mã hóa ra sao
  (O1/O2) — cần probe `reqqr` không tài khoản.
- Quét thật lại sau bản sửa `getLoginInfo` (lỗi 102 lần đầu) — cần
  user cầm app phụ quét lại với image mới.
- Nhận cuộc gọi đến, tiếng trực tiếp, độ trễ, độ ổn định — giai đoạn 2.

## 9. Quy trình test quét thật (khi user sẵn sàng, tài khoản PHỤ tuyệt đối)

1. Deploy container trên server (volume `/data` bền), mở UI.
2. Bấm “Lấy mã QR”, dùng **app Zalo của tài khoản phụ** quét, bấm chấp
   nhận trên điện thoại.
3. Kiểm tra: trang chính hiện danh bạ; gọi đi tới một tài khoản phụ
   khác; nghe/nói thử (sau khi engine giai đoạn 2 gắn vào).
4. Restart container, mở lại UI: phải vào thẳng trang chính, không quét
   lại (kiểm tra phiên bền). Nếu bị kickout/hết hạn → quay về trang QR
   và quét lại.
5. Ghi lại bất kỳ mã lỗi nào từ server (đặc biệt ở `reqqr`,
   `getLoginInfo`, voicecall) để sửa O5.

## 10. Ghi chú về luật tham chiếu

- Luật đứng 03/11 16:11 (phân tích kỹ code chatgpt2api trước mọi việc
  module) + luật 05/11 06:26 (LangChain làm công cụ tham chiếu cho
  web2api): **không áp dụng trực tiếp ở đây** — sản phẩm này không
  phải module web2api và không mirror chatgpt2api; tham chiếu duy nhất
  đã phân tích kỹ là **chính client Zalo PC 26.11.10** (bằng chứng:
  các file/hàm nêu trong mục 1–4). Kết luận này được ghi rõ theo đúng
  yêu cầu của luật (nêu khi “phần này không mirror chatgpt2api”).
- Không dùng code Zalo trong repo này: mọi thứ là viết lại từ đặc tả
  (trừ hằng số giao thức `SIGN_SALT` và các URL/mã API — xem mục 4.4).
  Blob WASM trust protocol không được copy hay nhúng.

## Cây file (workdir ~/workspace/zalo-pc-qr/)

```
bao-cao.md  README.md  Dockerfile  docker-compose.yml
zalo_pc_app/
  aes_pure.py  crypto.py  protocol.py  session.py
  qr_login.py  signaling.py  contacts.py  engine_seam.py  server.py
  static/  app.html  app.js  style.css
tests/
  test_aes.py  test_crypto.py  test_flow_mock.py  test_server_smoke.py
  mock_server.py  run_tests.py
```
