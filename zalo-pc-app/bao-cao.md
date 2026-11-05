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

**Chuẩn đối chiếu — ĐÍNH CHÍNH (17:03 ngày 05/11):** «zalo cũ»
mà user nhắc tới là ZALO ADDON (tích hợp Zalo trong HA / zalobot,
chạy zca-js), KHÔNG phải app Zalo trên điện thoại như đã hiểu lúc
đầu. Hai ảnh điện thoại hiện «Bạn bè (60)» / «Nhóm đang tham gia
(6)» CHƯA RÕ là tài khoản nào — KHÔNG lấy 60/6 làm ground truth
nữa. Số chuẩn là số addon hiện cho tài khoản phụ (đang chờ user trả
lời). Điều CHẮC CHẮN bất kể số chuẩn là bao nhiêu: tài khoản phụ CÓ
bạn bè (user 16:58: «bạn bè tôi cũng có mà») và CÓ nhóm (user
16:57: nhóm là 1 theo addon) — nên app hiện 0/0 là sai cả hai. Giả
thuyết «tài khoản trống» ở 7f là SAI. Ảnh gọi cho «BenBap» là tài
khoản phụ trên điện thoại gọi đi tới một người bạn — KHÔNG liên
quan tới lỗi số đếm; và app PC không đổ chuông/hiện gì khi có cuộc
gọi đến là ĐÚNG với bản hiện tại, vì nhận cuộc gọi đến là O3/giai
đoạn 2, chưa làm.

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
lại QR) — tab phải hiện đúng số addon hiện cho tài khoản phụ (số
chuẩn đang chờ user trả lời; chắc chắn lớn hơn 0 ở cả hai tab). Nếu
vẫn sai, gửi lại 2 dòng log `[contacts-shape]` (xem trên) — không
cần gửi tên hay id nào.

### 7h. Lấy addon Y NGUYÊN làm chuẩn, chỉ thêm calling — gọi theo threadID

**Chỉ đạo sản phẩm (user 17:05 ngày 05/11):** «xem lấy y nguyên và
chỉ thêm calling, vì khi gọi có thể phải gọi theo threadID» — lấy
Zalo addon (tích hợp Zalo trong HA / zalobot, chạy zca-js 2.1.2) Y
NGUYÊN làm chuẩn, chỉ THÊM calling lên trên, không tự vẽ lại mô
hình danh bạ riêng.

**Mô hình thread của addon (đối chiếu trực tiếp từ code addon):**
- zca-js `ThreadType`: User=0, Group=1 (`dist/models/Enum.d.ts`).
  HA `sendMessage` gửi `threadId` + `type` (1=nhóm, 0=1-1) —
  threadId CHÍNH LÀ định danh đích: 1-1 threadId = userId, nhóm
  threadId = groupId (thô, không tiền tố).
- Bạn bè: addon gọi `getAllFriends` (zca-js) → cùng endpoint +
  body với app PC (`{profile}/api/social/friend/getfriends`,
  `{incInvalid:1, page:1, count:20000, avatar_size, actiontime:0,
  imei}`) → mảng trần `User[]`. Nguồn dữ liệu KHỚP Y NGUYÊN, không
  lệch.
- Nhóm: addon gọi `getAllGroups` (zca-js) → `{group_poll}/api/
  group/getlg/v4` → chỉ trả `{version, gridVerMap: {groupId:
  version}}` (tập id + version, KHÔNG có tên/avatar); chi tiết từng
  nhóm lấy sau bằng `getGroupInfo` → POST `{group}/api/group/
  getmg-v2` với `{gridVerMap: {id: 0}}`. App PC lấy danh sách nhóm
  từ getlg/v3 (phân trang, item đầy đủ `{groupId, name, avt, ...}`).
  Hai đường KHÁC API nhưng cùng một tập nhóm của cùng một tài khoản
  (v3 là đường client PC thật dùng; v4+getmg-v2 là đường client web
  dùng). Số nhóm chuẩn để đối chiếu là số key trong `gridVerMap`
  của addon — tức số addon hiện cho tài khoản phụ.
- Envelope response: zca-js `handleZaloResponse` (`dist/utils.js`)
  giải mã `jsonData.data` bằng `ctx.secretKey` (khóa phiên zpw_enk)
  rồi mới kiểm inner `error_code` và lấy inner `data` — ĐỘC LẬP
  xác nhận đúng dạng hai lớp ở 7g, từ phía addon chứ không chỉ từ
  bundle PC.

**Lệch đã tìm thấy và đã sửa — đường gọi nhóm:** app PC trước đây
gửi MỌI lần bấm gọi (kể cả bấm vào nhóm) qua endpoint 1-1
`requestcall` (11300) với `calleeId` = id của hàng được bấm. Với
nhóm thì SAI hoàn toàn: client PC thật gọi nhóm qua endpoint riêng
`group/requestcall` (code 12433) với body `{groupId, callId,
typeRequest, data, partners}` (KHÔNG có imei) — bằng chứng:
command table map 12433 → `/api/voicecall/group/requestcall`, và
native bridge dispatch `case 12433: requestCallGroup(groupId,
callId, typeRequest, data, partners)`. Đã sửa: `protocol.py`
(`vc_requestcall_group`, `VOICECALL_GROUP`), `signaling.py`
(`request_call_group`), `server.py` (`/api/call/request` rẽ theo
`type`: "user" → 11300, "group" → 12433), `app.js` (`startCall`
gửi `type` theo tab đang mở + `partners: []`). Hàng trong danh bạ
giờ đúng nghĩa là một thread: id của hàng = threadId (userId hoặc
groupId thô), tab quyết định endpoint.
- `partners` ĐÃ CÓ (xong ở 7i): danh sách member userIds lấy từ
  topMember của getmg-v2 khi tải danh bạ; app.js gửi `peer.members`
  khi bấm gọi nhóm. Giới hạn còn lại: topMember có thể chỉ là một
  phần thành viên (hasMoreMember) — nếu nhóm lớn và server cần đủ
  members, bước tiếp theo là tải đủ qua getgi/v2. Giai đoạn 2
  (tiếng + nhận cuộc gọi đến) vẫn chưa làm.

### 7i. Danh sách nhóm chuyển sang đường addon (v4 + getGroupInfo)

**Quyết định (theo chỉ đạo 17:05 «lấy y nguyên» + kết quả đọc repo
17:10):** danh sách nhóm của app PC đi ĐÚNG đường addon, không giữ
v3 nữa. V3 là đường list của client PC thật, không phải của addon —
và giữ cả hai cách mà không biết cái nào đúng là điều user dặn
không làm. Đường mới (một đường duy nhất):

1. `GET {group}/api/group/getlg/v4` (code 12027, không body, không
   phân trang, chỉ common params zpw_ver=695/zpw_type=30) →
   `{version, gridVerMap: {groupId: version}}` — tập nhóm.
