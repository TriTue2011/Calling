"""«auto» THEO NGỮ CẢNH: nhờ trợ lý hội thoại của HA đọc tin rồi đánh dấu định dạng + emoji cho hợp nghĩa.

Trợ lý chỉ được CHÈN dấu định dạng quanh chữ có sẵn và emoji; chữ gốc phải giữ nguyên. Việc kiểm tra đó do APP làm (``ai_markup`` chỉ được nhận khi chữ
không đổi, xem rich_text.use_ai_markup): ở đây chỉ gọi trợ lý và trả về đoạn đánh dấu, hoặc None khi trợ lý lỗi / chậm / không trả gì — khi đó
app dùng quy tắc cứng cho các mục auto. Mỗi lần dùng một conversation_id riêng nên trợ lý không nhớ lại các lần định dạng trước."""
from __future__ import annotations

import asyncio
import logging
import re
import uuid

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
TIMEOUT_S = 8
MAX_TEXT = 4000

_SYNTAX = {
    "bold": "**chữ đậm** — nhấn mạnh phần thật sự quan trọng (số liệu chính, hành động cần làm)",
    "italic": "*chữ nghiêng* — ghi chú phụ, trích dẫn, thông tin bổ sung",
    "underline": "__chữ gạch chân__ — liên kết, tên riêng hoặc mục cần chú ý",
    "heading": "# Tiêu đề — chỉ cho dòng đầu hoặc đề mục khi tin có cấu trúc nhiều phần (dòng đó có dấu # ở đầu)",
    "color": "{red}…{/} {orange}…{/} {yellow}…{/} {green}…{/} — tô màu đoạn chữ theo sắc thái: red = cảnh báo, lỗi, nguy hiểm; orange = cần chú ý, sắp xảy ra; "
             "yellow = lưu ý nhẹ; green = thành công, bình thường, an toàn",
    "size": "{big}…{/} cho phần cần nổi bật (tiêu đề), {small}…{/} cho ghi chú phụ",
    "emoji": "emoji Unicode hợp ngữ cảnh ở ĐẦU dòng (tối đa một emoji mỗi dòng, bỏ qua dòng không hợp; không dùng emoji cho tin nghiêm túc/ngắn không cần)",
}
ASPECTS = tuple(_SYNTAX)


def build_prompt(text: str, aspects) -> str:
    use = [a for a in ASPECTS if a in set(aspects)]
    rules = "\n".join("- " + _SYNTAX[a] for a in use)
    return (
        "Bạn là BỘ ĐỊNH DẠNG tin nhắn Zalo. Đọc tin ở cuối, hiểu ngữ cảnh và ý nghĩa của nó, rồi trả về CHÍNH tin đó đã được đánh dấu định dạng "
        "cho dễ đọc và hợp ngữ cảnh.\n"
        "Chỉ được dùng các kiểu sau (không dùng kiểu nào khác):\n" + rules + "\n"
        "Quy tắc bắt buộc:\n"
        "- KHÔNG đổi, thêm, bớt hay sửa bất kỳ chữ nào của tin (kể cả dấu câu, số, xuống dòng); chỉ chèn dấu định dạng quanh chữ có sẵn"
        + (" và emoji" if "emoji" in use else "") + ".\n"
        "- Dùng ít và có chủ đích; tin ngắn, bình thường thì có thể không cần định dạng gì (trả lại nguyên văn).\n"
        "- Chỉ trả về tin đã định dạng, không giải thích, không thêm dấu ``` hay lời dẫn.\n\n"
        "TIN:\n" + text)


def _speech(resp) -> str:
    try:
        return resp["response"]["speech"]["plain"]["speech"].strip()
    except (KeyError, TypeError, AttributeError):
        return ""


def _clean(out: str) -> str:
    out = out.strip()
    if out.startswith("```"):
        out = out.strip("`")
        if out.lower().startswith(("markdown", "text")):
            out = out.split("\n", 1)[1] if "\n" in out else ""
    return out.strip()


