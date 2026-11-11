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
  speaker: media_player.loa_phong_khach   # tuỳ chọn; bỏ trống = loa mặc định đặt bằng dịch vụ `set_default_devices`
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

Loa/mic/camera mặc định và các tuỳ chọn đi kèm đặt bằng dịch vụ **`zalo_call.set_default_devices`** (`speaker`, `mic`, `mic_url`, `camera`, `call_volume`, `auto_mic` = tự phát mic khi nghe máy, `auto_video` / `auto_video_delay` = tự đồng ý khi bên kia xin gọi video, `echo_guard` = chống vọng; nếu loa R1 bị nhại tiếng: đặt `duplex` và R1 chọn engine **nâng cao**). Xem lại bằng `get_default_devices`.

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
| **Chữ: AI trả lời tự định dạng trong cùng lượt** | công tắc (mặc định **bật**) | Mức 1 bên dưới: AI tự định dạng khi trả lời, không chậm thêm |
| **Chữ: dùng AI đánh giá khi gửi send_message** | công tắc (mặc định tắt) | Mức 3 bên dưới: nhờ trợ lý đánh giá ngữ cảnh cho các mục `auto` (thêm vài giây) |
| **Chữ: trợ lý AI dùng cho chế độ auto** | chọn trợ lý hội thoại | Nên chọn trợ lý nhỏ/nhanh; Không = trợ lý của AI trả lời |
| **Chữ: tự thêm emoji (auto)** | công tắc **bật / tắt** | Bật: mọi tin tích hợp gửi tự có một emoji hợp ngữ cảnh ở đầu từng dòng chưa có emoji (xem mục Emoji). Mặc định tắt |

Mặc định mọi mục là `off` (tin gửi đi như cũ). Quy tắc `auto` dựa trên **hình dạng** của chữ (số, dấu ngoặc, liên kết, dấu câu), không dựa danh sách từ khoá.

### `auto` hoạt động thế nào: nhanh hay theo ngữ cảnh

Mục đích của `auto` là **tự đánh giá ngữ cảnh** để chọn màu, cỡ chữ, đậm/nghiêng, tiêu đề và emoji cho hợp. Có ba mức, **mặc định không làm chậm tin nhắn**:

| Mức | Khi nào | Tốc độ |
|---|---|---|
| **1. AI tự định dạng trong cùng lượt** | Câu trả lời của **AI tự trả lời** (mặc định bật, công tắc *Chữ: AI trả lời tự định dạng trong cùng lượt*): tích hợp nhúng một chỉ dẫn ngắn vào chính câu hỏi gửi trợ lý, trợ lý vừa trả lời vừa tự chọn đậm, màu, tiêu đề, emoji theo nội dung | **Không chậm thêm** (cùng một lần gọi) |
| **2. Quy tắc tức thì** | Mọi tin còn lại, và khi trợ lý quên định dạng: `auto` dùng quy tắc theo hình dạng chữ ở bảng trên (số, ngoặc, liên kết, dấu câu) | **Tức thì** |
| **3. Nhờ AI đánh giá riêng** (tuỳ chọn) | `send_message` có mục `auto` hoặc `auto_emoji`, và bật công tắc *Chữ: dùng AI đánh giá khi gửi send_message* hoặc `ai_style: true` | **Thêm vài giây** (một lần gọi trợ lý; quá 8 giây thì bỏ, dùng mức 2). Tin dưới 24 ký tự bỏ qua |

Mức 3: trợ lý hội thoại của HA đọc tin rồi đánh dấu định dạng + emoji theo ngữ cảnh (cảnh báo → đỏ, thành công → xanh lá, đề mục, nhấn mạnh…).
**Có kiểm soát:** trợ lý chỉ được chèn định dạng và emoji; app **chỉ nhận khi chữ gốc không bị đổi** (thêm/bớt/sửa một chữ là bỏ cả đánh dấu của AI và dùng mức 2). Lỗi hoặc quá giờ cũng quay về mức 2, tin vẫn gửi bình thường.
Muốn nhanh hơn nữa: chọn ở ô *Chữ: trợ lý AI dùng cho chế độ auto* một trợ lý **nhỏ/nhanh** (Không = dùng trợ lý của AI trả lời, rồi trợ lý mặc định của HA). Mức 3 tốn thêm token của trợ lý.