2. `POST {group}/api/group/getmg-v2` (code 12028, form body
   `params=<AES {gridVerMap: "{groupId: 0}"}>` — giá trị gridVerMap
   là CHUỖI JSON, không phải object lồng) →
   `{removedsGroup, unchangedsGroup, gridInfoMap: {groupId:
   {groupId, name, avt, fullAvt, creatorId, topMember: [{id, ...}],
   totalMember, type, ...}}}` — tên/avatar/thành viên. Không gọi
   getmg-v2 khi map rỗng (tài khoản không có nhóm → 0 hàng, không
   lỗi).

**Bằng chứng (3 nguồn độc lập, khớp nhau):**
- zca-js (addon): `getAllGroups` → GET `{group_poll}/api/group/
  getlg/v4`, trả `{version, gridVerMap}`; `getGroupInfo` → POST
  `{group}/api/group/getmg-v2` với `{gridVerMap:
  JSON.stringify(map)}`, trả `{removedsGroup, unchangedsGroup,
  gridInfoMap}` (xem `~/workspace/zalo-addon-doc/bao-cao-addon-96-
  services.md` §3 — đọc repo zalo_bot, 96 services đã xác minh).
- PC bundle: command table map `12027 → /api/group/getlg/v4`,
  `12028 → /api/group/getmg-v2`; `getInfoMultiGroup` POST đúng dạng
  trên; `_preFormatData` map `name → displayName, avt → avatar,
  fullAvt → bgavatar`, `topMember` mặc định `[]`; `fetchGroupsByIdsV2`
  tiêu thụ map `{groupId: info}`.
- Máy chủ zalobot (`api/zalo/zalo.js:1216`): `gInfo?.gridInfoMap`
  rồi `gmap[String(groupId)]` lấy `name` — gridInfoMap key theo
  groupId THÔ.

**Đã sửa:** `protocol.py` (bỏ `groups_params` v3; thêm
`groups_v4_url`, `group_info_multi_params/url/form`, code 12027/
12028); `contacts.py` (`groups()` 2 bước; `_group_row` từ
gridInfoMap kèm `members` = topMember ids; `_post` cho getmg-v2;
`describe_shape` biết `gridVerMap`/`gridInfoMap`); `server.py`
(transport thêm `http_post`, Contacts nhận đủ cả hai);
`mock_server.py` (thêm `do_POST`; phục vụ v4 + getmg-v2 đúng dạng
thật; BỎ route v1/v3); `app.js` (`startCall` gửi
`partners: peer.members || []`). Số đếm nhóm giờ theo đúng nguồn
của addon: số key trong `gridVerMap` = số addon hiện — khớp theo
cấu trúc, không còn hai nguồn số liệu lệch nhau.
- Log chẩn đoán giờ có 3 dòng (ví dụ thật từ test):
```text
[contacts-shape] friends raw=list len=3 first_item_keys=['avatar', 'displayName', 'userId'] rows=3
[contacts-shape] groups v4 raw=dict keys=['gridVerMap', 'version'] gridVerMap len=2 rows=2
[contacts-shape] groups info raw=dict keys=['gridInfoMap', 'removedsGroup', 'unchangedsGroup'] gridInfoMap len=2 first_item_keys=['avt', 'creatorId', 'fullAvt', 'groupId', 'name', 'topMember', 'totalMember', 'type'] rows=2
```
**Test mới/cập nhật:** `test_friends_groups_contract` (đúng 1 v4
GET + 1 getmg-v2 POST, không v3; members đúng topMember),
`test_group_row_from_info`, `test_group_info_wrong_body_rejected`
(thiếu gridVerMap, hoặc gửi dạng object thay vì chuỗi JSON),
`test_groups_v4_zpwtype_embed_rejected`; `test_empty_account`
(v4 rỗng → KHÔNG gọi getmg-v2); `test_shape_log_printed` (3 dòng
mới). Toàn bộ suite xanh 6/6 (xem mục 7).
- **Kiểm chứng cuối (cập nhật 7g):** sau redeploy, tab Nhóm phải
  hiện đúng số addon hiện cho tài khoản phụ (số chuẩn đang chờ
  user trả lời; chắc chắn lớn hơn 0). Vì số đếm giờ lấy từ đúng
  nguồn của addon, nếu vẫn lệch thì 2 dòng log `groups v4` +
  `groups info` sẽ cho biết server trả gì (số key trong gridVerMap
  và gridInfoMap) — gửi lại 2 dòng đó là đủ, không cần tên hay id.

**Test mới:** `test_group_call_uses_group_endpoint` (nhóm đi đúng
`group/requestcall` với `groupId`, không có `imei`; 1-1 vẫn đi
`requestcall` với `calleeId`); smoke test e2e thêm lần gọi nhóm
qua `/api/call/request` với `type: "group"`. Toàn bộ suite xanh
6/6 (xem mục 7).

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

### 7j. Làm lại toàn bộ web UI + theo dõi calling (lệnh 17:17, chốt thứ tự 17:25)

**Lệnh user 17:17 +07:** «Làm lại cả webui giống addon nhưng dùng
skill làm lại cho đẹp, hợp xu hướng và theo dõi thêm cả calling».
**Chốt thứ tự 17:25 +07:** «hoặc gọi ngay trên ui, service làm
custom zalo sau» — **gọi ngay trên UI trước; service HA `make_call`
làm sau, không làm trong lần này** (track service đã tách ra và dừng
lại). Vì vậy ưu tiên của lần sửa này: bấm tên/thread trên UI là gọi
được ngay (signaling theo threadID, đã có từ trước), kèm mục theo
dõi calling; không chờ service HA.

**«Giống addon» giữ nguyên gì:** cấu trúc/nội dung lấy y nguyên
addon — đăng nhập QR, danh bạ Bạn bè/Nhóm kèm số đếm, phiên bản,
trạng thái đăng nhập; thread = (threadId, type 0=user/1=group);
không vẽ lại mô hình danh bạ riêng (xem báo cáo đọc repo
`~/workspace/zalo-addon-doc/bao-cao-addon-96-services.md`). Tham
chiếu giao diện admin máy chủ zalobot (`~/workspace/zalo-container/
app/views/index.ejs`, Bootstrap cũ) chỉ ở mức cấu trúc/nội dung,
không copy kiểu.