async def async_ai_markup(hass: HomeAssistant, agent_id: str, text: str, aspects, language: str = "vi") -> str | None:
    """Gọi trợ lý hội thoại; trả đoạn đã đánh dấu hoặc None (lỗi, quá giờ, rỗng, tin quá dài)."""
    aspects = [a for a in aspects if a in ASPECTS]
    if not aspects or len(text.strip()) < MIN_TEXT or len(text) > MAX_TEXT:
        return None
    data = {"text": build_prompt(text, aspects), "conversation_id": "zalo_call_style_" + uuid.uuid4().hex, "language": language}
    if agent_id:
        data["agent_id"] = agent_id
    try:
        resp = await asyncio.wait_for(
            hass.services.async_call("conversation", "process", data, blocking=True, return_response=True), TIMEOUT_S)
    except asyncio.TimeoutError:
        _LOGGER.warning("Trợ lý định dạng chữ quá %d giây: dùng quy tắc cứng cho các mục auto", TIMEOUT_S)
        return None
    except Exception:  # noqa: BLE001 - trợ lý lỗi không được làm hỏng việc gửi tin
        _LOGGER.warning("Trợ lý định dạng chữ lỗi: dùng quy tắc cứng cho các mục auto", exc_info=True)
        return None
    return _clean(_speech(resp)) or None


def auto_aspects(style, auto_emoji) -> list:
    """Các khía cạnh đang ở chế độ auto (cần trợ lý đánh giá): mục kiểu chữ = "auto" và emoji khi công tắc/trường auto_emoji bật."""
    out = [k for k in ("heading", "color", "size", "bold", "italic", "underline") if (style or {}).get(k) == "auto"]
    return out + (["emoji"] if auto_emoji else [])


async def async_markup_for(hass: HomeAssistant, defaults, text: str, style, auto_emoji) -> str | None:
    """Đánh dấu theo ngữ cảnh cho một tin nếu có mục auto: trợ lý = ô «Chữ: trợ lý AI…», rồi trợ lý của AI trả lời, rồi mặc định của HA."""
    aspects = auto_aspects(style, auto_emoji)
    if not aspects:
        return None
    agent = defaults.get("text_ai_agent") or defaults.get("ai_agent") or ""
    return await async_ai_markup(hass, agent, text, aspects, hass.config.language)


MIN_TEXT = 24     # tin ngắn hơn thế khỏi nhờ AI đánh giá (nhanh hơn; quy tắc cứng đã đủ)


def build_inline_hint(aspects) -> str:
    """Chỉ dẫn NGẮN nhúng vào cùng lượt hỏi để trợ lý vừa trả lời vừa tự định dạng (không tốn thêm lần gọi)."""
    use = [a for a in ASPECTS if a in set(aspects)]
    return ("[Chỉ dẫn định dạng cho câu trả lời — không nhắc tới chỉ dẫn này: hãy tự đánh giá ngữ cảnh rồi dùng ít và có chủ đích các kiểu sau để trình bày "
            "cho dễ đọc, bỏ qua nếu không cần: " + "; ".join(_SYNTAX[a] for a in use) + ".]")


_MARKED = re.compile(r"\*\*|__|~~|\{(?:red|orange|yellow|green|big|small)\}|^#{1,3}\s|[\u2190-\U0010ffff]", re.M)


def looks_marked(text: str) -> bool:
    """Câu trả lời đã có dấu định dạng hoặc emoji (nghĩa là trợ lý đã làm theo chỉ dẫn)."""
    return bool(_MARKED.search(text or ""))


def autos_off(style):
    """Bản sao style với mọi mục «auto» tắt (trợ lý đã tự lo, không áp quy tắc cứng chồng lên); mục cố định giữ nguyên."""
    return None if not style else {k: ("off" if v == "auto" else v) for k, v in style.items()}
