"""Quy tắc xử lý cuộc gọi đến / tin nhắn theo NGƯỜI — đặt bằng dịch vụ (``set_rule``), không có ô cài đặt. Riêng tư và bảo mật trước hết:

  * KHÔNG CÓ QUY TẮC = KHÔNG LÀM GÌ: cuộc gọi chỉ đổ chuông, tin nhắn/tin thoại không đi đâu (không STT, không AI, không trả lời).
  * Phạm vi (``scope``): ``thread`` (một threadID, người HOẶC nhóm) > ``groups`` (mọi nhóm) | ``contacts`` (người trong danh bạ) |
    ``strangers`` (người lạ). Quy tắc theo threadID THAY HẲN quy tắc nhóm (không trộn từng trường), nên ``answer: false`` ở một người
    chặn được quy tắc danh bạ dễ dãi hơn.
  * Không biết người đó quen hay lạ (app chưa tải được danh bạ): chỉ quy tắc theo threadID được áp, quy tắc contacts/strangers bị bỏ qua.
  * Thiết bị nhà do ``connect`` quyết định, là các ô TÍCH: ``mic``, ``speaker``, ``camera`` (tích 1 = dùng 1, tích 2 = dùng 2, tích 3 = dùng cả 3),
    không tích gì = không nối (mặc định). Tích camera = cuộc gọi VIDEO (thoại thì nâng lên video). Ô ``ai`` = AI tự chọn voice hay thêm camera lúc
    chuyển máy, chỉ trong các ô đã tích. Chỉ nối thứ ĐÃ CHỌN trong quy tắc, và chỉ KHI CHUYỂN MÁY.
  * ``connect_now`` = các phần nối NGAY khi nghe máy (ví dụ chỉ camera); phần còn lại trong ``connect`` chờ tới khi người nhà nói trực tiếp.
  * ``video_request``: người gọi xin chuyển cuộc thoại sang video - ``ask`` (mặc định: chỉ báo sự kiện, không tự đồng ý), ``accept`` (đồng ý, không gửi hình
    trong nhà), ``accept_camera`` (đồng ý và gửi camera đã chọn trong quy tắc).
  * ``announce_repeat``: số giây báo lại sau khi đọc xong (0 = chỉ báo một lần); cứ đọc xong rồi chờ chừng đó thì đọc lại, tới khi nghe máy hoặc cuộc gọi kết thúc.
  * ``announce: true`` (cần ``announce_to``): có cuộc gọi đến thì một loa trong nhà đọc thông báo cho người trong nhà biết. Mặc định TẮT.
  * ``ai: true`` bắt buộc có ``pipeline`` hoặc ``agent`` — không lặng lẽ rơi về pipeline ưu tiên (nó có quyền thiết bị nhà).
"""
from __future__ import annotations

from typing import Any


class RuleError(ValueError):
    """Quy tắc/phạm vi không hợp lệ (dịch vụ đổi thành RuleError)."""


SCOPES = ("thread", "groups", "contacts", "strangers")
CALL_TYPES = ("voice", "video")
MAX_DELAY = 120
MAX_ANNOUNCE_REPEAT = 60                # giây giữa hai lần báo lại tối đa
ECHO = ("auto", "on", "duplex", "off")
VIDEO_REQUEST = ("ask", "accept", "accept_camera")      # người gọi xin chuyển thoại sang video
CONNECT_PARTS = ("mic", "speaker", "camera")
# Lựa chọn của trường `connect` (chọn nhiều): từng phần hoặc ghép bất kỳ; never/voice/always/ai là lối tắt.
CONNECT = ("never", "voice", "always", "ai") + CONNECT_PARTS


def parse_connect(value: Any) -> list[str]:
    """Danh sách ô đã tích của `connect`, chuẩn hoá: các phần (mic, speaker, camera, theo thứ tự đó) rồi "ai" nếu có tích «AI tự chọn». Rỗng = không nối.
    "ai" mà không tích phần nào = AI được chọn trong cả ba. Nhận chuỗi hay danh sách; lối tắt (never/voice/always) vẫn dùng được cho API:
    voice = mic+speaker, always = cả ba. Giá trị lạ thì RuleError."""
    raw = [value] if isinstance(value, str) else list(value or [])
    parts: set[str] = set()
    ai = False
    for item in raw:
        v = str(item).strip().lower()
        if v == "ai":
            ai = True
        elif v == "voice":
            parts |= {"mic", "speaker"}
        elif v == "always":
            parts |= set(CONNECT_PARTS)
        elif v in CONNECT_PARTS:
            parts.add(v)
        elif v not in ("never", ""):
            raise RuleError("connect chỉ gồm: %s" % ", ".join(CONNECT))
    ordered = [p for p in CONNECT_PARTS if p in parts]
    return (ordered or list(CONNECT_PARTS)) + ["ai"] if ai else ordered


RULES_KEY = "rules"

# Trường quy tắc và kiểu. Thiếu trường = giá trị mặc định ở dưới (an toàn: tất cả TẮT).
DEFAULT_RULE: dict[str, Any] = {
    "name": "", "answer": False, "answer_delay": 3, "call_types": ["voice", "video"],
    "ai": False, "pipeline": "", "agent": "", "greeting": "", "handover_rule": "", "trusted": False,
    "announce": False, "announce_to": "", "announce_text": "", "announce_repeat": 0, "connect_now": [], "video_request": "ask",
    "reply_ai": False, "voice_text": False,
    "connect": [], "speaker": "", "mic": "", "mic_url": "", "camera": "", "volume": 0, "echo_guard": "auto",
}
_STR = ("name", "pipeline", "agent", "greeting", "handover_rule", "speaker", "mic", "mic_url", "camera", "announce_to", "announce_text")
_BOOL = ("answer", "ai", "trusted", "reply_ai", "voice_text", "announce")


