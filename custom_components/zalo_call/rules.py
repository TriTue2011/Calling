"""Quy tắc xử lý cuộc gọi đến / tin nhắn theo NGƯỜI — đặt bằng dịch vụ (``set_rule``), không có ô cài đặt. Riêng tư và bảo mật trước hết:

  * KHÔNG CÓ QUY TẮC = KHÔNG LÀM GÌ: cuộc gọi chỉ đổ chuông, tin nhắn/tin thoại không đi đâu (không STT, không AI, không trả lời).
  * Phạm vi (``scope``): ``thread`` (một threadID, người HOẶC nhóm) > ``groups`` (mọi nhóm) | ``contacts`` (người trong danh bạ) |
    ``strangers`` (người lạ). Quy tắc theo threadID THAY HẲN quy tắc nhóm (không trộn từng trường), nên ``answer: false`` ở một người
    chặn được quy tắc danh bạ dễ dãi hơn.
  * Không biết người đó quen hay lạ (app chưa tải được danh bạ): chỉ quy tắc theo threadID được áp, quy tắc contacts/strangers bị bỏ qua.
  * Thiết bị nhà do ``connect`` quyết định (chọn nhiều): rỗng/``never`` (mặc định) = không nối gì; hoặc chọn từng phần ``mic``, ``speaker``,
    ``camera`` / ghép bất kỳ (chỉ mic, chỉ loa, chỉ cam, mic+loa, loa+cam...). Lối tắt: ``voice`` = mic+loa, ``always`` = cả ba, ``ai`` = AI tự chọn
    voice hay camera lúc chuyển máy (không chọn thì voice). Áp cho cả cuộc thoại lẫn video (thoại mà có camera thì nâng lên video). Chỉ nối thứ
    ĐÃ CHỌN trong quy tắc, và chỉ KHI CHUYỂN MÁY.
  * ``ai: true`` bắt buộc có ``pipeline`` hoặc ``agent`` — không lặng lẽ rơi về pipeline ưu tiên (nó có quyền thiết bị nhà).
"""
from __future__ import annotations

from typing import Any


class RuleError(ValueError):
    """Quy tắc/phạm vi không hợp lệ (dịch vụ đổi thành RuleError)."""


SCOPES = ("thread", "groups", "contacts", "strangers")
CALL_TYPES = ("voice", "video")
MAX_DELAY = 120
ECHO = ("auto", "on", "duplex", "off")
CONNECT_PARTS = ("mic", "speaker", "camera")
# Lựa chọn của trường `connect` (chọn nhiều): từng phần hoặc ghép bất kỳ; never/voice/always/ai là lối tắt.
CONNECT = ("never", "voice", "always", "ai") + CONNECT_PARTS


def parse_connect(value: Any) -> list[str]:
    """Danh sách phần sẽ nối, chuẩn hoá: tập con của (mic, speaker, camera) theo thứ tự đó, hoặc ["ai"] (AI chọn), hoặc [] (không nối).
    Nhận chuỗi hay danh sách. never = không; voice = mic+speaker; always = cả ba; mic/speaker/camera = từng phần. Giá trị lạ thì RuleError."""
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
    return ["ai"] if ai else [p for p in CONNECT_PARTS if p in parts]
RULES_KEY = "rules"

# Trường quy tắc và kiểu. Thiếu trường = giá trị mặc định ở dưới (an toàn: tất cả TẮT).
DEFAULT_RULE: dict[str, Any] = {
    "name": "", "answer": False, "answer_delay": 3, "call_types": ["voice", "video"],
    "ai": False, "pipeline": "", "agent": "", "greeting": "", "handover_rule": "", "trusted": False,
    "reply_ai": False, "voice_text": False,
    "connect": [], "speaker": "", "mic": "", "mic_url": "", "camera": "", "volume": 0, "echo_guard": "auto",
}
_STR = ("name", "pipeline", "agent", "greeting", "handover_rule", "speaker", "mic", "mic_url", "camera")
_BOOL = ("answer", "ai", "trusted", "reply_ai", "voice_text")


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
    if data.get("echo_guard") is not None:
        if data["echo_guard"] not in ECHO:
            raise RuleError("echo_guard chỉ gồm: %s" % ", ".join(ECHO))
        rule["echo_guard"] = data["echo_guard"]
    if rule["ai"] and not (rule["pipeline"] or rule["agent"]):
        raise RuleError(
            "ai: true cần chọn pipeline (Assist pipeline) hoặc agent (trợ lý hội thoại): không tự dùng pipeline ưu tiên vì nó có quyền "
            "thiết bị nhà")
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