Các mục để giá trị cố định (`on`, `small`, `big`, một màu cụ thể…) luôn được áp chắc chắn, không qua AI. Công tắc **Chữ: tự thêm emoji** cũng theo ba mức trên:
bật cho câu trả lời của AI thì AI tự chọn emoji; tin do người dùng **tự gắn emoji** rồi gửi thì giữ nguyên, các dòng đã có emoji không bị thêm nữa.

### Ghi đè từng tin: `zalo_call.send_message`

Các trường tương ứng (đều tuỳ chọn; **bỏ trống = theo mặc định trên thiết bị**, có điền = ghi đè cho tin này):

| Trường dịch vụ | Tương ứng ô thiết bị |
|---|---|
| `font_size` | cỡ chữ |
| `text_color` | màu chữ |
| `bold` · `italic` · `underline` · `heading` | in đậm · nghiêng · gạch chân · tiêu đề |
| `auto_emoji` | công tắc tự thêm emoji (`true` / `false`) |
| `ai_style` | `true` / `false`: nhờ AI đánh giá ngữ cảnh cho tin này (mức 3) hay dùng quy tắc tức thì; bỏ trống = theo công tắc |
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
| `auto_emoji` | `true` / `false`: bật / tắt tự thêm emoji **cho tin này**, ghi đè công tắc *Chữ: tự thêm emoji* trên thiết bị (bỏ trống = theo công tắc). Mỗi dòng chưa có emoji được thêm một emoji hợp ngữ cảnh (cảnh báo, lỗi, xong, nhiệt độ, cửa, đèn…); bảng nhỏ, bảo thủ |
| `auto_emphasis` | `red`/`orange`/`yellow`/`green` hoặc `true`: tô màu + in đậm con số và chữ đã in đậm (gần giống «màu chữ = auto» kèm «in đậm = auto», nhưng chọn được màu ngay ở đây) |

Sticker: `zalo_call.send_sticker` với `keyword: "cảm ơn"` (và `pick: random`) tự tìm rồi gửi. Thả cảm xúc lên một tin: `zalo_call.add_reaction` với `icon: heart` (bảng 54 biểu tượng).

**Trả lời của AI tự trả lời:** dùng cùng cài đặt mặc định ở trên, cộng thêm ô *AI: định dạng chữ trả lời* (mặc định `markdown`, để dấu `**` của AI thành chữ đậm thật), và *AI: tự nhấn mạnh số…*. Công tắc *Chữ: tự thêm emoji* cũng áp cho trả lời của AI.

## Cuộc gọi, AI và cảnh báo: hướng dẫn dễ hiểu

Mọi thứ đặt bằng **dịch vụ** (Công cụ nhà phát triển hoặc automation). Quy ước chữ trong hướng dẫn này:
- **Thiết bị nhà** = loa, mic, camera trong nhà bạn.
- **Người nhà nói trực tiếp** = người trong nhà tự nói chuyện với người gọi (sau khi AI chuyển cuộc gọi, hoặc bạn bấm nút).
- **Trợ lý giọng nói** = bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). AI dùng bộ này để nghe, trả lời và đọc.

### Nguyên tắc riêng tư (luôn đúng)
1. **Chưa có quy tắc cho một người thì hệ thống không làm gì** với người đó: cuộc gọi chỉ đổ chuông, tin nhắn không đi đâu.
2. **Thiết bị nhà tắt mặc định.** Chỉ dùng thứ bạn **đã chọn** và đã **tích**; chưa tích hoặc chưa chọn là không dùng, AI cũng không tự dùng được.
3. **Lúc AI đang nói chuyện thì chưa bật thiết bị nhà.** Chỉ khi người nhà nói trực tiếp mới bật.
4. Muốn AI nói chuyện thì phải chọn Trợ lý giọng nói (hoặc Trợ lý AI riêng): hệ thống không tự dùng bộ ưu tiên vì nó có quyền điều khiển nhà.

