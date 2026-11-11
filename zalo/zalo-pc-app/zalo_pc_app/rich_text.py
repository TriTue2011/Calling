"""Định dạng chữ cho tin nhắn Zalo: in đậm, nghiêng, gạch chân, gạch ngang, hai cỡ chữ, bốn màu, danh sách.

Zalo cá nhân nhận style THEO KHOẢNG KÝ TỰ, không phải markdown: tin gửi kèm ``textProperties`` =
``{"styles": [{"start", "len", "st"}], "ver": 0}`` (đúng cách thư viện zca-js 2.1.2 làm, cùng cách add-on zalo_bot cũ đang chạy).
``start`` và ``len`` tính theo đơn vị UTF-16 (emoji đếm là 2).

Mã ``st`` Zalo hiểu (nhiều mã gộp bằng dấu phẩy, ví dụ ``f_18,c_db342e,b``):
  b i u s            đậm, nghiêng, gạch chân, gạch ngang
  f_13 f_18          nhỏ, to — chỉ có hai cỡ này (mã khác bị Zalo lặng lẽ bỏ qua nên ở đây bị TỪ CHỐI)
  c_db342e c_f27806 c_f7b503 c_15a85f      đỏ, cam, vàng, xanh lá
  lst_1 lst_2        danh sách chấm đầu dòng, đánh số
  ind_10 .. ind_40   thụt lề bốn cấp

Ba việc của module:
  * ``validate_styles``: kiểm danh sách style do người gọi tự tính (sai thì ValueError rõ ràng, không gửi mù).
  * ``from_markdown``: markdown nhẹ + thẻ màu/cỡ -> (chữ thuần, style).
  * ``auto_emphasis``: tự nhấn mạnh CON SỐ (kèm đơn vị dính liền như 29°C, 75%) và chữ **đậm** bằng màu — theo quy tắc cú pháp
    của số, không theo danh sách từ khoá.
"""
from __future__ import annotations

import json
import re

COLORS = {"red": "c_db342e", "orange": "c_f27806", "yellow": "c_f7b503", "green": "c_15a85f"}
SIZES = {"small": "f_13", "big": "f_18"}
_ALIASES = {"đỏ": "red", "do": "red", "cam": "orange", "vàng": "yellow", "vang": "yellow", "xanh": "green",
            "nhỏ": "small", "nho": "small", "to": "big"}
_BASIC = ("b", "i", "u", "s")
_LISTS = ("lst_1", "lst_2")
_IND = re.compile(r"^ind_[1-4]0$")
_VALID = set(COLORS.values()) | set(SIZES.values()) | set(_BASIC) | set(_LISTS)
MAX_STYLES = 200

_TAG = re.compile(r"\{(/?)([^{}\s]{0,8})\}")
_NUMBER = re.compile(r"(?<![\w.,:/+-])[+-]?\d+(?:[.,:/]\d+)*(?:°[CFcf]?|%|[^\W\d_]{1,4}\b)?")


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _token_ok(tok: str) -> bool:
    return tok in _VALID or bool(_IND.match(tok))