**Hướng đã deal (skill design-taste-frontend, tasteskill v2, run
riêng app screen):** `draw.mjs --app --kind support --screens
list,detail --options 3` → style **`framed-sheet`, seed 540927485**,
sheet đầy đủ lưu tại `.taste-skill/direction.json`, notes tại
`.taste-skill/notes.md`. Face: khung tinted một bước low-chroma của
màu Zalo (ground xanh-xám #f2f6fa), accent là màu Zalo đậm lại
**#0066c2** (≥4.5:1 trên trắng; thay teal #1b6c80 đã deal bằng màu
thương hiệu, giữ nguyên tỉ lệ — lựa chọn face mà sheet cho phép,
không phải redraw palette). Type: IBM Plex Sans (400/500/600) +
IBM Plex Mono cho ID/khóa. **Không có lần redraw nào.**
- Font tự host: 10 file woff2 (Sans 400/500/600 + Mono 400/500,
  subset vietnamese + latin) trong `static/fonts/`, nguồn Google
  Fonts, giấy phép OFL — vì app chạy trên server LAN, trình duyệt có
  thể không với tới Google Fonts. Phục vụ qua `/fonts/*`
  (font/woff2).
- Layout: sidebar 228px + topbar 48px (khung L tinted, không có
  rule ngăn cách) + sheet trắng inset 8px phải/dưới, radius 16,
  không shadow. Số học ở 1440px: nội dung 1156 = contacts 748 +
  gap 24 + rail 384; count cards 3×244 + 2×8 = 748. Một gap 24px
  ngang/dọc. Hàng thread ≥48px (56px hai dòng): avatar chữ cái đầu
  trên nền nhạt riêng theo hue (6 hue, không violet), tên, threadId
  bằng mono, pill loại (Cá nhân/Nhóm), nút Gọi. Thẻ đếm là bộ lọc
  (Tất cả/Bạn bè/Nhóm, thẻ chọn viền accent 1.5px + nền nhạt).
- Câu idea: «On this screen, the addon's thread list becomes the
  dialler: every row is a thread you can call, and every call returns
  to the log as a thread with a result.» Live thing: gọi ngay từ
  danh sách (bấm một hàng → request gửi đi, cuộc gọi hiện live
  trong rail với trạng thái + đồng hồ đếm) + ô tìm kiếm lọc live
  theo tên HOẶC threadId.

**Theo dõi calling — server:** file mới `zalo_pc_app/call_log.py`
(class `CallLog`, thread-safe, chỉ bộ nhớ, cap 50 bản ghi mới nhất,
restart là mất; entry: call_id, peer, thread_id, type, status
sent|error|ended, started_at, ended_at, detail; KHÔNG bao giờ chứa
bí mật). `server.py`: `AppState.calls`; **GET `/api/calls`** (cần
đăng nhập, 401 nếu chưa) trả `{"calls": [mới nhất trước],
"active": <entry live hoặc None>}`; POST `/api/call/request` ghi
`record_start` khi thành công / `record_error` khi lỗi (peer lấy từ
body `peer_name` hoặc callee_id); POST `/api/call/end` ghi
`record_end`. Cuộc gọi mới thay thế cuộc live trước đó (cuộc cũ
thành «ended»).

**Theo dõi calling — UI:** sidebar thêm nav Cuộc gọi (dot khi có
cuộc live) + pill «Đang đổ chuông: <peer>» trên topbar; view Danh bạ
có rail Cuộc gọi (thẻ cuộc live + 5 lần gần nhất + «Xem tất cả»);
view Cuộc gọi riêng: bảng lịch sử đầy đủ (Thời gian / Đối phương /
ThreadID / Loại / Kết quả, số giờ/phút tabular, threadId mono);
view chi tiết cuộc gọi (tên + pill loại + threadId mono + đồng hồ
đếm live + nút Kết thúc; có placeholder «cuộc gọi đến» ẩn cho O3).
Poll `/api/calls` mỗi 5 giây khi đã đăng nhập; đồng hồ đếm cập nhật
mỗi giây. Ô tìm kiếm lọc cả danh sách lẫn lịch sử gọi. Phiên bản
mới: `2026-11-05-ui-moi-calls`.

**Giữ nguyên:** luồng QR, tải danh bạ (friends mảng trần; groups
v4+getmg-v2; envelope hai lớp; log `[contacts-shape]`), footer
phiên bản, Đăng xuất, gọi theo threadID (11300/12433, partners từ
topMember), ghi chú engine, QuietServer tắt tiếng RST; stack giữ
HTML/CSS/JS thuần, không migrate framework.

**Gate của skill:**
- `lint.mjs --app` trên 3 file mới: **0 FAIL, 12 WARN**. Một FAIL
  ban đầu (ký tự ☰ ở nút menu, bị coi là emoji) đã sửa thành SVG
  hamburger nội tuyến. 12 WARN còn lại đều là dùng đúng luật, giữ
  lại có lý do: `padStart(2,"0")` cho đồng hồ mm:ss (chính lint ghi
  «fine for a clock»); mono ×10 là IBM Plex Mono cho ID thật
  (threadId, version sha — hướng đã deal chọn face này); shadow ×1
  chỉ ở sidebar gấp lại trên tablet/phone, là menu trượt nổi — chỗ
  duy nhất skill cho phép shadow.
- **`inspect.mjs --app` KHÔNG chạy được** (đã thử): Chrome duy nhất
  trên VM (`/opt/meta-chromium/chrome`, «Muse Browser 155.0.8059.91»)
  từ chối khởi động headless — «Hatch WebGL domain policy is
  required for browser startup», exit code 13 (hai lần thử trực tiếp
  + một lần qua inspector, cùng lỗi). **Không có screenshot nào,
  không claim đã kiểm tra bằng trình duyệt.** Critique vòng cuối làm
  từ code (xem `.taste-skill/notes.md` §2.8): số học 1440/768/390
  đã đối chiếu tay; điểm yếu nhất là chưa có lần nhìn thật nào —
  lần nhìn đầu tiên phải làm sau deploy trên server (rủi ro lớn
  nhất: tên nhóm dài ở rail tại 768px; topbar chật tại 390px).

**Kiểm live thay thế (mock server, API HTTP thật):** GET / 200 có
nav/rail mới; `/style.css` 200 (10 @font-face); `/app.js` 200
(loadCalls + timer); font woff2 200, đúng magic `wOF2`; QR flow tới
«done»; danh bạ Ban A/B/C + Nhom X/Y; gọi user đi đúng
`/api/voicecall/requestcall` (11300), gọi nhóm đi đúng
`/api/voicecall/group/requestcall` (12433); `/api/calls` hiện cuộc
nhóm live, cuộc user đã ended (bị thay thế). **Toàn suite
`tests/run_tests.py` xanh 7/7** (thêm `tests/test_calls.py`: 7 test
unit CallLog + e2e `/api/calls` trong `test_server_smoke.py`, gồm
401 khi chưa đăng nhập và quét bí mật trong payload).

**Kiểm tra sau redeploy:** pull + up, giữ volume `/opt/zalo`,
không chown, không quét lại trừ khi trang hiện lại QR; footer phải
hiện `2026-11-05-ui-moi-calls` (hoặc commit sha); tab hiện đúng số
addon; bấm một tên → màn hình chi tiết cuộc gọi hiện «Đang đổ
chuông» + đồng hồ chạy; rail/mục Cuộc gọi ghi lại lần gọi đó sau
khi kết thúc. Lưu ý: lịch sử gọi mất khi restart container (chỉ
bộ nhớ).

