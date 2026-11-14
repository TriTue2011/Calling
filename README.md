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

## Mục lục

1. [Quy ước và nguyên tắc riêng tư](#1-quy-ước-và-nguyên-tắc-riêng-tư)
2. [Dịch vụ cuộc gọi, AI, cảnh báo và quy tắc: mã đầy đủ và giải thích từng ô, từng lựa chọn](#2-dịch-vụ-cuộc-gọi-ai-cảnh-báo-và-quy-tắc)
3. [Các trường hợp xảy ra, giải thích dễ hiểu](#3-các-trường-hợp-xảy-ra)
4. [Nhận cuộc gọi, sự kiện và ví dụ automation](#4-nhận-cuộc-gọi-sự-kiện-và-ví-dụ-automation)
5. [Tin nhắn, tệp, ghi âm và định dạng chữ](#5-tin-nhắn-tệp-ghi-âm-và-định-dạng-chữ)
6. [WebUI và bình chọn nhóm](#6-webui-và-bình-chọn-nhóm)
7. [Danh mục MỌI dịch vụ](#7-danh-mục-mọi-dịch-vụ)
8. [Blueprint mẫu: chọn từ danh sách, không gõ tay](#8-blueprint-mẫu-chọn-từ-danh-sách-không-gõ-tay)

## 1. Quy ước và nguyên tắc riêng tư

Mở **Công cụ nhà phát triển → Hành động**, gõ `zalo_call.` để chọn dịch vụ (mỗi ô có mô tả và ô chọn). Người nhận là **mã Zalo** (`thread_id`) của người hoặc nhóm: lấy bằng dịch vụ `list_contacts` hoặc `get_all_friends` / `get_all_groups`, hoặc mở WebUI của app → danh bạ.

Từ ngữ dùng trong tài liệu:
- **Thiết bị nhà** = loa, mic, camera trong nhà bạn.
- **Người nhà nói trực tiếp** = người trong nhà tự nói chuyện với người gọi (sau khi AI chuyển cuộc gọi, hoặc bạn bấm nút).
- **Trợ lý giọng nói (Assist)** = bộ nghe - hiểu - nói của Home Assistant (Cài đặt → Trợ lý giọng nói). AI dùng bộ này để nghe, trả lời và đọc.

### Người nhận: chọn từ danh sách, không gõ mã (thực thể `notify`)

Thay vì gõ mã Zalo, hãy **chọn người và nhóm từ danh bạ**: *Cài đặt → Thiết bị & dịch vụ → Zalo Call → ⚙️ Cấu hình → «Người và nhóm nhận»*. Mỗi người chọn xong thành một thực thể **`notify.zalo_<tên>`** để chọn trong blueprint và automation. Bỏ chọn thì thực thể biến mất.

**Mọi người và nhóm trong danh bạ đều tự có thực thể `notify` (ẩn khỏi bảng điều khiển)**, nên trong blueprint bạn chỉ cần gõ vài chữ của tên là ô chọn lọc ra danh sách, chọn xong là tự lấy threadID; tên trùng thì có thêm 4 số cuối mã để phân biệt. Danh sách làm mới mỗi giờ. Người **không có trong danh bạ** (người lạ) thì dán mã vào ô «Thêm người theo mã Zalo (threadID)» của blueprint. Ô «Người và nhóm nhận» ở trên chỉ để bỏ ẩn thực thể đó cho dễ thấy.

**Đường dự phòng thiết bị:** ô loa / mic / camera (ở quy tắc, dịch vụ gọi và blueprint) nhận **nhiều thực thể theo thứ tự ưu tiên** (dịch vụ: các thực thể cách nhau dấu phẩy, ví dụ `media_player.r1_loa,media_player.cam_phong_khach_speaker`). Khi nối, app lấy **thiết bị còn hoạt động đầu tiên** (thực thể tồn tại và không `unavailable`/`unknown`); thiết bị chính sống lại thì lần gọi sau dùng lại thiết bị chính.

**Nhiều loa R1:** `announce_to` nhận nhiều loa (cách nhau dấu phẩy): cuộc gọi đến được báo ra TẤT CẢ các loa, âm lượng báo đặt và trả lại cho từng loa. Muốn loa nào được nhấn nút thì nghe máy bằng loa và mic của chính loa đó, dùng blueprint «Nút cho cuộc gọi đến» với trigger nút của mọi loa và để ô Loa/Mic trống (nó tự lấy từ thiết bị của nút). Tự nghe máy sau N giây (không ai nhấn) thì dùng loa đầu danh sách còn hoạt động.

| Thuộc tính của thực thể | Ý nghĩa |
|---|---|
| `thread_id` | Mã Zalo của người hoặc nhóm, truyền thẳng vào `send_message`, `make_call`, `alert_call` |
| `type` | `user` (người) hoặc `group` (nhóm). **Chỉ `user` gọi điện được** |
| `loai` | «người» hoặc «nhóm» (để hiển thị) |

```yaml
# Dùng trong automation: mã Zalo lấy từ thực thể, không cần gõ
- action: zalo_call.alert_call
  data:
    thread_id: "{{ state_attr('notify.zalo_call_dai_ca', 'thread_id') }}"
    message: "Phát hiện có người ngã ở phòng khách"
# Gửi chữ cho thực thể (chuẩn của Home Assistant)
- action: notify.send_message
  target: {entity_id: notify.zalo_call_dai_ca}
  data: {title: "Báo", message: "Nhà đang mất điện"}
```

### Nguyên tắc riêng tư (luôn đúng)
1. **Chưa có quy tắc cho một người thì hệ thống không làm gì** với người đó: cuộc gọi chỉ đổ chuông, tin nhắn không đi đâu.
2. **Thiết bị nhà tắt mặc định.** Chỉ dùng thứ bạn **đã chọn** và đã **tích**; chưa tích hoặc chưa chọn là không dùng, AI cũng không tự dùng được.
3. **Lúc AI đang nói chuyện thì chưa bật thiết bị nhà.** Chỉ khi người nhà nói trực tiếp mới bật.
4. Muốn AI nói chuyện thì phải chọn Trợ lý giọng nói (hoặc Trợ lý AI riêng): hệ thống không tự dùng bộ ưu tiên vì nó có quyền điều khiển nhà.

## 2. Dịch vụ cuộc gọi, AI, cảnh báo và quy tắc

Mỗi dịch vụ dưới đây có: **mã YAML đủ mọi ô** (ô «tuỳ chọn» bỏ đi được), **bảng các ô**, và phần **giải thích từng lựa chọn** của mọi ô có danh sách chọn. Phần này được **sinh tự động** từ `services.yaml` nên luôn khớp với dịch vụ thật. Ô `entry_id` (chọn tài khoản Zalo) có ở mọi dịch vụ và chỉ cần khi bạn có nhiều tài khoản.

<!-- DICH-VU:LOI:BEGIN -->

### Dịch vụ cuộc gọi, AI và cảnh báo

<a id="make_call"></a>
#### Gọi điện đi — `zalo_call.make_call`

Gọi thoại hoặc video cho một người hay nhóm Zalo. Có thể chỉ gọi, hoặc đọc một thông báo rồi cúp, hoặc cho AI nói chuyện. Muốn báo động (có người ngã, cháy...) thì dùng «Gọi cảnh báo».

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.make_call
data:
  thread_id: "6643404425553198601"  # bắt buộc - Người hoặc nhóm cần gọi
  type: "user"                      # tuỳ chọn - Gọi thoại hay gọi video
  peer_name: "..."                  # tuỳ chọn - Tên hiện trong nhật ký
  srtp: "sess"                      # tuỳ chọn - Cách mã hoá tiếng (nâng cao)
  extend_profile: "native"          # tuỳ chọn - Kiểu kết nối với Zalo (nâng cao)
  speaker: "media_player.vi_du"     # tuỳ chọn - Loa trong nhà
  volume: 0                         # tuỳ chọn - Âm lượng loa (%)
  mic: "camera.vi_du"               # tuỳ chọn - Mic trong nhà
  mic_url: "..."                    # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"            # tuỳ chọn - Camera trong nhà
  connect: ["mic", "speaker"]       # tuỳ chọn - Thiết bị nhà dùng khi người nhà nói trực tiếp
  connect_now: ["mic", "speaker"]   # tuỳ chọn - Thiết bị nhà dùng NGAY khi người nhận nghe máy
  message: "..."                    # tuỳ chọn - Nội dung đọc khi người nhận nghe máy
  repeat: 1                         # tuỳ chọn - Đọc mấy lần
  ai: false                         # tuỳ chọn - Cho AI nói chuyện
  hangup_after: true                # tuỳ chọn - Tự cúp máy khi xong
  greeting: "..."                   # tuỳ chọn - Câu AI chào đầu tiên
  handover_rule: "..."              # tuỳ chọn - AI chuyển cho người nhà khi...
  tts_engine: "tts.vi_du"           # tuỳ chọn - Giọng đọc riêng
  language: "..."                   # tuỳ chọn - Ngôn ngữ
  pipeline: "Chatgpt"               # tuỳ chọn - Trợ lý giọng nói (Assist)
  agent: "conversation.vi_du"       # tuỳ chọn - Trợ lý AI riêng (không bắt buộc)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Người hoặc nhóm cần gọi | có | Mã Zalo của người (hoặc nhóm). Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `type` | Gọi thoại hay gọi video | không | Thoại, video hoặc nhóm. Bỏ trống = tự chọn: nếu có camera sẽ dùng (tích Camera ở ô «Thiết bị nhà dùng khi người nhà nói trực tiếp») thì gọi video, không thì gọi thoại. |
| `peer_name` | Tên hiện trong nhật ký | không | Tên người nhận hiện trong nhật ký cuộc gọi (bỏ trống = dùng mã). |
| `srtp` | Cách mã hoá tiếng (nâng cao) | không | Thường để trống: hệ thống tự chọn cách đã chạy tốt. |
| `extend_profile` | Kiểu kết nối với Zalo (nâng cao) | không | Thường để trống. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `volume` | Âm lượng loa (%) | không | Đặt âm lượng khi bật loa, trả lại mức cũ khi cúp. Bỏ trống = giữ nguyên. |
| `mic` | Mic trong nhà | không | Camera hoặc vệ tinh Assist (loa R1, camera Imou/Dahua) có mic, để gửi tiếng trong nhà cho người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người bên kia (cuộc gọi video). Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `connect` | Thiết bị nhà dùng khi người nhà nói trực tiếp | không | Tích ô nào thì dùng thứ đó: tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3. Không tích gì = không dùng thiết bị nào (mặc định, người lạ không nghe hay thấy được trong nhà). Tích Camera = cuộc gọi VIDEO. «AI tự chọn» = AI quyết dùng mic và loa hay thêm cả camera, chỉ trong các ô đã tích. Chỉ dùng được thiết bị đã chọn ở các ô Loa, Mic, Camera bên dưới. Thiết bị chỉ bật khi người nhà nói trực tiếp, lúc AI còn đang giữ máy thì chưa bật. |
| `connect_now` | Thiết bị nhà dùng NGAY khi người nhận nghe máy | không | Tích ô nào thì thứ đó bật ngay khi người nhận nghe máy, không chờ người nhà nói trực tiếp (ví dụ tích Camera để người nhận thấy hình trong nhà ngay, còn Mic và Loa chỉ bật khi người nhà nói). Tích Camera = cuộc gọi VIDEO. Không tích gì = chưa bật gì (mặc định). Chỉ bật được thiết bị đã chọn ở các ô Loa, Mic, Camera. |
| `message` | Nội dung đọc khi người nhận nghe máy | không | Câu được đọc bằng giọng nói ngay khi nghe máy. Bỏ trống = không đọc gì. |
| `repeat` | Đọc mấy lần | không | Số lần đọc (1 đến 3). |
| `ai` | Cho AI nói chuyện | không | AI nghe người bên kia và trả lời bằng giọng nói, tới khi họ nói không cần gì nữa, cúp máy, im lặng quá lâu hoặc 10 phút. Cần chọn Trợ lý giọng nói (hoặc đã đặt quy tắc cho người này). |
| `hangup_after` | Tự cúp máy khi xong | không | Cúp máy sau khi đọc xong thông báo, và sau khi AI nói chuyện xong. Mặc định: bật. |
| `greeting` | Câu AI chào đầu tiên | không | AI nói câu này ngay khi người nhận nghe máy (chỉ khi cho AI nói chuyện mà không có nội dung thông báo). Bỏ trống = câu chào trong quy tắc, không có thì «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?». |
| `handover_rule` | AI chuyển cho người nhà khi... | không | Thêm điều kiện riêng để AI chuyển cuộc gọi cho người nhà nói trực tiếp. Mặc định AI đã tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được. Khi chuyển, cuộc gọi không bị cúp, thiết bị nhà bật theo ô «Thiết bị nhà dùng khi người nhà nói trực tiếp», và Home Assistant bắn sự kiện zalo_call_ai_handover. |
| `tts_engine` | Giọng đọc riêng | không | Chọn nếu muốn dùng giọng khác. Bỏ trống = giọng của Trợ lý giọng nói. |
| `language` | Ngôn ngữ | không | Ví dụ vi. Bỏ trống = theo Trợ lý giọng nói. |
| `pipeline` | Trợ lý giọng nói (Assist) | không | Bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). Khi cho AI nói chuyện, AI nghe người gọi, trả lời và đọc bằng giọng của bộ này. Bắt buộc chọn nếu cho AI nói chuyện (không tự dùng bộ ưu tiên vì nó có quyền điều khiển thiết bị trong nhà). |
| `agent` | Trợ lý AI riêng (không bắt buộc) | không | Chỉ chọn nếu muốn dùng một trợ lý AI khác với trợ lý trong Trợ lý giọng nói. Với người lạ, nên chọn trợ lý KHÔNG điều khiển được thiết bị trong nhà. |

**Các lựa chọn:**

- **Gọi thoại hay gọi video** (`type`)
  - `user`: gọi thoại 1-1
  - `video`: gọi video 1-1
  - `group`: gọi nhóm
- **Cách mã hoá tiếng (nâng cao)** (`srtp`)
  - `sess`: khoá mã hoá lấy từ mã phiên của cuộc gọi (mặc định, đã chạy thật với điện thoại)
  - `off`: không mã hoá tiếng (RTP trần)
  - `key`: khoá tự sinh (thử nghiệm)
- **Kiểu kết nối với Zalo (nâng cao)** (`extend_profile`)
  - `native`: giống ứng dụng Zalo trên Linux (mặc định, đã chạy thật với điện thoại)
  - `pc`: bộ cũ của app (newZrtc=0)
  - `zca`: bộ của thư viện zca-js
- **Thiết bị nhà dùng khi người nhà nói trực tiếp** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)
- **Thiết bị nhà dùng NGAY khi người nhận nghe máy** (`connect_now`) - chọn được nhiều ô cùng lúc
  - `mic`: bật mic ngay khi người nhận nghe máy
  - `speaker`: bật loa ngay khi người nhận nghe máy
  - `camera`: bật camera ngay khi người nhận nghe máy (và là cuộc gọi VIDEO)


<a id="alert_call"></a>
#### Gọi cảnh báo — `zalo_call.alert_call`

Gọi để BÁO ĐỘNG: người nhận nghe máy, AI đọc nội dung cảnh báo (không hỏi gì), rồi làm theo ô «Đọc cảnh báo xong thì». Báo người ngã, có trộm: nên nối thiết bị nhà để người nhận xem hiện trường. Báo mất điện, rò nước: đọc xong cúp máy. Đọc xong, Home Assistant bắn sự kiện zalo_call_alert_done để automation biết đúng lúc đó.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.alert_call
data:
  thread_id: "6643404425553198601"  # bắt buộc - Người cần báo
  message: "..."                    # bắt buộc - Nội dung cảnh báo
  type: "user"                      # tuỳ chọn - Gọi thoại hay gọi video
  after: "hangup"                   # tuỳ chọn - Đọc cảnh báo xong thì
  pipeline: "Chatgpt"               # tuỳ chọn - Trợ lý giọng nói (để chọn giọng đọc)
  speaker: "media_player.vi_du"     # tuỳ chọn - Loa trong nhà
  mic: "camera.vi_du"               # tuỳ chọn - Mic trong nhà
  mic_url: "..."                    # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"            # tuỳ chọn - Camera trong nhà
  connect: ["mic", "speaker"]       # tuỳ chọn - Thiết bị nhà dùng ngay sau cảnh báo
  volume: 0                         # tuỳ chọn - Âm lượng loa (%)
  repeat: 1                         # tuỳ chọn - Đọc mấy lần
  tts_engine: "tts.vi_du"           # tuỳ chọn - Giọng đọc riêng
  language: "..."                   # tuỳ chọn - Ngôn ngữ
  peer_name: "..."                  # tuỳ chọn - Tên hiện trong nhật ký
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `thread_id` | Người cần báo | có | Mã Zalo của người nhận cảnh báo. Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `message` | Nội dung cảnh báo | có | Câu được đọc ngay khi người nhận nghe máy. |
| `type` | Gọi thoại hay gọi video | không | Bỏ trống = tự chọn: có camera sẽ dùng (mặc định cảnh báo dùng tất cả thiết bị đã cài, gồm camera) thì gọi video, không thì gọi thoại. |
| `after` | Đọc cảnh báo xong thì | không | Cúp máy: hợp báo mất điện, rò nước. Nối thiết bị nhà: hợp báo người ngã, có trộm. Giữ máy: người nhận hoặc automation tự cúp (dịch vụ «Kết thúc cuộc gọi»). Bỏ trống = tự chọn: có thiết bị để nối thì nối, không thì cúp. |
| `pipeline` | Trợ lý giọng nói (để chọn giọng đọc) | không | Bỏ trống = theo quy tắc của người này; không có thì giọng đọc mặc định của Home Assistant. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người nhận sau khi đọc xong. Bỏ trống = theo quy tắc của người này. |
| `mic` | Mic trong nhà | không | Mic gửi tiếng trong nhà cho người nhận sau khi đọc xong. Bỏ trống = theo quy tắc. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người nhận sau khi đọc xong. Bỏ trống = theo quy tắc. |
| `connect` | Thiết bị nhà dùng ngay sau cảnh báo | không | Tích ô nào thì dùng thứ đó (tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = cả 3). Tích Camera = cuộc gọi VIDEO. Bỏ trống = dùng TẤT CẢ thiết bị đã cài, kể cả camera, vì báo động thì người nhận phải thấy hiện trường. Muốn chỉ đọc rồi cúp thì chọn Cúp máy ở ô «Đọc cảnh báo xong thì». |
| `volume` | Âm lượng loa (%) | không | Đặt âm lượng khi bật loa, trả lại mức cũ khi cúp. Bỏ trống = giữ nguyên. |
| `repeat` | Đọc mấy lần | không | Số lần đọc (1 đến 3). |
| `tts_engine` | Giọng đọc riêng | không | Chọn nếu muốn dùng giọng khác. Bỏ trống = giọng của Trợ lý giọng nói. |
| `language` | Ngôn ngữ | không | Ví dụ vi. Bỏ trống = theo Trợ lý giọng nói. |
| `peer_name` | Tên hiện trong nhật ký | không | Tên người nhận hiện trong nhật ký cuộc gọi (bỏ trống = dùng mã). |

**Các lựa chọn:**

- **Gọi thoại hay gọi video** (`type`)
  - `user`: gọi thoại
  - `video`: gọi video
- **Đọc cảnh báo xong thì** (`after`)
  - `hangup`: cúp máy ngay sau khi đọc xong (hợp báo mất điện, rò nước)
  - `connect`: nối thiết bị nhà đã cài (hợp báo người ngã, có trộm)
  - `wait`: giữ máy: người nhận hoặc automation tự cúp bằng dịch vụ «Kết thúc cuộc gọi»
- **Thiết bị nhà dùng ngay sau cảnh báo** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)


<a id="answer_call"></a>
#### Nghe máy — `zalo_call.answer_call`

Nghe một cuộc gọi đang đổ chuông. Có thể kèm thông báo hoặc cho AI nói chuyện, giống «Gọi điện đi».

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.answer_call
data:
  call_id: "..."                   # tuỳ chọn - Mã cuộc gọi
  speaker: "media_player.vi_du"    # tuỳ chọn - Loa trong nhà
  volume: 0                        # tuỳ chọn - Âm lượng loa (%)
  mic: "camera.vi_du"              # tuỳ chọn - Mic trong nhà
  mic_url: "..."                   # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"           # tuỳ chọn - Camera trong nhà
  connect: ["mic", "speaker"]      # tuỳ chọn - Thiết bị nhà dùng khi người nhà nói trực tiếp
  connect_now: ["mic", "speaker"]  # tuỳ chọn - Thiết bị nhà dùng NGAY khi người nhận nghe máy
  message: "..."                   # tuỳ chọn - Nội dung đọc khi người nhận nghe máy
  repeat: 1                        # tuỳ chọn - Đọc mấy lần
  ai: false                        # tuỳ chọn - Cho AI nói chuyện
  hangup_after: true               # tuỳ chọn - Tự cúp máy khi xong
  greeting: "..."                  # tuỳ chọn - Câu AI chào đầu tiên
  handover_rule: "..."             # tuỳ chọn - AI chuyển cho người nhà khi...
  tts_engine: "tts.vi_du"          # tuỳ chọn - Giọng đọc riêng
  language: "..."                  # tuỳ chọn - Ngôn ngữ
  pipeline: "Chatgpt"              # tuỳ chọn - Trợ lý giọng nói (Assist)
  agent: "conversation.vi_du"      # tuỳ chọn - Trợ lý AI riêng (không bắt buộc)
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để nghe cuộc gọi đến hiện tại. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `volume` | Âm lượng loa (%) | không | Đặt âm lượng khi bật loa, trả lại mức cũ khi cúp. Bỏ trống = giữ nguyên. |
| `mic` | Mic trong nhà | không | Camera hoặc vệ tinh Assist (loa R1, camera Imou/Dahua) có mic, để gửi tiếng trong nhà cho người bên kia. Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người bên kia (cuộc gọi video). Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp. |
| `connect` | Thiết bị nhà dùng khi người nhà nói trực tiếp | không | Tích ô nào thì dùng thứ đó: tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3. Không tích gì = không dùng thiết bị nào (mặc định, người lạ không nghe hay thấy được trong nhà). Tích Camera = cuộc gọi VIDEO. «AI tự chọn» = AI quyết dùng mic và loa hay thêm cả camera, chỉ trong các ô đã tích. Chỉ dùng được thiết bị đã chọn ở các ô Loa, Mic, Camera bên dưới. Thiết bị chỉ bật khi người nhà nói trực tiếp, lúc AI còn đang giữ máy thì chưa bật. |
| `connect_now` | Thiết bị nhà dùng NGAY khi người nhận nghe máy | không | Tích ô nào thì thứ đó bật ngay khi người nhận nghe máy, không chờ người nhà nói trực tiếp (ví dụ tích Camera để người nhận thấy hình trong nhà ngay, còn Mic và Loa chỉ bật khi người nhà nói). Tích Camera = cuộc gọi VIDEO. Không tích gì = chưa bật gì (mặc định). Chỉ bật được thiết bị đã chọn ở các ô Loa, Mic, Camera. |
| `message` | Nội dung đọc khi người nhận nghe máy | không | Câu được đọc bằng giọng nói ngay khi nghe máy. Bỏ trống = không đọc gì. |
| `repeat` | Đọc mấy lần | không | Số lần đọc (1 đến 3). |
| `ai` | Cho AI nói chuyện | không | AI nghe người bên kia và trả lời bằng giọng nói, tới khi họ nói không cần gì nữa, cúp máy, im lặng quá lâu hoặc 10 phút. Cần chọn Trợ lý giọng nói (hoặc đã đặt quy tắc cho người này). |
| `hangup_after` | Tự cúp máy khi xong | không | Cúp máy sau khi đọc xong thông báo, và sau khi AI nói chuyện xong. Mặc định: bật. |
| `greeting` | Câu AI chào đầu tiên | không | AI nói câu này ngay khi người nhận nghe máy (chỉ khi cho AI nói chuyện mà không có nội dung thông báo). Bỏ trống = câu chào trong quy tắc, không có thì «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?». |
| `handover_rule` | AI chuyển cho người nhà khi... | không | Thêm điều kiện riêng để AI chuyển cuộc gọi cho người nhà nói trực tiếp. Mặc định AI đã tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được. Khi chuyển, cuộc gọi không bị cúp, thiết bị nhà bật theo ô «Thiết bị nhà dùng khi người nhà nói trực tiếp», và Home Assistant bắn sự kiện zalo_call_ai_handover. |
| `tts_engine` | Giọng đọc riêng | không | Chọn nếu muốn dùng giọng khác. Bỏ trống = giọng của Trợ lý giọng nói. |
| `language` | Ngôn ngữ | không | Ví dụ vi. Bỏ trống = theo Trợ lý giọng nói. |
| `pipeline` | Trợ lý giọng nói (Assist) | không | Bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). Khi cho AI nói chuyện, AI nghe người gọi, trả lời và đọc bằng giọng của bộ này. Bắt buộc chọn nếu cho AI nói chuyện (không tự dùng bộ ưu tiên vì nó có quyền điều khiển thiết bị trong nhà). |
| `agent` | Trợ lý AI riêng (không bắt buộc) | không | Chỉ chọn nếu muốn dùng một trợ lý AI khác với trợ lý trong Trợ lý giọng nói. Với người lạ, nên chọn trợ lý KHÔNG điều khiển được thiết bị trong nhà. |

**Các lựa chọn:**

- **Thiết bị nhà dùng khi người nhà nói trực tiếp** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)
- **Thiết bị nhà dùng NGAY khi người nhận nghe máy** (`connect_now`) - chọn được nhiều ô cùng lúc
  - `mic`: bật mic ngay khi người nhận nghe máy
  - `speaker`: bật loa ngay khi người nhận nghe máy
  - `camera`: bật camera ngay khi người nhận nghe máy (và là cuộc gọi VIDEO)


<a id="reject_call"></a>
#### Từ chối cuộc gọi đến — `zalo_call.reject_call`

Từ chối cuộc gọi đang đổ chuông.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.reject_call
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để từ chối cuộc gọi đến hiện tại. |


<a id="end_call"></a>
#### Kết thúc cuộc gọi — `zalo_call.end_call`

Kết thúc (hoặc huỷ khi còn đổ chuông) cuộc gọi đang có.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.end_call
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để kết thúc cuộc gọi gần nhất. |


<a id="say_in_call"></a>
#### Đọc lên cuộc gọi (TTS) — `zalo_call.say_in_call`

Đọc một câu bằng TTS của HA lên cuộc gọi đang nói.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.say_in_call
data:
  message: "..."           # bắt buộc - Nội dung
  call_id: "..."           # tuỳ chọn - Mã cuộc gọi
  tts_engine: "tts.vi_du"  # tuỳ chọn - Giọng đọc (TTS)
  language: "..."          # tuỳ chọn - Ngôn ngữ
  wait: true               # tuỳ chọn - Chờ đọc xong
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `message` | Nội dung | có | Câu cần đọc. |
| `call_id` | Mã cuộc gọi | không | Bỏ trống = cuộc gọi đang nói hiện tại. |
| `tts_engine` | Giọng đọc (TTS) | không | Thực thể tts.*; bỏ trống = mặc định của HA. |
| `language` | Ngôn ngữ | không | Ví dụ vi. |
| `wait` | Chờ đọc xong | không | Chờ đọc xong mới trả về. |


<a id="take_over_call"></a>
#### Người nhà nói trực tiếp (dừng AI) — `zalo_call.take_over_call`

Dừng AI đang giữ cuộc gọi và bật thiết bị nhà để người trong nhà nói chuyện trực tiếp với người gọi.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.take_over_call
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống = cuộc gọi đang nói hiện tại. |


<a id="accept_video"></a>
#### Đồng ý chuyển sang video — `zalo_call.accept_video`

Người đang gọi thoại xin chuyển sang video, bạn đồng ý. Chọn Camera để gửi hình trong nhà; không chọn thì chỉ đồng ý (người gọi thấy mình, nhưng không thấy hình trong nhà). Chỉ dùng được khi cuộc gọi đang nói.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.accept_video
data:
  call_id: "..."          # tuỳ chọn - Mã cuộc gọi
  camera: "camera.vi_du"  # tuỳ chọn - Camera
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống = cuộc gọi đang nói hiện tại. |
| `camera` | Camera | không | Camera gửi hình. |


<a id="upgrade_to_video"></a>
#### Chuyển cuộc gọi thoại sang video — `zalo_call.upgrade_to_video`

Khi đang gọi thoại, xin bên kia chuyển sang video rồi phát camera đã chọn (hoặc camera mặc định).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.upgrade_to_video
data:
  call_id: "..."          # tuỳ chọn - Mã cuộc gọi
  camera: "camera.vi_du"  # tuỳ chọn - Camera
  camera_url: "..."       # tuỳ chọn - Camera từ URL
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |
| `camera` | Camera | không | Camera HA phát hình. Bỏ trống = camera mặc định. |
| `camera_url` | Camera từ URL | không | rtsp/rtsps/http/https/rtmp (thắng ô Camera). |


<a id="start_call_video"></a>
#### Bật hình trong cuộc gọi — `zalo_call.start_call_video`

Phát hình camera lên cuộc gọi đang diễn ra (không xin chuyển loại cuộc gọi).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.start_call_video
data:
  call_id: "..."          # tuỳ chọn - Mã cuộc gọi
  camera: "camera.vi_du"  # tuỳ chọn - Camera
  camera_url: "..."       # tuỳ chọn - Camera từ URL
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |
| `camera` | Camera | không | Camera HA phát hình. Bỏ trống = camera mặc định. |
| `camera_url` | Camera từ URL | không | rtsp/rtsps/http/https/rtmp (thắng ô Camera). |


<a id="stop_call_video"></a>
#### Tắt hình trong cuộc gọi — `zalo_call.stop_call_video`

Dừng phát hình camera lên cuộc gọi đang diễn ra.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.stop_call_video
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |


<a id="start_call_mic"></a>
#### Bật mic trong cuộc gọi — `zalo_call.start_call_mic`

Phát tiếng từ camera, vệ tinh Assist (camera Imou/Dahua, loa R1) hoặc URL lên cuộc gọi đang diễn ra.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.start_call_mic
data:
  call_id: "..."       # tuỳ chọn - Mã cuộc gọi
  mic: "camera.vi_du"  # tuỳ chọn - Mic
  mic_url: "..."       # tuỳ chọn - Mic từ URL
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |
| `mic` | Mic | không | Camera hoặc vệ tinh Assist. Bỏ trống = mic mặc định. |
| `mic_url` | Mic từ URL | không | rtsp/rtsps/http/https/rtmp, hoặc luồng PCM của loa R1 (thắng ô Mic). |


<a id="stop_call_mic"></a>
#### Tắt mic trong cuộc gọi — `zalo_call.stop_call_mic`

Dừng phát tiếng lên cuộc gọi đang diễn ra.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.stop_call_mic
data:
  call_id: "..."  # tuỳ chọn - Mã cuộc gọi
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | không | Bỏ trống để dùng cuộc gọi đang diễn ra. |


<a id="set_default_devices"></a>
#### Đặt thiết bị mặc định — `zalo_call.set_default_devices`

Đặt các chế độ tự động mặc định (tự phát mic, tự đồng ý video, chống vọng, âm lượng). Loa, mic, camera KHÔNG còn mặc định - do quy tắc/automation chọn cho từng cuộc gọi. Trường nào bỏ trống thì giữ nguyên.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_default_devices
data:
  auto_mic: false       # tuỳ chọn - Tự phát mic khi nghe máy
  auto_video: false     # tuỳ chọn - Tự đồng ý khi bên kia xin gọi video (mọi người)
  video_consent: false  # tuỳ chọn - Cho phép đồng ý chuyển sang video (công tắc tổng)
  echo_guard: "auto"    # tuỳ chọn - Chống vọng
  auto_video_delay: 0   # tuỳ chọn - Chờ trước khi tự đồng ý (giây)
  call_volume: 0        # tuỳ chọn - Âm lượng cuộc gọi mặc định
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `auto_mic` | Tự phát mic khi nghe máy | không | Bật thì tự phát mic mặc định ngay khi cuộc gọi được nghe máy. |
| `auto_video` | Tự đồng ý khi bên kia xin gọi video (mọi người) | không | Bật thì khi BẤT KỲ AI xin chuyển sang video app cũng tự đồng ý và phát camera mặc định, không xét quy tắc từng người. Nên TẮT và dùng công tắc «Cho phép đồng ý chuyển sang video» cùng quy tắc từng người (video_request) để chỉ người được phép mới tự đồng ý. |
| `video_consent` | Cho phép đồng ý chuyển sang video (công tắc tổng) | không | Công tắc tổng, mặc định TẮT. Bật thì quy tắc video_request (accept, accept_camera) của từng người/nhóm mới được tự đồng ý khi họ xin chuyển sang video; tắt thì mọi người chỉ bị báo. Cũng là công tắc «Cho phép đồng ý chuyển sang video» trên thiết bị Zalo Call. |
| `echo_guard` | Chống vọng | không | auto = chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ R1); on = luôn chặn mic khi loa đang phát tiếng bên kia; duplex = song công, nói chen được (loa R1 dùng khử vọng của nó); off = tắt. |
| `auto_video_delay` | Chờ trước khi tự đồng ý (giây) | không | Số giây chờ rồi mới tự đồng ý lời xin chuyển sang video (0 = đồng ý ngay; chỉ áp dụng khi cuộc gọi còn đang nói). |
| `call_volume` | Âm lượng cuộc gọi mặc định | không | 1-100 % — âm lượng loa đặt khi nghe máy rồi trả lại khi cuộc gọi kết thúc; 0 = giữ nguyên âm lượng loa. |

**Các lựa chọn:**

- **Chống vọng** (`echo_guard`)
  - `auto`: chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ loa R1)
  - `on`: luôn chặn mic khi loa đang phát tiếng bên kia
  - `duplex`: song công: nói chen được (loa R1 dùng bộ khử vọng riêng)
  - `off`: tắt chống vọng


<a id="get_default_devices"></a>
#### Xem mic/loa/camera mặc định — `zalo_call.get_default_devices`

Trả về cài đặt thiết bị mặc định hiện tại (đặt bằng set_default_devices).

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.get_default_devices
```


### Dịch vụ quy tắc cho cuộc gọi đến và tin nhắn

<a id="set_rule"></a>
#### Đặt quy tắc cho cuộc gọi đến và tin nhắn — `zalo_call.set_rule`

Quy định hệ thống làm gì khi có người gọi hoặc nhắn đến. Chưa có quy tắc cho người đó thì hệ thống KHÔNG làm gì (chỉ đổ chuông, không trả lời tin nhắn). Quy tắc cho một người hoặc nhóm cụ thể được ưu tiên hơn quy tắc chung. Ô nào không điền thì giữ nguyên như cũ; quy tắc mới mặc định TẮT hết và không dùng thiết bị nhà.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.set_rule
data:
  scope: "thread"                    # bắt buộc - Áp dụng cho
  thread_id: "6643404425553198601"   # tuỳ chọn - Mã Zalo của người hoặc nhóm
  tag: "gia đình"                    # tuỳ chọn - Thẻ
  name: "..."                        # tuỳ chọn - Tên gọi (để bạn nhớ)
  answer: false                      # tuỳ chọn - Tự nghe máy
  answer_delay: 3                    # tuỳ chọn - Nghe máy sau (giây)
  call_types: ["voice", "video"]     # tuỳ chọn - Nghe loại cuộc gọi nào
  ai: false                          # tuỳ chọn - Cho AI nói chuyện khi nghe máy
  pipeline: "Chatgpt"                # tuỳ chọn - Trợ lý giọng nói (Assist)
  agent: "conversation.vi_du"        # tuỳ chọn - Trợ lý AI riêng (không bắt buộc)
  greeting: "..."                    # tuỳ chọn - Câu AI chào khi nghe máy
  handover_rule: "..."               # tuỳ chọn - AI chuyển cho người nhà khi...
  trusted: false                     # tuỳ chọn - Người tin cậy
  reply_ai: false                    # tuỳ chọn - AI trả lời tin nhắn
  voice_text: false                  # tuỳ chọn - Chuyển tin thoại thành chữ
  reply_trigger: "..."               # tuỳ chọn - Từ khóa gọi AI trong nhóm
  reply_senders: "..."               # tuỳ chọn - Người được gọi AI trong nhóm
  reply_quote: false                 # tuỳ chọn - Trả lời kèm trích dẫn tin gốc
  reply_prefix: "..."                # tuỳ chọn - Tiền tố câu trả lời
  announce: false                    # tuỳ chọn - Báo ra loa khi có cuộc gọi đến
  announce_to: "media_player.vi_du"  # tuỳ chọn - Loa dùng để báo
  announce_text: "..."               # tuỳ chọn - Câu báo ra loa
  announce_volume: 0                 # tuỳ chọn - Âm lượng lúc báo (%)
  announce_repeat: 0                 # tuỳ chọn - Báo lại sau mỗi (giây)
  connect_now: ["mic", "speaker"]    # tuỳ chọn - Thiết bị nhà dùng NGAY khi người nhận nghe máy
  video_request: "ask"               # tuỳ chọn - Khi người gọi xin chuyển sang video
  connect: ["mic", "speaker"]        # tuỳ chọn - Thiết bị nhà dùng khi người nhà nói trực tiếp
  speaker: "media_player.vi_du"      # tuỳ chọn - Loa trong nhà
  mic: "camera.vi_du"                # tuỳ chọn - Mic trong nhà
  mic_url: "..."                     # tuỳ chọn - Mic từ địa chỉ mạng (nâng cao)
  camera: "camera.vi_du"             # tuỳ chọn - Camera trong nhà
  volume: 0                          # tuỳ chọn - Âm lượng loa (%)
  echo_guard: "auto"                 # tuỳ chọn - Chống vọng âm
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `scope` | Áp dụng cho | có | Chọn đối tượng của quy tắc. «Một người hoặc một nhóm cụ thể» thì điền thêm Mã Zalo bên dưới. |
| `thread_id` | Mã Zalo của người hoặc nhóm | không | Chỉ cần khi chọn «Một người hoặc một nhóm cụ thể». Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `tag` | Thẻ | không | Chỉ cần khi chọn «Mọi người mang một thẻ». Gắn thẻ cho người bằng dịch vụ «Gắn thẻ và ghi chú cho người». |
| `name` | Tên gọi (để bạn nhớ) | không | Tên hiển thị trong các thông báo, ví dụ «Con trai». |
| `answer` | Tự nghe máy | không | Cuộc gọi 1-1 đến từ người thuộc quy tắc này sẽ tự được nghe sau thời gian chờ. |
| `answer_delay` | Nghe máy sau (giây) | không | Từ 0 đến 120 giây. Người gọi cúp trước khi hết giờ thì không nghe. |
| `call_types` | Nghe loại cuộc gọi nào | không | voice = thoại, video = video, hoặc cả hai. |
| `ai` | Cho AI nói chuyện khi nghe máy | không | Sau khi nghe máy, AI nghe và trả lời bằng giọng nói. Cần chọn Trợ lý giọng nói hoặc Trợ lý AI riêng. |
| `pipeline` | Trợ lý giọng nói (Assist) | không | Bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). Khi cho AI nói chuyện, AI nghe người gọi, trả lời và đọc bằng giọng của bộ này. Bắt buộc chọn nếu cho AI nói chuyện (không tự dùng bộ ưu tiên vì nó có quyền điều khiển thiết bị trong nhà). |
| `agent` | Trợ lý AI riêng (không bắt buộc) | không | Chỉ chọn nếu muốn dùng một trợ lý AI khác với trợ lý trong Trợ lý giọng nói. Với người lạ, nên chọn trợ lý KHÔNG điều khiển được thiết bị trong nhà. |
| `greeting` | Câu AI chào khi nghe máy | không | Bỏ trống = «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?». |
| `handover_rule` | AI chuyển cho người nhà khi... | không | Thêm điều kiện riêng để AI chuyển cuộc gọi cho người nhà nói trực tiếp. Mặc định AI đã tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được. Khi chuyển, cuộc gọi không bị cúp, thiết bị nhà bật theo ô «Thiết bị nhà dùng khi người nhà nói trực tiếp», và Home Assistant bắn sự kiện zalo_call_ai_handover. |
| `trusted` | Người tin cậy | không | Tin cậy thì AI nói chuyện bình thường. Không tin cậy (mặc định) thì AI được dặn không tiết lộ thông tin gia đình và không điều khiển thiết bị. |
| `reply_ai` | AI trả lời tin nhắn | không | AI trả lời tin chữ (và tin thoại nếu bật chuyển tin thoại thành chữ) của người hoặc nhóm này. Cần chọn Trợ lý giọng nói hoặc Trợ lý AI riêng. |
| `voice_text` | Chuyển tin thoại thành chữ | không | Tin thoại 1-1 được Zalo chuyển thành chữ, và Home Assistant bắn sự kiện zalo_call_voice_text. |
| `reply_trigger` | Từ khóa gọi AI trong nhóm | không | Chỉ áp cho NHÓM. Tin có từ này (không phân biệt hoa thường, ví dụ `@Bot`) mới được AI trả lời; từ khóa được bỏ khỏi câu hỏi. Để trống = AI trả lời mọi tin của nhóm. |
| `reply_senders` | Người được gọi AI trong nhóm | không | Chỉ áp cho NHÓM. Mã Zalo (threadID) của những người được phép gọi AI, cách nhau dấu phẩy. Để trống = mọi thành viên. Dán mã dài 19 chữ số hay mã số ngắn đều được. |
| `reply_quote` | Trả lời kèm trích dẫn tin gốc | không | Câu trả lời của AI trích dẫn đúng tin vừa hỏi (như zalo_bot). Chỉ với tin chữ; không trích được thì gửi tin thường. |
| `reply_prefix` | Tiền tố câu trả lời | không | Chữ thêm vào đầu câu trả lời của AI, ví dụ `Bot-Hass:`. |
| `announce` | Báo ra loa khi có cuộc gọi đến | không | Bật thì khi người này gọi đến, một loa trong nhà đọc «Có cuộc gọi ... từ ...» để người trong nhà biết (kể cả khi không tự nghe máy). Mặc định TẮT. |
| `announce_to` | Loa dùng để báo | không | Loa đọc thông báo cuộc gọi đến (bắt buộc khi bật báo ra loa). Giọng đọc lấy từ Trợ lý giọng nói của quy tắc. |
| `announce_text` | Câu báo ra loa | không | Có thể dùng {ten} (tên người gọi) và {loai} (thoại hoặc video). Bỏ trống = «Có cuộc gọi {loai} từ {ten}.» |
| `announce_volume` | Âm lượng lúc báo (%) | không | Âm lượng của loa khi đọc thông báo có cuộc gọi đến. 0 = giữ nguyên. Không ai nghe máy thì loa trở về mức cũ; có người nghe thì cuộc gọi tự đặt âm lượng của nó. Loa R1 có 15 mức: 6/15 là 40%. |
| `announce_repeat` | Báo lại sau mỗi (giây) | không | Đọc xong thông báo thì chờ chừng này giây rồi đọc lại, cứ thế tới khi có người nghe máy hoặc cuộc gọi kết thúc. 0 = chỉ báo một lần. |
| `connect_now` | Thiết bị nhà dùng NGAY khi người nhận nghe máy | không | Tích ô nào thì thứ đó bật ngay khi người nhận nghe máy, không chờ người nhà nói trực tiếp (ví dụ tích Camera để người nhận thấy hình trong nhà ngay, còn Mic và Loa chỉ bật khi người nhà nói). Tích Camera = cuộc gọi VIDEO. Không tích gì = chưa bật gì (mặc định). Chỉ bật được thiết bị đã chọn ở các ô Loa, Mic, Camera. |
| `video_request` | Khi người gọi xin chuyển sang video | không | Người đang gọi thoại có thể xin chuyển sang video. Mặc định KHÔNG tự đồng ý (riêng tư): chỉ báo cho automation qua sự kiện zalo_call_call_state (trạng thái video_request). Chọn đồng ý nếu muốn tự động, nhưng chỉ có tác dụng khi công tắc «Cho phép đồng ý chuyển sang video» trên thiết bị Zalo Call đang BẬT (mặc định TẮT). |
| `connect` | Thiết bị nhà dùng khi người nhà nói trực tiếp | không | Tích ô nào thì dùng thứ đó: tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3. Không tích gì = không dùng thiết bị nào (mặc định, người lạ không nghe hay thấy được trong nhà). Tích Camera = cuộc gọi VIDEO. «AI tự chọn» = AI quyết dùng mic và loa hay thêm cả camera, chỉ trong các ô đã tích. Chỉ dùng được thiết bị đã chọn ở các ô Loa, Mic, Camera bên dưới. Thiết bị chỉ bật khi người nhà nói trực tiếp, lúc AI còn đang giữ máy thì chưa bật. |
| `speaker` | Loa trong nhà | không | Loa phát tiếng người gọi khi người nhà nói trực tiếp. |
| `mic` | Mic trong nhà | không | Camera hoặc vệ tinh Assist có mic, gửi tiếng trong nhà cho người gọi khi người nhà nói trực tiếp. |
| `mic_url` | Mic từ địa chỉ mạng (nâng cao) | không | Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic. |
| `camera` | Camera trong nhà | không | Camera gửi hình cho người gọi khi người nhà nói trực tiếp (cuộc gọi video). |
| `volume` | Âm lượng loa (%) | không | Từ 0 đến 100. 0 = giữ nguyên. |
| `echo_guard` | Chống vọng âm | không | Tránh tiếng loa lọt ngược vào mic khi hai thứ cùng một thiết bị. |

**Các lựa chọn:**

- **Áp dụng cho** (`scope`)
  - `thread`: Một người hoặc một nhóm cụ thể
  - `tag`: Mọi người mang một thẻ (điền ô Thẻ)
  - `groups`: Mọi nhóm
  - `contacts`: Mọi người trong danh bạ
  - `strangers`: Mọi người lạ
- **Nghe loại cuộc gọi nào** (`call_types`) - chọn được nhiều ô cùng lúc
  - `voice`: nghe cuộc gọi thoại
  - `video`: nghe cuộc gọi video (chọn cả hai = nghe cả hai loại)
- **Thiết bị nhà dùng NGAY khi người nhận nghe máy** (`connect_now`) - chọn được nhiều ô cùng lúc
  - `mic`: bật mic ngay khi người nhận nghe máy
  - `speaker`: bật loa ngay khi người nhận nghe máy
  - `camera`: bật camera ngay khi người nhận nghe máy (và là cuộc gọi VIDEO)
- **Khi người gọi xin chuyển sang video** (`video_request`)
  - `ask`: không tự đồng ý: chỉ báo cho automation (trạng thái video_request), bạn hoặc blueprint quyết định (mặc định)
  - `accept`: tự đồng ý chuyển sang video nhưng KHÔNG gửi hình trong nhà (người gọi thấy bạn, không thấy nhà)
  - `accept_camera`: tự đồng ý và gửi camera đã chọn trong quy tắc
- **Thiết bị nhà dùng khi người nhà nói trực tiếp** (`connect`) - chọn được nhiều ô cùng lúc
  - `mic`: Mic: gửi tiếng trong nhà cho người gọi
  - `speaker`: Loa: phát tiếng người gọi ra loa trong nhà
  - `camera`: Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)
  - `ai`: AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)
- **Chống vọng âm** (`echo_guard`)
  - `auto`: chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ loa R1)
  - `on`: luôn chặn mic khi loa đang phát tiếng bên kia
  - `duplex`: song công: nói chen được (loa R1 dùng bộ khử vọng riêng)
  - `off`: tắt chống vọng


<a id="remove_rule"></a>
#### Xoá quy tắc — `zalo_call.remove_rule`

Xoá quy tắc của một người/nhóm cụ thể hoặc của một nhóm đối tượng. Từ đó hệ thống quay về «không làm gì» với họ.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.remove_rule
data:
  scope: "thread"   # bắt buộc - Áp dụng cho
  thread_id: "..."  # tuỳ chọn - Mã Zalo của người hoặc nhóm
  tag: "..."        # tuỳ chọn - Thẻ
```

| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `scope` | Áp dụng cho | có | Chọn đối tượng của quy tắc. «Một người hoặc một nhóm cụ thể» thì điền thêm Mã Zalo bên dưới. |
| `thread_id` | Mã Zalo của người hoặc nhóm | không | Chỉ cần khi chọn «Một người hoặc một nhóm cụ thể». Xem danh sách bằng dịch vụ «Xem danh bạ Zalo». |
| `tag` | Thẻ | không | Chỉ cần khi chọn «Mọi người mang một thẻ». Gắn thẻ cho người bằng dịch vụ «Gắn thẻ và ghi chú cho người». |

**Các lựa chọn:**

- **Áp dụng cho** (`scope`)
  - `thread`: Một người hoặc một nhóm cụ thể
  - `tag`: Mọi người mang một thẻ (điền ô Thẻ)
  - `groups`: Mọi nhóm
  - `contacts`: Mọi người trong danh bạ
  - `strangers`: Mọi người lạ


<a id="list_rules"></a>
#### Xem các quy tắc — `zalo_call.list_rules`

Trả về mọi quy tắc đang đặt.

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.list_rules
```


<a id="list_contacts"></a>
#### Xem danh bạ Zalo — `zalo_call.list_contacts`

Danh sách bạn bè và nhóm kèm mã Zalo, để điền vào các ô «Mã Zalo».

**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):

```yaml
action: zalo_call.list_contacts
```

<!-- DICH-VU:LOI:END -->

## 3. Các trường hợp xảy ra

Phần này giải thích bằng lời các trường hợp thực tế khi dùng các dịch vụ ở mục 2.

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

### Người gọi xin chuyển từ thoại sang video

Trong lúc đang nói chuyện thoại, người gọi có thể xin chuyển sang video. **Mặc định hệ thống KHÔNG tự đồng ý** (riêng tư): chỉ báo cho automation bằng sự kiện `zalo_call_call_state` với `state: video_request`.

| Bạn muốn | Cách làm |
|---|---|
| Không tự đồng ý, tự quyết bằng automation | Để mặc định (ô «Khi người gọi xin chuyển sang video» = Không tự đồng ý), dùng mẫu automation hoặc dịch vụ **Đồng ý chuyển sang video** (`accept_video`) |
| Tự đồng ý nhưng không cho thấy trong nhà | Quy tắc: ô trên = «Tự đồng ý, KHÔNG gửi hình trong nhà» |
| Tự đồng ý và gửi camera | Quy tắc: «Tự đồng ý và gửi camera đã chọn» (chọn camera ở ô Camera của quy tắc) |

Không có quy tắc cho người đó thì hệ thống không làm gì (người gọi chỉ thấy không ai đồng ý).

### Cuộc gọi đến theo quy tắc

| Quy tắc | Chuyện xảy ra |
|---|---|
| Không có quy tắc cho người đó | Chỉ đổ chuông. Bạn tự nghe hoặc từ chối. |
| Có quy tắc, bật «Báo ra loa» | Loa trong nhà báo «Có cuộc gọi...». |
| Bật «Tự nghe máy» | Sau «Nghe máy sau (giây)» thì tự nghe (người gọi cúp trước thì không nghe). |
| Bật thêm «Cho AI nói chuyện khi nghe máy» | AI chào và nói chuyện như bảng cuộc gọi đi. |

Quy tắc chọn theo **ai gọi**: một người hoặc nhóm cụ thể (ưu tiên cao nhất, thay hẳn quy tắc chung) / mọi nhóm / mọi người trong danh bạ / mọi người lạ. Chưa biết người gọi quen hay lạ (danh bạ chưa tải) thì chỉ quy tắc của người cụ thể được áp.

## 4. Nhận cuộc gọi, sự kiện và ví dụ automation

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

### Sự kiện cho automation

| Sự kiện | Khi nào |
|---|---|
| `zalo_call_call_state` | Mọi thay đổi của cuộc gọi: đổ chuông, nghe máy, kết thúc... |
| `zalo_call_ai_handover` | AI chuyển cho người nhà (và khi cảnh báo nối thiết bị): `reason`, `connected`, `camera` |
| `zalo_call_alert_done` | Cảnh báo đã đọc xong: `after`, `connected`, `ended`, `thread_id` |
| `zalo_call_call_state` với `state: video_request` | Người gọi xin chuyển cuộc thoại sang video (`call_id`, `thread_id`, `peer`) |
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

### Dùng bằng giọng nói qua Assist
Tích chọn **«Zalo Call»** cạnh «Assist» trong cài đặt trợ lý hội thoại LLM: «gọi cho Đại ca», «nghe máy», «từ chối», «cúp máy», «nhắn nhóm AI học hỏi…», «tiếp quản cuộc gọi». Trong cuộc gọi do AI giữ, trợ lý chỉ thấy **một** công cụ «chuyển sang trực tiếp» nên người lạ không sai khiến được gọi điện/nhắn tin.

### Lưu ý
- STT của Zalo chỉ chuyển được tin thoại do **app Zalo thật gửi** (nằm trong kho thoại Zalo); không dùng được cho cuộc gọi trực tiếp (âm thanh khác bị Zalo từ chối, mã 212). Trong cuộc gọi, STT của Assist pipeline lo phần đó.
- Tính năng giọng nói/AI trong cuộc gọi mới kiểm bằng test giả lập và hai cuộc gọi thử, chưa nhiều cuộc gọi thật; log: `custom_components.zalo_call.call_voice`.

## 5. Tin nhắn, tệp, ghi âm và định dạng chữ

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

### Định dạng chữ: cỡ chữ, màu, đậm, nghiêng, gạch chân, tiêu đề

Zalo cá nhân có **hai cỡ chữ** (nhỏ, to), **bốn màu** (đỏ, cam, vàng, xanh lá), đậm, nghiêng, gạch chân, gạch ngang và danh sách. Zalo Call cho cài đặt kiểu chữ **một lần trên thiết bị**
(áp cho mọi tin tích hợp gửi, kể cả trả lời của AI) và **ghi đè từng tin** ở dịch vụ `send_message`. Mỗi mục có thêm chế độ **`auto`**: tự định dạng theo nội dung chữ.

#### Cài đặt mặc định (thiết bị Zalo Call → nhóm *Cấu hình*)

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

#### `auto` hoạt động thế nào: nhanh hay theo ngữ cảnh

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

#### Ghi đè từng tin: `zalo_call.send_message`

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

#### Thứ tự ưu tiên

1. **Đánh dấu tường minh trong chữ** (markdown, thẻ màu) luôn thắng: cỡ và màu mặc định/auto **không đè** lên chỗ đã có cỡ hoặc màu.
2. **Trường của dịch vụ** `send_message` ghi đè **cài đặt mặc định** trên thiết bị.
3. **Cài đặt mặc định** trên thiết bị (áp cả cho trả lời của AI tự trả lời).

#### Đánh dấu tay trong chữ (`format: markdown`)

| Viết | Ra |
|---|---|
| `**đậm**` · `*nghiêng*` · `__gạch chân__` · `~~gạch ngang~~` | đậm · nghiêng · gạch chân · gạch ngang |
| `# Tiêu đề` | to + đậm |
| `- mục` · `1. mục` | danh sách chấm · đánh số |
| `{red}đỏ{/}` `{orange}` `{yellow}` `{green}` (hoặc `{đỏ}` `{cam}` `{vàng}` `{xanh}`) | màu |
| `{big}to{/}` · `{small}nhỏ{/}` | cỡ chữ (chỉ hai cỡ) |
| `\*` | ký tự `*` nguyên văn |

Có thể kết hợp với `auto_emphasis` (tự tô số và chữ đậm), `emoji`, `zalo_emoji`, `auto_emoji`: xem mục tiếp.

#### Emoji

| Trường | Làm gì |
|---|---|
| `emoji` | Chọn trong bảng 35 biểu tượng hoặc gõ emoji bất kỳ: chèn vào đầu tin. Mã `:ok:` `:canhbao:`… trong chữ cũng đổi thành emoji |
| `zalo_emoji` | Emoji **của Zalo** (heart, haha, wow, cry…): chèn mã (`/-heart`, `:>`…) vào đầu tin, Zalo hiện thành ảnh emoji như trong bảng emoji của ô chat |
| `auto_emoji` | `true` / `false`: bật / tắt tự thêm emoji **cho tin này**, ghi đè công tắc *Chữ: tự thêm emoji* trên thiết bị (bỏ trống = theo công tắc). Mỗi dòng chưa có emoji được thêm một emoji hợp ngữ cảnh (cảnh báo, lỗi, xong, nhiệt độ, cửa, đèn…); bảng nhỏ, bảo thủ |
| `auto_emphasis` | `red`/`orange`/`yellow`/`green` hoặc `true`: tô màu + in đậm con số và chữ đã in đậm (gần giống «màu chữ = auto» kèm «in đậm = auto», nhưng chọn được màu ngay ở đây) |

Sticker: `zalo_call.send_sticker` với `keyword: "cảm ơn"` (và `pick: random`) tự tìm rồi gửi. Thả cảm xúc lên một tin: `zalo_call.add_reaction` với `icon: heart` (bảng 54 biểu tượng).

**Trả lời của AI tự trả lời:** dùng cùng cài đặt mặc định ở trên, cộng thêm ô *AI: định dạng chữ trả lời* (mặc định `markdown`, để dấu `**` của AI thành chữ đậm thật), và *AI: tự nhấn mạnh số…*. Công tắc *Chữ: tự thêm emoji* cũng áp cho trả lời của AI.

## 6. WebUI và bình chọn nhóm

### WebUI: mọi dịch vụ đều làm được trên tab «Dịch vụ»

Tab **Dịch vụ** của WebUI liệt kê **toàn bộ** dịch vụ (dịch vụ gốc + các API mở rộng của zca-js, gom theo nhóm) và có ô **Tìm dịch vụ**. Chọn thread ở ô «Thread thao tác» rồi bấm **Chạy**:

- **Gửi tin** (`send_message`): đủ cỡ chữ, màu chữ, in đậm, nghiêng, gạch chân, tiêu đề (mỗi mục có chế độ *auto*), emoji, emoji Zalo, tự thêm emoji, tự nhấn mạnh số. Cùng bảng lựa chọn với dịch vụ trong HA.
- **Gửi tệp / ảnh / video / ghi âm / liên kết**: chọn tệp ngay trên trang.
- **Sticker**: nhập Sticker ID hoặc chỉ cần *từ khoá* (tự tìm rồi gửi; `pick: random` để chọn ngẫu nhiên).
- **Tài khoản, webhook, mã QR, danh bạ**: nút xem/đặt/xoá tương ứng.
- **API mở rộng (hơn 200 API)**: mỗi API một form; trường `threadId`/`groupId`/`type` để trống thì lấy từ thread đang chọn; API cần tham số phức tạp thì dán JSON vào ô `params`. API nguy hiểm (xoá, rời nhóm…) có hộp xác nhận.
- Chỉ **không áp dụng**: gửi danh thiếp (`send_card`, app chưa có đường gửi) và proxy theo tài khoản (app chạy một tài khoản); hai loại này hiện lý do thay vì form.

Một test (`tests/test_app_js_all_services.js`) bắt buộc mọi dịch vụ trong danh mục phải có dòng form/nút, nên thêm dịch vụ mới mà quên WebUI thì CI đỏ.

### Bình chọn nhóm: lọc người chưa bình chọn, xoá khỏi nhóm (WebUI)

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

## 7. Danh mục MỌI dịch vụ

Toàn bộ **363 dịch vụ** (tin nhắn, bạn bè, nhóm, hồ sơ, nhắc hẹn, sticker, ghi chú/bình chọn, Zalo Business...), mỗi dịch vụ có mã YAML đầy đủ, bảng các ô và giải thích từng lựa chọn, nằm ở **[docs/DICH-VU.md](docs/DICH-VU.md)** (tệp sinh tự động, quá dài để đặt hết trong README). Chỉ mục:

<!-- DICH-VU:CHI-MUC:BEGIN -->

| Dịch vụ | Mã | Làm gì |
|---|---|---|
| **Cuộc gọi, AI và cảnh báo** | | |
| [Gọi điện đi](docs/DICH-VU.md#make_call) | `zalo_call.make_call` | Gọi thoại hoặc video cho một người hay nhóm Zalo. Có thể chỉ gọi, hoặc đọc một thông báo rồi cúp, hoặc cho AI... |
| [Gọi cảnh báo](docs/DICH-VU.md#alert_call) | `zalo_call.alert_call` | Gọi để BÁO ĐỘNG: người nhận nghe máy, AI đọc nội dung cảnh báo (không hỏi gì), rồi làm theo ô «Đọc cảnh báo... |
| [Nghe máy](docs/DICH-VU.md#answer_call) | `zalo_call.answer_call` | Nghe một cuộc gọi đang đổ chuông. Có thể kèm thông báo hoặc cho AI nói chuyện, giống «Gọi điện đi». |
| [Từ chối cuộc gọi đến](docs/DICH-VU.md#reject_call) | `zalo_call.reject_call` | Từ chối cuộc gọi đang đổ chuông. |
| [Kết thúc cuộc gọi](docs/DICH-VU.md#end_call) | `zalo_call.end_call` | Kết thúc (hoặc huỷ khi còn đổ chuông) cuộc gọi đang có. |
| [Đọc lên cuộc gọi (TTS)](docs/DICH-VU.md#say_in_call) | `zalo_call.say_in_call` | Đọc một câu bằng TTS của HA lên cuộc gọi đang nói. |
| [Người nhà nói trực tiếp (dừng AI)](docs/DICH-VU.md#take_over_call) | `zalo_call.take_over_call` | Dừng AI đang giữ cuộc gọi và bật thiết bị nhà để người trong nhà nói chuyện trực tiếp với người gọi. |
| [Đồng ý chuyển sang video](docs/DICH-VU.md#accept_video) | `zalo_call.accept_video` | Người đang gọi thoại xin chuyển sang video, bạn đồng ý. Chọn Camera để gửi hình trong nhà; không chọn thì chỉ... |
| [Chuyển cuộc gọi thoại sang video](docs/DICH-VU.md#upgrade_to_video) | `zalo_call.upgrade_to_video` | Khi đang gọi thoại, xin bên kia chuyển sang video rồi phát camera đã chọn (hoặc camera mặc định). |
| [Bật hình trong cuộc gọi](docs/DICH-VU.md#start_call_video) | `zalo_call.start_call_video` | Phát hình camera lên cuộc gọi đang diễn ra (không xin chuyển loại cuộc gọi). |
| [Tắt hình trong cuộc gọi](docs/DICH-VU.md#stop_call_video) | `zalo_call.stop_call_video` | Dừng phát hình camera lên cuộc gọi đang diễn ra. |
| [Bật mic trong cuộc gọi](docs/DICH-VU.md#start_call_mic) | `zalo_call.start_call_mic` | Phát tiếng từ camera, vệ tinh Assist (camera Imou/Dahua, loa R1) hoặc URL lên cuộc gọi đang diễn ra. |
| [Tắt mic trong cuộc gọi](docs/DICH-VU.md#stop_call_mic) | `zalo_call.stop_call_mic` | Dừng phát tiếng lên cuộc gọi đang diễn ra. |
| [Đặt thiết bị mặc định](docs/DICH-VU.md#set_default_devices) | `zalo_call.set_default_devices` | Đặt các chế độ tự động mặc định (tự phát mic, tự đồng ý video, chống vọng, âm lượng). Loa, mic, camera KHÔNG... |
| [Xem mic/loa/camera mặc định](docs/DICH-VU.md#get_default_devices) | `zalo_call.get_default_devices` | Trả về cài đặt thiết bị mặc định hiện tại (đặt bằng set_default_devices). |
| **Quy tắc cho cuộc gọi đến và tin nhắn** | | |
| [Đặt quy tắc cho cuộc gọi đến và tin nhắn](docs/DICH-VU.md#set_rule) | `zalo_call.set_rule` | Quy định hệ thống làm gì khi có người gọi hoặc nhắn đến. Chưa có quy tắc cho người đó thì hệ thống KHÔNG làm... |
| [Xoá quy tắc](docs/DICH-VU.md#remove_rule) | `zalo_call.remove_rule` | Xoá quy tắc của một người/nhóm cụ thể hoặc của một nhóm đối tượng. Từ đó hệ thống quay về «không làm gì» với... |
| [Xem các quy tắc](docs/DICH-VU.md#list_rules) | `zalo_call.list_rules` | Trả về mọi quy tắc đang đặt. |
| [Xem danh bạ Zalo](docs/DICH-VU.md#list_contacts) | `zalo_call.list_contacts` | Danh sách bạn bè và nhóm kèm mã Zalo, để điền vào các ô «Mã Zalo». |
| **Tin nhắn** | | |
| [send_message](docs/DICH-VU.md#send_message) | `zalo_call.send_message` | Gửi tin nhắn Zalo |
| [send_file](docs/DICH-VU.md#send_file) | `zalo_call.send_file` | Gửi một file bất kỳ qua URL hoặc từ đường dẫn cục bộ. |
| [send_image](docs/DICH-VU.md#send_image) | `zalo_call.send_image` | Gửi ảnh Zalo |
| [send_image_to_user](docs/DICH-VU.md#send_image_to_user) | `zalo_call.send_image_to_user` | Gửi 1 ảnh đến user |
| [send_images_to_user](docs/DICH-VU.md#send_images_to_user) | `zalo_call.send_images_to_user` | Gửi nhiều ảnh đến user |
| [send_image_to_group](docs/DICH-VU.md#send_image_to_group) | `zalo_call.send_image_to_group` | Gửi 1 ảnh đến group |
| [send_images_to_group](docs/DICH-VU.md#send_images_to_group) | `zalo_call.send_images_to_group` | Gửi nhiều ảnh đến group |
| [Thu hồi tin nhắn](docs/DICH-VU.md#undo_message) | `zalo_call.undo_message` | Thu hồi tin nhắn đã gửi |
| [send_voice](docs/DICH-VU.md#send_voice) | `zalo_call.send_voice` | Gửi tin nhắn thoại: từ tệp âm thanh, hoặc để TTS của Home Assistant đọc chữ |
| [Xem lịch sử nhóm](docs/DICH-VU.md#get_group_chat_history) | `zalo_call.get_group_chat_history` | Lấy lịch sử tin nhắn của một nhóm |
| [Thả reaction](docs/DICH-VU.md#add_reaction) | `zalo_call.add_reaction` | Thả cảm xúc vào một tin nhắn |
| [Xóa tin nhắn](docs/DICH-VU.md#delete_message) | `zalo_call.delete_message` | Xóa một tin nhắn (chỉ ở phía mình) |
| [Chuyển tiếp tin nhắn](docs/DICH-VU.md#forward_message) | `zalo_call.forward_message` | Chuyển tiếp một tin nhắn |
| [Phân tích link lấy preview](docs/DICH-VU.md#parse_link) | `zalo_call.parse_link` | Phân tích link để lấy thông tin preview |
| [send_card](docs/DICH-VU.md#send_card) | `zalo_call.send_card` | Gửi danh thiếp của một người dùng |
| [send_link](docs/DICH-VU.md#send_link) | `zalo_call.send_link` | Gửi một tin nhắn chứa liên kết có preview |
| [send_video](docs/DICH-VU.md#send_video) | `zalo_call.send_video` | Gửi video qua URL hoặc từ đường dẫn cục bộ |
| [Trích dẫn tin nhắn](docs/DICH-VU.md#quote_message) | `zalo_call.quote_message` | Trích dẫn tin nhắn |
| [Đánh dấu đã xem / đã nhận](docs/DICH-VU.md#mark_seen) | `zalo_call.mark_seen` | Đánh dấu đã xem / đã nhận |
| [Xem tin nhắn quan trọng](docs/DICH-VU.md#fetch_important) | `zalo_call.fetch_important` | Xem tin nhắn quan trọng |
| **Tài khoản và webhook** | | |
| [get_logged_accounts](docs/DICH-VU.md#get_logged_accounts) | `zalo_call.get_logged_accounts` | Lấy danh sách tài khoản Zalo đã login |
| [get_account_details](docs/DICH-VU.md#get_account_details) | `zalo_call.get_account_details` | Lấy chi tiết một tài khoản Zalo |
| [get_account_webhooks](docs/DICH-VU.md#get_account_webhooks) | `zalo_call.get_account_webhooks` | Lấy tất cả config webhook |
| [get_account_webhook](docs/DICH-VU.md#get_account_webhook) | `zalo_call.get_account_webhook` | Lấy config webhook cho account |
| [set_account_webhook](docs/DICH-VU.md#set_account_webhook) | `zalo_call.set_account_webhook` | Cập nhật config webhook |
| [delete_account_webhook](docs/DICH-VU.md#delete_account_webhook) | `zalo_call.delete_account_webhook` | Xóa config webhook |
| [get_proxies](docs/DICH-VU.md#get_proxies) | `zalo_call.get_proxies` | Lấy danh sách proxy |
| [add_proxy](docs/DICH-VU.md#add_proxy) | `zalo_call.add_proxy` | Thêm proxy mới |
| [remove_proxy](docs/DICH-VU.md#remove_proxy) | `zalo_call.remove_proxy` | Xóa proxy |
| [get_login_qr](docs/DICH-VU.md#get_login_qr) | `zalo_call.get_login_qr` | Lấy mã QR đăng nhập Zalo từ server và hiển thị lên thông báo. |
| **Hồ sơ và bạn bè** | | |
| [Tìm người dùng theo SĐT](docs/DICH-VU.md#find_user) | `zalo_call.find_user` | Tìm user bằng số điện thoại |
| [Xem thông tin người dùng](docs/DICH-VU.md#get_user_info) | `zalo_call.get_user_info` | Lấy thông tin user |
| [Gửi lời mời kết bạn](docs/DICH-VU.md#send_friend_request) | `zalo_call.send_friend_request` | Gửi lời mời kết bạn |
| [Chấp nhận kết bạn](docs/DICH-VU.md#accept_friend_request) | `zalo_call.accept_friend_request` | Chấp nhận lời mời kết bạn từ một người dùng |
| [Chặn người dùng](docs/DICH-VU.md#block_user) | `zalo_call.block_user` | Chặn một người dùng |
| [Bỏ chặn người dùng](docs/DICH-VU.md#unblock_user) | `zalo_call.unblock_user` | Bỏ chặn một người dùng |
| [get_all_friends](docs/DICH-VU.md#get_all_friends) | `zalo_call.get_all_friends` | Lấy danh sách tất cả bạn bè |
| [Xem lời mời kết bạn đã gửi](docs/DICH-VU.md#get_sent_friend_requests) | `zalo_call.get_sent_friend_requests` | Lấy danh sách lời mời kết bạn đã gửi |
| [Thu hồi lời mời kết bạn](docs/DICH-VU.md#undo_friend_request) | `zalo_call.undo_friend_request` | Thu hồi lời mời kết bạn đã gửi |
| [Hủy kết bạn](docs/DICH-VU.md#remove_friend) | `zalo_call.remove_friend` | Hủy kết bạn với một người dùng (không hoàn tác được) |
| [Đổi biệt danh](docs/DICH-VU.md#change_friend_alias) | `zalo_call.change_friend_alias` | Thay đổi biệt danh của một người bạn |
| [Xóa biệt danh](docs/DICH-VU.md#remove_friend_alias) | `zalo_call.remove_friend_alias` | Xóa biệt danh của một người bạn |
| [get_all_groups](docs/DICH-VU.md#get_all_groups) | `zalo_call.get_all_groups` | Lấy danh sách tất cả nhóm đã tham gia |
| [Cập nhật thông tin cá nhân](docs/DICH-VU.md#update_profile) | `zalo_call.update_profile` | Cập nhật thông tin cá nhân |
| [Cập nhật cài đặt riêng tư](docs/DICH-VU.md#update_settings) | `zalo_call.update_settings` | Cập nhật cài đặt riêng tư |
| [Chặn xem nhật ký](docs/DICH-VU.md#block_view_feed) | `zalo_call.block_view_feed` | Chặn/bỏ chặn một người bạn xem nhật ký |
| [Đổi ảnh đại diện](docs/DICH-VU.md#change_account_avatar) | `zalo_call.change_account_avatar` | Thay đổi ảnh đại diện |
| [Xem ảnh đại diện đã dùng](docs/DICH-VU.md#get_avatar_list) | `zalo_call.get_avatar_list` | Lấy danh sách các ảnh đại diện đã sử dụng |
| [Xem hoạt động cuối](docs/DICH-VU.md#last_online) | `zalo_call.last_online` | Xem thời gian hoạt động cuối cùng của một người dùng |
| [Từ chối lời mời kết bạn](docs/DICH-VU.md#reject_friend_request) | `zalo_call.reject_friend_request` | Từ chối lời mời kết bạn |
| [Xem cài đặt riêng tư](docs/DICH-VU.md#get_settings) | `zalo_call.get_settings` | Xem cài đặt riêng tư |
| **Nhóm** | | |
| [Tạo nhóm mới](docs/DICH-VU.md#create_group) | `zalo_call.create_group` | Tạo group mới |
| [Xem thông tin nhóm](docs/DICH-VU.md#get_group_info) | `zalo_call.get_group_info` | Lấy info group |
| [Mời thành viên vào nhóm](docs/DICH-VU.md#add_user_to_group) | `zalo_call.add_user_to_group` | Thêm thành viên vào group |
| [Đuổi thành viên](docs/DICH-VU.md#remove_user_from_group) | `zalo_call.remove_user_from_group` | Xóa thành viên khỏi group (không hoàn tác được) |
| [Đổi tên nhóm](docs/DICH-VU.md#change_group_name) | `zalo_call.change_group_name` | Đổi tên nhóm |
| [Đổi ảnh đại diện nhóm](docs/DICH-VU.md#change_group_avatar) | `zalo_call.change_group_avatar` | Đổi ảnh đại diện nhóm |
| [Thêm phó nhóm](docs/DICH-VU.md#add_group_deputy) | `zalo_call.add_group_deputy` | Thêm phó nhóm |
| [Xóa phó nhóm](docs/DICH-VU.md#remove_group_deputy) | `zalo_call.remove_group_deputy` | Xóa phó nhóm |
| [Chuyển quyền sở hữu nhóm](docs/DICH-VU.md#change_group_owner) | `zalo_call.change_group_owner` | Chuyển quyền sở hữu nhóm (không hoàn tác được) |
| [Giải tán nhóm](docs/DICH-VU.md#disperse_group) | `zalo_call.disperse_group` | Giải tán nhóm (không hoàn tác được) |
| [Bật link tham gia nhóm](docs/DICH-VU.md#enable_group_link) | `zalo_call.enable_group_link` | Kích hoạt và lấy link tham gia nhóm |
| [Tắt link tham gia nhóm](docs/DICH-VU.md#disable_group_link) | `zalo_call.disable_group_link` | Vô hiệu hóa link tham gia nhóm |
| [Tham gia nhóm bằng link](docs/DICH-VU.md#join_group) | `zalo_call.join_group` | Tham gia nhóm bằng link mời |
| [Rời nhóm](docs/DICH-VU.md#leave_group) | `zalo_call.leave_group` | Rời khỏi nhóm (không hoàn tác được) |
| [Tạo ghi chú trong nhóm](docs/DICH-VU.md#create_note_group) | `zalo_call.create_note_group` | Tạo ghi chú mới trong nhóm |
| [Sửa ghi chú trong nhóm](docs/DICH-VU.md#edit_note_group) | `zalo_call.edit_note_group` | Chỉnh sửa ghi chú trong nhóm |
| [Xem bảng tin của nhóm](docs/DICH-VU.md#get_list_board) | `zalo_call.get_list_board` | Lấy danh sách các mục trên bảng tin của nhóm |
| [Tạo bình chọn](docs/DICH-VU.md#create_poll) | `zalo_call.create_poll` | Tạo một cuộc bình chọn trong nhóm |
| [Xem chi tiết bình chọn](docs/DICH-VU.md#get_poll_detail) | `zalo_call.get_poll_detail` | Lấy thông tin chi tiết của một cuộc bình chọn |
| [Khóa bình chọn](docs/DICH-VU.md#lock_poll) | `zalo_call.lock_poll` | Khóa một cuộc bình chọn |
| [Xem link nhóm](docs/DICH-VU.md#get_group_link) | `zalo_call.get_group_link` | Xem link nhóm |
| [Bỏ phiếu bình chọn](docs/DICH-VU.md#vote_poll) | `zalo_call.vote_poll` | Bỏ phiếu bình chọn |
| **Sticker** | | |
| [Gửi sticker](docs/DICH-VU.md#send_sticker) | `zalo_call.send_sticker` | Gửi sticker |
| [Xem danh mục sticker](docs/DICH-VU.md#get_stickers) | `zalo_call.get_stickers` | Tìm kiếm sticker theo từ khóa |
| [Xem chi tiết bộ sticker](docs/DICH-VU.md#get_stickers_detail) | `zalo_call.get_stickers_detail` | Lấy thông tin chi tiết của một bộ sticker |
| **Nhắc hẹn** | | |
| [Tạo nhắc hẹn](docs/DICH-VU.md#create_reminder) | `zalo_call.create_reminder` | Tạo nhắc nhở mới |
| [Xóa nhắc hẹn](docs/DICH-VU.md#remove_reminder) | `zalo_call.remove_reminder` | Xóa nhắc nhở |
| [Sửa nhắc hẹn](docs/DICH-VU.md#edit_reminder) | `zalo_call.edit_reminder` | Chỉnh sửa một nhắc hẹn |
| [Xem chi tiết nhắc hẹn](docs/DICH-VU.md#get_reminder) | `zalo_call.get_reminder` | Lấy thông tin chi tiết của một nhắc hẹn |
| [Xem danh sách nhắc hẹn](docs/DICH-VU.md#get_list_reminder) | `zalo_call.get_list_reminder` | Lấy danh sách các nhắc hẹn trong một cuộc trò chuyện |
| [Xem phản hồi nhắc hẹn](docs/DICH-VU.md#get_reminder_responses) | `zalo_call.get_reminder_responses` | Lấy danh sách phản hồi cho một nhắc hẹn |
| [Thêm tin nhắn nhanh](docs/DICH-VU.md#add_quick_message) | `zalo_call.add_quick_message` | Thêm một tin nhắn nhanh mới |
| [Xem tin nhắn nhanh](docs/DICH-VU.md#get_quick_message) | `zalo_call.get_quick_message` | Lấy danh sách tin nhắn nhanh |
| [Xóa tin nhắn nhanh](docs/DICH-VU.md#remove_quick_message) | `zalo_call.remove_quick_message` | Xóa tin nhắn nhanh |
| [Sửa tin nhắn nhanh](docs/DICH-VU.md#update_quick_message) | `zalo_call.update_quick_message` | Cập nhật tin nhắn nhanh |
| **Hội thoại** | | |
| [Tắt thông báo](docs/DICH-VU.md#set_mute) | `zalo_call.set_mute` | Tắt thông báo cho cuộc trò chuyện |
| [Ghim/bỏ ghim hội thoại](docs/DICH-VU.md#set_pinned_conversation) | `zalo_call.set_pinned_conversation` | Ghim hoặc bỏ ghim cuộc trò chuyện |
| [Xem hội thoại chưa đọc](docs/DICH-VU.md#get_unread_mark) | `zalo_call.get_unread_mark` | Lấy danh sách các cuộc trò chuyện được đánh dấu là chưa đọc |
| [Đánh dấu hội thoại chưa đọc](docs/DICH-VU.md#add_unread_mark) | `zalo_call.add_unread_mark` | Đánh dấu một cuộc trò chuyện là chưa đọc |
| [Bỏ đánh dấu chưa đọc](docs/DICH-VU.md#remove_unread_mark) | `zalo_call.remove_unread_mark` | Bỏ đánh dấu chưa đọc cho một cuộc trò chuyện |
| [Xóa hội thoại](docs/DICH-VU.md#delete_chat) | `zalo_call.delete_chat` | Xóa một cuộc trò chuyện khỏi danh sách (không hoàn tác được) |
| [Xem hội thoại đã lưu trữ](docs/DICH-VU.md#get_archived_chat_list) | `zalo_call.get_archived_chat_list` | Lấy danh sách các cuộc trò chuyện đã được lưu trữ |
| [Xem hội thoại đang tự xóa](docs/DICH-VU.md#get_auto_delete_chat) | `zalo_call.get_auto_delete_chat` | Lấy danh sách các cuộc trò chuyện đang bật tự động xóa tin nhắn |
| [Bật/tắt tự xóa tin nhắn](docs/DICH-VU.md#update_auto_delete_chat) | `zalo_call.update_auto_delete_chat` | Bật/tắt chế độ tự động xóa tin nhắn |
| [Xem hội thoại ẩn](docs/DICH-VU.md#get_hidden_conversations) | `zalo_call.get_hidden_conversations` | Lấy danh sách các cuộc trò chuyện đang bị ẩn bằng mã PIN |
| [Ẩn/bỏ ẩn hội thoại](docs/DICH-VU.md#set_hidden_conversations) | `zalo_call.set_hidden_conversations` | Ẩn hoặc bỏ ẩn một cuộc trò chuyện |
| [Đặt PIN hội thoại ẩn](docs/DICH-VU.md#update_hidden_convers_pin) | `zalo_call.update_hidden_convers_pin` | Đặt hoặc thay đổi mã PIN cho các cuộc trò chuyện ẩn |
| [Gỡ PIN hội thoại ẩn](docs/DICH-VU.md#reset_hidden_convers_pin) | `zalo_call.reset_hidden_convers_pin` | Gỡ bỏ mã PIN cho các cuộc trò chuyện ẩn |
| [Xem danh sách tắt thông báo](docs/DICH-VU.md#get_mute) | `zalo_call.get_mute` | Lấy danh sách các cuộc trò chuyện đang bị tắt thông báo |
| [Xem hội thoại đã ghim](docs/DICH-VU.md#get_pin_conversations) | `zalo_call.get_pin_conversations` | Lấy danh sách các cuộc trò chuyện đã được ghim |
| **Nhãn và «đang nhập»** | | |
| [Xem danh sách nhãn](docs/DICH-VU.md#get_labels) | `zalo_call.get_labels` | Lấy danh sách các nhãn |
| [Gửi trạng thái đang gõ](docs/DICH-VU.md#send_typing_event) | `zalo_call.send_typing_event` | Gửi thông báo đang soạn tin nhắn |
| [Gắn nhãn cho hội thoại](docs/DICH-VU.md#update_label) | `zalo_call.update_label` | Gắn nhãn cho hội thoại |
| **Phiên và xác thực (nâng cao)** | | |
| [decryptGids](docs/DICH-VU.md#decrypt_gids) | `zalo_call.decrypt_gids` | decryptGids — Giải mã danh sách Global ID (g_...) ẩn danh thành User ID thật (tương ứng hàm... |
| [encryptGids](docs/DICH-VU.md#encrypt_gids) | `zalo_call.encrypt_gids` | encryptGids — Mã hóa danh sách UID thật sang định danh ẩn danh Global Noise ID (OTDAKO...) (command 12053) |
| [exportSession](docs/DICH-VU.md#export_session) | `zalo_call.export_session` | exportSession — Xuất toàn bộ thông tin phiên đăng nhập hiện tại (uid, imei, userAgent, language, cookie) dưới... |
| [getContext](docs/DICH-VU.md#get_context) | `zalo_call.get_context` | getContext — API getContext thuộc phân hệ auth. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly... |
| [getCookie](docs/DICH-VU.md#get_cookie) | `zalo_call.get_cookie` | getCookie — Get the current cookie string (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc... |
| [getListDevice](docs/DICH-VU.md#get_list_device) | `zalo_call.get_list_device` | getListDevice — Lấy danh sách các thiết bị đang đăng nhập tài khoản Zalo hiện tại. |
| [getNoisedIds](docs/DICH-VU.md#get_noised_ids) | `zalo_call.get_noised_ids` | getNoisedIds — Chuyển đổi danh sách UID cá nhân (fids) và GID nhóm (gids) dạng số thuần (từ SQLite ZDB4.0... |
| [getOwnId](docs/DICH-VU.md#get_own_id) | `zalo_call.get_own_id` | getOwnId — API getOwnId thuộc phân hệ auth. (chưa tự động: khong dung dich vu Zalo qua serviceMap (xu ly cuc... |
| [getQR](docs/DICH-VU.md#get_q_r) | `zalo_call.get_q_r` | getQR — Lấy mã QR của danh sách người dùng theo UID. |
| [lostFocus](docs/DICH-VU.md#lost_focus) | `zalo_call.lost_focus` | lostFocus — Gửi tín hiệu thông báo ứng dụng chuyển sang chế độ chạy nền (Background). |
| [scanURL](docs/DICH-VU.md#scan_u_r_l) | `zalo_call.scan_u_r_l` | scanURL — Quét và kiểm tra độ an toàn của đường dẫn URL thông qua bộ lọc bảo mật Zalo. |
| [updateActiveStatus](docs/DICH-VU.md#update_active_status) | `zalo_call.update_active_status` | updateActiveStatus — Cập nhật trạng thái hoạt động (Online / Offline / Ping) của tài khoản. (chưa tự động:... |
| [updateLang](docs/DICH-VU.md#update_lang) | `zalo_call.update_lang` | updateLang — Cập nhật ngôn ngữ hiển thị của phiên tài khoản Zalo. |
| **Chat (nâng cao)** | | |
| [getBlockSharingConversations](docs/DICH-VU.md#get_block_sharing_conversations) | `zalo_call.get_block_sharing_conversations` | getBlockSharingConversations — Lấy danh sách hội thoại đang bật chế độ chặn chia sẻ / chuyển tiếp tin nhắn... |
| [getConvOfflineMessages](docs/DICH-VU.md#get_conv_offline_messages) | `zalo_call.get_conv_offline_messages` | getConvOfflineMessages — Lấy danh sách hội thoại nhóm có tin nhắn ngoại tuyến mới (command 12300) |
| [getDirectMessageStatus](docs/DICH-VU.md#get_direct_message_status) | `zalo_call.get_direct_message_status` | getDirectMessageStatus — Truy vấn trạng thái Đã nhận (deliver) và Đã xem (seen) tin nhắn trong các hội thoại... |
| [getLastSeen](docs/DICH-VU.md#get_last_seen) | `zalo_call.get_last_seen` | getLastSeen — Lấy thông tin trạng thái đã xem cuối cùng của danh sách nhóm và cá nhân (command 12009) |
| [getLastSeenReaction](docs/DICH-VU.md#get_last_seen_reaction) | `zalo_call.get_last_seen_reaction` | getLastSeenReaction — Lấy trạng thái đã xem cảm xúc (Reaction) cuối cùng của danh sách nhóm và cá nhân... |
| [getRecentSearchList](docs/DICH-VU.md#get_recent_search_list) | `zalo_call.get_recent_search_list` | getRecentSearchList — Lấy danh sách lịch sử tìm kiếm gần đây trên Zalo (command 12125) |
| [getSuggestedConversations](docs/DICH-VU.md#get_suggested_conversations) | `zalo_call.get_suggested_conversations` | getSuggestedConversations — Lấy danh sách các cuộc hội thoại được gợi ý (command 11233) |
| [getTranslateSetting](docs/DICH-VU.md#get_translate_setting) | `zalo_call.get_translate_setting` | getTranslateSetting — Lấy cấu hình tính năng dịch tin nhắn tự động bằng Zalo AI (command 13395) |
| [markSubTabSeen](docs/DICH-VU.md#mark_sub_tab_seen) | `zalo_call.mark_sub_tab_seen` | markSubTabSeen — Đánh dấu đã xem các tab phụ của danh sách hội thoại (command 16214) |
| [preloadConversations](docs/DICH-VU.md#preload_conversations) | `zalo_call.preload_conversations` | preloadConversations — Tải trước tin nhắn cuối cùng và trạng thái đã đọc của các hội thoại đang hoạt động... |
| [renewMessageLink](docs/DICH-VU.md#renew_message_link) | `zalo_call.renew_message_link` | renewMessageLink — Gia hạn đường dẫn tải tệp đính kèm / đa phương tiện đã hết hạn trong tin nhắn (command... |
| [sendBankCard](docs/DICH-VU.md#send_bank_card) | `zalo_call.send_bank_card` | sendBankCard — Gửi danh thiếp thông tin tài khoản ngân hàng (Bank Card) vào cuộc trò chuyện. (không hoàn tác... |
| [sendDeliveredEvent](docs/DICH-VU.md#send_delivered_event) | `zalo_call.send_delivered_event` | sendDeliveredEvent — Gửi tín hiệu xác nhận Đã nhận (Delivered) cho một hoặc nhiều tin nhắn. (chưa tự động:... |
| [sendReport](docs/DICH-VU.md#send_report) | `zalo_call.send_report` | sendReport — Gửi báo cáo vi phạm (Report Abuse) đối với người dùng hoặc cuộc trò chuyện. (chưa tự động: khong... |
| [sendSeenEvent](docs/DICH-VU.md#send_seen_event) | `zalo_call.send_seen_event` | sendSeenEvent — Gửi tín hiệu xác nhận Đã xem (Seen) cho các tin nhắn trong hội thoại. (chưa tự động: khong... |
| [setPinnedConversations](docs/DICH-VU.md#set_pinned_conversations) | `zalo_call.set_pinned_conversations` | setPinnedConversations — Ghim hoặc bỏ ghim cuộc trò chuyện lên đầu danh sách. |
| [translateMessage](docs/DICH-VU.md#translate_message) | `zalo_call.translate_message` | translateMessage — Dịch thủ công một tin nhắn văn bản bằng Zalo AI (command 13397) |
| [translateMessageAuto](docs/DICH-VU.md#translate_message_auto) | `zalo_call.translate_message_auto` | translateMessageAuto — Gửi yêu cầu dịch tự động hàng loạt tin nhắn đến bằng Zalo AI (command 13398). Kết quả... |
| [translateMessageSuggest](docs/DICH-VU.md#translate_message_suggest) | `zalo_call.translate_message_suggest` | translateMessageSuggest — Gửi yêu cầu dịch gợi ý tin nhắn đang soạn thảo bằng Zalo AI (command 13399). Kết... |
| [undo](docs/DICH-VU.md#undo) | `zalo_call.undo` | undo — Thu hồi (Undo) một tin nhắn đã gửi với tất cả mọi người trong cuộc trò chuyện. (chưa tự động: khong... |
| [undoMultiMessage](docs/DICH-VU.md#undo_multi_message) | `zalo_call.undo_multi_message` | undoMultiMessage — Thu hồi hàng loạt nhiều tin nhắn cùng lúc trong hội thoại cá nhân hoặc nhóm (command 12115... |
| [updateArchivedChatList](docs/DICH-VU.md#update_archived_chat_list) | `zalo_call.update_archived_chat_list` | updateArchivedChatList — Đưa cuộc trò chuyện vào mục Lưu trữ (Archive) hoặc khôi phục ra ngoài. |
| [updateBlockSharingConversation](docs/DICH-VU.md#update_block_sharing_conversation) | `zalo_call.update_block_sharing_conversation` | updateBlockSharingConversation — Bật hoặc tắt chế độ chặn chia sẻ / chuyển tiếp tin nhắn trong một hội thoại... |
| [updatePinConversations](docs/DICH-VU.md#update_pin_conversations) | `zalo_call.update_pin_conversations` | updatePinConversations — Cập nhật danh sách hội thoại ghim qua /api/pinconvers/update (command 12121) hoặc... |
| [updateRecentSearch](docs/DICH-VU.md#update_recent_search) | `zalo_call.update_recent_search` | updateRecentSearch — Cập nhật danh sách lịch sử tìm kiếm gần đây trên Zalo (command 12126) |
| [updateTranslateSetting](docs/DICH-VU.md#update_translate_setting) | `zalo_call.update_translate_setting` | updateTranslateSetting — Cập nhật cấu hình dịch tin nhắn Zalo AI cho một hội thoại (command 13396) (chưa tự... |
| **Nhóm (nâng cao)** | | |
| [addGroupBlockedMember](docs/DICH-VU.md#add_group_blocked_member) | `zalo_call.add_group_blocked_member` | addGroupBlockedMember — Chặn một hoặc nhiều thành viên khỏi nhóm (không cho tham gia lại). (không hoàn tác... |
| [analyseGroup](docs/DICH-VU.md#analyse_group) | `zalo_call.analyse_group` | analyseGroup — Lấy dữ liệu phân tích/thống kê của nhóm qua /api/group/analyse (command 12407) |
| [checkQuotaCommunityMember](docs/DICH-VU.md#check_quota_community_member) | `zalo_call.check_quota_community_member` | checkQuotaCommunityMember — Kiểm tra điều kiện/hạn mức thành viên Cộng đồng đối với một thành viên cụ thể... |
| [deleteGroupInviteBox](docs/DICH-VU.md#delete_group_invite_box) | `zalo_call.delete_group_invite_box` | deleteGroupInviteBox — Xóa lời mời tham gia nhóm trong hộp thư lời mời nhóm. (không hoàn tác được) |
| [getE2eeGroupList](docs/DICH-VU.md#get_e2ee_group_list) | `zalo_call.get_e2ee_group_list` | getE2eeGroupList — Lấy danh sách các nhóm đang bật mã hóa đầu cuối E2EE (command 12146) |
| [getExtraGroupInfo](docs/DICH-VU.md#get_extra_group_info) | `zalo_call.get_extra_group_info` | getExtraGroupInfo — Lấy ngữ cảnh và vai trò mở rộng của người dùng đối với nhiều nhóm (command 12607) |
| [getGroupBlockedMember](docs/DICH-VU.md#get_group_blocked_member) | `zalo_call.get_group_blocked_member` | getGroupBlockedMember — Lấy danh sách các tài khoản đang bị chặn khỏi nhóm. (không hoàn tác được) |
| [getGroupCloudMessageJump](docs/DICH-VU.md#get_group_cloud_message_jump) | `zalo_call.get_group_cloud_message_jump` | getGroupCloudMessageJump — Nhảy tới vị trí một tin nhắn nhóm cụ thể trên Zalo Cloud Message và lấy ngữ cảnh... |
| [getGroupCloudMessagePath](docs/DICH-VU.md#get_group_cloud_message_path) | `zalo_call.get_group_cloud_message_path` | getGroupCloudMessagePath — Lấy chuỗi tin nhắn nhóm theo đường dẫn nhảy tới một tin nhắn cụ thể (globalMsgId /... |
| [getGroupInfoV2](docs/DICH-VU.md#get_group_info_v2) | `zalo_call.get_group_info_v2` | getGroupInfoV2 — Lấy thông tin nhóm và danh sách thành viên theo trang qua /api/group/getgi/v2 hoặc... |
| [getGroupInviteBoxInfo](docs/DICH-VU.md#get_group_invite_box_info) | `zalo_call.get_group_invite_box_info` | getGroupInviteBoxInfo — Lấy thông tin chi tiết của một lời mời vào nhóm cụ thể. |
| [getGroupInviteBoxList](docs/DICH-VU.md#get_group_invite_box_list) | `zalo_call.get_group_invite_box_list` | getGroupInviteBoxList — Lấy danh sách tất cả lời mời tham gia nhóm đang chờ trong hộp thư. |
| [getGroupLinkInfo](docs/DICH-VU.md#get_group_link_info) | `zalo_call.get_group_link_info` | getGroupLinkInfo — Tra cứu thông tin nhóm và danh sách thành viên theo trang từ đường dẫn nhóm công khai... |
| [getGroupListV3](docs/DICH-VU.md#get_group_list_v3) | `zalo_call.get_group_list_v3` | getGroupListV3 — Lấy danh sách nhóm theo trang kèm thông tin thành viên đại diện (currentMems) và gợi ý nhóm... |
| [getGroupMembersInfo](docs/DICH-VU.md#get_group_members_info) | `zalo_call.get_group_members_info` | getGroupMembersInfo — Giải mã hàng loạt thông tin hồ sơ thành viên (displayName, zaloName, avatar, globalId)... |
| [getGroupMessageStatus](docs/DICH-VU.md#get_group_message_status) | `zalo_call.get_group_message_status` | getGroupMessageStatus — Truy vấn trạng thái Đã nhận (deliver) và Đã xem (seen) tin nhắn của danh sách thành... |
| [getMultiGroupCloudMessages](docs/DICH-VU.md#get_multi_group_cloud_messages) | `zalo_call.get_multi_group_cloud_messages` | getMultiGroupCloudMessages — Đồng bộ nhanh tin nhắn Cloud của nhiều nhóm cùng lúc theo danh sách groupIds... |
| [getPendingGroupMembers](docs/DICH-VU.md#get_pending_group_members) | `zalo_call.get_pending_group_members` | getPendingGroupMembers — Lấy danh sách các yêu cầu xin vào nhóm đang chờ Quản trị viên phê duyệt. |
| [getQuotaCommunity](docs/DICH-VU.md#get_quota_community) | `zalo_call.get_quota_community` | getQuotaCommunity — Kiểm tra hạn mức nâng cấp nhóm lên Cộng đồng của tài khoản (command 12181) |
| [getRelatedFriendGroup](docs/DICH-VU.md#get_related_friend_group) | `zalo_call.get_related_friend_group` | getRelatedFriendGroup — Kiểm tra danh sách các nhóm chung giữa tài khoản hiện tại và danh sách UID truyền vào... |
| [inviteUserToGroups](docs/DICH-VU.md#invite_user_to_groups) | `zalo_call.invite_user_to_groups` | inviteUserToGroups — Gửi lời mời tham gia một hoặc nhiều nhóm tới người dùng. |
| [joinGroupInviteBox](docs/DICH-VU.md#join_group_invite_box) | `zalo_call.join_group_invite_box` | joinGroupInviteBox — Chấp nhận lời mời tham gia nhóm từ hộp thư lời mời. |
| [removeGroupBlockedMember](docs/DICH-VU.md#remove_group_blocked_member) | `zalo_call.remove_group_blocked_member` | removeGroupBlockedMember — Gỡ chặn (Unblock) cho người dùng khỏi danh sách chặn của nhóm. (không hoàn tác... |
| [removeGroupTopic](docs/DICH-VU.md#remove_group_topic) | `zalo_call.remove_group_topic` | removeGroupTopic — Xóa chủ đề đang ghim trên đầu nhóm (command 11829) (không hoàn tác được) |
| [removeUserFromGroups](docs/DICH-VU.md#remove_user_from_groups) | `zalo_call.remove_user_from_groups` | removeUserFromGroups — Xóa một thành viên khỏi nhiều nhóm cùng lúc (command 12606) (không hoàn tác được) |
| [reviewPendingMemberRequest](docs/DICH-VU.md#review_pending_member_request) | `zalo_call.review_pending_member_request` | reviewPendingMemberRequest — Phê duyệt (Chấp nhận hoặc Từ chối) yêu cầu xin tham gia nhóm của thành viên mới. |
| [updateGroupSettings](docs/DICH-VU.md#update_group_settings) | `zalo_call.update_group_settings` | updateGroupSettings — Cập nhật các thiết lập quyền hạn của nhóm (ẩn thành viên lockViewMember, duyệt thành... |
| [upgradeGroupToCommunity](docs/DICH-VU.md#upgrade_group_to_community) | `zalo_call.upgrade_group_to_community` | upgradeGroupToCommunity — Nâng cấp nhóm thường lên Cộng đồng (Community - tối đa 1000 thành viên). |
| **Bạn bè (nâng cao)** | | |
| [clearUnreadFriendRequests](docs/DICH-VU.md#clear_unread_friend_requests) | `zalo_call.clear_unread_friend_requests` | clearUnreadFriendRequests — Đánh dấu đã xem danh sách lời mời kết bạn chưa đọc (command 12232) (không hoàn... |
| [findUserByUsername](docs/DICH-VU.md#find_user_by_username) | `zalo_call.find_user_by_username` | findUserByUsername — Tìm kiếm thông tin tài khoản Zalo thông qua Username. |
| [getAliasList](docs/DICH-VU.md#get_alias_list) | `zalo_call.get_alias_list` | getAliasList — Lấy danh sách toàn bộ tên gợi nhớ (Alias) đã đặt cho bạn bè. |
| [getAliasListV2](docs/DICH-VU.md#get_alias_list_v2) | `zalo_call.get_alias_list_v2` | getAliasListV2 — Lấy danh sách tên gợi nhớ (Alias) của bạn bè chuẩn V2 có hỗ trợ phân trang (command 12205) |
| [getBlockFriends](docs/DICH-VU.md#get_block_friends) | `zalo_call.get_block_friends` | getBlockFriends — Lấy danh sách người dùng đang bị chặn chuẩn V2 (command 11429) (không hoàn tác được) |
| [getCloseFriends](docs/DICH-VU.md#get_close_friends) | `zalo_call.get_close_friends` | getCloseFriends — Lấy danh sách bạn thân (Close Friends). |
| [getExtraFriendInfo](docs/DICH-VU.md#get_extra_friend_info) | `zalo_call.get_extra_friend_info` | getExtraFriendInfo — Lấy ngữ cảnh và vai trò mở rộng (ví dụ role: ["boss"]) của danh sách bạn bè (command... |
| [getFriendBoardList](docs/DICH-VU.md#get_friend_board_list) | `zalo_call.get_friend_board_list` | getFriendBoardList — Lấy thông tin bảng tin chung với một người bạn. |
| [getFriendOnlines](docs/DICH-VU.md#get_friend_onlines) | `zalo_call.get_friend_onlines` | getFriendOnlines — Lấy danh sách bạn bè đang trực tuyến (Online) kèm trạng thái thiết bị. |
| [getFriendRecommendations](docs/DICH-VU.md#get_friend_recommendations) | `zalo_call.get_friend_recommendations` | getFriendRecommendations — Lấy danh sách gợi ý kết bạn và lời mời kết bạn đã nhận. |
| [getFriendRequestStatus](docs/DICH-VU.md#get_friend_request_status) | `zalo_call.get_friend_request_status` | getFriendRequestStatus — Kiểm tra trạng thái quan hệ bạn bè và lời mời kết bạn với một UID. |
| [getFriendsActivePCWeb](docs/DICH-VU.md#get_friends_active_p_c_web) | `zalo_call.get_friends_active_p_c_web` | getFriendsActivePCWeb — Lấy danh sách bạn bè đang hoạt động trên Zalo PC / Web qua... |
| [getFriendsEmojiStatus](docs/DICH-VU.md#get_friends_emoji_status) | `zalo_call.get_friends_emoji_status` | getFriendsEmojiStatus — Lấy danh sách trạng thái Emoji (Emoji Status) hiện tại của bạn bè (command 16301) |
| [getLastReadContactTab](docs/DICH-VU.md#get_last_read_contact_tab) | `zalo_call.get_last_read_contact_tab` | getLastReadContactTab — Lấy dấu thời gian lần cuối đọc tab Danh bạ (command 12230) |
| [getMultiUserQRCodes](docs/DICH-VU.md#get_multi_user_q_r_codes) | `zalo_call.get_multi_user_q_r_codes` | getMultiUserQRCodes — Lấy mã QR cá nhân của một hoặc nhiều người dùng (command 12128) |
| [getMultiUsersByPhones](docs/DICH-VU.md#get_multi_users_by_phones) | `zalo_call.get_multi_users_by_phones` | getMultiUsersByPhones — Tra cứu hàng loạt thông tin tài khoản Zalo từ danh sách nhiều số điện thoại cùng lúc. |
| [getPhonebookV2](docs/DICH-VU.md#get_phonebook_v2) | `zalo_call.get_phonebook_v2` | getPhonebookV2 — Lấy danh bạ bạn bè đồng bộ từ số điện thoại chuẩn V2 (command 12428) |
| [readContactTab](docs/DICH-VU.md#read_contact_tab) | `zalo_call.read_contact_tab` | readContactTab — Đánh dấu đã đọc tab Danh bạ (command 12231) |
| [removeFriendRecommendation](docs/DICH-VU.md#remove_friend_recommendation) | `zalo_call.remove_friend_recommendation` | removeFriendRecommendation — Xóa một gợi ý kết bạn khỏi danh sách đề xuất (command 11432) (không hoàn tác... |
| [removeFriendRecommendationV2](docs/DICH-VU.md#remove_friend_recommendation_v2) | `zalo_call.remove_friend_recommendation_v2` | removeFriendRecommendationV2 — Xóa một gợi ý kết bạn khỏi danh sách đề xuất V2 (command 11438) (không hoàn... |
| [updateCloseFriend](docs/DICH-VU.md#update_close_friend) | `zalo_call.update_close_friend` | updateCloseFriend — Thêm hoặc xóa người dùng khỏi danh sách Bạn thân (command 11421) |
| [verifyFriend](docs/DICH-VU.md#verify_friend) | `zalo_call.verify_friend` | verifyFriend — Kiểm tra và xác thực danh sách bạn bè qua /api/social/friend/verify (command 11138) |
| **Hồ sơ (nâng cao)** | | |
| [deleteAvatar](docs/DICH-VU.md#delete_avatar) | `zalo_call.delete_avatar` | deleteAvatar — Xóa một hoặc nhiều ảnh đại diện cũ trong kho ảnh đại diện. (không hoàn tác được) |
| [disableLimitSearchPhoneReminder](docs/DICH-VU.md#disable_limit_search_phone_reminder) | `zalo_call.disable_limit_search_phone_reminder` | disableLimitSearchPhoneReminder — Tắt thông báo nhắc nhở giới hạn tìm kiếm số điện thoại (command 12131)... |
| [fetchAccountInfo](docs/DICH-VU.md#fetch_account_info) | `zalo_call.fetch_account_info` | fetchAccountInfo — API fetchAccountInfo thuộc phân hệ profile. |
| [getAvatarUrlProfile](docs/DICH-VU.md#get_avatar_url_profile) | `zalo_call.get_avatar_url_profile` | getAvatarUrlProfile — Lấy đường dẫn ảnh đại diện của danh sách hồ sơ người dùng. |
| [getEmojiStatusConfig](docs/DICH-VU.md#get_emoji_status_config) | `zalo_call.get_emoji_status_config` | getEmojiStatusConfig — Lấy cấu hình và danh sách bộ biểu tượng Trạng thái Emoji (Emoji Status - command 16300) |
| [getEnterpriseProfiles](docs/DICH-VU.md#get_enterprise_profiles) | `zalo_call.get_enterprise_profiles` | getEnterpriseProfiles — Lấy thông tin hồ sơ doanh nghiệp (Zalo Enterprise) của một hoặc nhiều tài khoản... |
| [getFullAvatar](docs/DICH-VU.md#get_full_avatar) | `zalo_call.get_full_avatar` | getFullAvatar — Lấy ảnh đại diện kích thước gốc (Full HD) của một người dùng theo UID. |
| [getMiniProfile](docs/DICH-VU.md#get_mini_profile) | `zalo_call.get_mini_profile` | getMiniProfile — Lấy nhanh thông tin hồ sơ rút gọn (Avatar, Global ID, gói Biz) của danh sách người dùng... |
| [getProfileExtra](docs/DICH-VU.md#get_profile_extra) | `zalo_call.get_profile_extra` | getProfileExtra — Lấy thông tin mở rộng của hồ sơ cá nhân (command 11864) |
| [getProfileRank](docs/DICH-VU.md#get_profile_rank) | `zalo_call.get_profile_rank` | getProfileRank — Lấy hạng tài khoản Zalo của một người dùng (ví dụ "WHITE", "GOLD" - command 12012) |
| [getProfileVerificationStatus](docs/DICH-VU.md#get_profile_verification_status) | `zalo_call.get_profile_verification_status` | getProfileVerificationStatus — Kiểm tra trạng thái xác thực định danh (eKYC) của tài khoản Zalo (command... |
| [pushProfileVerificationMessage](docs/DICH-VU.md#push_profile_verification_message) | `zalo_call.push_profile_verification_message` | pushProfileVerificationMessage — Yêu cầu đẩy tin nhắn hướng dẫn xác thực tài khoản (eKYC) từ Official Account... |
| [registerTrialBizAccount](docs/DICH-VU.md#register_trial_biz_account) | `zalo_call.register_trial_biz_account` | registerTrialBizAccount — Đăng ký dùng thử gói Zalo Business V2 cho tài khoản (command 12152) |
| [reuseAvatar](docs/DICH-VU.md#reuse_avatar) | `zalo_call.reuse_avatar` | reuseAvatar — Sử dụng lại một ảnh đại diện cũ từ kho lịch sử ảnh đại diện. |
| [updateProfileBio](docs/DICH-VU.md#update_profile_bio) | `zalo_call.update_profile_bio` | updateProfileBio — Cập nhật dòng tiểu sử (Status / Bio) trên trang cá nhân. |
| [updateProfileMode](docs/DICH-VU.md#update_profile_mode) | `zalo_call.update_profile_mode` | updateProfileMode — Cập nhật chế độ hồ sơ người dùng (command 11865) |
| **Đồng bộ (nâng cao)** | | |
| [cancelPullMobile](docs/DICH-VU.md#cancel_pull_mobile) | `zalo_call.cancel_pull_mobile` | cancelPullMobile — Huỷ yêu cầu đồng bộ tin nhắn từ điện thoại đang chờ (cancel_pull_mobile_msg, command... |
| [deleteMobileMsgSnapshot](docs/DICH-VU.md#delete_mobile_msg_snapshot) | `zalo_call.delete_mobile_msg_snapshot` | deleteMobileMsgSnapshot — Xóa bản chụp nhanh (snapshot) dữ liệu đồng bộ tin nhắn từ thiết bị di động sau khi... |
| [downloadTransferSync](docs/DICH-VU.md#download_transfer_sync) | `zalo_call.download_transfer_sync` | downloadTransferSync — Tải khối dữ liệu snapshot đồng bộ tin nhắn từ máy chủ transfersync.zaloapp.com (chưa... |
| [getBackupMsgInfo](docs/DICH-VU.md#get_backup_msg_info) | `zalo_call.get_backup_msg_info` | getBackupMsgInfo — Lấy thông tin bản sao lưu tin nhắn hiện có trên máy chủ (command 12096) |
| [getCrossDbInfo](docs/DICH-VU.md#get_cross_db_info) | `zalo_call.get_cross_db_info` | getCrossDbInfo — Lấy thông tin cơ sở dữ liệu chéo (Cross-DB) phục vụ đồng bộ dữ liệu sang máy tính (command... |
| [getSyncData](docs/DICH-VU.md#get_sync_data) | `zalo_call.get_sync_data` | getSyncData — Tải xuống file sao lưu tin nhắn từ sự kiện syncmsg_info (.db.crypt, định dạng ZDB4.0) và lưu ra... |
| [pullMobile](docs/DICH-VU.md#pull_mobile) | `zalo_call.pull_mobile` | pullMobile — Yêu cầu thiết bị di động Zalo đóng gói và tải lên bản sao lưu tin nhắn (pull_mobile_msg, command... |
| [requestSyncFromPhone](docs/DICH-VU.md#request_sync_from_phone) | `zalo_call.request_sync_from_phone` | requestSyncFromPhone — Phát tín hiệu yêu cầu đồng bộ tin nhắn từ ứng dụng Zalo trên điện thoại... |
| [submitSyncMediaActions](docs/DICH-VU.md#submit_sync_media_actions) | `zalo_call.submit_sync_media_actions` | submitSyncMediaActions — Gửi danh sách hành động đồng bộ hóa tệp đa phương tiện lên máy chủ (command 16213) |
| [uploadBackupChunk](docs/DICH-VU.md#upload_backup_chunk) | `zalo_call.upload_backup_chunk` | uploadBackupChunk — Tải lên gói dữ liệu phân mảnh (chunk) sao lưu tin nhắn từ máy tính sang điện thoại... |
| **Zalo Cloud** | | |
| [ackCloudOnboarding](docs/DICH-VU.md#ack_cloud_onboarding) | `zalo_call.ack_cloud_onboarding` | ackCloudOnboarding — Xác nhận hoàn tất bước khởi tạo (Onboarding ACK V1) trên ZCloud (command 12746) (chưa tự... |
| [getCloudDownloadUrls](docs/DICH-VU.md#get_cloud_download_urls) | `zalo_call.get_cloud_download_urls` | getCloudDownloadUrls — Lấy danh sách đường dẫn tải xuống các tệp Media lưu trữ trên ZCloud theo noiseIds... |
| [getCloudInfo](docs/DICH-VU.md#get_cloud_info) | `zalo_call.get_cloud_info` | getCloudInfo — Lấy thông tin gói thuê bao Zalo Cloud (command 12754) (chưa tự động: goi 0 request (nhieu buoc... |
| [getCloudSettings](docs/DICH-VU.md#get_cloud_settings) | `zalo_call.get_cloud_settings` | getCloudSettings — Lấy cấu hình giới hạn tệp và cài đặt ZCloud của tài khoản (command 12756) (chưa tự động:... |
| [getCloudUploadUrl](docs/DICH-VU.md#get_cloud_upload_url) | `zalo_call.get_cloud_upload_url` | getCloudUploadUrl — Lấy đường dẫn tải lên tệp di trú lên ZCloud (command 12752) (chưa tự động: goi 0 request... |
| [getCloudViewerKey](docs/DICH-VU.md#get_cloud_viewer_key) | `zalo_call.get_cloud_viewer_key` | getCloudViewerKey — Lấy cặp khóa phiên (viewer_key và khóa giải mã AES-256 enk) cho hệ thống ZCloud / MyCloud... |
| [getFamilyProfile](docs/DICH-VU.md#get_family_profile) | `zalo_call.get_family_profile` | getFamilyProfile — Lấy thông tin nhóm gia đình ZFamily (command 12757) (chưa tự động: goi 0 request (nhieu... |
| [getFamilyUsage](docs/DICH-VU.md#get_family_usage) | `zalo_call.get_family_usage` | getFamilyUsage — Kiểm tra dung lượng sử dụng gói ZCloud Gia đình (Family Usage - command 12758) (chưa tự... |
| [getFamilyViewerKey](docs/DICH-VU.md#get_family_viewer_key) | `zalo_call.get_family_viewer_key` | getFamilyViewerKey — Lấy cặp khóa phiên (viewer_key và khóa giải mã AES-256 enk) cho gói gia đình ZFamily... |
| [getUsageMyCloud](docs/DICH-VU.md#get_usage_my_cloud) | `zalo_call.get_usage_my_cloud` | getUsageMyCloud — Kiểm tra hạn mức và dung lượng sử dụng Cloud của tôi (MyCloud - command 12748) (chưa tự... |
| [getUsageZCloud](docs/DICH-VU.md#get_usage_z_cloud) | `zalo_call.get_usage_z_cloud` | getUsageZCloud — Kiểm tra dung lượng sử dụng ZCloud V2 (bao gồm MyCloud và Sao lưu tin nhắn - command 12749)... |
| [migrateCloudRecent](docs/DICH-VU.md#migrate_cloud_recent) | `zalo_call.migrate_cloud_recent` | migrateCloudRecent — Thực hiện di trú dữ liệu tệp tin gần đây lên ZCloud (command 12753) (chưa tự động: goi 0... |
| [resetCloudQueue](docs/DICH-VU.md#reset_cloud_queue) | `zalo_call.reset_cloud_queue` | resetCloudQueue — Đặt lại hàng đợi đồng bộ Media trên ZCloud (command 12744) (chưa tự động: goi 0 request... |
| [submitCloudMediaExtInfo](docs/DICH-VU.md#submit_cloud_media_ext_info) | `zalo_call.submit_cloud_media_ext_info` | submitCloudMediaExtInfo — Gửi thông tin mở rộng (siêu dữ liệu / khóa giải mã) của các tệp Media lên hàng đợi... |
| [submitCloudVerifyAction](docs/DICH-VU.md#submit_cloud_verify_action) | `zalo_call.submit_cloud_verify_action` | submitCloudVerifyAction — Gửi hành động xác thực bảo mật ZCloud (Onboarding ACK V2 - command 12750) (chưa tự... |
| [verifyCloudMedia](docs/DICH-VU.md#verify_cloud_media) | `zalo_call.verify_cloud_media` | verifyCloudMedia — Kiểm tra và lấy danh sách mục Media lưu trữ trên ZCloud (command 12740 / 12761) (chưa tự... |
| **Cuộc gọi theo thư viện zca-js (nâng cao)** | | |
| [addUserGroupCall](docs/DICH-VU.md#add_user_group_call) | `zalo_call.add_user_group_call` | addUserGroupCall — Mời thêm thành viên mới vào cuộc gọi nhóm đang diễn ra (cmd 12435 -... |
| [answerAckVoiceCall](docs/DICH-VU.md#answer_ack_voice_call) | `zalo_call.answer_ack_voice_call` | answerAckVoiceCall — Gửi xác nhận hoàn tất bắt tay nhận cuộc gọi 1-1 (cmd 11304 - /api/voicecall/answerack,... |
| [answerGroupCall](docs/DICH-VU.md#answer_group_call) | `zalo_call.answer_group_call` | answerGroupCall — Chấp nhận tham gia cuộc gọi nhóm khi nhận được lời mời (cmd 12436 -... |
| [answerVoiceCall](docs/DICH-VU.md#answer_voice_call) | `zalo_call.answer_voice_call` | answerVoiceCall — Chấp nhận (Bắt máy) cuộc gọi Thoại/Video 1-1 đến (cmd 11303 - /api/voicecall/answer, signal... |
| [broadcastGroupCallState](docs/DICH-VU.md#broadcast_group_call_state) | `zalo_call.broadcast_group_call_state` | broadcastGroupCallState — Phát quảng bá trạng thái thiết bị (Mic, Camera, Screen Share) tới các thành viên... |
| [cancelGroupCall](docs/DICH-VU.md#cancel_group_call) | `zalo_call.cancel_group_call` | cancelGroupCall — Hủy lời mời cuộc gọi nhóm (cmd 12437 - /api/voicecall/group/cancel). (chưa tự động: khong... |
| [cancelVoiceCall](docs/DICH-VU.md#cancel_voice_call) | `zalo_call.cancel_voice_call` | cancelVoiceCall — Hủy cuộc gọi 1-1 đang đổ chuông trước khi người nhận bắt máy (cmd 11305 -... |
| [createController](docs/DICH-VU.md#create_controller) | `zalo_call.create_controller` | createController — Khởi tạo bộ điều phối cuộc gọi ZaloCallController quản lý vòng đời gọi đi, nhận cuộc gọi... |
| [createRtcSession](docs/DICH-VU.md#create_rtc_session) | `zalo_call.create_rtc_session` | createRtcSession — Khởi tạo phiên gọi thoại / video 2 chiều thuần TypeScript (ZaloRtcSession — UDP ZRTPPacket... |
| [endGroupCall](docs/DICH-VU.md#end_group_call) | `zalo_call.end_group_call` | endGroupCall — Rời khỏi cuộc gọi nhóm hoặc từ chối lời mời gọi nhóm (cmd 12438 -... |
| [endVoiceCall](docs/DICH-VU.md#end_voice_call) | `zalo_call.end_voice_call` | endVoiceCall — Kết thúc cuộc gọi 1-1 đang diễn ra hoặc từ chối cuộc gọi đến (cmd 11306 -... |
| [finishGroupCall](docs/DICH-VU.md#finish_group_call) | `zalo_call.finish_group_call` | finishGroupCall — Kết thúc hoàn toàn phòng gọi nhóm cho tất cả thành viên (cmd 12446 -... |
| [getGroupCallState](docs/DICH-VU.md#get_group_call_state) | `zalo_call.get_group_call_state` | getGroupCallState — Truy vấn trạng thái hiện tại và danh sách thành viên trong phòng gọi nhóm (cmd 12445 -... |
| [holdVoiceCall](docs/DICH-VU.md#hold_voice_call) | `zalo_call.hold_voice_call` | holdVoiceCall — Tạm giữ (Hold) cuộc gọi 1-1 đang diễn ra hoặc phản hồi yêu cầu tạm giữ (cmd 11307 holdreq /... |
| [joinGroupCall](docs/DICH-VU.md#join_group_call) | `zalo_call.join_group_call` | joinGroupCall — Chủ động tham gia vào một cuộc gọi nhóm đang diễn ra từ banner nhóm (cmd 12043 -... |
| [logEndVoiceCall](docs/DICH-VU.md#log_end_voice_call) | `zalo_call.log_end_voice_call` | logEndVoiceCall — Gửi thống kê chất lượng cuộc gọi (QoS/Billing stats) sau khi kết thúc cuộc gọi 1-1 (cmd... |
| [notifyGroupCall](docs/DICH-VU.md#notify_group_call) | `zalo_call.notify_group_call` | notifyGroupCall — Gửi thông báo sự kiện cuộc gọi nhóm vào luồng chat nhóm (cmd 12447 -... |
| [pingGroupCall](docs/DICH-VU.md#ping_group_call) | `zalo_call.ping_group_call` | pingGroupCall — Gửi nhịp tim (Heartbeat Ping) duy trì kết nối của thành viên trong phòng gọi nhóm (cmd 12097... |
| [requestAudioToVideoCall](docs/DICH-VU.md#request_audio_to_video_call) | `zalo_call.request_audio_to_video_call` | requestAudioToVideoCall — Yêu cầu nâng cấp từ cuộc gọi Thoại sang cuộc gọi Video hoặc phản hồi yêu cầu (cmd... |
| [requestGroupCall](docs/DICH-VU.md#request_group_call) | `zalo_call.request_group_call` | requestGroupCall — Bước 1 gọi nhóm (cmd 12433 - /api/voicecall/group/requestcall): Xin cấp phát phòng gọi... |
| [requestShareScreenCall](docs/DICH-VU.md#request_share_screen_call) | `zalo_call.request_share_screen_call` | requestShareScreenCall — Yêu cầu bắt đầu hoặc kết thúc chia sẻ màn hình (Screen Share) trong cuộc gọi 1-1... |
| [requestVoiceCall](docs/DICH-VU.md#request_voice_call) | `zalo_call.request_voice_call` | requestVoiceCall — Bước 1 gọi 1-1 (cmd 11300 - /api/voicecall/requestcall, signal 401): Xin cấp phát phòng... |
| [ringRingGroupCall](docs/DICH-VU.md#ring_ring_group_call) | `zalo_call.ring_ring_group_call` | ringRingGroupCall — Báo hiệu thiết bị đang đổ chuông cho lời mời gọi nhóm (cmd 12439 -... |
| [ringRingVoiceCall](docs/DICH-VU.md#ring_ring_voice_call) | `zalo_call.ring_ring_voice_call` | ringRingVoiceCall — Báo hiệu thiết bị đang đổ chuông cho cuộc gọi 1-1 đến (cmd 11302 -... |
| [sendRequestGroupCall](docs/DICH-VU.md#send_request_group_call) | `zalo_call.send_request_group_call` | sendRequestGroupCall — Bước 2 gọi nhóm (cmd 12434 - /api/voicecall/group/request): Phát tín hiệu mời gọi nhóm... |
| [sendRequestVoiceCall](docs/DICH-VU.md#send_request_voice_call) | `zalo_call.send_request_voice_call` | sendRequestVoiceCall — Bước 2 gọi 1-1 (cmd 11301 - /api/voicecall/request, signal 416): Gửi gói mời gọi... |
| [sendVoiceCall](docs/DICH-VU.md#send_voice_call) | `zalo_call.send_voice_call` | sendVoiceCall — Khởi tạo cuộc gọi Thoại hoặc Video 1-1 trọn gói (tự động thực hiện 2 bước 11300 + 11301 làm... |
| [shareScreenGroupCall](docs/DICH-VU.md#share_screen_group_call) | `zalo_call.share_screen_group_call` | shareScreenGroupCall — Bắt đầu hoặc dừng chia sẻ màn hình trong cuộc gọi nhóm (cmd 12044 -... |
| [unholdVoiceCall](docs/DICH-VU.md#unhold_voice_call) | `zalo_call.unhold_voice_call` | unholdVoiceCall — Khôi phục (Unhold) cuộc gọi 1-1 đang tạm giữ hoặc phản hồi yêu cầu khôi phục (cmd 11309... |
| [updateCallMediaState](docs/DICH-VU.md#update_call_media_state) | `zalo_call.update_call_media_state` | updateCallMediaState — Đồng bộ trạng thái bật/tắt Mic và Camera trong cuộc gọi 1-1 (cmd 12006 -... |
| **Phương tiện** | | |
| [getConversationMedia](docs/DICH-VU.md#get_conversation_media) | `zalo_call.get_conversation_media` | getConversationMedia — Lấy danh sách Kho Lưu Trữ (Ảnh/Video "media", File "file", hoặc Link "link") trong hội... |
| [getMediaStorePreview](docs/DICH-VU.md#get_media_store_preview) | `zalo_call.get_media_store_preview` | getMediaStorePreview — Lấy danh sách xem trước nhanh Kho Lưu Trữ (Ảnh/Video, File, Link) của nhóm (command... |
| [getPersonalMedia](docs/DICH-VU.md#get_personal_media) | `zalo_call.get_personal_media` | getPersonalMedia — Lấy danh sách Kho Lưu Trữ Ảnh/Video ("media"), File ("file"), hoặc Link ("link") trong... |
| [getPersonalMediaPreview](docs/DICH-VU.md#get_personal_media_preview) | `zalo_call.get_personal_media_preview` | getPersonalMediaPreview — Lấy danh sách xem trước nhanh Kho Lưu Trữ trong Cloud của tôi (Send2Me) (command... |
| [removeConversationMedia](docs/DICH-VU.md#remove_conversation_media) | `zalo_call.remove_conversation_media` | removeConversationMedia — Xóa mục Ảnh/Video, File hoặc Link khỏi Kho Lưu Trữ của nhóm (command 11842) (không... |
| [removePersonalMedia](docs/DICH-VU.md#remove_personal_media) | `zalo_call.remove_personal_media` | removePersonalMedia — Xóa mục lưu trữ trong Kho Lưu Trữ Cloud của tôi (Send2Me) (command 12222) (không hoàn... |
| [uploadAttachment](docs/DICH-VU.md#upload_attachment) | `zalo_call.upload_attachment` | uploadAttachment — Tải tệp đính kèm (Ảnh, Video, File) lên máy chủ Zalo để lấy thông tin fileUrl / fileId... |
| **Sticker (nâng cao)** | | |
| [getAIStickerList](docs/DICH-VU.md#get_a_i_sticker_list) | `zalo_call.get_a_i_sticker_list` | getAIStickerList — Lấy danh sách Sticker AI của người dùng (command 12190) |
| [getDefaultGuggyGifs](docs/DICH-VU.md#get_default_guggy_gifs) | `zalo_call.get_default_guggy_gifs` | getDefaultGuggyGifs — Lấy danh sách ảnh động Guggy GIF mặc định (command 11749) |
| [getGifCategories](docs/DICH-VU.md#get_gif_categories) | `zalo_call.get_gif_categories` | getGifCategories — Lấy danh sách danh mục ảnh động Giphy GIF (command 11294) |
| [getGifDictionaries](docs/DICH-VU.md#get_gif_dictionaries) | `zalo_call.get_gif_dictionaries` | getGifDictionaries — Lấy danh sách từ điển ảnh động Giphy GIF (command 11298) |
| [getGifsByCategory](docs/DICH-VU.md#get_gifs_by_category) | `zalo_call.get_gifs_by_category` | getGifsByCategory — Lấy danh sách ảnh động Giphy GIF theo ID danh mục (command 11295) |
| [getGifsByDictionary](docs/DICH-VU.md#get_gifs_by_dictionary) | `zalo_call.get_gifs_by_dictionary` | getGifsByDictionary — Lấy danh sách ảnh động Giphy GIF theo ID từ điển (command 11299) |
| [getMessageEffectById](docs/DICH-VU.md#get_message_effect_by_id) | `zalo_call.get_message_effect_by_id` | getMessageEffectById — Lấy chi tiết một hiệu ứng tin nhắn theo ID và kích thước (command 11743) |
| [getMessageEffects](docs/DICH-VU.md#get_message_effects) | `zalo_call.get_message_effects` | getMessageEffects — Lấy thông tin hiệu ứng tin nhắn theo danh sách ID (command 11742) |
| [getPersonalizedStickerList](docs/DICH-VU.md#get_personalized_sticker_list) | `zalo_call.get_personalized_sticker_list` | getPersonalizedStickerList — Lấy danh sách Sticker cá nhân hóa của tài khoản (command 11745) |
| [getRecommendedStickers](docs/DICH-VU.md#get_recommended_stickers) | `zalo_call.get_recommended_stickers` | getRecommendedStickers — Lấy danh sách các bộ Sticker được Zalo đề xuất (command 11748) |
| [getStickerCategoriesV2](docs/DICH-VU.md#get_sticker_categories_v2) | `zalo_call.get_sticker_categories_v2` | getStickerCategoriesV2 — Lấy danh sách danh mục bộ nhãn dán (Sticker Categories V2 - command 12020) (chưa tự... |
| [getStickerCategoryDetail](docs/DICH-VU.md#get_sticker_category_detail) | `zalo_call.get_sticker_category_detail` | getStickerCategoryDetail — Lấy danh sách toàn bộ nhãn dán nằm trong một bộ nhãn dán (Category/Pack ID). |
| [getStickerHello](docs/DICH-VU.md#get_sticker_hello) | `zalo_call.get_sticker_hello` | getStickerHello — Lấy danh sách Sticker chào hỏi gợi ý khi bắt đầu trò chuyện mới (command 11751) |
| [getStickerSuggestKeywords](docs/DICH-VU.md#get_sticker_suggest_keywords) | `zalo_call.get_sticker_suggest_keywords` | getStickerSuggestKeywords — Lấy bộ từ khóa gợi ý Sticker tự động khi gõ tin nhắn (command 11740) |
| [getStickerSuggestion](docs/DICH-VU.md#get_sticker_suggestion) | `zalo_call.get_sticker_suggestion` | getStickerSuggestion — Gợi ý Sticker/GIF theo từ khóa đang nhập (command 11741) |
| [getTenorStickerMapping](docs/DICH-VU.md#get_tenor_sticker_mapping) | `zalo_call.get_tenor_sticker_mapping` | getTenorStickerMapping — Lấy bảng ánh xạ Tenor sang Sticker Zalo (command 12015) |
| [getTrendingGifs](docs/DICH-VU.md#get_trending_gifs) | `zalo_call.get_trending_gifs` | getTrendingGifs — Lấy danh sách ảnh động Giphy GIF thịnh hành (command 11296) |
| [searchGifs](docs/DICH-VU.md#search_gifs) | `zalo_call.search_gifs` | searchGifs — Tìm kiếm ảnh động Giphy GIF theo từ khóa (command 11297) |
| [searchGuggyGifs](docs/DICH-VU.md#search_guggy_gifs) | `zalo_call.search_guggy_gifs` | searchGuggyGifs — Tìm kiếm ảnh động Guggy GIF theo từ khóa (command 11750) |
| [searchSticker](docs/DICH-VU.md#search_sticker) | `zalo_call.search_sticker` | searchSticker — Tìm kiếm nhãn dán nâng cao theo từ khóa. |
| [updatePersonalizedStickerList](docs/DICH-VU.md#update_personalized_sticker_list) | `zalo_call.update_personalized_sticker_list` | updatePersonalizedStickerList — Cập nhật danh sách các bộ Sticker cá nhân hóa của người dùng (command 11746) |
| **Ghi chú, bình chọn, việc cần làm** | | |
| [ackDingTodo](docs/DICH-VU.md#ack_ding_todo) | `zalo_call.ack_ding_todo` | ackDingTodo — Xác nhận đã nhận nhắc nhở (Ding ACK) trong Zalo To-Do (command 12427) |
| [addPollOptions](docs/DICH-VU.md#add_poll_options) | `zalo_call.add_poll_options` | addPollOptions — Thêm phương án lựa chọn mới vào một cuộc Bình chọn (Poll) đang mở trong nhóm. |
| [createNote](docs/DICH-VU.md#create_note) | `zalo_call.create_note` | createNote — Tạo một Ghi chú (Note) mới trên Bảng tin nhóm và tùy chọn ghim lên đầu. |
| [createTodo](docs/DICH-VU.md#create_todo) | `zalo_call.create_todo` | createTodo — Tạo công việc mới trong Zalo To-Do (command 12413) |
| [deleteTodo](docs/DICH-VU.md#delete_todo) | `zalo_call.delete_todo` | deleteTodo — Xóa công việc trong Zalo To-Do (command 12415) (không hoàn tác được) |
| [dingTodo](docs/DICH-VU.md#ding_todo) | `zalo_call.ding_todo` | dingTodo — Gửi nhắc nhở (Ding) cho các công việc trong Zalo To-Do (command 12426) |
| [editNote](docs/DICH-VU.md#edit_note) | `zalo_call.edit_note` | editNote — Chỉnh sửa nội dung ghi chú đã tạo trên Bảng tin nhóm. |
| [getListPinTopics](docs/DICH-VU.md#get_list_pin_topics) | `zalo_call.get_list_pin_topics` | getListPinTopics — Lấy danh sách chủ đề / tin nhắn đã ghim trong bảng tin nhóm (command 12001) |
| [getTodoDetail](docs/DICH-VU.md#get_todo_detail) | `zalo_call.get_todo_detail` | getTodoDetail — Lấy chi tiết công việc trong Zalo To-Do (command 12417) |
| [getTodoList](docs/DICH-VU.md#get_todo_list) | `zalo_call.get_todo_list` | getTodoList — Lấy danh sách công việc trong Zalo To-Do (command 12416) |
| [multiUnpinBoardTopics](docs/DICH-VU.md#multi_unpin_board_topics) | `zalo_call.multi_unpin_board_topics` | multiUnpinBoardTopics — Bỏ ghim đồng thời nhiều chủ đề khỏi bảng tin nhóm (command 12010) |
| [pinBoardTopic](docs/DICH-VU.md#pin_board_topic) | `zalo_call.pin_board_topic` | pinBoardTopic — Ghim một chủ đề / bài đăng lên bảng tin nhóm (command 12004) |
| [pinFriendMessage](docs/DICH-VU.md#pin_friend_message) | `zalo_call.pin_friend_message` | pinFriendMessage — Ghim tin nhắn / chủ đề trong hội thoại cá nhân 1-1 (command 12067) |
| [reorderFriendBoard](docs/DICH-VU.md#reorder_friend_board) | `zalo_call.reorder_friend_board` | reorderFriendBoard — Sắp xếp lại thứ tự các tin nhắn đã ghim trong hội thoại 1-1 (command 12068) |
| [reorderPinTopics](docs/DICH-VU.md#reorder_pin_topics) | `zalo_call.reorder_pin_topics` | reorderPinTopics — Sắp xếp lại thứ tự các chủ đề đã ghim trên bảng tin nhóm (command 12002) |
| [sharePoll](docs/DICH-VU.md#share_poll) | `zalo_call.share_poll` | sharePoll — Chia sẻ lại cuộc Bình chọn vào luồng tin nhắn nhóm. |
| [unpinBoardTopic](docs/DICH-VU.md#unpin_board_topic) | `zalo_call.unpin_board_topic` | unpinBoardTopic — Bỏ ghim một chủ đề khỏi bảng tin nhóm (command 12005) |
| [unpinFriendMessages](docs/DICH-VU.md#unpin_friend_messages) | `zalo_call.unpin_friend_messages` | unpinFriendMessages — Bỏ ghim một hoặc nhiều tin nhắn trong hội thoại 1-1 (command 12069) |
| [updateTodo](docs/DICH-VU.md#update_todo) | `zalo_call.update_todo` | updateTodo — Cập nhật nội dung công việc trong Zalo To-Do (command 12414) |
| [updateTodoStatus](docs/DICH-VU.md#update_todo_status) | `zalo_call.update_todo_status` | updateTodoStatus — Cập nhật trạng thái công việc trong Zalo To-Do (command 12418) |
| [verifyTodo](docs/DICH-VU.md#verify_todo) | `zalo_call.verify_todo` | verifyTodo — Kiểm tra tính đồng bộ của danh sách công việc trong Zalo To-Do (command 12603) |
| **Zalo Business (OA)** | | |
| [addConversationLabel](docs/DICH-VU.md#add_conversation_label) | `zalo_call.add_conversation_label` | addConversationLabel — Tạo nhãn phân loại hội thoại mới (command 12163) |
| [blockOA](docs/DICH-VU.md#block_o_a) | `zalo_call.block_o_a` | blockOA — Chặn nhận tin nhắn / thông báo từ một Zalo Official Account (OA) qua /api/social/oa/block (cmd... |
| [convertOAIds](docs/DICH-VU.md#convert_o_a_ids) | `zalo_call.convert_o_a_ids` | convertOAIds — Chuyển đổi danh sách OA ID sang Zalo UID nội bộ (hoặc ngược lại) qua /api/social/oa/convertid... |
| [createAutoReply](docs/DICH-VU.md#create_auto_reply) | `zalo_call.create_auto_reply` | createAutoReply — Tạo kịch bản Trả lời tự động (Auto Reply) theo khung giờ cho Zalo Business. |
| [createBankAccount](docs/DICH-VU.md#create_bank_account) | `zalo_call.create_bank_account` | createBankAccount — Thêm thông tin tài khoản ngân hàng mới vào danh bạ ngân hàng. (không hoàn tác được) |
| [createCatalog](docs/DICH-VU.md#create_catalog) | `zalo_call.create_catalog` | createCatalog — Tạo Danh mục sản phẩm (Catalog) mới cho Zalo Business. |
| [createProductCatalog](docs/DICH-VU.md#create_product_catalog) | `zalo_call.create_product_catalog` | createProductCatalog — Thêm sản phẩm mới vào Danh mục sản phẩm (Product Catalog). |
| [deleteAutoReply](docs/DICH-VU.md#delete_auto_reply) | `zalo_call.delete_auto_reply` | deleteAutoReply — Xóa một kịch bản Trả lời tự động. (không hoàn tác được) |
| [deleteBankAccount](docs/DICH-VU.md#delete_bank_account) | `zalo_call.delete_bank_account` | deleteBankAccount — Xóa một tài khoản ngân hàng đã lưu. (không hoàn tác được) |
| [deleteCatalog](docs/DICH-VU.md#delete_catalog) | `zalo_call.delete_catalog` | deleteCatalog — Xóa một Danh mục sản phẩm (Catalog). (không hoàn tác được) |
| [deleteConversationLabel](docs/DICH-VU.md#delete_conversation_label) | `zalo_call.delete_conversation_label` | deleteConversationLabel — Xóa một hoặc nhiều nhãn phân loại hội thoại (command 12165) (không hoàn tác được) |
| [deleteProductCatalog](docs/DICH-VU.md#delete_product_catalog) | `zalo_call.delete_product_catalog` | deleteProductCatalog — Xóa một hoặc nhiều sản phẩm khỏi Danh mục sản phẩm. (không hoàn tác được) |
| [deleteSingleProduct](docs/DICH-VU.md#delete_single_product) | `zalo_call.delete_single_product` | deleteSingleProduct — Xóa một sản phẩm đơn lẻ khỏi danh mục Zalo Business (command 12042) (không hoàn tác... |
| [getAutoReplyList](docs/DICH-VU.md#get_auto_reply_list) | `zalo_call.get_auto_reply_list` | getAutoReplyList — Lấy danh sách các kịch bản Trả lời tự động của tài khoản. |
| [getBizAccount](docs/DICH-VU.md#get_biz_account) | `zalo_call.get_biz_account` | getBizAccount — Lấy thông tin cấu hình tài khoản Zalo Business (ZBusiness). |
| [getCatalogList](docs/DICH-VU.md#get_catalog_list) | `zalo_call.get_catalog_list` | getCatalogList — Lấy danh sách các Danh mục sản phẩm (Catalogs) của tài khoản. |
| [getListBank](docs/DICH-VU.md#get_list_bank) | `zalo_call.get_list_bank` | getListBank — Lấy danh sách mã ngân hàng (BIN / NAPAS) được Zalo hỗ trợ. (không hoàn tác được) |
| [getListBankAccount](docs/DICH-VU.md#get_list_bank_account) | `zalo_call.get_list_bank_account` | getListBankAccount — Lấy danh sách các tài khoản ngân hàng đã lưu của người dùng. (không hoàn tác được) |
| [getOAProfile](docs/DICH-VU.md#get_o_a_profile) | `zalo_call.get_o_a_profile` | getOAProfile — Lấy hồ sơ chuẩn hóa đầy đủ của một Zalo Official Account (OA) theo oaId (bao gồm tích vàng... |
| [getProductCatalogList](docs/DICH-VU.md#get_product_catalog_list) | `zalo_call.get_product_catalog_list` | getProductCatalogList — Lấy danh sách các sản phẩm nằm trong một Danh mục sản phẩm (Catalog). |
| [getProductDetail](docs/DICH-VU.md#get_product_detail) | `zalo_call.get_product_detail` | getProductDetail — Lấy thông tin chi tiết một sản phẩm trong danh mục Zalo Business (command 12057) |
| [registerCatalog](docs/DICH-VU.md#register_catalog) | `zalo_call.register_catalog` | registerCatalog — Đăng ký kích hoạt tính năng Danh mục sản phẩm (Catalog) cho tài khoản. |
| [reorderConversationLabels](docs/DICH-VU.md#reorder_conversation_labels) | `zalo_call.reorder_conversation_labels` | reorderConversationLabels — Sắp xếp lại vị trí hiển thị của các nhãn phân loại hội thoại (command 12166) |
| [unblockOA](docs/DICH-VU.md#unblock_o_a) | `zalo_call.unblock_o_a` | unblockOA — Bỏ chặn một Zalo Official Account (OA) để tiếp tục nhận tin nhắn qua /api/social/oa/unblock (cmd... |
| [updateAutoReply](docs/DICH-VU.md#update_auto_reply) | `zalo_call.update_auto_reply` | updateAutoReply — Cập nhật nội dung và thời gian hoạt động của kịch bản Trả lời tự động. |
| [updateBankAccount](docs/DICH-VU.md#update_bank_account) | `zalo_call.update_bank_account` | updateBankAccount — Cập nhật thông tin tài khoản ngân hàng đã lưu. (không hoàn tác được) |
| [updateCatalog](docs/DICH-VU.md#update_catalog) | `zalo_call.update_catalog` | updateCatalog — Cập nhật tên hoặc ảnh của Danh mục sản phẩm. |
| [updateConversationLabelItem](docs/DICH-VU.md#update_conversation_label_item) | `zalo_call.update_conversation_label_item` | updateConversationLabelItem — Cập nhật thông tin một nhãn phân loại hội thoại và danh sách hội thoại gắn nhãn... |
| [updateProductCatalog](docs/DICH-VU.md#update_product_catalog) | `zalo_call.update_product_catalog` | updateProductCatalog — Cập nhật thông tin chi tiết, giá bán và hình ảnh của sản phẩm trong Danh mục. |
| [uploadProductPhoto](docs/DICH-VU.md#upload_product_photo) | `zalo_call.upload_product_photo` | uploadProductPhoto — Tải ảnh sản phẩm lên máy chủ Zalo phục vụ cho Product Catalog hoặc Quick Message. (chưa... |
| **Khác** | | |
| [Chuyển giọng nói thành văn bản (Zalo AI)](docs/DICH-VU.md#voice_to_text) | `zalo_call.voice_to_text` | Gửi một tin nhắn thoại (URL tệp .aac/.mp3/.m4a trên máy chủ Zalo) cho Zalo AI và trả về văn bản. Chỉ dùng cho... |
| [Gắn thẻ và ghi chú cho người](docs/DICH-VU.md#set_contact_tags) | `zalo_call.set_contact_tags` | Gắn thẻ (ví dụ «gia đình») và ghi chú cho một người hoặc nhóm. Đặt quy tắc cho một thẻ (dịch vụ «Đặt quy... |
| [Đọc cài đặt của app](docs/DICH-VU.md#get_app_settings) | `zalo_call.get_app_settings` | Đọc mọi cài đặt của app Zalo Call (tài khoản app, webhook, thiết bị, lưu trữ, proxy, bảo mật, đồng bộ lịch... |
| [Ghi cài đặt của app](docs/DICH-VU.md#set_app_settings) | `zalo_call.set_app_settings` | Ghi một mục cài đặt của app. App tự kiểm giá trị và báo lỗi rõ ràng. Ví dụ: mục «webhooks» với... |
| [Đổi mật khẩu app](docs/DICH-VU.md#set_app_password) | `zalo_call.set_app_password` | Đổi mật khẩu đăng nhập app Zalo Call và cập nhật luôn mật khẩu HA dùng với app (tích hợp tự tải lại). Các... |
| [Gửi thử webhook](docs/DICH-VU.md#test_webhook) | `zalo_call.test_webhook` | Gửi thử một loại webhook từ app sang HA để kiểm đường nhận. |
| [Đăng nhập Zalo bằng mã QR](docs/DICH-VU.md#login_qr) | `zalo_call.login_qr` | Bắt đầu đăng nhập Zalo bằng mã QR theo kiểu đã chọn. Mã hiện ở thực thể ảnh «Mã QR đăng nhập» của thiết bị... |
| [Đăng xuất Zalo](docs/DICH-VU.md#logout) | `zalo_call.logout` | Đăng xuất Zalo (xóa phiên Zalo của app, quay về màn hình mã QR). Tài khoản và mật khẩu đăng nhập app vẫn giữ. |

<!-- DICH-VU:CHI-MUC:END -->

## 8. Blueprint mẫu: chọn từ danh sách, không gõ tay

Năm mẫu automation dựng sẵn cho Zalo Call, nằm ở kho **[TriTue2011/Blueprint](https://github.com/TriTue2011/Blueprint)** (mô tả đầy đủ trong README của kho đó). Mọi thứ **chọn từ danh sách**: cảm biến, người nhận (thực thể `notify.zalo_...`), loa/mic/camera, câu có sẵn, kiểu chữ, ô tích thiết bị nhà. Cần Zalo Call từ bản `2026.11.11.2`.

| Mẫu | Làm gì | Nhập |
|---|---|---|
| **Gọi cảnh báo khi cảm biến kích hoạt** | Có người/khói/rò nước/cửa mở/mất điện thì gọi cảnh báo, gọi **lần lượt** từng người cho tới khi có người nghe máy, nối thiết bị nhà | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FTriTue2011%2FBlueprint%2Fmain%2Fzalo_call_alert_sensor.yaml) |
| **Một nút bấm nghe máy, cúp máy hoặc gọi đi** | Cùng một nút: có cuộc gọi đến thì nghe, đang gọi thì cúp, rảnh thì gọi/cảnh báo/nhắn tin (hợp nút giữa loa R1) | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FTriTue2011%2FBlueprint%2Fmain%2Fzalo_call_nut_bam.yaml) |
| **Quy tắc cho cuộc gọi đến** | Báo ra loa, tự nghe máy, AI nói chuyện, thiết bị nhà dùng khi người nhà nói trực tiếp | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FTriTue2011%2FBlueprint%2Fmain%2Fzalo_call_incoming_rule.yaml) |
| **Messenger tuỳ biến** | Nhắn tin hoặc gọi khi thiết bị đổi trạng thái / vượt ngưỡng / báo cáo hằng ngày; kiểu chữ chọn từ danh sách | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FTriTue2011%2FBlueprint%2Fmain%2Fzalo_call_messenger.yaml) |
| **Gọi hoặc nhắn nhắc hẹn theo lịch** | Đúng giờ gọi đọc lời nhắc (thuốc, ngủ, thức dậy, ăn...) | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FTriTue2011%2FBlueprint%2Fmain%2Fzalo_call_nhac_hen.yaml) |

## Kho này gồm

| Thư mục | Là gì |
|---|---|
| `custom_components/zalo_call/` | Tích hợp Home Assistant (HACS bắt buộc đặt ở gốc kho; **một tích hợp mỗi kho**) |
| `zalo/zalo-pc-app/` | App Zalo dạng PC chạy Docker: đăng nhập QR, gọi thoại/video, WebUI. Ảnh `ghcr.io/tritue2011/zalo-calling` |
| `tests/` | Test của tích hợp (bộ test của app nằm trong `zalo/zalo-pc-app/tests/`) |
| `.github/workflows/` | `ci.yml` (test), `release.yml` (thẻ `vX` → Release + `zalo_call.zip`), `image.yml` (thẻ `vX` → ảnh Docker) |

Phát hành: đẩy thẻ `vX.Y.Z.N` khớp `version` trong `custom_components/zalo_call/manifest.json`.
Chi tiết kỹ thuật của app: [`zalo/README.md`](zalo/README.md).
