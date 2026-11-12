"""Bảng TỪ NGỮ người dùng nhìn thấy cho các dịch vụ gọi / AI / cảnh báo / quy tắc của tích hợp zalo_call.

Một chỗ duy nhất để rà soát chữ. Nguyên tắc viết: câu ngắn, nói việc cần làm; KHÔNG dùng thuật ngữ kỹ thuật làm tên ô (threadID, pipeline, agent, STT,
TTS, handover, ghi đè, stream...). Tên kỹ thuật chỉ xuất hiện trong phần mô tả khi cần (tên sự kiện cho automation). gen_ha_catalog.py áp bảng này lên
services.yaml; id trường/dịch vụ KHÔNG đổi (automation cũ vẫn chạy), chỉ đổi chữ hiển thị.

Thuật ngữ thống nhất:
  «người nhà nói trực tiếp» = người trong nhà tự nói chuyện với người gọi (sau khi AI chuyển cuộc gọi, hoặc bấm nút);
  «thiết bị nhà»            = loa, mic, camera trong nhà;
  «Trợ lý giọng nói»        = bộ nghe - hiểu - nói của Home Assistant (Assist).
"""

CONNECT_NAME = "Thiết bị nhà dùng khi người nhà nói trực tiếp"
CONNECT_HELP = ("Tích ô nào thì dùng thứ đó: tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3. Không tích gì = không dùng thiết bị nào (mặc định, "
                "người lạ không nghe hay thấy được trong nhà). Tích Camera = cuộc gọi VIDEO. «AI tự chọn» = AI quyết dùng mic và loa hay thêm cả camera, "
                "chỉ trong các ô đã tích. Chỉ dùng được thiết bị đã chọn ở các ô Loa, Mic, Camera bên dưới. Thiết bị chỉ bật khi người nhà nói trực "
                "tiếp, lúc AI còn đang giữ máy thì chưa bật.")
CONNECT_OPTIONS = [
    {"value": "mic", "label": "Mic - gửi tiếng trong nhà cho người gọi"},
    {"value": "speaker", "label": "Loa - phát tiếng người gọi ra loa trong nhà"},
    {"value": "camera", "label": "Camera - gửi hình trong nhà (tích ô này là cuộc gọi VIDEO)"},
    {"value": "ai", "label": "AI tự chọn trong các ô đã tích"},
]

CONNECT_NOW = ("Thiết bị nhà dùng NGAY khi người nhận nghe máy",
               "Tích ô nào thì thứ đó bật ngay khi người nhận nghe máy, không chờ người nhà nói trực tiếp (ví dụ tích Camera để người nhận thấy hình trong nhà "
               "ngay, còn Mic và Loa chỉ bật khi người nhà nói). Tích Camera = cuộc gọi VIDEO. Không tích gì = chưa bật gì (mặc định). Chỉ bật được thiết "
               "bị đã chọn ở các ô Loa, Mic, Camera.")
CONNECT_NOW_OPTIONS = [o for o in CONNECT_OPTIONS if o["value"] != "ai"]

PIPELINE = ("Trợ lý giọng nói (Assist)",
            "Bộ nghe - hiểu - nói của Home Assistant (Cài đặt, Trợ lý giọng nói). Khi cho AI nói chuyện, AI nghe người gọi, trả lời và đọc bằng giọng "
            "của bộ này. Bắt buộc chọn nếu cho AI nói chuyện (không tự dùng bộ ưu tiên vì nó có quyền điều khiển thiết bị trong nhà).")
AGENT = ("Trợ lý AI riêng (không bắt buộc)",
         "Chỉ chọn nếu muốn dùng một trợ lý AI khác với trợ lý trong Trợ lý giọng nói. Với người lạ, nên chọn trợ lý KHÔNG điều khiển được thiết bị trong nhà.")
HANDOVER = ("AI chuyển cho người nhà khi...",
            "Thêm điều kiện riêng để AI chuyển cuộc gọi cho người nhà nói trực tiếp. Mặc định AI đã tự chuyển khi người gọi muốn gặp người trong nhà, có "
            "việc khẩn cấp hoặc AI không giúp được. Khi chuyển, cuộc gọi không bị cúp, thiết bị nhà bật theo ô «%s», và Home Assistant bắn sự kiện "
            "zalo_call_ai_handover." % CONNECT_NAME)
