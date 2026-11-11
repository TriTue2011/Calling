# 📞 Zalo Calling

Gọi **thoại và video Zalo** từ Home Assistant: điện thoại đổ chuông, nghe máy xong tiếng bên kia ra **loa trong nhà**
(R1, loa camera, `media_player`), mic loa/camera gửi sang điện thoại, video phát hình từ **camera nhà**.

> ⚠️ App không chính thức, đăng nhập Zalo bằng mã QR. **Dùng tài khoản Zalo phụ.**
> Telegram: xem kho riêng [Telegram-calling](https://github.com/TriTue2011/Telegram-calling).

## Thêm nhanh vào Home Assistant

Cần **2 phần**: ① app Zalo (add-on hoặc Docker) và ② tích hợp **Zalo Call** (HACS). Bấm các nút (cần
[My Home Assistant](https://my.home-assistant.io) trỏ về HA của bạn):

| Bước | Nút |
|---|---|
| ① Thêm kho add-on (HAOS / Supervised) | [![Thêm kho add-on](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FTriTue2011%2Fhas-addons) |
| ② Mở tích hợp trong HACS | [![Mở trong HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TriTue2011&repository=Zalo-calling&category=integration) |
| ③ Thêm tích hợp (sau khi tải + khởi động lại HA) | [![Thêm tích hợp](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=zalo_call) |

**Không dùng được nút?** Làm tay:

1. **App:** Cài đặt → Add-on → Cửa hàng → ⋮ → Kho lưu trữ → `https://github.com/TriTue2011/has-addons` → cài **Zalo Calling**
   (hoặc chạy Docker: xem [hướng dẫn đầy đủ](https://github.com/TriTue2011/has-addons/blob/main/zalo_calling/README.md#docker)).
2. **Tích hợp (HACS 2.x):** HACS → **⋮ → Custom repositories** → dán `https://github.com/TriTue2011/Zalo-calling`,
   **Type = Integration** → **Add** → tìm **Zalo Call** trong HACS → **Download** → khởi động lại HA.
3. **Cài đặt → Thiết bị & Dịch vụ → Thêm tích hợp → Zalo Call**: địa chỉ app `http://<IP HA>:8080` + tài khoản WebUI.

Hướng dẫn từng bước, cách cấu hình loa/mic/camera, gọi bằng service, lỗi thường gặp:
**[zalo_calling/README.md](https://github.com/TriTue2011/has-addons/blob/main/zalo_calling/README.md)** (kho has-addons).

## Cách dùng các dịch vụ

Mở **Công cụ nhà phát triển → Hành động**, gõ `zalo_call.` để chọn dịch vụ (mỗi trường có ô chọn). Người nhận là `thread_id` + `type` (`user` = 1-1, `group` = nhóm).
Lấy `thread_id`: dịch vụ `get_all_friends` / `get_all_groups` (kết quả trả về cho automation), hoặc mở WebUI của app → danh bạ.

### Gọi đi

```yaml
service: zalo_call.make_call
data:
  thread_id: "6643404425553198601"
  type: video                          # user = thoại 1-1 · video = video 1-1 · group = nhóm
  volume: 70                           # tuỳ chọn, 0-100: âm lượng loa lúc gọi, hết cuộc tự trả lại mức cũ
  speaker: media_player.loa_phong_khach   # tuỳ chọn; bỏ trống = ô «Loa mặc định» trên thiết bị Zalo Call
  mic: camera.phong_khach              # tuỳ chọn: tiếng từ camera hoặc loa R1 (Assist satellite) gửi sang điện thoại
  camera: camera.phong_khach           # tuỳ chọn (cuộc gọi video): hình gửi đi; bỏ trống = «Camera mặc định»
```

Điện thoại đổ chuông; nghe máy xong tiếng bên kia ra loa, mic loa/camera gửi sang họ. Kết thúc: `zalo_call.end_call` (cũng dùng để huỷ khi còn đổ chuông).
Đang gọi thoại muốn lên video: `zalo_call.upgrade_to_video` (xin bên kia, rồi phát camera đã chọn).

### Nhận cuộc gọi

Có người gọi tới tài khoản Zalo → HA bắn sự kiện **`zalo_call_call_state`** (cũng là cảm biến *Cuộc gọi* trên thiết bị). Trường `state`:
`incoming` (đang đổ chuông) · `ringing` (mình gọi, bên kia đang đổ chuông) · `answered` (đã nối) · `declined` · `no_answer` · `missed` · `rejected` · `ended` · `error`;
kèm `call_id`, `thread_id`, `peer`, `call_type`, `end_reason`. Nghe/từ chối bằng `zalo_call.answer_call` / `zalo_call.reject_call` (bỏ `call_id` nếu chỉ có một cuộc).

```yaml
automation:
  - alias: Zalo gọi đến → báo điện thoại, tự nghe sau 10 giây
    triggers:
      - trigger: event
        event_type: zalo_call_call_state
        event_data: {state: incoming}
    actions:
      - action: notify.mobile_app_dien_thoai
        data: {message: "Zalo gọi đến từ {{ trigger.event.data.peer }}"}
      - delay: 10
      - action: zalo_call.answer_call
        data: {volume: 60}
```

Công tắc trên thiết bị: *Tự phát mic khi nghe máy*, *Tự đồng ý khi bên kia xin gọi video*; ô *Chống vọng* (nếu loa R1 bị nhại tiếng: đặt **Song công** và R1 chọn engine **nâng cao**).

### Tin nhắn, tệp, ghi âm

| Việc | Dịch vụ | Ví dụ |
|---|---|---|
| Gửi chữ | `send_message` | `message: "Xin chào"` (định dạng/màu/emoji: mục dưới) |
| Gửi ảnh / tệp / video | `send_image` · `send_file` · `send_video` | `file: /config/www/anh.jpg` (đường dẫn trong thư mục cho phép, hoặc URL) |
| Gửi **tin thoại** | `send_voice` | `file: /config/www/loi-chao.mp3` (mp3/m4a/wav, tự đổi sang AAC); phản hồi có `voice_url` |
| Gửi liên kết có xem trước | `send_link` | `link: https://...`, `message: "xem nè"` |
| Sticker theo từ khoá | `send_sticker` | `keyword: "cảm ơn"`, `pick: random` |
| Thả cảm xúc / trả lời / thu hồi | `add_reaction` · `quote_message` · `undo_message` | `icon: heart` (bảng 54 biểu tượng), `msg_id`, `cli_msg_id` |
| Dịch bằng Zalo AI | `translate_message` | `msgId`, `threadId`, `srcLang: vi`, `desLang: en`, `text` (thử thật với `en`, `ko`) |
| Giọng nói → chữ (STT) | `voice_to_text` | `voiceUrl:` đường dẫn tin thoại **nhận từ người khác**; kết quả ở sự kiện `zalo_call_voice_to_text` (`req_id`, `text`) |
| Đọc nhóm | `get_group_chat_history`, `get_all_groups` | trả dữ liệu cho automation (`response_variable`) |

`msg_id` / `cli_msg_id` lấy từ phản hồi lúc gửi hoặc từ sự kiện **`zalo_call_message`** (tin đến: `content`, `thread_id`, `thread_type`, `is_self`…).

**Gửi tin có TTS của HA thành tin thoại:** tạo tệp âm thanh bằng `tts.speak`/`tts.google_translate_say` ra `/config/www/`, rồi `zalo_call.send_voice` với `file:` trỏ tới tệp đó.

## Định dạng chữ: cỡ chữ, màu, đậm, nghiêng, gạch chân, tiêu đề

Zalo cá nhân có **hai cỡ chữ** (nhỏ, to), **bốn màu** (đỏ, cam, vàng, xanh lá), đậm, nghiêng, gạch chân, gạch ngang và danh sách. Zalo Call cho cài đặt kiểu chữ **một lần trên thiết bị**
(áp cho mọi tin tích hợp gửi, kể cả trả lời của AI) và **ghi đè từng tin** ở dịch vụ `send_message`. Mỗi mục có thêm chế độ **`auto`**: tự định dạng theo nội dung chữ.

### Cài đặt mặc định (thiết bị Zalo Call → nhóm *Cấu hình*)

| Ô trên thiết bị | Giá trị | Ý nghĩa |
|---|---|---|
| **Chữ: cỡ chữ** | `off` · `small` · `big` · `auto` | `small`/`big`: cả tin nhỏ/to. `auto`: tiêu đề to, dòng nằm trọn trong ngoặc `(…)` nhỏ |
| **Chữ: màu chữ** | `off` · `auto` · `red` · `orange` · `yellow` · `green` | Màu cố định cho cả tin. `auto`: chỉ **con số** (29°C, 75%, 15:30, 10/11) được tô màu «màu dùng cho chế độ auto» |
| **Chữ: in đậm** | `off` · `on` · `auto` | `on`: cả tin. `auto`: con số |
| **Chữ: in nghiêng** | `off` · `on` · `auto` | `on`: cả tin. `auto`: đoạn trong `"…"` `“…”` `‘…’` hoặc `(…)` |
| **Chữ: gạch chân** | `off` · `on` · `auto` | `on`: cả tin. `auto`: liên kết `http(s)://…` và địa chỉ email |
| **Chữ: tiêu đề dòng đầu** | `off` · `on` · `auto` | `on`: dòng đầu thành **to + đậm**. `auto`: chỉ khi tin có nhiều dòng, dòng đầu ≤ 60 ký tự và **không** kết thúc bằng dấu câu (`. ! ? … , ;`); dòng ngắn kết thúc bằng `:` thành đề mục (đậm) |
| **Chữ: màu dùng cho chế độ auto** | `red` · `orange` · `yellow` · `green` | Màu của «màu chữ = auto» (mặc định `red`) |

Mặc định mọi mục là `off` (tin gửi đi như cũ). Quy tắc `auto` dựa trên **hình dạng** của chữ (số, dấu ngoặc, liên kết, dấu câu), không dựa danh sách từ khoá.

### Ghi đè từng tin: `zalo_call.send_message`

Các trường tương ứng (đều tuỳ chọn; **bỏ trống = theo mặc định trên thiết bị**, có điền = ghi đè cho tin này):

| Trường dịch vụ | Tương ứng ô thiết bị |
|---|---|
| `font_size` | cỡ chữ |
| `text_color` | màu chữ |
| `bold` · `italic` · `underline` · `heading` | in đậm · nghiêng · gạch chân · tiêu đề |
| `auto_color` | màu dùng cho chế độ auto |

```yaml
# Mặc định trên thiết bị: tiêu đề = auto, màu chữ = auto. Tin này thêm: số in đậm, không tô màu.
service: zalo_call.send_message
data:
  thread_id: "6643404425553198601"
  type: user
  message: |
    Báo cáo nhà hôm nay
    Nhiệt độ 29°C, độ ẩm 75% lúc 15:30
    Chi tiết: https://example.com
  bold: auto            # con số in đậm
  text_color: off       # ghi đè «màu chữ = auto» của thiết bị, tin này không tô màu
```

Kết quả: dòng đầu **to + đậm** (tiêu đề auto), `29°C`, `75%`, `15:30` in đậm, liên kết giữ nguyên.

### Thứ tự ưu tiên

1. **Đánh dấu tường minh trong chữ** (markdown, thẻ màu) luôn thắng: cỡ và màu mặc định/auto **không đè** lên chỗ đã có cỡ hoặc màu.
2. **Trường của dịch vụ** `send_message` ghi đè **cài đặt mặc định** trên thiết bị.
3. **Cài đặt mặc định** trên thiết bị (áp cả cho trả lời của AI tự trả lời).

### Đánh dấu tay trong chữ (`format: markdown`)

| Viết | Ra |
|---|---|
| `**đậm**` · `*nghiêng*` · `__gạch chân__` · `~~gạch ngang~~` | đậm · nghiêng · gạch chân · gạch ngang |
| `# Tiêu đề` | to + đậm |
| `- mục` · `1. mục` | danh sách chấm · đánh số |
| `{red}đỏ{/}` `{orange}` `{yellow}` `{green}` (hoặc `{đỏ}` `{cam}` `{vàng}` `{xanh}`) | màu |
| `{big}to{/}` · `{small}nhỏ{/}` | cỡ chữ (chỉ hai cỡ) |
| `\*` | ký tự `*` nguyên văn |

Có thể kết hợp với `auto_emphasis` (tự tô số và chữ đậm), `emoji`, `zalo_emoji`, `auto_emoji`: xem mục tiếp.

### Emoji

| Trường | Làm gì |
|---|---|
| `emoji` | Chọn trong bảng 35 biểu tượng hoặc gõ emoji bất kỳ: chèn vào đầu tin. Mã `:ok:` `:canhbao:`… trong chữ cũng đổi thành emoji |
| `zalo_emoji` | Emoji **của Zalo** (heart, haha, wow, cry…): chèn mã (`/-heart`, `:>`…) vào đầu tin, Zalo hiện thành ảnh emoji như trong bảng emoji của ô chat |
| `auto_emoji` | Tự thêm một emoji hợp ngữ cảnh vào đầu từng dòng chưa có (cảnh báo, lỗi, xong, nhiệt độ, cửa, đèn…). Bảng nhỏ, bảo thủ, mặc định tắt |
| `auto_emphasis` | `red`/`orange`/`yellow`/`green` hoặc `true`: tô màu + in đậm con số và chữ đã in đậm (gần giống «màu chữ = auto» kèm «in đậm = auto», nhưng chọn được màu ngay ở đây) |

Sticker: `zalo_call.send_sticker` với `keyword: "cảm ơn"` (và `pick: random`) tự tìm rồi gửi. Thả cảm xúc lên một tin: `zalo_call.add_reaction` với `icon: heart` (bảng 54 biểu tượng).

**Trả lời của AI tự trả lời:** dùng cùng cài đặt mặc định ở trên, cộng thêm ô *AI: định dạng chữ trả lời* (mặc định `markdown`, để dấu `**` của AI thành chữ đậm thật), *AI: tự nhấn mạnh số…* và công tắc *AI tự thêm emoji vào trả lời*.

## Kho này gồm

| Thư mục | Là gì |
|---|---|
| `custom_components/zalo_call/` | Tích hợp Home Assistant (HACS bắt buộc đặt ở gốc kho; **một tích hợp mỗi kho**) |
| `zalo/zalo-pc-app/` | App Zalo dạng PC chạy Docker: đăng nhập QR, gọi thoại/video, WebUI. Ảnh `ghcr.io/tritue2011/zalo-calling` |
| `tests/` | Test của tích hợp (bộ test của app nằm trong `zalo/zalo-pc-app/tests/`) |
| `.github/workflows/` | `ci.yml` (test), `release.yml` (thẻ `vX` → Release + `zalo_call.zip`), `image.yml` (thẻ `vX` → ảnh Docker) |

Phát hành: đẩy thẻ `vX.Y.Z.N` khớp `version` trong `custom_components/zalo_call/manifest.json`.
Chi tiết kỹ thuật của app: [`zalo/README.md`](zalo/README.md).
