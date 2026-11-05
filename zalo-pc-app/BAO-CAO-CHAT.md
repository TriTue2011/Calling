# Chat theo thread — bao cao (ban copy `~/workspace/zalo-pc-qr-chat/`)

- Ngay: 2026-11-05. Co so copy: `~/workspace/zalo-pc-qr/` tai thoi
  diem copy (da gom sua loi goi 114 — `VERSION` goc
  `2026-11-05-call-114-fix`; ban nay bump len `2026-11-05-chat`).
- Khong sua `~/workspace/zalo-pc-qr/`, khong sua
  `~/workspace/calling-push/`, khong push. Khong dang nhap that,
  khong goi that, khong gui tin that bang tai khoan nao (chi mock).
- Khong dung `signaling.py` hay body requestcall (loi 114 do agent
  khac sua — ban copy da co sua do).

## 1. File da doi / them (chi trong ban copy)

| File | Thay doi |
|---|---|
| `zalo_pc_app/chat.py` (MOI) | Toan bo logic chat: gui text/file/anh/voice, lich su nhom, typing/seen, `ChatStore` (tin da gui trong phien, RAM), `build_multipart` / `parse_multipart`, `normalize_message`. |
| `zalo_pc_app/server.py` | MOC TOI THIEU (3 cho, deu danh dau `CHAT HOOK`): (a) `_Transport.http_post_multipart` + `_request(..., content_type=...)` — them method, khong doi `http_post` cu; (b) `AppState.chat_store = ChatStore()`; (c) route `GET /api/thread/<id>/history` trong `do_GET`, helper `_chat_client` / `_read_raw` / `_handle_thread_post`, va 3 dong re route `/api/thread/*` o dau `do_POST` (multipart doc raw, khong doc JSON truoc). |
| `zalo_pc_app/__init__.py` | `VERSION = "2026-11-05-chat"`, them `chat_mod` vao `__all__`. |
| `zalo_pc_app/static/app.html` | View moi `view-chat` (head thread, notice, history, composer, nut Goi) + doi subline Danh ba: bam hang mo chat, nut Goi moi goi. |
| `zalo_pc_app/static/app.js` | Bam hang danh ba -> `openThread()` (truoc la `startCall` truc tiep); nut `Goi` tren hang va trong chat van goi `startCall` cu. Them: `loadThreadHistory`, `renderMessages`, `sendChatText`, `sendChatFile`, `toggleRecord` (MediaRecorder), `onChatInput` (typing throttle 4 s), seen sau khi tai lich su. Nut `← Danh ba` trong chat chi `show("view-main")`, KHONG `loadMain()` (tranh goi lai `/api/contacts` -> 429). |
| `zalo_pc_app/static/style.css` | CSS chat: `.chat-wrap/.chat-head/.chat-history/.bubble(-in/-out)/.composer/.notice-box/.rec-state`, dung dung token framed-sheet san co. |
| `tests/mock_server.py` | Them route mock: GET sms/sendmsg/history/typing/seen; POST multipart sharefile_full/sendmp3/voicemp3/photo/sendpt (kiem tra AES params, `type=2/11`, `fileContent`, filename). |
| `tests/test_chat.py` (MOI) | 8 test (xem §3). |
| `tests/run_tests.py` | Them `test_chat.py` vao danh sach. |

## 2. Endpoint da dung cho tung thao tac (ma lenh, bundle PC that)

Tat ca sau login: `zpw_ver=695 & zpw_type=30` + `params=<AES-JSON bang
zpw_enk>` + cookie `zpw_sek`; response envelope hai lop giai ma bang
`crypto.decode_postlogin_data` (giong contacts/signaling).