### 7k. Lỗi gọi 114 «Tham số không hợp lệ» — body requestcall sai hai chỗ (chạy thật 17:31)

**Bằng chứng chạy thật:** user redeploy đúng bản cb57faa (footer
khớp), danh bạ hiện đủ, bấm gọi một bạn bè 1-1 → đồng hồ chạy tới
00:03 rồi báo «Lỗi gọi: response inner error_code=114 Tham số
không hợp lệ». POST /api/call/request đã gửi requestcall (11300)
tới server Zalo và server trả inner error 114 — request tới nơi
nhưng tham số trong body bị chê. Envelope đã đúng (danh bạ 60/6
chạy thật, giải mã hai lớp hoạt động, lỗi nêu rõ là «inner»),
nên nghi phạm nằm ở BODY của requestcall.

**Body cũ đang gửi** (`protocol.vc_requestcall` +
`signaling.request_call` + `server /api/call/request` +
`app.js startCall`): `{calleeId: peer.id (chuỗi), callId:
String(Date.now()) (chuỗi 13 chữ số), codec: "[]" (chuỗi),
typeRequest: 0, imei: device_id}`.

**Bằng chứng bundle — field nào sai:**

1. **`typeRequest: 0` — SAI GIÁ TRỊ (nghi phạm chính).**
   Bundle PC (`compact-app-pc.*.js`, lớp wZ — call helper):
   command table `W(11300,"/api/voicecall/requestcall")`;
   `static requestCall(e,t,n,a)` → body `{calleeId:e, callId:t,
   codec: n ?? "[]", typeRequest:a, imei: getZaloClientID()}`.
   Native bridge dispatch: `case 401: requestCall(n.calleeId,
   n.callId, n.codec, n.type)` — tham số thứ 4 là `n.type`.
   Renderer `makeCall(e,t,n,a,i)` gửi native
   `{type:"request", command:"makeCall", data:{partner:s, type:o,
   groupInfo:i}}` với `o = n?(t?6:5):(t?3:1)` — **1-1 audio=1,
   1-1 video=3, nhóm audio=5, nhóm video=6**; UI dispatch
   `DO_CALL` gọi `makeCall(false, conversation)` (audio) nên
   type=1. Giá trị 0 KHÔNG xuất hiện ở đâu trong từ vựng loại
   cuộc gọi của client thật. Sửa: 1-1 audio → 1, nhóm audio → 5
   (video 3/6 đã ghi chú trong code, app này chỉ gọi audio).
2. **`callId` dạng CHUỖI 13 chữ số — SAI KIỂU + SAI MIỀN
   (nghi phạm thứ hai).** ZaloCall.exe strings:
   `_initCallConfig ... callId = %u` (cùng `userId = %u`,
   `partnerId = %u`, `makeCall isVideo = %d`) — engine native
   lưu callId dạng uint32; renderer stringify object signal của
   native nên trên dây callId là JSON NUMBER. `String(Date.now())`
   vừa sai kiểu vừa vượt uint32 (1,7 nghìn tỷ > 4,29 tỷ). Sửa:
   epoch seconds (`Math.floor(Date.now()/1000)`, ~1,76 tỷ, vừa
   uint32); server chuẩn hoá lại (`_normalize_call_id`: chuỗi
   số → int, thiếu/sai/vượt miền → epoch seconds) và giữ một
   guard đơn điệu trong process để hai lần bấm trong cùng một
   giây không trùng callId; server trả `call_id` hiệu lực về để
   UI dùng đúng id đó cho /api/call/end.
3. **`codec: "[]"` — GIỮ NGUYÊN (không phải nghi phạm chắc
   chắn).** Đây chính là fallback có ghi trong code client thật
   (`codec: n ?? "[]"` khi native không đưa danh sách codec),
   nên server chấp nhận nó là hợp lý; engine thường gửi danh
   sách codec thật nhưng chưa biết định dạng chuỗi codec thật
   nên KHÔNG bịa một danh sách. Nếu 114 vẫn còn sau bản này,
   codec là nghi phạm còn lại đầu tiên.
4. **`calleeId` dạng chuỗi — GIỮ NGUYÊN (đúng).** ThreadId thật
   19 chữ số vượt giới hạn số nguyên an toàn của JS (2^53 ≈
   9,0×10^15 < 6,6×10^18) nên renderer thật BUỘC phải mang nó
   dạng chuỗi, nếu không sẽ mất chính xác; native nhận partner
   id dạng chuỗi JS từ `makeCall data.partner[].id`.

**Đã sửa:** `protocol.py` thêm hằng `CALL_TYPE_*` (1/3/5/6) +
docstring cho `vc_requestcall`/`vc_requestcall_group` (mặc định
nhóm 0 → 5); `signaling.py` mặc định 1 / 5; `server.py`
`_normalize_call_id` + `_type_request_for` (KHÔNG tin
`type_request` trong body — UI cũ gửi 0) + trả `call_id` hiệu
lực; `app.js` `startCall` sinh callId số epoch seconds,
`type_request` 1/5, nhận `call_id` server trả về; `VERSION`
→ `2026-11-05-call-114-fix`.

**Test:** mock `_voicecall` nay kiểm đúng contract của
requestcall như server thật — body sai (typeRequest ngoài
1/3/5/6, callId không phải số uint32, thiếu calleeId/groupId)
trả về **inner 114** trong envelope hai lớp (không phải
assertion của mock), đúng dạng lỗi user gặp. Mới
`tests/test_call_114.py` 7 test: body cũ 1-1 → 114, body mới
1-1 → qua, riêng typeRequest 0 → 114, riêng callId chuỗi →
114, body cũ nhóm → 114, body mới nhóm → qua, chuẩn hoá ở
server (kể cả guard đơn điệu). Cập nhật theo contract mới:
`test_flow_mock.py` (2 chỗ gọi), `test_server_smoke.py`
(gửi đúng payload UI cũ — chuỗi mili-giây + type_request 0 —
qua HTTP, assert server chuẩn hoá thành typeRequest 1/5 +
callId số), `test_contacts.py` body3. Toàn suite
`tests/run_tests.py` xanh 8/8; `node --check app.js` + py_compile
OK.

**Kiểm tra sau redeploy:** pull + up (giữ volume `/opt/zalo`,
không quét lại); footer phải hiện `2026-11-05-call-114-fix`
(hoặc commit sha mới); bấm một tên bạn bè → kỳ vọng bên kia
**đổ chuông** thay vì lỗi 114 (đồng hồ chạy, trạng thái «Đã gửi
yêu cầu gọi. Bên kia đang đổ chuông»). **Lưu ý trung thực:** qua
được 114 mới chỉ chứng minh tham số đã đúng — tiếng vẫn chưa có
(giai đoạn 2) nên bên kia đổ chuông nhưng chưa nói chuyện được;
nếu server trả mã lỗi KHÁC sau bản này (không phải 114), ghi rõ
mã mới đó là gì và nghĩa của nó, đừng claim xong. Nghi phạm còn
lại nếu 114 vẫn còn: codec `"[]"` (xem mục 3 ở trên).