### 3 dịch vụ chính, dùng khi nào

| Dịch vụ | Dùng khi | Chuyện xảy ra |
|---|---|---|
| **Gọi điện đi** (`make_call`) | Bạn hoặc automation muốn gọi ai đó | Chỉ gọi / đọc một thông báo rồi cúp / cho AI nói chuyện |
| **Gọi cảnh báo** (`alert_call`) | Báo động: có người ngã, trộm, cháy, mất điện, rò nước | AI đọc cảnh báo, không hỏi gì, rồi làm theo ô «Đọc cảnh báo xong thì» |
| **Đặt quy tắc cho cuộc gọi đến và tin nhắn** (`set_rule`) | Có người gọi hoặc nhắn vào nhà | Theo quy tắc: đổ chuông / báo ra loa / tự nghe máy / cho AI nghe |

### Các trường hợp cuộc gọi đi

| Bạn làm | Chuyện xảy ra |
|---|---|
| Gọi điện đi, không điền gì thêm | Gọi thường. Người nhận nghe máy thì dùng thiết bị mặc định như trước. |
| Gọi điện đi + **Nội dung đọc** | Người nhận nghe máy, hệ thống đọc rồi **tự cúp**. |
| Gọi điện đi + **Cho AI nói chuyện** | AI chào trước (hoặc đọc nội dung), rồi nói chuyện. Thiết bị nhà **chưa bật** (trừ thứ bạn tích ở ô «dùng NGAY khi người nhận nghe máy», ví dụ chỉ Camera). |
| ...trong lúc AI nói chuyện, người gọi muốn gặp người nhà hoặc khẩn cấp | AI chuyển cho người nhà: cuộc gọi **không cúp**, thiết bị nhà bật theo ô «Thiết bị nhà dùng khi người nhà nói trực tiếp». |
| ...người gọi nói «không cần gì nữa» / tạm biệt | AI chào lại rồi **tự cúp**. |
| **Gọi cảnh báo** báo người ngã, trộm (không chọn gì thêm) | Đọc cảnh báo, rồi **dùng tất cả thiết bị nhà đã cài, gồm camera** (cuộc gọi là video). |
| **Gọi cảnh báo** báo mất điện, rò nước (chọn «Cúp máy») | Đọc cảnh báo xong là **tự cúp**. |
| **Gọi cảnh báo** + «Giữ máy» | Đọc xong giữ máy; người nhận hoặc automation tự cúp bằng dịch vụ «Kết thúc cuộc gọi». |

Mọi cảnh báo đọc xong đều bắn sự kiện `zalo_call_alert_done` (có `after`, `connected`, `ended`) để automation biết **đúng lúc đó**.

### Ô tích «Thiết bị nhà dùng khi người nhà nói trực tiếp» (`connect`)
Có ở Gọi điện đi, Nghe máy, Gọi cảnh báo và quy tắc. **Tích ô nào dùng thứ đó**:

| Bạn tích | Dùng |
|---|---|
| (không tích gì) | Không dùng thiết bị nhà nào (mặc định) |
| Mic | Chỉ mic |
| Loa | Chỉ loa |
| Camera | Chỉ camera, **và cuộc gọi là video** (cuộc thoại thì được nâng lên video) |
| Mic + Loa | Nói chuyện qua loa và mic (thoại hoặc video không hình) |
| Loa + Camera | Nghe người gọi và gửi hình, không gửi tiếng trong nhà |
| Mic + Loa + Camera | Dùng cả ba |
| **AI tự chọn** (kèm các ô muốn cho phép) | AI quyết dùng mic và loa, hay thêm camera (khẩn cấp cần xem hình), chỉ trong các ô đã tích |