GREETING_CALL = ("Câu AI chào đầu tiên",
                 "AI nói câu này ngay khi người nhận nghe máy (chỉ khi cho AI nói chuyện mà không có nội dung thông báo). Bỏ trống = câu chào trong quy tắc, "
                 "không có thì «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?».")
DEVICE_NOTE = " Với cuộc gọi có AI: chỉ bật khi người nhà nói trực tiếp."

COMMON_CALL_FIELDS = {
    "thread_id": ("Người hoặc nhóm cần gọi", "Mã Zalo của người (hoặc nhóm). Xem danh sách bằng dịch vụ «Xem danh bạ Zalo»."),
    "type": ("Gọi thoại hay gọi video",
             "Thoại, video hoặc nhóm. Bỏ trống = tự chọn: nếu có camera sẽ dùng (tích Camera ở ô «%s») thì gọi video, không thì gọi thoại." % CONNECT_NAME),
    "peer_name": ("Tên hiện trong nhật ký", "Tên người nhận hiện trong nhật ký cuộc gọi (bỏ trống = dùng mã)."),
    "srtp": ("Cách mã hoá tiếng (nâng cao)", "Thường để trống: hệ thống tự chọn cách đã chạy tốt."),
    "extend_profile": ("Kiểu kết nối với Zalo (nâng cao)", "Thường để trống."),
    "speaker": ("Loa trong nhà", "Loa phát tiếng người bên kia." + DEVICE_NOTE),
    "volume": ("Âm lượng loa (%)", "Đặt âm lượng khi bật loa, trả lại mức cũ khi cúp. Bỏ trống = giữ nguyên."),
    "mic": ("Mic trong nhà", "Camera hoặc vệ tinh Assist (loa R1, camera Imou/Dahua) có mic, để gửi tiếng trong nhà cho người bên kia." + DEVICE_NOTE),
    "mic_url": ("Mic từ địa chỉ mạng (nâng cao)", "Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic."),
    "camera": ("Camera trong nhà", "Camera gửi hình cho người bên kia (cuộc gọi video)." + DEVICE_NOTE),
    "message": ("Nội dung đọc khi người nhận nghe máy", "Câu được đọc bằng giọng nói ngay khi nghe máy. Bỏ trống = không đọc gì."),
    "repeat": ("Đọc mấy lần", "Số lần đọc (1 đến 3)."),
    "ai": ("Cho AI nói chuyện",
           "AI nghe người bên kia và trả lời bằng giọng nói, tới khi họ nói không cần gì nữa, cúp máy, im lặng quá lâu hoặc 10 phút. Cần chọn Trợ lý "
           "giọng nói (hoặc đã đặt quy tắc cho người này)."),
    "hangup_after": ("Tự cúp máy khi xong", "Cúp máy sau khi đọc xong thông báo, và sau khi AI nói chuyện xong. Mặc định: bật."),
    "greeting": GREETING_CALL, "handover_rule": HANDOVER, "pipeline": PIPELINE, "agent": AGENT,
    "tts_engine": ("Giọng đọc riêng", "Chọn nếu muốn dùng giọng khác. Bỏ trống = giọng của Trợ lý giọng nói."),
    "language": ("Ngôn ngữ", "Ví dụ vi. Bỏ trống = theo Trợ lý giọng nói."),
    "connect": (CONNECT_NAME, CONNECT_HELP),
    "connect_now": CONNECT_NOW,
}