| Thao tac | Endpoint |
|---|---|
| Gui text 1-1 | GET `{chat-wpa}/api/message/sms` (11151) `{message, clientId, imei, toid}` |
| Gui text nhom | GET `{group-wpa}/api/group/sendmsg` (11163) `{message, clientId, imei, visibility, grid}` |
| Lich su nhom | GET `{group-wpa}/api/group/history` (11240) `{grid, count}` |
| Lich su 1-1 | KHONG CO endpoint — UI hien thong bao gioi han + tin da gui trong phien |
| Dinh kem file 1-1 / nhom | POST multipart `{files-wpa}/api/message/sharefile_full` (11146) / `/api/group/sharefile_full` (11191), `params=<AES {toid\|grid, clientId}>`, `&type=2/11`, FormData `fileContent` |
| Gui anh 1-1 / nhom | POST multipart `{chat-wpa}/api/message/photo` (11152) / `{group-wpa}/api/group/sendpt` (11164), `params=<AES {clientId, desc, width, height, toid\|grid}>`, `&type=2/11`, FormData `fileContent` (width/height doc tu anh that o UI, 0 neu khong biet) |
| Gui file ghi am 1-1 / nhom | POST multipart `{files-wpa}/api/message/voicemp3` (11148) / `/api/group/sendmp3` (11169), `params=<AES {toid\|grid, clientId}>`, `&type=2/11`, FormData `fileContent` = file da ghi |
| Dang go | GET `{chat-wpa}/api/message/typing` (11144) `{toid, destType:"USER", imei}` / `{group-wpa}/api/group/typing` (11196) `{grid, imei}` — UI goi toi da 1 lan/4 s khi go |
| Da xem | GET `{chat-wpa}/api/message/seen` (11150) / `{group-wpa}/api/group/seen` (11167) `{msg_ids:[...]}` — UI goi sau khi tai lich su |

Route server app (moi): `GET /api/thread/<id>/history?type=user|group&count=50`,
`POST /api/thread/<id>/send` (JSON `{type, message}`),
`POST /api/thread/<id>/sendfile` (multipart: field `type`, `kind=file|photo`,
`width`, `height`, `file`),
`POST /api/thread/<id>/sendvoice` (multipart: field `type`, `file`),
`POST /api/thread/<id>/typing`, `POST /api/thread/<id>/seen`
(JSON `{type, msg_ids}`).

## 3. Ket qua test

`python3 tests/run_tests.py` — **ALL TEST SUITES PASSED (9/9)**,
gom `test_chat.py` 8/8:

- `test_send_text_user_and_group` (11151/11163, body AES dung, tin rong -> ValueError)
- `test_group_history` (11240, 2 tin chuan hoa, `has_more=false`)
- `test_user_history_has_no_endpoint` (khong co cuoc goi `/api/message/history` nao trong mock log)
- `test_send_file_photo_voice` (6 duong upload: sharefile/photo/voice x 1-1/nhom)
- `test_typing_and_seen` (11144/11196/11150/11167)
- `test_multipart_roundtrip`, `test_chat_store_local_echo`
- `test_server_thread_routes` (e2e qua server that + mock: 401 khi chua login;
  lich su nhom; lich su 1-1 tra `unavailable` + notice; gui text hien ngay
  trong lich su sau do; gui rong -> 400; sendfile/sendvoice multipart;
  thieu file -> 400; typing/seen; 401 lai sau logout)

Them: `node --check app.js` OK; smoke chay server that + mock: `/`,
`/app.js`, `/style.css` phuc vu du marker `view-chat`, `openThread`,
`toggleRecord`, `chat-history`, `bubble-out`.

## 4. Gioi han con lai (noi ro)

1. **Lich su 1-1:** khong co endpoint HTTPS. UI hien ghi chu
   «Lich su 1-1 chua lay duoc qua HTTPS…» + chi tin gui trong phien.
   Muon lich su cu phai lan tiep `pull_mobile_msg` (12000) /
   `get_backupmsginfo` (12096) / `get_crossdb` (12412) hoac DB local.
2. **Tin den / sync (O3):** khong co endpoint polling; tin den khong
   tu cap nhat. UI co nut «Tai lai lich su» (nhom) + ghi chu o chan
   chat. Can dot lan kenh sync/control rieng hoac webhook (buoc sau).
3. **E2EE:** hoi thoai 1-1 bat E2EE co nhanh `e2eeExt` rieng; code nay
   gui bang 11151 thuong. Neu server tra loi thi UI hien loi; chua co
   cach phat hien E2EE truoc khi gui.