**Nối ngay hay chờ?** Ô này chỉ bật thiết bị **khi người nhà nói trực tiếp**. Muốn một thứ bật **ngay khi người nhận nghe máy** thì tích thêm ở ô **«Thiết bị nhà dùng NGAY khi người nhận nghe máy»** (`connect_now`, mặc định không tích gì). Ví dụ: tích Camera ở ô «ngay» và Mic + Loa ở ô «khi người nhà nói trực tiếp» thì người nhận thấy hình trong nhà từ đầu, còn tiếng trong nhà chỉ bật khi bạn hoặc AI chuyển cho người nhà.

Muốn chọn **thiết bị nào** thì dùng các ô Loa, Mic, Camera. Gọi video mà không nêu `type`: tích Camera là gọi video, không tích là gọi thoại.

### Báo ra loa khi có cuộc gọi đến (bật/tắt, mặc định TẮT)
Trong quy tắc (`set_rule`): bật **«Báo ra loa khi có cuộc gọi đến»** và chọn **«Loa dùng để báo»**. Khi người đó gọi đến, loa đọc «Có cuộc gọi thoại/video từ (tên)», kể cả khi bạn không cho tự nghe máy. Đổi câu bằng **«Câu báo ra loa»** (dùng `{ten}`, `{loai}`). Giọng đọc lấy từ Trợ lý giọng nói của quy tắc.

### Cuộc gọi đến theo quy tắc

| Quy tắc | Chuyện xảy ra |
|---|---|
| Không có quy tắc cho người đó | Chỉ đổ chuông. Bạn tự nghe hoặc từ chối. |
| Có quy tắc, bật «Báo ra loa» | Loa trong nhà báo «Có cuộc gọi...». |
| Bật «Tự nghe máy» | Sau «Nghe máy sau (giây)» thì tự nghe (người gọi cúp trước thì không nghe). |
| Bật thêm «Cho AI nói chuyện khi nghe máy» | AI chào và nói chuyện như bảng cuộc gọi đi. |

Quy tắc chọn theo **ai gọi**: một người hoặc nhóm cụ thể (ưu tiên cao nhất, thay hẳn quy tắc chung) / mọi nhóm / mọi người trong danh bạ / mọi người lạ. Chưa biết người gọi quen hay lạ (danh bạ chưa tải) thì chỉ quy tắc của người cụ thể được áp.

### Sự kiện cho automation

| Sự kiện | Khi nào |
|---|---|
| `zalo_call_call_state` | Mọi thay đổi của cuộc gọi: đổ chuông, nghe máy, kết thúc... |
| `zalo_call_ai_handover` | AI chuyển cho người nhà (và khi cảnh báo nối thiết bị): `reason`, `connected`, `camera` |
| `zalo_call_alert_done` | Cảnh báo đã đọc xong: `after`, `connected`, `ended`, `thread_id` |
| `zalo_call_voice_text` | Tin thoại đã được chuyển thành chữ |

### Ví dụ
```yaml
# Quy tắc cho một người: nghe sau 5 giây, AI nói chuyện, báo ra loa phòng khách, khi chuyển trực tiếp dùng mic+loa+camera
- action: zalo_call.set_rule
  data: {scope: thread, thread_id: "6643404425553198601", name: Đại ca, answer: true, answer_delay: 5,
         ai: true, pipeline: Chatgpt, trusted: true,
         announce: true, announce_to: media_player.loa_phong_khach,
         connect: [mic, speaker, camera], speaker: media_player.r1_loa, mic: assist_satellite.r1, camera: camera.phong_khach}
# Báo người ngã: đọc rồi dùng tất cả thiết bị đã cài (gồm camera)
- action: zalo_call.alert_call
  data: {thread_id: "6643404425553198601", message: "Phát hiện có người ngã ở phòng khách"}
# Báo mất điện: đọc xong tự cúp
- action: zalo_call.alert_call
  data: {thread_id: "6643404425553198601", message: "Nhà đang mất điện", after: hangup}
```