---

### 7l. Gọi đi qua 114 nhưng ĐIỆN THOẠI BÊN KIA KHÔNG ĐỔ CHUÔNG — thiếu bước `request` (11301 / 12434) sau requestcall (chạy thật 17:51)

**Triệu chứng chạy thật (ảnh user 17:51 +07):** redeploy 01f7ee7, gọi 1-1
→ UI hiện «Đang đổ chuông», đồng hồ chạy tới 00:26, mục Cuộc gọi ghi lại
lần gọi, KHÔNG còn lỗi 114. NHƯNG điện thoại người được gọi không hiện
cuộc gọi đến. «Đang đổ chuông» trên UI chỉ là trạng thái cục bộ sau khi
requestcall được chấp nhận — không phải xác nhận bên kia đã nhận.

**Bằng chứng mới 17:54 (ảnh từ điện thoại user) — thay đổi hướng điều tra:**
điện thoại của user đang ở màn hình gọi đi cho một bạn khác («BenBap —
Đang đổ chuông») thì phía trên hiện banner CUỘC GỌI ĐẾN từ «Đại ca —
Đang gọi đến» (nút Từ chối / Trả lời). Tức là điện thoại ĐÃ hiện cuộc gọi
đến từ Đại ca, chỉ vài phút sau cuộc gọi PC 17:51 mà user báo «không
thấy». Hai giả thuyết, CHƯA PHÂN BIỆT ĐƯỢC:
(a) cuộc gọi từ app PC tới muộn — server giữ lời mời đến khi có đủ
thông tin (hoặc đẩy chậm), tới nơi sau vài phút;
(b) Đại ca thấy cuộc gọi nhỡ từ app PC nên gọi lại ngay.
Cả hai đều nghĩa là: tín hiệu gọi ĐÃ tới được phía bên kia ở mức nào
đó — không phải hoàn toàn không tới. Điều này loại giả thuyết «thiếu
bước nên không tới được», và thêm hai khả năng phải kiểm: TRỄ chuyển
tiếp, và cuộc gọi PC chỉ hiện thành «cuộc gọi nhỡ» ở bên kia thay vì
đổ chuông ngay. **Cần user xác nhận trước khi kết luận: Đại ca gọi lại
hay cuộc gọi PC tới muộn.** (Không ghi số điện thoại hay threadId cụ
thể từ ảnh.)

**Luồng đầy đủ của client thật — lần từ bundle (không đoán):**
Zalo PC 26.11.10, renderer `compact-app-pc.*.js`:
- UI bấm gọi → renderer `makeCall` chỉ gửi MỘT tin cho native engine
  qua pipe: `{type:"request", command:"makeCall", data:{partner:[{id,
  avatar, name}], type:1/3/5/6, groupInfo}}`. Mọi bước báo hiệu sau đó
  đều do ENGINE quyết định, phát qua pipe `sendSignal` → main chuyển
  cho renderer qua IPC `call-send-signal` → hàm `handleSendSignal`
  (`dSignal`) map mã lệnh sang hàm HTTPS API (lớp wZ). Trích nguyên
  văn hai case quan trọng:
  `case 401: a=s.default.requestCall(n.calleeId,n.callId,n.codec,n.type);`
  `case 416: a=s.default.sendRequestCall(n.calleeId,n.rtcpAddress,
  n.rtpAddress,n.codec,n.extendData,n.session,n.callId);`
  (case 407: `sendRingRingCall` — do BÊN NGHE gửi khi máy nó đổ chuông,
  không phải bên gọi; case 402 answer, 408 answerack, 405 cancel, 409
  endcall, 411–414 hold/unhold; nhóm: 12433 requestCallGroup, 12434
  sendRequestCallGroup, 12435–12439.)
- Lớp wZ, nguyên văn:
  `static sendRequestCall(e,t,n,a,i,r,s){let l=.../api/voicecall/request?...,
  c={calleeId:e,rtcpAddress:t,rtpAddress:n,codec:a,session:r,callId:o,
  imei:D.a.getZaloClientID()};return i&&(c.extendData=i,c.subCommand=3),
  ...this._get(l,null,11301)}`
  và nhóm:
  `static sendRequestCallGroup(e,t,n,a,i,r,o){.../api/voicecall/group/request?...,
  c={calleeId:e,callId:t,callType:n,data:a,session:i,partners:r,groupId:o};
  ...this._get(l,null,12434)}`
- Các field của signal 416 đến từ NATIVE ENGINE, không phải renderer:
  payload signal 416 trong ZaloCall.exe là `{command, calleeId, callId,
  rtpAddress, rtcpAddress, extendData, session}` (strings còn liệt kê
  `rtpAddressIPv6`, `rtcpAddressIPv6`, `rtcpIP`). Engine cấp các địa chỉ
  relay này từ máy chủ relay ZRTP lúc bắt đầu gọi — pcap 2026-11-04 cho
  thấy máy gọi bắt đầu setup media tới relay 20–40 ms sau gói TCP cuối của server (pcap không chứa thời điểm bấm gọi nên không đo được độ trễ sau khi bấm gọi);
  client mang cả cấu hình `timeoutMakeCall2ZRtp` cho bước này. Mobile
  khớp 1-1: opcode 416 `voiceRequestCallZRTPWithExtendData` (`g4 g4` rồi
  7 blob nhị phân — nội dung blob vẫn CHƯA BIẾT, xem giai-ma-packet.md).

**Kết luận:** app cũ chỉ gửi bước 1 (11300). Hàm `send_request` (11301)
đã có sẵn trong `signaling.py` từ giai đoạn 1 nhưng KHÔNG AI GỌI (dead
code). Server chấp nhận requestcall nhưng chỉ giữ một lời mời chưa có
địa chỉ media — nên máy bên kia không đổ chuông (hoặc đổ chuông muộn /
chỉ hiện cuộc gọi nhỡ, đúng hai giả thuyết ở trên).

**Đã sửa:**
- `protocol.py`: thêm `vc_request_group` (12434) đúng dạng bundle;
  `vc_request` (11301) đã có sẵn, đối chiếu lại khớp nguyên văn wZ.