SERVICES = {
    "make_call": ("Gọi điện đi", "Gọi thoại hoặc video cho một người hay nhóm Zalo. Có thể chỉ gọi, hoặc đọc một thông báo rồi cúp, hoặc cho AI nói "
                  "chuyện. Muốn báo động (có người ngã, cháy...) thì dùng «Gọi cảnh báo»."),
    "answer_call": ("Nghe máy", "Nghe một cuộc gọi đang đổ chuông. Có thể kèm thông báo hoặc cho AI nói chuyện, giống «Gọi điện đi»."),
    "alert_call": ("Gọi cảnh báo", "Gọi để BÁO ĐỘNG: người nhận nghe máy, AI đọc nội dung cảnh báo (không hỏi gì), rồi làm theo ô «Đọc cảnh báo xong thì». "
                   "Báo người ngã, có trộm: nên nối thiết bị nhà để người nhận xem hiện trường. Báo mất điện, rò nước: đọc xong cúp máy. Đọc xong, Home "
                   "Assistant bắn sự kiện zalo_call_alert_done để automation biết đúng lúc đó."),
    "set_rule": ("Đặt quy tắc cho cuộc gọi đến và tin nhắn",
                 "Quy định hệ thống làm gì khi có người gọi hoặc nhắn đến. Chưa có quy tắc cho người đó thì hệ thống KHÔNG làm gì (chỉ đổ chuông, không trả "
                 "lời tin nhắn). Quy tắc cho một người hoặc nhóm cụ thể được ưu tiên hơn quy tắc chung. Ô nào không điền thì giữ nguyên như cũ; quy tắc "
                 "mới mặc định TẮT hết và không dùng thiết bị nhà."),
    "remove_rule": ("Xoá quy tắc", "Xoá quy tắc của một người/nhóm cụ thể hoặc của một nhóm đối tượng. Từ đó hệ thống quay về «không làm gì» với họ."),
    "list_rules": ("Xem các quy tắc", "Trả về mọi quy tắc đang đặt."),
    "list_contacts": ("Xem danh bạ Zalo", "Danh sách bạn bè và nhóm kèm mã Zalo, để điền vào các ô «Mã Zalo»."),
    "accept_video": ("Đồng ý chuyển sang video", "Người đang gọi thoại xin chuyển sang video, bạn đồng ý. Chọn Camera để gửi hình trong nhà; không chọn thì chỉ đồng ý "
                     "(người gọi thấy mình, nhưng không thấy hình trong nhà). Chỉ dùng được khi cuộc gọi đang nói."),
    "take_over_call": ("Người nhà nói trực tiếp (dừng AI)",
                       "Dừng AI đang giữ cuộc gọi và bật thiết bị nhà để người trong nhà nói chuyện trực tiếp với người gọi."),
}

ALERT_FIELDS = {
    "thread_id": ("Người cần báo", "Mã Zalo của người nhận cảnh báo. Xem danh sách bằng dịch vụ «Xem danh bạ Zalo»."),
    "message": ("Nội dung cảnh báo", "Câu được đọc ngay khi người nhận nghe máy."),
    "type": ("Gọi thoại hay gọi video",
             "Bỏ trống = tự chọn: có camera sẽ dùng (mặc định cảnh báo dùng tất cả thiết bị đã cài, gồm camera) thì gọi video, không thì gọi thoại."),
    "after": ("Đọc cảnh báo xong thì",
              "Cúp máy: hợp báo mất điện, rò nước. Nối thiết bị nhà: hợp báo người ngã, có trộm. Giữ máy: người nhận hoặc automation tự cúp (dịch vụ "
              "«Kết thúc cuộc gọi»). Bỏ trống = tự chọn: có thiết bị để nối thì nối, không thì cúp."),
    "pipeline": ("Trợ lý giọng nói (để chọn giọng đọc)", "Bỏ trống = theo quy tắc của người này; không có thì giọng đọc mặc định của Home Assistant."),
    "speaker": ("Loa trong nhà", "Loa phát tiếng người nhận sau khi đọc xong. Bỏ trống = theo quy tắc của người này."),
    "mic": ("Mic trong nhà", "Mic gửi tiếng trong nhà cho người nhận sau khi đọc xong. Bỏ trống = theo quy tắc."),
    "camera": ("Camera trong nhà", "Camera gửi hình cho người nhận sau khi đọc xong. Bỏ trống = theo quy tắc."),
    "connect": ("Thiết bị nhà dùng ngay sau cảnh báo",
                "Tích ô nào thì dùng thứ đó (tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = cả 3). Tích Camera = cuộc gọi VIDEO. Bỏ trống = dùng TẤT CẢ thiết "
                "bị đã cài, kể cả camera, vì báo động thì người nhận phải thấy hiện trường. Muốn chỉ đọc rồi cúp thì chọn Cúp máy ở ô «Đọc cảnh báo xong thì»."),
}