### Quy tắc cuộc gọi đến: các ô của `set_rule`
Ô nào không nêu thì giữ như cũ (quy tắc mới: tắt hết).

| Nhóm | Ô | Ý nghĩa |
|---|---|---|
| Áp dụng cho | Áp dụng cho, Mã Zalo, Tên gọi | Ai (xem danh sách bằng «Xem danh bạ Zalo») |
| Nghe máy | Tự nghe máy, Nghe máy sau (giây), Nghe loại cuộc gọi nào | Tự nghe sau 0-120 giây; thoại, video hoặc cả hai |
| Báo ra loa | Báo ra loa..., Loa dùng để báo, Câu báo ra loa | Báo người trong nhà biết có cuộc gọi (mặc định tắt) |
| AI | Cho AI nói chuyện, Trợ lý giọng nói, Trợ lý AI riêng, Câu AI chào, AI chuyển cho người nhà khi..., Người tin cậy | AI nói chuyện; người tin cậy thì AI không bị dặn «đừng tiết lộ thông tin nhà» |
| Tin nhắn | AI trả lời tin nhắn, Chuyển tin thoại thành chữ | AI trả lời tin chữ (nhóm thì trả lời vào nhóm) |
| Thiết bị nhà | Thiết bị nhà dùng khi người nhà nói trực tiếp, Loa, Mic, Camera, Âm lượng, Chống vọng âm | Xem bảng ô tích ở trên |

Các dịch vụ khác: «Xoá quy tắc», «Xem các quy tắc», «Xem danh bạ Zalo», «Người nhà nói trực tiếp (dừng AI)» (cũng là một nút trên thiết bị), «Kết thúc cuộc gọi».

### Dùng bằng giọng nói qua Assist
Tích chọn **«Zalo Call»** cạnh «Assist» trong cài đặt trợ lý hội thoại LLM: «gọi cho Đại ca», «nghe máy», «từ chối», «cúp máy», «nhắn nhóm AI học hỏi…», «tiếp quản cuộc gọi». Trong cuộc gọi do AI giữ, trợ lý chỉ thấy **một** công cụ «chuyển sang trực tiếp» nên người lạ không sai khiến được gọi điện/nhắn tin.

### Lưu ý
- STT của Zalo chỉ chuyển được tin thoại do **app Zalo thật gửi** (nằm trong kho thoại Zalo); không dùng được cho cuộc gọi trực tiếp (âm thanh khác bị Zalo từ chối, mã 212). Trong cuộc gọi, STT của Assist pipeline lo phần đó.
- Tính năng giọng nói/AI trong cuộc gọi mới kiểm bằng test giả lập và hai cuộc gọi thử, chưa nhiều cuộc gọi thật; log: `custom_components.zalo_call.call_voice`.


## WebUI: mọi dịch vụ đều làm được trên tab «Dịch vụ»

Tab **Dịch vụ** của WebUI liệt kê **toàn bộ** dịch vụ (dịch vụ gốc + các API mở rộng của zca-js, gom theo nhóm) và có ô **Tìm dịch vụ**. Chọn thread ở ô «Thread thao tác» rồi bấm **Chạy**:

- **Gửi tin** (`send_message`): đủ cỡ chữ, màu chữ, in đậm, nghiêng, gạch chân, tiêu đề (mỗi mục có chế độ *auto*), emoji, emoji Zalo, tự thêm emoji, tự nhấn mạnh số. Cùng bảng lựa chọn với dịch vụ trong HA.
- **Gửi tệp / ảnh / video / ghi âm / liên kết**: chọn tệp ngay trên trang.
- **Sticker**: nhập Sticker ID hoặc chỉ cần *từ khoá* (tự tìm rồi gửi; `pick: random` để chọn ngẫu nhiên).
- **Tài khoản, webhook, mã QR, danh bạ**: nút xem/đặt/xoá tương ứng.
- **API mở rộng (hơn 200 API)**: mỗi API một form; trường `threadId`/`groupId`/`type` để trống thì lấy từ thread đang chọn; API cần tham số phức tạp thì dán JSON vào ô `params`. API nguy hiểm (xoá, rời nhóm…) có hộp xác nhận.
- Chỉ **không áp dụng**: gửi danh thiếp (`send_card`, app chưa có đường gửi) và proxy theo tài khoản (app chạy một tài khoản); hai loại này hiện lý do thay vì form.