- `signaling.py`: thêm `send_request_group` (12434).
- Mới `zalo_pc_app/media_endpoints.py` — seam cấp địa chỉ media cho
  bước request. Giai đoạn 1 chưa có engine nên trả chuỗi rỗng cho
  rtcp/rtp/session, không extendData, codec `"[]"` (cùng fallback như
  requestcall). **Chuỗi rỗng là PLACEHOLDER, không phải địa chỉ thật —
  server thật có chấp nhận hay không là CHƯA XÁC MINH, đúng là điều
  test thật phải cho thấy.** Giai đoạn 2 engine sẽ thay provider này
  bằng địa chỉ relay thật từ bắt tay ZRTP; không chỗ nào khác đổi.
- `server.py` `/api/call/request`: sau requestcall thành công, gửi tiếp
  bước request (1-1 → 11301; nhóm → 12434, calleeId lấy bằng groupId —
  CHƯA XÁC MINH TỪ BUNDLE, xem dưới). Bước này là BEST-EFFORT: nếu
  server từ chối (ví dụ 114 vì địa chỉ rỗng), cuộc gọi vẫn báo ok như
  cũ (requestcall đã qua) nhưng trả về `request_sent=false` +
  `request_error` và ghi vào call log, để phân biệt «lời mời có thể
  chưa được chuyển» với «đã gửi đủ».
- `call_log.py`: entry thêm `request_sent` (True/False/None) +
  `request_detail`; phương thức `record_request`. Sửa luôn docstring cũ
  ở `sent` — câu «requestcall được chấp nhận thì bên kia đổ chuông» là
  SAI sau phát hiện này; «sent» giờ chỉ nghĩa là «lời mời đã gửi đủ»,
  chưa phải «máy bên kia đang đổ chuông».
- Mock `tests/mock_server.py`: theo dõi trạng thái từng callId
  (`voice_calls`, `voice_call_state`): «requested» khi có requestcall,
  «delivered» chỉ khi có thêm bước request cùng callId. Nhánh
  `request` / `group/request`: chỉ kiểm tra những gì bundle chứng minh
  được (calleeId + callId số uint32; nhóm thêm groupId) — KHÔNG kiểm
  giá trị rtcp/rtp/session (mock không được bịa ra một lỗi từ chối mà
  server thật chưa từng được thấy). Thêm `request_mode="error114"` để
  test mô phỏng server từ chối bước 2.
- Mới `tests/test_call_11301.py` 7 test: body 11301/12434 đúng dạng
  bundle; luồng cũ (chỉ requestcall) → requested nhưng KHÔNG BAO GIỜ
  delivered (tái hiện triệu chứng thật); luồng mới qua API thật →
  đủ 2 bước đúng thứ tự, cùng callId, delivered, `request_sent=true`,
  call log ghi nhận (cả 1-1 và nhóm); bước request lỗi → cuộc gọi vẫn
  ok, `request_sent=false` + lỗi 114 ghi rõ; request không có
  requestcall trước → không delivered. Toàn suite xanh 9/9; `node
  --check app.js` + py_compile OK. Cập nhật `test_calls.py` (whitelist
  key của snapshot thêm 2 key mới; `record_error` cũng mang đủ key để
  dạng entry đồng nhất).
- Phiên bản mới: `2026-11-05-call-11301`.

**CHƯA XÁC MINH (ghi rõ, đừng claim):**
1. Server thật có chấp nhận địa chỉ media rỗng ở bước 11301 không.
   Nếu từ chối (114 hoặc mã khác), `request_error` trong response và
   call log sẽ ghi rõ mã đó — đó là kết quả test thật cần thu thập,
   không phải thất bại của bản sửa.
2. `calleeId` của 12434 (gọi nhóm) lấy bằng groupId — giá trị này không
   nhìn thấy trong đoạn bundle đã trích; nhóm là đích của cuộc gọi nên
   đây là giả thuyết hợp lý nhất, cần kiểm chứng live.
3. Nội dung thật của `session` / `extendData` (vật liệu ZRTP/relay) —
   chỉ engine giai đoạn 2 mới cấp được; bản này chỉ chứng minh bước
   báo hiệu đã đủ, chưa chứng minh tiếng đi được.
4. «Đang đổ chuông» trên UI vẫn là trạng thái cục bộ (chưa có kênh
   sync O3 để nhận 407 ringring thật từ bên kia) — chỉ test thật với
   máy bên kia mới xác nhận nó đổ chuông đúng lúc.

**Kiểm tra sau redeploy:** pull + up (giữ volume `/opt/zalo`, không
quét lại); footer phải hiện `2026-11-05-call-11301` (hoặc sha mới);
bấm một tên bạn bè gọi lại và NHÌN MÁY BÊN KIA NGAY: kỳ vọng máy bên
kia **đổ chuông trong vài giây** (không phải vài phút sau) và giữ
chuông thay vì chỉ hiện cuộc gọi nhỡ. Ghi lại: (a) máy bên kia đổ
chuông sau bao lâu, (b) nếu không đổ chuông thì UI/mục Cuộc gọi có ghi
`request_sent=false` + mã lỗi gì không, (c) xác nhận giúp câu hỏi ở
trên: lần 17:54 Đại ca gọi lại hay cuộc gọi PC tới muộn.

---

## 7m. Nút «Kết thúc» bấm không được — cuộc gọi kẹt ở «đang đổ chuông» (2026-11-05 18:06, chạy thật)

**Triệu chứng thật (ảnh user 18:06):** bản 4f40c7e đang chạy; cuộc gọi
1-1 đổ chuông tới 00:52 (từ 18:05); bấm nút «Kết thúc» KHÔNG có tác
dụng — cuộc gọi vẫn ở trạng thái đang đổ chuông, pill topbar vẫn
hiện, đồng hồ vẫn chạy. Đến 18:09 lịch sử mới ghi «Đã kết thúc» —
nút không hẳn hỏng hoàn toàn mà **CHẬM/trễ**: bấm nhiều lần mới ăn,
hoặc UI chỉ cập nhật sau lần poll sau, hoặc request endcall chậm.

**Hai chỗ gãy (đều có bằng chứng code):**

(A) **Server — `/api/call/end` chỉ đánh dấu ended khi endcall Zalo
thành công.** Handler cũ (server.py, bản 4f40c7e):
`sig.endcall(...)` trước, `record_end(...)` sau, lỗi thì trả 502 —
`record_end` không bao giờ chạy khi endcall lỗi/chậm. Cuộc gọi ở
lại `"sent"` trong log → UI poll `/api/calls` thấy nó vẫn active
mãi. UI lại bỏ qua lỗi trả về (`endCall` không kiểm `r.error`).
Đây là chỗ gãy chính cho triệu chứng 18:06.

(B) **UI — `endCall()` chỉ lấy mục tiêu từ `currentCall ||
detailCall`, là biến của phiên trang.** Sau khi load lại trang, cả
hai đều null → nút Kết thúc ở rail KHÔNG GỬI request nào (no-op),
dù server vẫn giữ cuộc gọi active. Ngoài ra `call_id` từ màn hình
chi tiết là CHUỖI (log lưu `str(call_id)`) — gửi dạng chuỗi thì
server thật có thể trả 114 như requestcall (§7k). Và UI không có
phản hồi ngay trong lúc POST đang bay (đồng hồ vẫn chạy, pill vẫn
hiện) nên người dùng tưởng nút hỏng.