RULE_FIELDS = {
    "scope": ("Áp dụng cho", "Chọn đối tượng của quy tắc. «Một người hoặc một nhóm cụ thể» thì điền thêm Mã Zalo bên dưới."),
    "thread_id": ("Mã Zalo của người hoặc nhóm", "Chỉ cần khi chọn «Một người hoặc một nhóm cụ thể». Xem danh sách bằng dịch vụ «Xem danh bạ Zalo»."),
    "name": ("Tên gọi (để bạn nhớ)", "Tên hiển thị trong các thông báo, ví dụ «Con trai»."),
    "answer": ("Tự nghe máy", "Cuộc gọi 1-1 đến từ người thuộc quy tắc này sẽ tự được nghe sau thời gian chờ."),
    "answer_delay": ("Nghe máy sau (giây)", "Từ 0 đến 120 giây. Người gọi cúp trước khi hết giờ thì không nghe."),
    "call_types": ("Nghe loại cuộc gọi nào", "voice = thoại, video = video, hoặc cả hai."),
    "ai": ("Cho AI nói chuyện khi nghe máy", "Sau khi nghe máy, AI nghe và trả lời bằng giọng nói. Cần chọn Trợ lý giọng nói hoặc Trợ lý AI riêng."),
    "greeting": ("Câu AI chào khi nghe máy", "Bỏ trống = «Xin chào, tôi là trợ lý của gia đình. Bạn cần gì ạ?»."),
    "trusted": ("Người tin cậy", "Tin cậy thì AI nói chuyện bình thường. Không tin cậy (mặc định) thì AI được dặn không tiết lộ thông tin gia đình và không "
                                 "điều khiển thiết bị."),
    "reply_ai": ("AI trả lời tin nhắn", "AI trả lời tin chữ (và tin thoại nếu bật chuyển tin thoại thành chữ) của người hoặc nhóm này. Cần chọn Trợ lý giọng nói "
                                         "hoặc Trợ lý AI riêng."),
    "voice_text": ("Chuyển tin thoại thành chữ", "Tin thoại 1-1 được Zalo chuyển thành chữ, và Home Assistant bắn sự kiện zalo_call_voice_text."),
    "announce": ("Báo ra loa khi có cuộc gọi đến", "Bật thì khi người này gọi đến, một loa trong nhà đọc «Có cuộc gọi ... từ ...» để người trong nhà biết (kể cả "
                                                   "khi không tự nghe máy). Mặc định TẮT."),
    "announce_to": ("Loa dùng để báo", "Loa đọc thông báo cuộc gọi đến (bắt buộc khi bật báo ra loa). Giọng đọc lấy từ Trợ lý giọng nói của quy tắc."),
    "announce_volume": ("Âm lượng lúc báo (%)", "Âm lượng của loa khi đọc thông báo có cuộc gọi đến. 0 = giữ nguyên. Không ai nghe máy thì loa trở về mức cũ; có người nghe thì cuộc gọi tự đặt âm lượng của nó. Loa R1 có 15 mức: 6/15 là 40%."),
    "announce_repeat": ("Báo lại sau mỗi (giây)", "Đọc xong thông báo thì chờ chừng này giây rồi đọc lại, cứ thế tới khi có người nghe máy hoặc cuộc gọi kết thúc. 0 = chỉ báo một lần."),
    "announce_text": ("Câu báo ra loa", "Có thể dùng {ten} (tên người gọi) và {loai} (thoại hoặc video). Bỏ trống = «Có cuộc gọi {loai} từ {ten}.»"),
    "speaker": ("Loa trong nhà", "Loa phát tiếng người gọi khi người nhà nói trực tiếp."),
    "mic": ("Mic trong nhà", "Camera hoặc vệ tinh Assist có mic, gửi tiếng trong nhà cho người gọi khi người nhà nói trực tiếp."),
    "mic_url": ("Mic từ địa chỉ mạng (nâng cao)", "Địa chỉ rtsp/http của luồng tiếng, nếu mic không có trong danh sách. Thắng ô Mic."),
    "camera": ("Camera trong nhà", "Camera gửi hình cho người gọi khi người nhà nói trực tiếp (cuộc gọi video)."),
    "volume": ("Âm lượng loa (%)", "Từ 0 đến 100. 0 = giữ nguyên."),
    "echo_guard": ("Chống vọng âm", "Tránh tiếng loa lọt ngược vào mic khi hai thứ cùng một thiết bị."),
    "connect": (CONNECT_NAME, CONNECT_HELP),
    "connect_now": CONNECT_NOW,
    "video_request": ("Khi người gọi xin chuyển sang video", "Người đang gọi thoại có thể xin chuyển sang video. Mặc định KHÔNG tự đồng ý (riêng tư): chỉ báo cho "
                      "automation qua sự kiện zalo_call_call_state (trạng thái video_request). Chọn đồng ý nếu muốn tự động, nhưng chỉ có tác dụng khi công tắc "
                      "«Cho phép đồng ý chuyển sang video» trên thiết bị Zalo Call đang BẬT (mặc định TẮT)."),
    "handover_rule": HANDOVER, "pipeline": PIPELINE, "agent": AGENT,
}
VIDEO_REQUEST_OPTIONS = [
    {"value": "ask", "label": "Không tự đồng ý (chỉ báo cho automation, mặc định)"},
    {"value": "accept", "label": "Tự đồng ý, KHÔNG gửi hình trong nhà"},
    {"value": "accept_camera", "label": "Tự đồng ý và gửi camera đã chọn bên dưới"},
]
RULE_SCOPE_OPTIONS = [
    {"value": "thread", "label": "Một người hoặc một nhóm cụ thể"},
    {"value": "groups", "label": "Mọi nhóm"},
    {"value": "contacts", "label": "Mọi người trong danh bạ"},
    {"value": "strangers", "label": "Mọi người lạ"},
]
CALL_TYPE_OPTIONS = [{"value": "voice", "label": "Thoại"}, {"value": "video", "label": "Video"}]
AFTER_OPTIONS = [{"value": "hangup", "label": "Cúp máy"}, {"value": "connect", "label": "Nối thiết bị nhà"}, {"value": "wait", "label": "Giữ máy"}]