Một test (`tests/test_app_js_all_services.js`) bắt buộc mọi dịch vụ trong danh mục phải có dòng form/nút, nên thêm dịch vụ mới mà quên WebUI thì CI đỏ.

## Bình chọn nhóm: lọc người chưa bình chọn, xoá khỏi nhóm (WebUI)

Mở WebUI của app (`http://<IP>:8080`) → mục **Bình chọn nhóm**:

1. Chọn **nhóm** → **Tải bình chọn**: hiện các bình chọn của nhóm (câu hỏi, mở/đóng, số người đã chọn). Mặc định tick các bình chọn **đang mở**; bình chọn **ẩn danh** không có danh sách người chọn nên không dùng được.
2. Chọn cách lọc rồi **Hiện người chưa bình chọn**:
   - *không bình chọn cuộc nào* (mặc định, an toàn nhất), *bỏ sót ít nhất một cuộc*, hoặc *bình chọn ít hơn N cuộc*.
   - Bình chọn cho chọn nhiều phương án thì ai có tên ở bất kỳ phương án nào đều tính là đã trả lời.
3. Tick người cần xoá, rồi **Xoá người đã chọn** hoặc **Xoá toàn bộ người chưa bình chọn** (xoá từng đợt tối đa 10 người, cách nhau 1,5 giây, có nút **Dừng**). Cả hai đều bắt bạn **gõ đúng số người** để xác nhận. Xoá **không hoàn tác được**.

An toàn: **trưởng nhóm, phó nhóm và chính tài khoản Zalo này không bao giờ nằm trong danh sách** (hiện ở mục «Được giữ lại»). Mỗi lần xoá, máy chủ **tính lại** danh sách từ dữ liệu mới nhất và chỉ xoá ID nằm trong đó. Nhóm lớn mà danh sách thành viên chưa đủ thì chỉ cho xem, không cho xoá.
Cần là **trưởng nhóm hoặc phó nhóm** thì Zalo mới cho xoá người; không đủ quyền thì từng người báo lỗi.

Gọi bằng API (cùng đăng nhập app): `GET /api/group/<id>/polls`, `POST /api/group/<id>/poll_non_voters` (`poll_ids`, `mode`: `none`/`any`/`min`, `min_votes`),
`POST /api/group/<id>/remove_members` (thêm `confirm: true` và `member_ids` hoặc `all: true`).

## Kho này gồm

| Thư mục | Là gì |
|---|---|
| `custom_components/zalo_call/` | Tích hợp Home Assistant (HACS bắt buộc đặt ở gốc kho; **một tích hợp mỗi kho**) |
| `zalo/zalo-pc-app/` | App Zalo dạng PC chạy Docker: đăng nhập QR, gọi thoại/video, WebUI. Ảnh `ghcr.io/tritue2011/zalo-calling` |
| `tests/` | Test của tích hợp (bộ test của app nằm trong `zalo/zalo-pc-app/tests/`) |
| `.github/workflows/` | `ci.yml` (test), `release.yml` (thẻ `vX` → Release + `zalo_call.zip`), `image.yml` (thẻ `vX` → ảnh Docker) |

Phát hành: đẩy thẻ `vX.Y.Z.N` khớp `version` trong `custom_components/zalo_call/manifest.json`.
Chi tiết kỹ thuật của app: [`zalo/README.md`](zalo/README.md).