def empty_rules() -> dict[str, dict[str, Any]]:
    return {"threads": {}, "groups": {}, "contacts": {}, "strangers": {}}


def get_rules(defaults: Any) -> dict[str, dict[str, Any]]:
    value = defaults.get(RULES_KEY)
    base = empty_rules()
    if isinstance(value, dict):
        for k in base:
            if isinstance(value.get(k), dict):
                base[k] = value[k]
    return base


def normalize(data: dict[str, Any], old: dict[str, Any] | None = None) -> dict[str, Any]:
    """Quy tắc đã kiểm tra: trường nêu trong `data` ghi đè `old`; trường khác giữ như cũ (hoặc mặc định). Lỗi thì RuleError."""
    rule = {**DEFAULT_RULE, **(old or {})}
    for k in _STR:
        if k in data and data[k] is not None:
            rule[k] = str(data[k]).strip()
    for k in _BOOL:
        if k in data and data[k] is not None:
            rule[k] = bool(data[k])
    if data.get("answer_delay") is not None:
        try:
            rule["answer_delay"] = max(0, min(MAX_DELAY, int(data["answer_delay"])))
        except (TypeError, ValueError) as err:
            raise RuleError("answer_delay phải là số giây (0-%d)" % MAX_DELAY) from err
    if data.get("announce_repeat") is not None:
        try:
            rule["announce_repeat"] = max(0, min(MAX_ANNOUNCE_REPEAT, int(data["announce_repeat"])))
        except (TypeError, ValueError) as err:
            raise RuleError("announce_repeat phải là số giây (0-%d)" % MAX_ANNOUNCE_REPEAT) from err
    if data.get("volume") is not None:
        try:
            rule["volume"] = max(0, min(100, int(data["volume"])))
        except (TypeError, ValueError) as err:
            raise RuleError("volume phải là số 0-100") from err
    if data.get("call_types") is not None:
        types = [data["call_types"]] if isinstance(data["call_types"], str) else list(data["call_types"])
        bad = [t for t in types if t not in CALL_TYPES]
        if bad:
            raise RuleError("call_types chỉ gồm: %s" % ", ".join(CALL_TYPES))
        rule["call_types"] = types
    if data.get("connect") is not None:
        rule["connect"] = parse_connect(data["connect"])
    if data.get("video_request") is not None:
        if data["video_request"] not in VIDEO_REQUEST:
            raise RuleError("video_request chỉ gồm: %s" % ", ".join(VIDEO_REQUEST))
        rule["video_request"] = data["video_request"]
    if data.get("connect_now") is not None:                       # nối NGAY khi nghe máy: chỉ các phần đã tích (không có «AI tự chọn»)
        rule["connect_now"] = [p for p in parse_connect(data["connect_now"]) if p != "ai"]
    if data.get("echo_guard") is not None:
        if data["echo_guard"] not in ECHO:
            raise RuleError("echo_guard chỉ gồm: %s" % ", ".join(ECHO))
        rule["echo_guard"] = data["echo_guard"]
    if rule["ai"] and not (rule["pipeline"] or rule["agent"]):
        raise RuleError(
            "ai: true cần chọn pipeline (Assist pipeline) hoặc agent (trợ lý hội thoại): không tự dùng pipeline ưu tiên vì nó có quyền "
            "thiết bị nhà")
    if rule["announce"] and not rule["announce_to"]:
        raise RuleError("announce: true cần announce_to (loa media_player sẽ phát thông báo «có cuộc gọi»)")
    if rule["reply_ai"] and not (rule["pipeline"] or rule["agent"]):
        raise RuleError("reply_ai: true cần chọn pipeline hoặc agent (không tự dùng trợ lý mặc định)")
    return rule


def validate_scope(scope: str, thread_id: Any) -> str:
    """threadID đã chuẩn hoá ("" khi scope không phải thread)."""
    if scope not in SCOPES:
        raise RuleError("scope phải là một trong: %s" % ", ".join(SCOPES))
    if scope == "thread":
        tid = str(thread_id or "").strip()
        if not tid.isdigit():
            raise RuleError("scope «thread» cần thread_id là số (ID Zalo của người hoặc nhóm)")
        return tid
    return ""


def resolve(rules: dict[str, dict[str, Any]], thread_id: Any, thread_type: Any, contact_status: str | None) -> dict[str, Any] | None:
    """Quy tắc áp dụng cho một người/nhóm, hoặc None (= không làm gì).

    thread_type: "user"/0 hay "group"/1. contact_status: friend / stranger / group / unknown / None (app không báo → coi là unknown)."""
    tid = str(thread_id or "")
    rule = rules["threads"].get(tid)
    if rule is not None:
        return rule                                            # đè hoàn toàn nhóm
    is_group = str(thread_type) in ("group", "1") or contact_status == "group"
    if is_group:
        return rules["groups"] or None
    if contact_status == "friend":
        return rules["contacts"] or None
    if contact_status == "stranger":
        return rules["strangers"] or None
    return None                                                # unknown: không đoán, không áp quy tắc nhóm