def validate_styles(message: str, styles) -> list:
    """Chuẩn hoá và kiểm style do người gọi tự tính. Sai thì ValueError (Zalo lặng lẽ bỏ qua mã lạ nên không để lọt)."""
    if not styles:
        return []
    if not isinstance(styles, list) or len(styles) > MAX_STYLES:
        raise ValueError("styles phải là danh sách (tối đa %d mục)" % MAX_STYLES)
    total = utf16_len(message)
    out = []
    for e in styles:
        try:
            start, length, st = int(e["start"]), int(e["len"]), str(e["st"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("mỗi style cần start, len (số) và st (mã)")
        toks = [t.strip() for t in st.split(",") if t.strip()]
        if not toks or not all(_token_ok(t) for t in toks):
            raise ValueError("mã style không hợp lệ: %r (hợp lệ: b i u s f_13 f_18 c_db342e c_f27806 c_f7b503 c_15a85f lst_1 lst_2 ind_10..ind_40)" % st)
        if start < 0 or length <= 0 or start + length > total:
            raise ValueError("style vượt ngoài nội dung (start=%d len=%d, nội dung dài %d đơn vị UTF-16)" % (start, length, total))
        out.append({"start": start, "len": length, "st": ",".join(toks)})
    return out


def text_properties(styles: list) -> str:
    return json.dumps({"styles": styles, "ver": 0}, ensure_ascii=False, separators=(",", ":"))


def _order(tokens) -> str:
    rank = lambda t: (0 if t.startswith("f_") else 1 if t.startswith("c_") else 2 if t in _BASIC else 3, t)
    return ",".join(sorted(tokens, key=rank))


def _runs(chars: list, marks: list) -> list:
    """Gộp các ký tự liền nhau có cùng tập style thành một khoảng; vị trí tính theo UTF-16, xuống dòng cắt khoảng."""
    out, pos, run = [], 0, None
    for ch, mk in zip(chars, marks):
        n = utf16_len(ch)
        if ch != "\n" and mk:
            if run and run["mk"] == mk and run["end"] == pos:
                run["end"] = pos + n
            else:
                if run:
                    out.append(run)
                run = {"start": pos, "end": pos + n, "mk": mk}
        elif run:
            out.append(run)
            run = None
        pos += n
    if run:
        out.append(run)
    return [{"start": r["start"], "len": r["end"] - r["start"], "st": _order(r["mk"])} for r in out]


def _closer_ahead(s: str, marker: str, i: int) -> bool:
    return s.find(marker, i + len(marker)) != -1


def _inline(line: str, base: frozenset):
    """Một dòng -> (danh sách ký tự thuần, danh sách tập style). Dấu không có cặp đóng thì giữ nguyên là chữ."""
    chars, marks = [], []
    active: set = set()
    tags: list = []                                     # mã màu/cỡ đang mở; màu và cỡ cuối cùng thắng
    i, n = 0, len(line)

    def emit(c):
        st = set(base) | active
        for kind in ("c_", "f_"):
            top = [t for t in tags if t.startswith(kind)]
            if top:
                st.add(top[-1])
        chars.append(c)
        marks.append(frozenset(st))

    while i < n:
        c = line[i]
        if c == "\\" and i + 1 < n and line[i + 1] in "*_~{}\\#-":
            emit(line[i + 1])
            i += 2
            continue
        two = line[i:i + 2]
        toggled = {"**": "b", "__": "u", "~~": "s"}.get(two)
        if toggled and (toggled in active or _closer_ahead(line, two, i)):
            active.symmetric_difference_update({toggled})
            i += 2
            continue
        if c in "*_" and two != c * 2:
            prev = line[i - 1] if i else " "
            nxt = line[i + 1] if i + 1 < n else " "
            word = c == "_"
            if "i" in active:
                if not prev.isspace() and not (word and nxt.isalnum()):
                    active.discard("i")
                    i += 1
                    continue
            elif not nxt.isspace() and not (word and prev.isalnum()) and _closer_ahead(line, c, i):
                active.add("i")
                i += 1
                continue
        if c == "{":
            m = _TAG.match(line, i)
            if m:
                closing, name = m.group(1), _ALIASES.get(m.group(2), m.group(2))
                code = COLORS.get(name) or SIZES.get(name)
                if closing and tags and (name == "" or code in tags):
                    if name == "":
                        tags.pop()
                    else:
                        tags.reverse()
                        tags.remove(code)
                        tags.reverse()
                    i = m.end()
                    continue
                if not closing and code and "{/" in line[m.end():]:
                    tags.append(code)
                    i = m.end()
                    continue
        emit(c)
        i += 1
    return chars, marks


_HEADING = re.compile(r"^#{1,3}\s+")
_BULLET = re.compile(r"^\s*[-*•]\s+")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+")


def from_markdown(text: str):
    """Markdown nhẹ -> (chữ thuần, ký tự, style từng ký tự, style cả dòng).

    ``**đậm**`` ``*nghiêng*``/``_nghiêng_`` ``__gạch chân__`` ``~~gạch ngang~~``, ``# tiêu đề`` (to + đậm), ``- mục`` / ``1. mục``
    (danh sách), thẻ ``{red}..{/}`` ``{orange}`` ``{yellow}`` ``{green}`` (tiếng Việt: ``{đỏ}`` ``{cam}`` ``{vàng}`` ``{xanh}``) và
    ``{big}..{/}`` ``{small}..{/}``. Dấu ``\\`` đặt trước để giữ nguyên ký tự đặc biệt.
    Danh sách là kiểu CẢ DÒNG nên trả riêng (một khoảng phủ cả dòng), không trộn vào các khoảng chữ."""
    chars, marks, line_styles, pos = [], [], [], 0
    for k, line in enumerate(str(text).split("\n")):
        base, lst = frozenset(), ""
        h = _HEADING.match(line)
        if h:
            line, base = line[h.end():], frozenset({"f_18", "b"})
        else:
            b = _BULLET.match(line)
            nm = _NUMBERED.match(line)
            if b:
                line, lst = line[b.end():], "lst_1"
            elif nm:
                line, lst = line[nm.end():], "lst_2"
        c, m = _inline(line, base)
        if k:
            chars.append("\n")
            marks.append(frozenset())
            pos += 1
        width = sum(utf16_len(x) for x in c)
        if lst and width:
            line_styles.append({"start": pos, "len": width, "st": lst})
        pos += width
        chars.extend(c)
        marks.extend(m)
    return "".join(chars), chars, marks, line_styles


def auto_emphasis(plain: str, chars: list, marks: list, color: str = "red"):
    """Thêm đậm + màu cho con số (kèm đơn vị dính liền) và cho chữ đã in đậm mà chưa có màu. Không đụng chỗ đã có màu."""
    code = COLORS.get(color, COLORS["red"])
    marks = list(marks)
    for m in _NUMBER.finditer(plain):
        for k in range(m.start(), m.end()):
            if not any(t.startswith("c_") for t in marks[k]):
                marks[k] = frozenset(set(marks[k]) | {"b", code})
    for k, mk in enumerate(marks):
        if "b" in mk and not any(t.startswith("c_") for t in mk):
            marks[k] = frozenset(set(mk) | {code})
    return marks


# ---------------------------------------------------------------------------------------------------------------------
# Emoji. Ba đường: mã ``:ten:`` (bảng dưới, cũng là danh sách chọn ở dịch vụ HA), tiền tố ``emoji``, và ``auto_emoji``.
# Chọn emoji hợp nghĩa là việc về NGỮ NGHĨA, không có quy tắc cú pháp nào thay được (khác với số: số nhận ra bằng hình dạng),
# nên auto_emoji dùng một bảng nhỏ, bảo thủ: tối đa một emoji ở ĐẦU mỗi dòng, bỏ qua dòng đã có emoji, mặc định TẮT.
EMOJI = {
    "ok": "✅", "xong": "✅", "check": "✅", "x": "❌", "loi": "❌", "error": "❌",
    "warn": "⚠️", "canhbao": "⚠️", "alert": "🚨", "khancap": "🚨",
    "info": "ℹ️", "thongtin": "ℹ️", "hoi": "❓", "question": "❓", "idea": "💡", "den": "💡",
    "fire": "🔥", "chay": "🔥", "water": "💧", "nuoc": "💧", "doam": "💧", "temp": "🌡️", "nhietdo": "🌡️",
    "sun": "☀️", "nang": "☀️", "rain": "🌧️", "mua": "🌧️", "moon": "🌙", "dem": "🌙",
    "door": "🚪", "cua": "🚪", "lock": "🔒", "khoa": "🔒", "unlock": "🔓", "mokhoa": "🔓",
    "bell": "🔔", "chuong": "🔔", "home": "🏠", "nha": "🏠", "car": "🚗", "xe": "🚗",
    "wifi": "📶", "battery": "🔋", "pin": "🔋", "power": "⚡", "dien": "⚡", "tv": "📺",
    "music": "🎵", "nhac": "🎵", "camera": "📷", "video": "🎥", "phone": "📞", "goi": "📞",
    "time": "⏰", "gio": "⏰", "calendar": "📅", "lich": "📅", "heart": "❤️", "tim": "❤️",
    "like": "👍", "thich": "👍", "clap": "👏", "party": "🎉", "chucmung": "🎉", "star": "⭐", "money": "💰", "tien": "💰",
}
_SHORTCODE = re.compile(r":([a-z0-9_]{1,12}):")
_LINE_MARK = re.compile(r"^(?:#{1,3}\s+|\s*[-*•]\s+|\s*\d+[.)]\s+)?")
_ASCII_ALNUM = re.compile(r"[A-Za-z0-9]")
# auto_emoji: (mẫu, emoji), thử theo thứ tự, dòng khớp mẫu đầu tiên được một emoji. Nghiêng về an toàn trước, tiện sau.
_AUTO = [
    (r"cảnh báo|nguy hiểm|khẩn cấp|báo động|cháy|khói|rò rỉ|ngập|xâm nhập", "🚨"),
    (r"lỗi|thất bại|không thể|hỏng|mất kết nối|không kết nối", "❌"),
    (r"chú ý|lưu ý|cẩn thận|sắp hết|pin yếu", "⚠️"),
    (r"thành công|hoàn tất|hoàn thành|đã xong|xong rồi|đã bật|đã tắt|đã mở|đã đóng|đã khoá|đã khóa", "✅"),
    (r"nhiệt độ", "🌡️"), (r"độ ẩm", "💧"), (r"đèn", "💡"), (r"cửa", "🚪"), (r"mưa", "🌧️"), (r"nắng", "☀️"),
]
_AUTO_RE = [(re.compile(r"(?<!\w)(?:%s)(?!\w)" % p, re.I), e) for p, e in _AUTO]


def _has_emoji(text: str) -> bool:
    return any(ord(ch) >= 0x2190 for ch in text.strip()[:2])


def expand_shortcodes(text: str) -> str:
    """``:ok:`` -> ✅ cho tên có trong bảng EMOJI; tên lạ giữ nguyên (không đoán)."""
    return _SHORTCODE.sub(lambda m: EMOJI.get(m.group(1), m.group(0)), text)


def normalize_emoji(value):
    """Giá trị ``emoji`` (ô chọn của HA hoặc JSON) -> chuỗi emoji hoặc None. Nhận: tên trong bảng (``ok`` hoặc ``:ok:``) hoặc
    chính ký tự emoji (không chứa chữ/số ASCII, tối đa 16 đơn vị UTF-16). Khác thì ValueError."""
    if value is None or value is False:
        return None
    v = str(value).strip()
    if not v:
        return None
    name = v.strip(":").lower()
    if name in EMOJI:
        return EMOJI[name]
    if _ASCII_ALNUM.search(v) or utf16_len(v) > 16 or not any(ord(ch) >= 0x2190 for ch in v):
        raise ValueError("emoji phải là biểu tượng hoặc một tên trong bảng: " + ", ".join(sorted(EMOJI)))
    return v


def zalo_emoji_code(name) -> str | None:
    """Ten emoji Zalo (bang 54 bieu tuong cua reaction: heart, haha, wow, cry...) -> ma chu ma Zalo hien thanh anh trong khung chat
    (``/-heart``, ``:>``, ``;xx``...). Rong -> None; ten la -> ValueError kem danh sach."""
    v = str(name or "").strip().lower()
    if not v:
        return None
    from . import services
    if v not in services.REACTION_ICONS:
        raise ValueError("zalo_emoji phai la mot ten trong bang: " + ", ".join(sorted(services.REACTION_ICONS)))
    return services.REACTION_ICONS[v][1]


def _add_prefix(line: str, emoji: str) -> str:
    """Chèn emoji vào đầu dòng, SAU dấu tiêu đề / danh sách để kiểu dòng vẫn nhận ra."""
    m = _LINE_MARK.match(line)
    return line[:m.end()] + emoji + " " + line[m.end():]


def auto_emoji_text(text: str) -> str:
    """Thêm một emoji hợp ngữ cảnh vào đầu những dòng chưa có emoji (xem ghi chú bảng _AUTO)."""
    out = []
    for line in str(text).split("\n"):
        body = line[_LINE_MARK.match(line).end():]
        if body.strip() and not _has_emoji(body):
            for rx, e in _AUTO_RE:
                if rx.search(body):
                    line = _add_prefix(line, e)
                    break
        out.append(line)
    return "\n".join(out)


def normalize_emphasis(value):
    """Giá trị ``auto_emphasis`` từ JSON hoặc ô chữ của HA -> None (tắt) hoặc tên màu (True = đỏ)."""
    if value is None or value is False:
        return None
    if value is True:
        return "red"
    v = str(value).strip().lower()
    if v in ("", "false", "0", "off", "no", "none", "tắt", "tat"):
        return None
    if v in ("true", "1", "on", "yes", "auto", "bật", "bat"):
        return "red"
    v = _ALIASES.get(v, v)
    if v not in COLORS:
        raise ValueError("auto_emphasis phải là red/orange/yellow/green (hoặc đỏ/cam/vàng/xanh), true hoặc để trống")
    return v


# ---------------------------------------------------------------------------------------------------------------------
# Kiểu chữ MẶC ĐỊNH / theo từng tin: cỡ chữ, màu, đậm, nghiêng, gạch chân, tiêu đề — mỗi mục có chế độ «auto».
# Quy tắc auto theo CÚ PHÁP của chữ (hình dạng), không theo danh sách từ khoá:
#   đậm auto      con số (29°C, 75%, 15:30, 10/11)         | nghiêng auto   đoạn trong "…" “…” ‘…’ hoặc (…)
#   gạch chân auto  liên kết http(s):// và địa chỉ email     | tiêu đề auto  dòng đầu của tin nhiều dòng, ngắn (≤ 60 ký tự), không kết thúc
#                   bằng dấu câu (. ! ? … , ;); dòng ngắn kết thúc bằng «:» thành đề mục (đậm)
#   cỡ chữ auto   tiêu đề → to, dòng nằm trọn trong ngoặc (…) → nhỏ  | màu auto  con số → màu «auto_color» (mặc định đỏ)
# Chữ đã được đánh dấu tường minh (markdown, thẻ {red}…) luôn thắng: cỡ và màu mặc định không đè lên chỗ đã có cỡ/màu.
STYLE_SIZE = ("off", "small", "big", "auto")
STYLE_COLOR = ("off", "auto", "red", "orange", "yellow", "green")
STYLE_TOGGLE = ("off", "on", "auto")
STYLE_AUTO_COLOR = ("red", "orange", "yellow", "green")
STYLE_DEFAULT = {"size": "off", "color": "off", "bold": "off", "italic": "off", "underline": "off", "heading": "off", "auto_color": "red"}
_ON = {"on", "true", "1", "yes", "bat", "bật", "co", "có"}
_OFF = {"", "off", "false", "0", "no", "none", "tat", "tắt", "khong", "không"}
_AUTO = {"auto", "tu dong", "tự động"}
_QUOTED = re.compile(r'"[^"\n]+"|“[^”\n]+”|‘[^’\n]+’|\([^()\n]+\)')
_LINK = re.compile(r"https?://[^\s]+|[\w.+-]+@[\w-]+\.[\w.-]+")
_HEADING_MAX = 60


def _mode(key: str, value, allowed: tuple, extra: dict | None = None) -> str:
    if value is None or value is False:
        return "off"
    if value is True:
        return "on" if "on" in allowed else "auto"
    v = str(value).strip().lower()
    v = (extra or {}).get(v, v)
    if v in _OFF:
        return "off"
    if v in _AUTO and "auto" in allowed:
        return "auto"
    if v in _ON and "on" in allowed:
        return "on"
    if v in allowed:
        return v
    raise ValueError("%s phải là một trong: %s" % (key, ", ".join(allowed)))


def normalize_style(value) -> dict:
    """Đổi giá trị (dict từ HA/JSON, thiếu khoá = tắt) thành dict đủ 7 khoá; giá trị lạ thì ValueError nêu các lựa chọn hợp lệ."""
    if value in (None, "", False):
        return dict(STYLE_DEFAULT)
    if not isinstance(value, dict):
        raise ValueError("style phải là một đối tượng {size, color, bold, italic, underline, heading, auto_color}")
    unknown = set(value) - set(STYLE_DEFAULT)
    if unknown:
        raise ValueError("style không có khoá: %s" % ", ".join(sorted(unknown)))
    vi_color = dict(_ALIASES)
    out = {
        "size": _mode("size", value.get("size"), STYLE_SIZE, {"nhỏ": "small", "nho": "small", "to": "big", "lớn": "big"}),
        "color": _mode("color", value.get("color"), STYLE_COLOR, vi_color),
        "bold": _mode("bold", value.get("bold"), STYLE_TOGGLE),
        "italic": _mode("italic", value.get("italic"), STYLE_TOGGLE),
        "underline": _mode("underline", value.get("underline"), STYLE_TOGGLE),
        "heading": _mode("heading", value.get("heading"), STYLE_TOGGLE),
    }
    ac = value.get("auto_color")
    out["auto_color"] = "red" if ac in (None, "", False) else _mode("auto_color", ac, STYLE_AUTO_COLOR, vi_color)
    if out["auto_color"] == "off":
        out["auto_color"] = "red"
    return out


def style_is_active(style: dict) -> bool:
    return any(style[k] != "off" for k in ("size", "color", "bold", "italic", "underline", "heading"))


def _heading_spans(plain: str, mode: str):
    """[(bắt đầu, kết thúc, 'big'|'sub')] theo chế độ tiêu đề (on: dòng đầu có chữ; auto: xem quy tắc ở đầu mục)."""
    lines, pos = [], 0
    for ln in plain.split("\n"):
        lines.append((pos, pos + len(ln), ln))
        pos += len(ln) + 1
    filled = [x for x in lines if x[2].strip()]
    spans = []
    if mode == "on" and filled:
        spans.append((filled[0][0], filled[0][1], "big"))
    elif mode == "auto" and len(filled) >= 2:
        a, b, ln = filled[0]
        s = ln.strip()
        if len(s) <= _HEADING_MAX and not s.endswith((".", "!", "?", "…", ",", ";", ":")):
            spans.append((a, b, "big"))
        for a, b, ln in filled[1:]:
            s = ln.strip()
            if s.endswith(":") and len(s) <= _HEADING_MAX:
                spans.append((a, b, "sub"))
    return spans


def apply_style(plain: str, marks: list, style: dict) -> list:
    """Áp kiểu chữ mặc định/auto lên mark từng ký tự (marks cùng độ dài plain). Không đè chỗ đã có màu/cỡ tường minh."""
    marks = [set(m) for m in marks]
    n = len(plain)

    def add(a: int, b: int, *tokens, skip_prefix: str = ""):
        for k in range(a, min(b, n)):
            if plain[k] == "\n":
                continue
            if skip_prefix and any(t.startswith(skip_prefix) for t in marks[k]):
                continue
            marks[k].update(tokens)

    for a, b, kind in _heading_spans(plain, style["heading"]):         # 1) tiêu đề trước (to + đậm; đề mục phụ chỉ đậm)
        add(a, b, "b", *(("f_18",) if kind == "big" else ()), skip_prefix="f_" if kind == "big" else "")
    if style["size"] in ("small", "big"):                                # 2) cỡ chữ
        add(0, n, SIZES[style["size"]], skip_prefix="f_")
    elif style["size"] == "auto":
        pos = 0
        for ln in plain.split("\n"):
            s = ln.strip()
            if len(s) > 2 and s.startswith("(") and s.endswith(")"):
                add(pos, pos + len(ln), SIZES["small"], skip_prefix="f_")
            pos += len(ln) + 1
    if style["color"] in COLORS:                                         # 3) màu
        add(0, n, COLORS[style["color"]], skip_prefix="c_")
    elif style["color"] == "auto":
        for m in _NUMBER.finditer(plain):
            add(m.start(), m.end(), COLORS[style["auto_color"]], skip_prefix="c_")
    for key, token, rx in (("bold", "b", _NUMBER), ("italic", "i", _QUOTED), ("underline", "u", _LINK)):   # 4) đậm / nghiêng / gạch chân
        if style[key] == "on":
            add(0, n, token)
        elif style[key] == "auto":
            for m in rx.finditer(plain):
                add(m.start(), m.end(), token)
    return [frozenset(m) for m in marks]


def render(text: str, fmt: str = "plain", emphasis=None, styles=None, emoji=None, auto_emoji=False, zalo_emoji=None, style=None):
    """Đầu vào của tầng gửi tin. Trả ``(chữ_gửi_đi, danh_sách_style)``.

    * ``fmt="markdown"``: đổi markdown/thẻ thành style (bỏ các dấu định dạng khỏi chữ).
    * ``emphasis``: ``True`` hoặc tên màu (red/orange/yellow/green hay đỏ/cam/vàng/xanh) -> tự nhấn mạnh số và chữ đậm.
    * ``emoji``: emoji (hoặc tên trong bảng EMOJI) chèn vào đầu tin; ``auto_emoji``: tự thêm emoji hợp ngữ cảnh ở đầu từng dòng;
      mã ``:ten:`` trong chữ được đổi thành emoji khi dùng markdown, emoji hoặc auto_emoji.
    * ``style``: kiểu chữ mặc định/auto (cỡ, màu, đậm, nghiêng, gạch chân, tiêu đề) — xem normalize_style / apply_style.
    * ``styles``: style tự tính (chỉ dùng được với fmt="plain" và không có emphasis, vì chữ phải giữ nguyên để khoảng khớp).
    """
    text = str(text)
    st = normalize_style(style)
    prefix = normalize_emoji(emoji)
    zcode = zalo_emoji_code(zalo_emoji)
    if styles:
        if fmt == "markdown" or emphasis or prefix or zcode or auto_emoji or style_is_active(st):
            raise ValueError("styles tự tính không dùng chung với format=markdown, style, auto_emphasis, emoji hay auto_emoji "
                             "(chữ bị đổi thì khoảng tự tính không còn khớp)")
        return text, validate_styles(text, styles)
    if fmt not in ("plain", "markdown", "", None):
        raise ValueError("format phải là plain hoặc markdown")
    if fmt == "markdown" or prefix or auto_emoji:
        text = expand_shortcodes(text)
    if auto_emoji:
        text = auto_emoji_text(text)
    if zcode:
        prefix = (zcode + " " + prefix) if prefix else zcode
    if prefix:
        first, _, rest = text.partition("\n")
        text = _add_prefix(first, prefix) + ("\n" + rest if rest else "")
    if fmt == "markdown":
        plain, chars, marks, line_styles = from_markdown(text)
    else:
        plain, chars, marks, line_styles = text, list(text), [frozenset()] * len(text), []
    if emphasis:
        marks = auto_emphasis(plain, chars, marks, normalize_emphasis(emphasis) or "red")
    if style_is_active(st):
        marks = apply_style(plain, marks, st)
    return plain, validate_styles(plain, _runs(chars, marks) + line_styles)