**Bằng chứng bundle cho body endcall (không đoán):** renderer
`compact-app-pc.*.js`, native bridge `case 409:
a=s.default.sendEndCall(n.toId,n.callId)` → lớp wZ `static
sendEndCall(e,t){...a={uidTo:e,callId:t,status:3,imei:D.a.getZaloClientID()};...this._get(l,null,11306)}`
— body 1-1 là `{uidTo, callId, status:3, imei}`, code 11306, đúng
như `vc_endcall` đã viết (không sửa body này). Nhóm:
`sendEndCallGroup` → `{calleeId, callId, callType, hostCall, data,
partners}`, `/api/voicecall/group/endcall`, code 12438; `hostCall`
chỉ có tên field trong bundle, không có ngữ nghĩa giá trị — app gửi
`True` (bên gọi là host của cuộc gọi đi), ghi UNCONFIRMED.

**Timeout đổ chuông (đã kiểm, KHÔNG bịa):** trong bundle chỉ có
một cấu hình timeout liên quan gọi điện là `timeoutMakeCall2ZRtp`
— cấu hình server đẩy xuống engine (`ZaloCall.exe` nhận
`timeoutMakeCall2ZRtp` lúc khởi tạo), mặc định `0` (tắt), là
timeout cho quá trình bắt tay media sau makeCall, KHÔNG phải timeout
«đổ chuông không trả lời thì tự kết thúc». Không tìm thấy timeout
đổ chuông nào ở phía renderer (engine giữ máy trạng thái cuộc gọi).
Vì vậy bản này KHÔNG thêm timeout đổ chuông bịa ra — thuốc chữa cho
cuộc kẹt là nút Kết thúc phải luôn ăn (local-first) + phản hồi ngay.

**Đã sửa (workdir, chưa push — xem cuối mục):**
- `server.py` `/api/call/end` — **local-first**: xác định mục tiêu
  (call_id ép về số uint32 bằng `_coerce_call_id`, không hợp lệ thì
  lấy cuộc đang live — tối đa một cuộc live nên ý định nút Kết thúc
  là không mơ hồ), `record_end` TRƯỚC, rồi mới thử endcall Zalo
  (best-effort); lỗi Zalo ghi vào `detail` của entry + trả về
  (`zalo_endcall_ok` / `zalo_error`). Response luôn ok khi đã kết
  thúc cục bộ (`ended_call_id`, `data` giữ như cũ). Nhóm đi
  `group/endcall` (12438), 1-1 đi `endcall` (11306).
- `call_log.py` — `record_end(call_id, detail="")`,
  `end_active(detail="")` (kết thúc cuộc đang live),
  `record_end_error(call_id, detail)` (gắn lỗi Zalo vào entry đã
  kết thúc).
- `protocol.py` — thêm `vc_endcall_group` đúng dạng bundle;
  `signaling.py` — thêm `endcall_group`.
- `static/app.js` — viết lại `endCall()`: lấy mục tiêu từ
  `currentCall || detailCall || callsData.active` (rail vẫn ăn sau
  khi load lại trang); ép call_id chuỗi số về Number; chặn bấm đôi
  (`ending`); **xóa trạng thái ngay trên UI** (optimistic: active →
  ended, pill biến mất) rồi mới POST + poll đối chiếu; bỏ
  `loadMain()` cuối hàm (không cần tải lại danh bạ sau khi kết thúc
  — vừa chậm vừa dính 429); khi Zalo không xác nhận thì ở lại màn
  hình chi tiết với cảnh báo thay vì về danh bạ im lặng.
  `showCallDetail` giữ `type` + `requestSent`/`requestError` trong
  `detailCall`; mới `renderCallDetail()`; `startCall` lưu kết quả
  bước 2 (`request_sent`/`request_error`) lên `currentCall` và làm
  mới dòng chẩn đoán sau `loadCalls()`.
- `static/app.html` — thêm `<p id="call-request">` ở màn hình chi
  tiết: hiện «Bước 2 (11301): đã gửi…» / «KHÔNG gửi được — <mã lỗi>.
  Máy bên kia có thể chưa đổ chuông.» / «chưa có thông tin.» — BẮT
  BUỘC theo bằng chứng 18:09 (màn hình cũ chỉ có câu chung nên bước
  2 bị từ chối cũng không nhìn thấy).
- Mock `tests/mock_server.py` — thêm `endcall_mode`
  ("ok"|"error"|"slow"); nhánh `endcall`/`group/endcall` kiểm đúng
  contract bundle (uidTo + callId số uint32 + status 3 + imei;
  nhóm: calleeId + callId số + callType 5/6 + có hostCall);
  "error" trả inner 500 mô phỏng server từ chối; "slow" ngủ 2 giây
  mô phỏng endcall ì.
- Mới `tests/test_call_end.py` 8 test + `tests/test_app_js_end.js`
  (harness Node vm, stub DOM/fetch — kiểm `endCall()` khi
  currentCall/detailCall null và dòng chẩn đoán ở màn hình chi
  tiết); `run_tests.py` nối thêm 2 lệnh node (`--check app.js` +
  harness). Test PHAI FAIL ở code cũ (chạy trên code 4f40c7e: 1/8 —
  chỉ test bấm đôi qua) và PASS ở code mới (8/8 + harness + toàn
  suite xanh). Các ca: end khi Zalo từ chối → vẫn kết thúc cục bộ
  + detail ghi lỗi; end call_id chuỗi → body Zalo mang số; end id
  sai → kết thúc cuộc live; end chậm → log đã xóa active trước khi
  POST trả về; end 2 lần an toàn; end nhóm → đúng 12438.
- Phiên bản mới: `2026-11-05-call-end-fix`.

**CHƯA ĐẨY — LÝ DO (ghi rõ, không giấu):** lúc làm xong bản này,
checkout `~/workspace/calling-push` đang giữ bản merge lớn CHƯA
COMMIT của điều phối viên UI (chat/services/đăng nhập/webhook/cache
— server.py 65KB so với 28KB ở workdir), và điều phối viên vẫn đang
ghi file (protocol.py sửa cách đây vài giây lúc kiểm tra). Đẩy từ
checkout lúc này sẽ cuốn cả merge chưa xong của người khác; đẩy từ
workdir thì workdir không phải repo git. Fix nằm ở workdir
`~/workspace/zalo-pc-qr/` (đã test xanh toàn suite) + file patch
`fix-call-end.patch` (diff so với 4f40c7e, xem dưới). Trình tự đúng:
điều phối viên commit/push merge trước → áp patch này lên trên (lưu
ý 1 điểm giao nhau: handler `/api/call/end` trong merge có thêm
webhook hook `dispatch_call_event(..., ended_entry, ...)` — khi áp
patch phải giữ lại hook đó, gọi với entry `ended` sau bước
`record_end` local-first; `endCall()` trong merge vẫn là bản cũ nên
patch cho app.js áp thẳng được).

