"""Giải thích TỪNG lựa chọn của mọi ô chọn (select) trong services.yaml, dùng cho docs/DICH-VU.md và README.

Tra cứu (xem `explain`): ghi chú riêng của «dịch_vụ.ô» → ghi chú chung của ô theo bộ lựa chọn → nhãn có sẵn trong services.yaml (ô có nhãn như emoji,
biểu tượng, connect...). Chỗ Zalo chưa chú giải nghĩa thì ghi thẳng là chưa chú giải, KHÔNG đoán. Test `test_zalo_call_docs` đòi mọi lựa chọn của mọi ô
chọn đều tra ra được lời giải thích, nên thêm dịch vụ có ô chọn mới mà quên ghi chú sẽ báo lỗi.
"""

_THREAD = {"user": "trò chuyện 1-1 với một người", "group": "nhóm"}
_NUM_THREAD = {"0": "người dùng (trò chuyện 1-1)", "1": "nhóm"}
_NUM_UNKNOWN = {"0": "mã 0 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)", "1": "mã 1 của Zalo (app chưa chú giải nghĩa; giữ mặc định nếu không chắc)"}
_ONOFF = {"1": "bật", "0": "tắt"}
_ST_UNKNOWN = {"1": "mã trạng thái 1 của Zalo (app chưa chú giải nghĩa)", "0": "mã trạng thái 0 của Zalo (app chưa chú giải nghĩa)"}
_OFF_ON_AUTO = {"off": "tắt", "on": "bật", "auto": "tự động: áp cho con số trong tin"}
_COLORS = {"red": "đỏ", "orange": "cam", "yellow": "vàng", "green": "xanh lá"}

# (tên ô, bộ lựa chọn) -> {giá trị: giải thích}; bộ lựa chọn = tuple theo đúng thứ tự trong services.yaml
GENERIC = {
    ("type", ("user", "group")): _THREAD,
    ("type", ("user", "video", "group")): {"user": "gọi thoại 1-1", "video": "gọi video 1-1", "group": "gọi nhóm"},
    ("type", ("user", "video")): {"user": "gọi thoại", "video": "gọi video"},
    ("format", ("plain", "markdown")): {"plain": "chữ thường, gửi đúng như đã gõ (mặc định)",
                                        "markdown": "hiểu dấu đánh dấu: **đậm**, *nghiêng*, __gạch chân__, ~~gạch ngang~~, # tiêu đề, danh sách, {red}màu{/}, {big}to{/}"},
    ("auto_emphasis", ("red", "orange", "yellow", "green")): {k: "tự tô " + v + " cho con số (29°C, 75%, 15:30) và chữ đậm" for k, v in _COLORS.items()},
    ("font_size", ("off", "small", "big", "auto")): {"off": "không đổi cỡ chữ", "small": "chữ nhỏ", "big": "chữ to",
                                                     "auto": "tự động: tiêu đề to, dòng trong ngoặc nhỏ"},
    ("text_color", ("off", "auto", "red", "orange", "yellow", "green")): {"off": "không tô màu", "auto": "tự động: tô màu con số (màu lấy ở ô «Màu dùng cho chế độ auto»)",
                                                                         **{k: "chữ màu " + v for k, v in _COLORS.items()}},
    ("bold", ("off", "on", "auto")): {"off": "không in đậm", "on": "in đậm cả tin", "auto": "tự động: in đậm con số"},
    ("italic", ("off", "on", "auto")): {"off": "không in nghiêng", "on": "in nghiêng cả tin", "auto": "tự động: in nghiêng con số"},
    ("underline", ("off", "on", "auto")): {"off": "không gạch chân", "on": "gạch chân cả tin", "auto": "tự động: gạch chân con số"},
    ("heading", ("off", "on", "auto")): {"off": "không làm tiêu đề", "on": "dòng đầu thành tiêu đề (to, đậm)",
                                         "auto": "tự động: dòng đầu ngắn của tin nhiều dòng thành tiêu đề; dòng kết thúc bằng «:» thành đề mục"},
    ("auto_color", ("red", "orange", "yellow", "green")): {k: "màu " + v + " dùng cho chế độ auto của «Màu chữ»" for k, v in _COLORS.items()},
    ("pick", ("first", "random")): {"first": "lấy kết quả đầu tiên (mặc định)", "random": "chọn ngẫu nhiên trong các kết quả"},
    ("gender", ("0", "1")): {"0": "nam", "1": "nữ"},
    ("setting_type", ("online_status", "seen_status", "receive_message", "phone_search")): {
        "online_status": "cài đặt hiện trạng thái đang hoạt động", "seen_status": "cài đặt hiện «đã xem» tin nhắn",
        "receive_message": "cài đặt ai được nhắn tin cho mình", "phone_search": "cài đặt cho người khác tìm mình bằng số điện thoại"},
    ("duration", ("3600", "14400", "-1", "0")): {"3600": "tắt thông báo 1 giờ", "14400": "tắt thông báo 4 giờ", "-1": "tắt thông báo vĩnh viễn",
                                                 "0": "bật lại thông báo"},
    ("ttl", ("0", "86400000", "604800000")): {"0": "tắt tự xoá tin", "86400000": "tự xoá sau 1 ngày (tính bằng mili giây)",
                                              "604800000": "tự xoá sau 7 ngày (tính bằng mili giây)"},
    ("srtp", ("sess", "off", "key")): {
        "sess": "khoá mã hoá lấy từ mã phiên của cuộc gọi (mặc định, đã chạy thật với điện thoại)",
        "off": "không mã hoá tiếng (RTP trần)", "key": "khoá tự sinh (thử nghiệm)"},
    ("extend_profile", ("native", "pc", "zca")): {
        "native": "giống ứng dụng Zalo trên Linux (mặc định, đã chạy thật với điện thoại)", "pc": "bộ cũ của app (newZrtc=0)", "zca": "bộ của thư viện zca-js"},
    ("echo_guard", ("auto", "on", "duplex", "off")): {
        "auto": "chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ loa R1)", "on": "luôn chặn mic khi loa đang phát tiếng bên kia",
        "duplex": "song công: nói chen được (loa R1 dùng bộ khử vọng riêng)", "off": "tắt chống vọng"},
    ("video_request", ("ask", "accept", "accept_camera")): {
        "ask": "không tự đồng ý: chỉ báo cho automation (trạng thái video_request), bạn hoặc blueprint quyết định (mặc định)",
        "accept": "tự đồng ý chuyển sang video nhưng KHÔNG gửi hình trong nhà (người gọi thấy bạn, không thấy nhà)",
        "accept_camera": "tự đồng ý và gửi camera đã chọn trong quy tắc"},
    ("scope", ("thread", "groups", "contacts", "strangers")): {
        "thread": "một người hoặc một nhóm cụ thể (điền thêm Mã Zalo); được ưu tiên cao nhất và thay hẳn quy tắc chung",
        "groups": "mọi nhóm", "contacts": "mọi người trong danh bạ (bạn bè)", "strangers": "mọi người lạ (không có trong danh bạ)"},
    ("call_types", ("voice", "video")): {"voice": "nghe cuộc gọi thoại", "video": "nghe cuộc gọi video (chọn cả hai = nghe cả hai loại)"},
    ("connect", ("mic", "speaker", "camera", "ai")): {
        "mic": "Mic: gửi tiếng trong nhà cho người gọi", "speaker": "Loa: phát tiếng người gọi ra loa trong nhà",
        "camera": "Camera: gửi hình trong nhà (tích ô này là cuộc gọi VIDEO; cuộc thoại được nâng lên video)",
        "ai": "AI tự chọn: AI quyết dùng mic + loa hay thêm camera, chỉ trong các ô đã tích (không ô nào thì trong cả ba; AI không chọn thì chỉ mic + loa)"},
    ("connect_now", ("mic", "speaker", "camera")): {
        "mic": "bật mic ngay khi người nhận nghe máy", "speaker": "bật loa ngay khi người nhận nghe máy",
        "camera": "bật camera ngay khi người nhận nghe máy (và là cuộc gọi VIDEO)"},
    ("after", ("hangup", "connect", "wait")): {
        "hangup": "cúp máy ngay sau khi đọc xong (hợp báo mất điện, rò nước)",
        "connect": "nối thiết bị nhà đã cài (hợp báo người ngã, có trộm)",
        "wait": "giữ máy: người nhận hoặc automation tự cúp bằng dịch vụ «Kết thúc cuộc gọi»"},
}