def _set(fields, key, pair):
    if key in fields:
        fields[key]["name"], fields[key]["description"] = pair


def apply(extra: dict) -> None:
    """Áp bảng từ ngữ lên dict dịch vụ (đã nạp từ EXTRA_YAML). Chỉ đổi chữ hiển thị và nhãn ô chọn."""
    for svc, (name, desc) in SERVICES.items():
        if svc in extra:
            extra[svc]["name"], extra[svc]["description"] = name, desc
    for svc in ("make_call", "answer_call"):
        for key, pair in COMMON_CALL_FIELDS.items():
            _set(extra.get(svc, {}).get("fields", {}), key, pair)
    for key, pair in {**COMMON_CALL_FIELDS, **ALERT_FIELDS}.items():
        _set(extra.get("alert_call", {}).get("fields", {}), key, ALERT_FIELDS.get(key, pair))
    for key, pair in RULE_FIELDS.items():
        _set(extra.get("set_rule", {}).get("fields", {}), key, pair)
    for svc in ("remove_rule",):
        _set(extra.get(svc, {}).get("fields", {}), "scope", RULE_FIELDS["scope"])
        _set(extra.get(svc, {}).get("fields", {}), "thread_id", RULE_FIELDS["thread_id"])
    for svc in ("set_rule", "remove_rule"):
        f = extra.get(svc, {}).get("fields", {})
        if "scope" in f:
            f["scope"]["selector"] = {"select": {"options": RULE_SCOPE_OPTIONS}}
    f = extra.get("set_rule", {}).get("fields", {})
    if "video_request" in f:
        f["video_request"]["selector"] = {"select": {"options": VIDEO_REQUEST_OPTIONS}}
    if "call_types" in f:
        f["call_types"]["selector"] = {"select": {"options": CALL_TYPE_OPTIONS, "multiple": True}}
    for svc in ("make_call", "answer_call", "alert_call", "set_rule"):
        f = extra.get(svc, {}).get("fields", {})
        if "connect" in f:
            f["connect"]["selector"] = {"select": {"options": CONNECT_OPTIONS, "multiple": True}}
    for svc in ("make_call", "answer_call", "set_rule"):
        f = extra.get(svc, {}).get("fields", {})
        if "connect_now" in f:
            f["connect_now"]["selector"] = {"select": {"options": CONNECT_NOW_OPTIONS, "multiple": True}}
    f = extra.get("alert_call", {}).get("fields", {})
    if "after" in f:
        f["after"]["selector"] = {"select": {"options": AFTER_OPTIONS}}