4. **`visibility` (nhom):** gui `0` mac dinh; gia tri that tu
   `getVisibility(convId)` chua lan het — neu gui nhom that bai thi
   day la nghi pham dau tien.
5. **Ghi am:** MediaRecorder cua trinh duyet thuong cho **webm/opus**,
   khong phai mp3; server forward dung file nhan duoc (ten `voice.webm`).
   Zalo that co the tu choi file khong phai mp3 — muon chac mp3 can
   bo ma hoa mp3 (vd. wasm lame) o buoc sau. UI + response deu ghi ro
   «thu am tai trinh duyet roi gui file, khong phai ghi am native».
6. **Lich su nhom:** shape that chua thay truc tiep — `normalize_message`
   best-effort (nhieu key fallback); neu server tra key la thi tin van
   hien o dang tho (co `raw` giu lai).
7. **Anh:** `width/height` lay tu anh that o UI; neu anh loi doc thi
   gui 0 (best-effort).
8. **ChatStore chi RAM:** tin da gui mat khi restart server (giong
   `call_log`). Muon ben thi can DB local (nhu docker cu: 5000 tin/nhom).
9. **File >100 MB** bi server tu choi (400) — gioi han tu dat, chua
   theo gioi han that cua Zalo.

## 5. Agent tich hop can chu y khi gop

- **Dang nhap app (user/mat khau):** CHUA CO trong ban copy nay. Route
  chat hien chi dung `_require_login` (phien Zalo `zpw_sek`, giong
  `/api/contacts`). Khi phan dang nhap app xong, gan them kiem tra
  dang nhap app vao `_require_login` hoac vao dau route history /
  `_handle_thread_post` (2 diem moc `CHAT HOOK` trong `server.py`).
  Khong doi ten route — UI dang goi dung cac path tren.
- **Sua 429:** nut «← Danh ba» trong chat da tranh `loadMain()`; nhung
  `loadThreadHistory` moi lan mo thread van goi 1 lan `group/history`
  (nhom) — neu them polling lich su thi phai co cache/backoff, khong
  poll lien tuc. Nut «Tai lai lich su» la thu cong, khong tu dong.
- **Sua 114 / goi:** khong dung den `signaling.py`, `protocol.py`,
  body requestcall. Nut Goi trong chat goi thang `startCall` cu.
  Ban copy da gom sua 114 (base `2026-11-05-call-114-fix`); khi gop
  ve nhanh chinh chi can giu ca 2 phan (server.py co ca
  `_normalize_call_id` lan `CHAT HOOK`).
- **So thanh vien nhom «0»:** loi da biet (17:45 +07, agent khac sua).
  UI chat CHI hien «N thanh vien» khi `members.length > 0`, khong bao
  gio hien «0 thanh vien». Hang danh ba van dung code cu (chua sua).
- **Webhook / phu service (96):** chat chua co webhook, chua co
  reaction (khong co endpoint gui), chua co undo/delete/forward/quote
  (endpoint da biet: 11281/11192, 11779/11834, 11199/11818, 11771/11197
  — them route tuong tu `_handle_thread_post` khi lam).
- **Merge `server.py`:** 3 diem moc `CHAT HOOK` (import `chat_mod`,
  `http_post_multipart`, `chat_store`, route history, `_handle_thread_post`).
  `protocol.py` KHONG doi (domain chat/files dinh nghia trong `chat.py`).
- **Merge `app.js`:** diem va cham duy nhat la `li.onclick` (mo chat
  thay vi goi ngay) + `VIEWS`/`show()`. Nut Goi tren hang khong doi.
- **Chua kiem tren trinh duyet that:** Chrome tren VM tu choi headless
  (da biet tu dot UI truoc) — can nhin truc quan 1440/768/390px tren
  trinh duyet that sau khi gop + redeploy, dac biet composer o 390px
  (da lam wrap 2 hang) va bong tin dai.
- **Kiem that lan dau (sau gop):** mo thread nhom -> lich su hien;
  gui text nhom -> doi phuong nhan duoc; gui text 1-1 -> neu loi thi
  ghi ma loi (nghi E2EE hoac visibility); gui file/anh/voice -> kiem
  doi phuong mo duoc file khong (dac biet voice .webm).