**Kiểm tra sau redeploy:** pull + up (giữ volume `/opt/zalo`,
không quét lại); footer phải hiện `2026-11-05-call-end-fix` (hoặc
sha mới); gọi lại, bấm Kết thúc → cuộc gọi tắt NGAY, pill biến mất,
lịch sử ghi «Đã kết thúc»; màn hình chi tiết hiện dòng «Bước 2
(11301): …» cho biết bước 2 có được server chấp nhận không.

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
- Gọi đi sau bản sửa 114 (xem 7k) — đã kiểm thật 17:51: 114 hết,
  UI «Đang đổ chuông» 00:26, nhưng máy bên kia không hiện cuộc gọi
  đến; xem 7l — bản sửa bước `request` (11301) đã xong, cần gọi thật
  lại để chứng minh máy bên kia đổ chuông ngay (không phải vài phút
  sau / chỉ hiện cuộc gọi nhỡ).
- Nhận cuộc gọi đến, tiếng trực tiếp, độ trễ, độ ổn định — giai đoạn 2.
- Giao diện mới 7j chưa được nhìn bằng trình duyệt thật ở bất kỳ
  chiều rộng nào: inspector của skill không chạy được trên VM (Chrome
  từ chối khởi động headless, xem 7j); chỉ mới kiểm bằng lint + API
  live + đối chiếu số học tay. Lần nhìn đầu tiên phải làm sau deploy:
  1440px (rail 384 có tràn tên nhóm dài không), 768px (sidebar gấp,
  rail xếp dưới), 390px (topbar + pill cuộc gọi có chật không).

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
  call_log.py  media_endpoints.py
  static/  app.html  app.js  style.css  fonts/ (10 file woff2)
tests/
  test_aes.py  test_crypto.py  test_flow_mock.py  test_server_smoke.py
  test_calls.py  test_call_114.py  test_call_11301.py
  test_call_end.py  test_app_js_end.js
  mock_server.py  run_tests.py
fix-call-end.patch  (patch của §7m so với 4f40c7e, áp sau merge UI)
.taste-skill/  direction.json  notes.md
```

---

## Bản gộp 2026-11-05 — app đúng chuẩn addon + docker cũ (VERSION 2026-11-05-addon-day-du)

Gộp từ base `4f40c7e` (sửa 114 + bước request 11301/12434) với 6 phần làm
song song trong các bản copy riêng (điều phối viên tự gộp tay bằng merge
3 chiều, ancestor `01f7ee7`; không lấy file nào đè file nào). Chi tiết
từng phần xem các báo cáo đi kèm trong cùng thư mục:
`bao-cao-doi-chieu-addon.md` (bảng đối chiếu), `bao-cao-429.md`,
`bao-cao-view.md`, `bao-cao-webhook.md`, `BAO-CAO-CHAT.md`.

- **Đăng nhập app** (`app_auth.py`, `static/login.html`): cổng ngoài
  user/mật khẩu qua env `ZALO_PC_APP_USER` + `ZALO_PC_APP_PASSWORD`
  (hoặc `ZALO_PC_APP_PASSWORD_HASH`, hash PBKDF2 210k vòng); mọi
  `/api/*` (trừ login/status) và mọi trang (trừ /login) đều 401/302 khi
  chưa đăng nhập app; phiên cookie 8 giờ. `POST /api/logout` xóa cả
  phiên Zalo lẫn phiên app.
- **Chat theo thread** (`chat.py`): bấm hàng danh bạ mở khung chat kiểu
  Zalo PC — gửi text (11151/11163), file (11146/11191), ảnh
  (11152/11164), ghi âm MediaRecorder rồi gửi mp3 (11148/11169), lịch
  sử nhóm (11240), typing/seen, nút Gọi dùng sẵn signaling.
- **Phủ service** (`services.py`): panel «Dịch vụ» — 50/96 service thao
  tác được (48 qua panel + 2 danh bạ); 25 service chưa có đường PC hiện
  «Chưa hỗ trợ» (409 + lý do, không nút giả); 10 service chỉ thuộc máy
  chủ zalobot phiên web (ghi rõ); 11 service thuộc khung chat.
- **Webhook** (`webhooks.py`): trang cài đặt 4 URL
  (message/group_event/reaction/call) + công tắc + «Gửi thử»; lưu
  `<DATA_DIR>/webhooks.json` (0600); dispatch `call.sent/error/ended`
  bắn ngay; tin nhắn/nhóm/reaction đã có cấu hình + dispatch sẵn nhưng
  chưa có nguồn sự kiện (cần kênh sync O3).
- **429 + số thành viên + load chậm** (`server.py` cache/SWR,
  `contacts.py` member_count): cache contacts TTL 120s; backoff sau 429
  60s (gấp đôi mỗi lần, tối đa 300s); gặp 429 trả cache kèm thời gian
  chờ; nút «Tải lại» khóa tạm + đếm ngược; stale-while-revalidate (trả
  cache cũ ngay + làm mới nền); số thành viên lấy từ
  totalMember/memberIds/currentMems (không đếm topMember); UI giữ danh
  sách cũ khi tải lại lỗi, không để trống 0/0/0. `view-loading` trung
  tính lúc tải trang — không nháy trang QR khi đã đăng nhập.
- **Build trên server** (`docker-compose.build.yml`,
  `HUONG-DAN-BUILD-TREN-SERVER.md`): build image từ source ngay trên
  server (`zalo-pc-app:local`), sau mỗi push chỉ cần pull + up -d
  --build; Portainer KHÔNG build được từ source (có bằng chứng lỗi thật
  18:13 trong hướng dẫn) nên dùng lệnh trực tiếp.

Giới hạn còn lại (nói rõ, không claim đã xong): lịch sử 1-1 không có
endpoint HTTPS; tin đến chưa tự cập nhật (cần sync O3); E2EE nhánh
riêng; ghi âm webm/opus (Zalo thật có thể từ chối vì không phải mp3);
nhiều thao tác service gắn cờ `body_unverified` (path + mã lệnh có
trong bundle thật, body dùng tham số addon); webhook tin nhắn/nhóm/
reaction chưa có nguồn sự kiện; địa chỉ media ở bước 11301 vẫn là
chuỗi rỗng (engine giai đoạn 2 kết luận NO-GO 18:17 — cần disassembly
ZaloCall.exe + capture cuộc gọi PC thật); một tài khoản app duy nhất;
chưa chống brute-force ở `/api/app/login`; chưa kiểm trực quan bằng
trình duyệt thật (Chrome trên VM không khởi động được).