# ghi chú riêng của «dịch_vụ.ô» (thắng ghi chú chung)
SERVICE = {
    ("send_bank_card", "type"): _NUM_THREAD, ("set_pinned_conversations", "type"): _NUM_THREAD,
    ("translate_message", "type"): _NUM_UNKNOWN, ("translate_message_auto", "type"): _NUM_UNKNOWN, ("translate_message_suggest", "type"): _NUM_UNKNOWN,
    ("update_translate_setting", "type"): _NUM_UNKNOWN, ("push_profile_verification_message", "type"): _NUM_UNKNOWN,
    ("get_todo_list", "type"): _NUM_UNKNOWN,
    ("remove_friend_recommendation_v2", "type"): {"0": "loại gợi ý mặc định (mã 0 của Zalo)", "1": "loại gợi ý mã 1 của Zalo (app chưa chú giải nghĩa)"},
    ("pin_board_topic", "type"): {"0": "loại chủ đề mã 0 của Zalo (ghi chú, bình chọn, nhắc hẹn; app chưa chú giải mã nào là loại nào)",
                                  "1": "loại chủ đề mã 1 của Zalo (app chưa chú giải)"},
    ("update_settings", "status"): _ONOFF,
    ("update_profile_bio", "status"): _ST_UNKNOWN, ("create_todo", "status"): _ST_UNKNOWN, ("update_todo", "status"): _ST_UNKNOWN,
    ("update_todo_status", "status"): _ST_UNKNOWN,
}


def explain(service: str, field: str, options: list) -> dict[str, str]:
    """{giá trị: giải thích} cho mọi lựa chọn của một ô chọn; lựa chọn nào không tra ra thì KHÔNG có trong kết quả (test báo thiếu)."""
    values = [str(o["value"]) if isinstance(o, dict) else str(o) for o in options]
    labels = {str(o["value"]): str(o.get("label") or "") for o in options if isinstance(o, dict)}
    table = SERVICE.get((service, field)) or GENERIC.get((field, tuple(values))) or {}
    out = {}
    for v in values:
        if v in table:
            out[v] = table[v]
        elif labels.get(v) and labels[v].strip() != v:
            out[v] = labels[v].strip()
        elif field in ("icon", "zalo_emoji"):
            out[v] = "biểu tượng cảm xúc Zalo tên «%s» (giữ nguyên tên tiếng Anh)" % v
    return out
