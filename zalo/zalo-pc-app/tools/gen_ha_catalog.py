"""Sinh danh muc 96 service cho tich hop HA `zalo_call` tu danh muc cua
chinh app (zalo_pc_app.services.build_catalog) — de services.yaml va
catalog.json KHONG bao gio lech voi app. Chay tu thu muc zalo/zalo-pc-app:

    python3 tools/gen_ha_catalog.py

Ghi: ../../custom_components/zalo_call/catalog.json va services.yaml.
Cach goi tung nhom (kind):
  svc   POST /api/svc/<action>                  (78 service)
  chat  /api/thread/<id>/{send,sendfile,...}    (11 service)
  view  GET /api/contacts                       (2 service)
  acct  tich hop tu lo: webhook/tai khoan/proxy (10 service cua zalobot)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ROOT))           # zalo/zalo-pc-app -> goc repo
OUT = os.path.join(REPO, "custom_components", "zalo_call")
sys.path.insert(0, ROOT)

from zalo_pc_app import services as S  # noqa: E402

# 11 service gui tin: truong rieng cua tich hop (khong co trong catalog app).
CHAT_FIELDS = {
    "send_message": [
        ("message", "Nội dung tin nhắn", True),
        ("format", "Định dạng chữ: plain (mặc định) hoặc markdown — **đậm**, *nghiêng*, __gạch chân__, ~~gạch ngang~~, "
                   "# tiêu đề (to + đậm), - mục / 1. mục (danh sách), {red}chữ đỏ{/} {orange} {yellow} {green} "
                   "(hoặc {đỏ} {cam} {vàng} {xanh}), {big}..{/} {small}..{/}", False),
        ("auto_emphasis", "Tự nhấn mạnh con số (29°C, 75%, 15:30) và chữ đậm bằng màu: red, orange, yellow, green "
                          "(hoặc đỏ, cam, vàng, xanh) hoặc true = đỏ. Để trống = tắt", False),
        ("emoji", "Emoji chèn vào đầu tin: chọn trong bảng hoặc gõ emoji bất kỳ (🎉). Mã :ten: trong chữ (ví dụ :ok:) "
                  "cũng được đổi thành emoji", False),
        ("auto_emoji", "Tự thêm emoji hợp ngữ cảnh vào đầu từng dòng chưa có emoji (cảnh báo, lỗi, xong, nhiệt độ, cửa, đèn…). "
                       "true = bật, false = tắt cho tin này; bỏ trống = theo công tắc «Chữ: tự thêm emoji» trên thiết bị", False),
        ("font_size", "Cỡ chữ cho tin này (ghi đè mặc định trên thiết bị): off, small, big hoặc auto (tiêu đề to, dòng trong ngoặc nhỏ). Bỏ trống = theo mặc định", False),
        ("text_color", "Màu chữ cho tin này: off, auto (con số), red, orange, yellow, green. Bỏ trống = theo mặc định", False),
        ("bold", "In đậm: off, on, auto (con số). Bỏ trống = theo mặc định", False),
        ("italic", "In nghiêng: off, on, auto (đoạn trong \"…\" hoặc (…)). Bỏ trống = theo mặc định", False),
        ("underline", "Gạch chân: off, on, auto (liên kết, email). Bỏ trống = theo mặc định", False),
        ("heading", "Tiêu đề: off, on (dòng đầu), auto (dòng đầu ngắn của tin nhiều dòng; dòng kết thúc «:» thành đề mục). Bỏ trống = theo mặc định", False),
        ("ai_style", "true = nhờ trợ lý AI đánh giá ngữ cảnh cho các mục auto của tin này (thêm vài giây; quá 8 giây thì dùng quy tắc tức thì); false = quy tắc tức thì; bỏ trống = theo công tắc «Chữ: dùng AI đánh giá…» trên thiết bị", False),
        ("auto_color", "Màu dùng cho chế độ auto của «Màu chữ»: red, orange, yellow, green. Bỏ trống = theo mặc định", False),
        ("zalo_emoji", "Emoji của Zalo (bảng emoji trong ô chat Zalo): chọn tên (heart, haha, wow, cry…) để chèn mã tương ứng "
                       "vào đầu tin; Zalo hiện thành ảnh emoji. Dùng được cùng ô Emoji.", False)],
    "send_file": [("file", "Đường dẫn tệp trong HA hoặc URL", True)],
    "send_image": [("file", "Ảnh (đường dẫn trong HA hoặc URL)", True)],
    "send_image_to_user": [("file", "Ảnh (đường dẫn hoặc URL)", True)],
    "send_images_to_user": [("files", "Các ảnh, cách nhau dấu phẩy", True)],
    "send_image_to_group": [("file", "Ảnh (đường dẫn hoặc URL)", True)],
    "send_images_to_group": [("files", "Các ảnh, cách nhau dấu phẩy", True)],
    "send_voice": [("file", "Tệp âm thanh (đường dẫn hoặc URL)", True)],
    "send_card": [("user_id", "UserId của danh thiếp", True)],
    "send_link": [("link", "Đường link", True),
                  ("message", "Lời nhắn kèm theo", False)],
    "send_video": [("file", "Tệp video (đường dẫn hoặc URL)", True)],
}
# 10 service chi co o may chu zalobot: tich hop tu tra loi tu trang thai app.
ACCT = {
    "get_logged_accounts": [], "get_account_details": [],
    "get_account_webhooks": [], "get_account_webhook": [],
    "set_account_webhook": [("message_webhook_url", "URL webhook tin nhắn", False),
                            ("group_event_webhook_url", "URL webhook sự kiện nhóm", False),
                            ("reaction_webhook_url", "URL webhook cảm xúc", False),
                            ("call_webhook_url", "URL webhook cuộc gọi", False)],
    "delete_account_webhook": [], "get_proxies": [], "add_proxy": [],
    "remove_proxy": [], "get_login_qr": [],
}


def _emoji_options():
    from zalo_pc_app import rich_text
    seen, opts = set(), []
    for name, ch in rich_text.EMOJI.items():
        if ch in seen:
            continue                                   # một biểu tượng, một dòng chọn (tên đầu tiên trong bảng)
        seen.add(ch)
        opts.append({"value": name, "label": "%s  %s" % (ch, name)})
    return opts


def _reaction_options():
    return [{"value": n, "label": n} for n in sorted(S.REACTION_ICONS)]


# Truong co danh sach chon (select) thay cho o go chu: bang emoji va bang bieu tuong cam xuc.
SELECTOR_OVERRIDES = {
    ("send_message", "emoji"): {"select": {"options": _emoji_options(), "custom_value": True, "mode": "dropdown"}},
    ("send_message", "auto_emoji"): {"boolean": None},
    ("send_message", "font_size"): {"select": {"options": ["off", "small", "big", "auto"], "mode": "dropdown"}},
    ("send_message", "text_color"): {"select": {"options": ["off", "auto", "red", "orange", "yellow", "green"], "mode": "dropdown"}},
    ("send_message", "bold"): {"select": {"options": ["off", "on", "auto"], "mode": "dropdown"}},
    ("send_message", "italic"): {"select": {"options": ["off", "on", "auto"], "mode": "dropdown"}},
    ("send_message", "underline"): {"select": {"options": ["off", "on", "auto"], "mode": "dropdown"}},
    ("send_message", "heading"): {"select": {"options": ["off", "on", "auto"], "mode": "dropdown"}},
    ("send_message", "ai_style"): {"boolean": None},
    ("send_message", "auto_color"): {"select": {"options": ["red", "orange", "yellow", "green"], "mode": "dropdown"}},
    ("send_message", "zalo_emoji"): {"select": {"options": _reaction_options(), "custom_value": False, "mode": "dropdown"}},
    ("send_message", "format"): {"select": {"options": ["plain", "markdown"], "mode": "dropdown"}},
    ("send_message", "auto_emphasis"): {"select": {"options": ["red", "orange", "yellow", "green"], "custom_value": True,
                                                  "mode": "dropdown"}},
    ("send_sticker", "pick"): {"select": {"options": ["first", "random"], "mode": "dropdown"}},
    ("add_reaction", "icon"): {"select": {"options": _reaction_options(), "custom_value": True, "mode": "dropdown"}},
}

ENTRY_ID_FIELD = {
    "name": "Tài khoản Zalo Call",
    "description": "Chọn tài khoản khi có nhiều tích hợp Zalo Call "
                   "(bỏ trống = tài khoản đầu tiên).",
    "required": False,
    "selector": {"config_entry": {"integration": "zalo_call"}},
}
# Ten truong cu cua zalobot -> ten truong cua tich hop nay.
FIELD_ALIASES = {
    "file": ["file_path_or_url", "image_path", "video_path_or_url",
             "voice_path"],
    "files": ["image_paths"],
}


def _load_meta():
    """Thong tin truong (mo ta, kieu nhap, vi du) lay tu dich vu zalobot cu —
    tests: tools/zalo_bot_field_meta.json."""
    path = os.path.join(HERE, "zalo_bot_field_meta.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _lookup(svc, key, meta):
    own = (meta.get(svc) or {}).get("fields") or {}
    for k in [key] + FIELD_ALIASES.get(key, []):
        if k in own:
            return own[k]
    for other in meta.values():                    # cung ten o dich vu khac
        f = (other.get("fields") or {}).get(key)
        if f and f.get("description"):
            return f
    return {}


_FIELD_TEXT = {
    ("send_sticker", "keyword"): "Gõ từ khoá (ví dụ: cảm ơn, haha, yêu) — tự tìm sticker rồi gửi; dùng thay cho Sticker ID / Cate ID.",
    ("send_sticker", "pick"): "first = kết quả đầu (mặc định), random = chọn ngẫu nhiên trong các kết quả.",
}


def _field_entry(svc, f, meta):
    m = dict(_lookup(svc, f["key"], meta))
    if (svc, f["key"]) in _FIELD_TEXT:
        m["description"] = _FIELD_TEXT[(svc, f["key"])]
    if f.get("description"):
        m["description"] = f["description"]
    if "selector" in f:
        m["selector"] = f["selector"]
    entry = {"name": f["label"],
             "description": m.get("description") or f["label"],
             "required": bool(f["required"]),
             "selector": m.get("selector") or {"text": None}}
    for k in ("example", "default"):
        if k in m:
            entry[k] = m[k]
    return entry



def _zca_extras(core):
    """Cac API zca-js KHONG nam trong 96 dich vu PC: moi cai thanh mot service HA,
    goi qua POST /api/svc/<ten_snake> (app tu chuyen sang bo goi chung zca_api)."""
    import re
    reg_path = os.path.join(ROOT, "zalo_pc_app", "zca_registry.json")
    with open(reg_path, encoding="utf-8") as fh:
        apis = json.load(fh)["apis"]
    have = {e["name"] for e in core} | {e["action"] for e in core if e["action"]}
    extras = []
    for a in apis:
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", a["name"]).lower()
        if a.get("covered_by") or name in have or name in S.OPS or name in (
                "make_call", "answer_call", "reject_call", "end_call",
                "voice_to_text", "upgrade_to_video", "start_call_video",
                "stop_call_video", "start_call_mic", "stop_call_mic",
                "set_default_devices"):
            continue
        fields = [{"key": f["name"], "label": f["name"], "required": bool(f["required"]),
                   "description": ((f.get("description") or f["name"]) + " (" + f["type"] + ")")[:200]}
                  for f in a.get("args", [])]
        if a["mode"] == "raw":
            from zalo_pc_app import zca_api
            built = a["name"] in zca_api._RAW_BUILDERS            # app tự dựng được params từ các trường ở trên (vd. dịch)
            fields.append({"key": "params", "label": "params", "required": not built,
                           "description": ("Tuỳ chọn: JSON nguyên khối nếu muốn tự dựng; bỏ trống thì app dựng từ các trường ở trên."
                                           if built else "JSON đúng như zca-js gửi (API này có biểu thức phức tạp)."),
                           "selector": {"object": None}})
        if a["danger"]:
            fields.append({"key": "confirm", "label": "confirm", "required": False,
                           "description": "Đặt true để xác nhận thao tác nguy hiểm.",
                           "selector": {"boolean": None}})
        label = a["name"] + (" — " + a["summary"] if a.get("summary") else "")
        if a["mode"] == "manual":
            label += " (chưa tự động: %s)" % a.get("reason", "")
        extras.append({"name": name, "no": None, "kind": "zca", "action": name,
                       "group": "zca_" + a["domain"], "label": label[:240],
                       "thread": "none", "danger": a["danger"], "fields": fields})
    return extras



def main():
    cat = S.build_catalog()["services"]
    seen, out = set(), []
    for s in cat:
        no = s.get("addon_no")
        if no is None or no in seen:
            continue
        seen.add(no)
        name = s["addon"]
        st = s["status"]
        if st == "supported":
            kind, fields = "svc", [(f["key"], f.get("label", f["key"]),
                                    bool(f.get("required")))
                                   for f in s["fields"]]
        elif st == "chat":
            kind, fields = "chat", CHAT_FIELDS[name]
        elif st == "view":
            kind, fields = "view", []
        else:
            kind, fields = "acct", ACCT[name]
        out.append({"name": name, "no": no, "kind": kind,
                    "action": s.get("action"), "group": s["group"],
                    "label": s["label"], "thread": s["thread"],
                    "danger": bool(s.get("danger")),
                    "fields": [{"key": k, "label": l, "required": r}
                               for k, l, r in fields]})
    out.sort(key=lambda x: x["no"])
    assert len(out) == 96, len(out)
    # Gui sticker theo TU KHOA: tich hop HA tim (search_sticker) roi gui, nen sticker_id khong con bat buoc.
    for e in out:
        if e["name"] == "send_sticker":
            for f in e["fields"]:
                if f["key"] == "sticker_id":
                    f["required"] = False
            e["fields"] += [{"key": "keyword", "label": "Từ khoá sticker", "required": False},
                            {"key": "pick", "label": "Chọn kết quả", "required": False}]
    # Op co that trong app nhung nam ngoai 96 dich vu zalobot: van la service HA.
    have = {e["name"] for e in out} | {e["action"] for e in out if e["action"]}
    for action, spec in S.OPS.items():
        if action in have or action == "keepAlive":
            continue
        out.append({"name": action, "no": None, "kind": "svc", "action": action,
                    "group": spec["group"], "label": spec["label"],
                    "thread": spec["thread"], "danger": bool(spec["danger"]),
                    "fields": [{"key": f["key"], "label": f.get("label", f["key"]),
                                "required": bool(f.get("required"))}
                               for f in spec["fields"]]})
    out.extend(_zca_extras(out))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    # services.yaml dung yaml.safe_dump tu mot dict: KHONG BAO GIO sinh ra
    # `fields:` rong (null) — HA bo CA tep neu mot service co `fields: null`
    # ("expected a mapping at 'x.fields'"), khien moi service mat truong nhap.
    import yaml
    meta = _load_meta()
    doc = {}
    for e in out:
        sm = meta.get(e["name"]) or {}
        desc = sm.get("description") or e["label"]
        if e["danger"]:
            desc += " (không hoàn tác được)"
        fields = {"entry_id": ENTRY_ID_FIELD}
        if e["thread"] != "none" and e["kind"] in ("svc", "chat"):
            fields["thread_id"] = {
                "name": "Mã hội thoại (threadId)",
                "description": "UserId (1-1) hoặc GroupId (nhóm).",
                "required": True, "example": "5841349563795164131",
                "selector": {"text": None}}
            fields["type"] = {
                "name": "Loại hội thoại",
                "description": "user = 1-1, group = nhóm.",
                "default": "user",
                "selector": {"select": {"options": ["user", "group"]}}}
        for f in e["fields"]:
            fields[f["key"]] = _field_entry(e["name"], f, meta)
            sel = SELECTOR_OVERRIDES.get((e["name"], f["key"]))
            if sel:
                fields[f["key"]]["selector"] = sel
        doc[e["name"]] = {"name": e["label"].split(" — ")[0]
                          if e["kind"] == "zca" else e["label"],
                          "description": desc,
                          "fields": fields}
    extra = yaml.safe_load(EXTRA_YAML)
    for name, svc in extra.items():
        flds = svc.get("fields") or {}
        svc["fields"] = {"entry_id": ENTRY_ID_FIELD, **flds}
        doc[name] = svc
    with open(os.path.join(OUT, "services.yaml"), "w", encoding="utf-8") as f:
        f.write("# SINH TU DONG bang zalo/zalo-pc-app/tools/gen_ha_catalog.py — dung sua tay.\n")
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=100)
    print("ok: %d service" % len(out))


EXTRA_YAML = '''make_call:
  name: Gọi điện
  description: Gọi thoại hoặc video cho một người hay nhóm.
  fields:
    thread_id:
      name: Mã hội thoại (threadId)
      description: UserId (gọi 1-1) hoặc GroupId (gọi nhóm).
      required: true
      example: "6643404425553198601"
      selector:
        text: null
    type:
      name: Loại cuộc gọi
      description: user = thoại 1-1, video = video 1-1, group = nhóm.
      default: user
      selector:
        select:
          options:
          - user
          - video
          - group
    peer_name:
      name: Tên hiển thị
      description: Tên người nhận hiện trong nhật ký cuộc gọi (bỏ trống = dùng mã).
      selector:
        text: null
    srtp:
      name: Chế độ mã hoá tiếng
      description: sess = khoá lấy từ sessId của cuộc gọi (mặc định, đã chạy thật); off = RTP trần; key = khoá tự sinh (thử). Bỏ trống = app tự chọn theo kết quả thật.
      selector:
        select:
          options:
          - sess
          - 'off'
          - key
    extend_profile:
      name: Hồ sơ tín hiệu cuộc gọi
      description: native = giống engine Zalo-Linux (mặc định, đã chạy thật với điện thoại); pc = bộ cũ của app (newZrtc=0); zca = bộ của zca-js.
      default: native
      selector:
        select:
          options:
          - native
          - pc
          - zca
    speaker:
      name: Loa (ghi đè mặc định)
      description: media_player phát tiếng bên kia. Bỏ trống = loa mặc định (thực thể "Loa mặc định"); để rỗng = không phát loa cho cuộc này.
      selector:
        entity:
          domain: media_player
    volume:
      name: Âm lượng loa trong cuộc gọi (ghi đè mặc định)
      description: 1-100 % — đặt âm lượng loa khi nghe máy rồi trả lại mức cũ khi cuộc gọi kết thúc. Bỏ trống = dùng «Âm lượng cuộc gọi» mặc định trên thiết bị; 0 = giữ nguyên âm lượng loa.
      selector:
        number:
          min: 0
          max: 100
          mode: slider
          unit_of_measurement: '%'
    mic:
      name: Mic (ghi đè mặc định)
      description: Camera (lấy tiếng từ stream của nó) hoặc vệ tinh Assist của camera Imou/Dahua hay loa R1. Bỏ trống = mic mặc định; để rỗng = không phát mic cho cuộc này.
      selector:
        entity:
          domain:
          - camera
          - assist_satellite
    mic_url:
      name: Mic từ URL bất kỳ (ghi đè mặc định)
      description: rtsp/rtsps/http/https/rtmp, hoặc luồng PCM của loa R1. Thắng ô Mic.
      selector:
        text: null
    camera:
      name: Camera video (ghi đè mặc định)
      description: Camera HA phát hình lên cuộc gọi video (hoặc khi chuyển thoại sang video). Bỏ trống = camera mặc định; để rỗng = không phát hình cho cuộc này.
      selector:
        entity:
          domain: camera
    connect:
      name: Nối thiết bị nhà khi chuyển máy
      description: never = không nối gì. voice = chỉ loa + mic. always = nối cả camera (thoại thì nâng lên video). Bỏ trống = theo quy tắc của threadID (set_rule); không có quy tắc thì voice nếu lời gọi nêu thiết bị, không thì never.
      selector:
        select:
          options:
          - never
          - voice
          - always
    message:
      name: Thông báo bằng giọng nói
      description: Câu đọc (TTS của HA) ngay khi cuộc gọi được nghe máy. Bỏ trống = không đọc.
      selector:
        text:
          multiline: true
    repeat:
      name: Đọc mấy lần
      description: Số lần đọc thông báo (1-3).
      default: 1
      selector:
        number:
          min: 1
          max: 3
          mode: box
    ai:
      name: AI nói chuyện trong cuộc gọi
      description: Sau thông báo (nếu có), nghe người bên kia nói rồi trả lời bằng AI (Assist pipeline của HA - STT, trợ lý, TTS) tới khi họ cúp, im lặng quá lâu hoặc 10 phút.
      default: false
      selector:
        boolean:
    hangup_after:
      name: Cúp máy khi xong
      description: Cúp máy sau khi đọc xong (và sau cuộc trò chuyện AI). Mặc định bật khi có message hoặc ai.
      default: true
      selector:
        boolean:
    greeting:
      name: Câu AI nói đầu tiên
      description: Chỉ khi bật AI mà không có message - AI nói câu này trước rồi mới lắng nghe.
      selector:
        text:
    handover_rule:
      name: AI tự chuyển sang trực tiếp khi…
      description: Điều kiện riêng để AI tự chuyển cuộc gọi sang trực tiếp (nối mic nhà, dừng AI, không cúp máy) và bắn sự kiện zalo_call_ai_handover. Mặc định AI cũng tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được.
      selector:
        text:
    tts_engine:
      name: Giọng đọc (TTS)
      description: Thực thể tts.* dùng để đọc. Bỏ trống = giọng của pipeline.
      selector:
        entity:
          domain: tts
    language:
      name: Ngôn ngữ
      description: Ngôn ngữ cho STT/TTS (ví dụ vi). Bỏ trống = của pipeline / HA.
      selector:
        text:
    pipeline:
      name: Assist pipeline (STT, TTS, trợ lý)
      description: Pipeline cho AI trong cuộc gọi này. ai=true bắt buộc có pipeline hoặc agent (hoặc quy tắc cho threadID) — không tự dùng pipeline ưu tiên vì nó có quyền thiết bị nhà.
      selector:
        assist_pipeline:
    agent:
      name: Trợ lý hội thoại (agent)
      description: Dùng riêng trợ lý này thay trợ lý của pipeline (nên là trợ lý KHÔNG có quyền thiết bị khi người gọi là người lạ).
      selector:
        conversation_agent:
answer_call:
  name: Nghe máy
  description: Nghe cuộc gọi đến (nối loa/mic đã chọn).
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để nghe cuộc gọi đến hiện tại.
      selector:
        text: null
    speaker:
      name: Loa (ghi đè mặc định)
      description: media_player phát tiếng bên kia. Bỏ trống = loa mặc định (thực thể "Loa mặc định"); để rỗng = không phát loa cho cuộc này.
      selector:
        entity:
          domain: media_player
    volume:
      name: Âm lượng loa trong cuộc gọi (ghi đè mặc định)
      description: 1-100 % — đặt âm lượng loa khi nghe máy rồi trả lại mức cũ khi cuộc gọi kết thúc. Bỏ trống = dùng «Âm lượng cuộc gọi» mặc định trên thiết bị; 0 = giữ nguyên âm lượng loa.
      selector:
        number:
          min: 0
          max: 100
          mode: slider
          unit_of_measurement: '%'
    mic:
      name: Mic (ghi đè mặc định)
      description: Camera (lấy tiếng từ stream của nó) hoặc vệ tinh Assist của camera Imou/Dahua hay loa R1. Bỏ trống = mic mặc định; để rỗng = không phát mic cho cuộc này.
      selector:
        entity:
          domain:
          - camera
          - assist_satellite
    mic_url:
      name: Mic từ URL bất kỳ (ghi đè mặc định)
      description: rtsp/rtsps/http/https/rtmp, hoặc luồng PCM của loa R1. Thắng ô Mic.
      selector:
        text: null
    camera:
      name: Camera video (ghi đè mặc định)
      description: Camera HA phát hình lên cuộc gọi video (hoặc khi chuyển thoại sang video). Bỏ trống = camera mặc định; để rỗng = không phát hình cho cuộc này.
      selector:
        entity:
          domain: camera
    connect:
      name: Nối thiết bị nhà khi chuyển máy
      description: never = không nối gì. voice = chỉ loa + mic. always = nối cả camera (thoại thì nâng lên video). Bỏ trống = theo quy tắc của threadID (set_rule); không có quy tắc thì voice nếu lời gọi nêu thiết bị, không thì never.
      selector:
        select:
          options:
          - never
          - voice
          - always
    message:
      name: Thông báo bằng giọng nói
      description: Câu đọc (TTS của HA) ngay khi cuộc gọi được nghe máy. Bỏ trống = không đọc.
      selector:
        text:
          multiline: true
    repeat:
      name: Đọc mấy lần
      description: Số lần đọc thông báo (1-3).
      default: 1
      selector:
        number:
          min: 1
          max: 3
          mode: box
    ai:
      name: AI nói chuyện trong cuộc gọi
      description: Sau thông báo (nếu có), nghe người bên kia nói rồi trả lời bằng AI (Assist pipeline của HA - STT, trợ lý, TTS) tới khi họ cúp, im lặng quá lâu hoặc 10 phút.
      default: false
      selector:
        boolean:
    hangup_after:
      name: Cúp máy khi xong
      description: Cúp máy sau khi đọc xong (và sau cuộc trò chuyện AI). Mặc định bật khi có message hoặc ai.
      default: true
      selector:
        boolean:
    greeting:
      name: Câu AI nói đầu tiên
      description: Chỉ khi bật AI mà không có message - AI nói câu này trước rồi mới lắng nghe.
      selector:
        text:
    handover_rule:
      name: AI tự chuyển sang trực tiếp khi…
      description: Điều kiện riêng để AI tự chuyển cuộc gọi sang trực tiếp (nối mic nhà, dừng AI, không cúp máy) và bắn sự kiện zalo_call_ai_handover. Mặc định AI cũng tự chuyển khi người gọi muốn gặp người trong nhà, có việc khẩn cấp hoặc AI không giúp được.
      selector:
        text:
    tts_engine:
      name: Giọng đọc (TTS)
      description: Thực thể tts.* dùng để đọc. Bỏ trống = giọng của pipeline.
      selector:
        entity:
          domain: tts
    language:
      name: Ngôn ngữ
      description: Ngôn ngữ cho STT/TTS (ví dụ vi). Bỏ trống = của pipeline / HA.
      selector:
        text:
    pipeline:
      name: Assist pipeline (STT, TTS, trợ lý)
      description: Pipeline cho AI trong cuộc gọi này. ai=true bắt buộc có pipeline hoặc agent (hoặc quy tắc cho threadID) — không tự dùng pipeline ưu tiên vì nó có quyền thiết bị nhà.
      selector:
        assist_pipeline:
    agent:
      name: Trợ lý hội thoại (agent)
      description: Dùng riêng trợ lý này thay trợ lý của pipeline (nên là trợ lý KHÔNG có quyền thiết bị khi người gọi là người lạ).
      selector:
        conversation_agent:
reject_call:
  name: Từ chối cuộc gọi đến
  description: Từ chối cuộc gọi đang đổ chuông.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để từ chối cuộc gọi đến hiện tại.
      selector:
        text: null
voice_to_text:
  name: Chuyển giọng nói thành văn bản (Zalo AI)
  description: Gửi một tin nhắn thoại (URL tệp .aac/.mp3/.m4a trên máy chủ Zalo) cho Zalo AI và trả về văn bản. Chỉ dùng cho tin nhắn thoại, không phải mic trực tiếp. Kết quả cũng bắn sự kiện zalo_call_voice_to_text.
  fields:
    url:
      name: URL tệp ghi âm
      description: Đường dẫn tin nhắn thoại trên máy chủ Zalo (lấy từ sự kiện tin nhắn thoại).
      required: true
      selector:
        text: null
    wait:
      name: Chờ tối đa (giây)
      description: Zalo AI trả kết quả bất đồng bộ; chờ tối đa ngần này giây (0 = không chờ, lấy bằng sự kiện).
      default: 25
      selector:
        number:
          min: 0
          max: 60
          mode: box
upgrade_to_video:
  name: Chuyển cuộc gọi thoại sang video
  description: Khi đang gọi thoại, xin bên kia chuyển sang video rồi phát camera đã chọn (hoặc camera mặc định).
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để dùng cuộc gọi đang diễn ra.
      selector:
        text: null
    camera:
      name: Camera
      description: Camera HA phát hình. Bỏ trống = camera mặc định.
      selector:
        entity:
          domain: camera
    camera_url:
      name: Camera từ URL
      description: rtsp/rtsps/http/https/rtmp (thắng ô Camera).
      selector:
        text: null
start_call_video:
  name: Bật hình trong cuộc gọi
  description: Phát hình camera lên cuộc gọi đang diễn ra (không xin chuyển loại cuộc gọi).
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để dùng cuộc gọi đang diễn ra.
      selector:
        text: null
    camera:
      name: Camera
      description: Camera HA phát hình. Bỏ trống = camera mặc định.
      selector:
        entity:
          domain: camera
    camera_url:
      name: Camera từ URL
      description: rtsp/rtsps/http/https/rtmp (thắng ô Camera).
      selector:
        text: null
stop_call_video:
  name: Tắt hình trong cuộc gọi
  description: Dừng phát hình camera lên cuộc gọi đang diễn ra.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để dùng cuộc gọi đang diễn ra.
      selector:
        text: null
start_call_mic:
  name: Bật mic trong cuộc gọi
  description: Phát tiếng từ camera, vệ tinh Assist (camera Imou/Dahua, loa R1) hoặc URL lên cuộc gọi đang diễn ra.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để dùng cuộc gọi đang diễn ra.
      selector:
        text: null
    mic:
      name: Mic
      description: Camera hoặc vệ tinh Assist. Bỏ trống = mic mặc định.
      selector:
        entity:
          domain:
          - camera
          - assist_satellite
    mic_url:
      name: Mic từ URL
      description: rtsp/rtsps/http/https/rtmp, hoặc luồng PCM của loa R1 (thắng ô Mic).
      selector:
        text: null
stop_call_mic:
  name: Tắt mic trong cuộc gọi
  description: Dừng phát tiếng lên cuộc gọi đang diễn ra.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để dùng cuộc gọi đang diễn ra.
      selector:
        text: null
set_default_devices:
  name: Đặt thiết bị mặc định
  description: Đặt loa, mic, camera và chế độ tự động mặc định (giống các thực thể trên thiết bị Zalo Call). Trường nào bỏ trống thì giữ nguyên; để rỗng thì bỏ thiết bị đó.
  fields:
    speaker:
      name: Loa mặc định
      description: Loa (media_player) phát tiếng bên kia.
      selector:
        entity:
          domain: media_player
    mic:
      name: Mic mặc định
      description: Camera hoặc vệ tinh Assist (camera Imou/Dahua, loa R1) lấy tiếng.
      selector:
        entity:
          domain:
          - camera
          - assist_satellite
    mic_url:
      name: Mic mặc định từ URL
      description: rtsp/rtsps/http/https/rtmp, hoặc luồng PCM của loa R1 (thắng ô Mic).
      selector:
        text: null
    camera:
      name: Camera mặc định
      description: Camera HA phát hình lên cuộc gọi video.
      selector:
        entity:
          domain: camera
    auto_mic:
      name: Tự phát mic khi nghe máy
      description: Bật thì tự phát mic mặc định ngay khi cuộc gọi được nghe máy.
      selector:
        boolean: null
    auto_video:
      name: Tự đồng ý khi bên kia xin gọi video
      description: Bật thì khi bên kia xin chuyển sang video sẽ tự đồng ý và phát camera mặc định.
      selector:
        boolean: null
    echo_guard:
      name: Chống vọng
      description: auto = chỉ chặn mic khi mic và loa là cùng một thiết bị (ví dụ R1); on = luôn chặn mic khi loa đang phát tiếng bên kia; duplex = song công, nói chen được (loa R1 dùng khử vọng của nó); off = tắt.
      selector:
        select:
          options:
          - auto
          - 'on'
          - duplex
          - 'off'
    auto_video_delay:
      name: Chờ trước khi tự đồng ý (giây)
      description: Số giây chờ rồi mới tự đồng ý lời xin chuyển sang video (0 = đồng ý ngay; chỉ áp dụng khi cuộc gọi còn đang nói).
      selector:
        number:
          min: 0
          max: 120
          mode: box
          unit_of_measurement: s
    call_volume:
      name: Âm lượng cuộc gọi mặc định
      description: 1-100 % — âm lượng loa đặt khi nghe máy rồi trả lại khi cuộc gọi kết thúc; 0 = giữ nguyên âm lượng loa.
      selector:
        number:
          min: 0
          max: 100
          mode: slider
          unit_of_measurement: '%'
say_in_call:
  name: Đọc lên cuộc gọi (TTS)
  description: Đọc một câu bằng TTS của HA lên cuộc gọi đang nói.
  fields:
    message:
      name: Nội dung
      description: Câu cần đọc.
      required: true
      selector:
        text:
          multiline: true
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống = cuộc gọi đang nói hiện tại.
      selector:
        text:
    tts_engine:
      name: Giọng đọc (TTS)
      description: Thực thể tts.*; bỏ trống = mặc định của HA.
      selector:
        entity:
          domain: tts
    language:
      name: Ngôn ngữ
      description: Ví dụ vi.
      selector:
        text:
    wait:
      name: Chờ đọc xong
      description: Chờ đọc xong mới trả về.
      default: true
      selector:
        boolean:
take_over_call:
  name: Tiếp quản cuộc gọi
  description: Người thật tiếp quản cuộc gọi đang do AI hoặc thông báo giữ - dừng AI và trả mic nhà về nguồn mặc định (loa/mic nhà đã nối từ lúc nghe máy).
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống = cuộc gọi đang nói hiện tại.
      selector:
        text:
set_rule:
  name: Đặt quy tắc cuộc gọi đến / tin nhắn
  description: >-
    Quy tắc xử lý theo threadID (người hoặc nhóm), theo người trong danh bạ, theo người lạ hoặc theo mọi nhóm. KHÔNG CÓ QUY TẮC = KHÔNG LÀM GÌ
    (chỉ đổ chuông, tin nhắn không đi đâu). Quy tắc theo threadID thay hẳn quy tắc nhóm. Chưa biết quen hay lạ (danh bạ lỗi) thì chỉ quy tắc
    theo threadID được áp. Trường nào không nêu thì giữ như cũ; quy tắc mới mặc định TẮT hết, không nối thiết bị nhà.
  fields:
    scope:
      name: Áp cho
      description: thread = một threadID (cần thread_id) | groups = mọi nhóm | contacts = người trong danh bạ | strangers = người lạ.
      required: true
      selector:
        select:
          options:
          - thread
          - groups
          - contacts
          - strangers
    thread_id:
      name: ThreadID (gõ tay)
      description: ID Zalo của người hoặc nhóm (chỉ khi scope = thread). Lấy danh sách bằng dịch vụ list_contacts.
      example: "6643404425553198601"
      selector:
        text:
    name:
      name: Tên ghi chú
      description: Tên ghi chú cho quy tắc.
      selector:
        text:
    answer:
      name: Tự nghe máy
      description: Cuộc gọi 1-1 đến từ người thuộc quy tắc này sẽ được tự nghe sau thời gian chờ.
      selector:
        boolean:
    answer_delay:
      name: Chờ bao lâu rồi nghe máy (giây)
      description: 0-120. Người gọi cúp trước khi hết giờ thì không nghe.
      default: 3
      selector:
        number:
          min: 0
          max: 120
          mode: box
          unit_of_measurement: s
    call_types:
      name: Loại cuộc gọi được nghe
      description: voice, video hoặc cả hai (nhận video CHƯA kiểm trên cuộc gọi thật).
      default:
      - voice
      - video
      selector:
        select:
          multiple: true
          options:
          - voice
          - video
    ai:
      name: Dùng AI trong cuộc gọi
      description: Sau khi nghe máy, AI nghe và trả lời bằng giọng nói (STT, trợ lý, TTS). Cần chọn pipeline hoặc agent.
      selector:
        boolean:
    pipeline:
      name: Assist pipeline (STT, TTS, trợ lý)
      description: Chọn từ danh sách pipeline của HA.
      selector:
        assist_pipeline:
    agent:
      name: Trợ lý hội thoại (agent)
      description: Dùng riêng trợ lý này thay trợ lý của pipeline (nên là trợ lý KHÔNG có quyền thiết bị với người lạ).
      selector:
        conversation_agent:
    greeting:
      name: Câu chào đầu cuộc gọi
      description: Câu AI nói đầu cuộc gọi đến (trống = câu mặc định).
      selector:
        text:
    handover_rule:
      name: AI tự chuyển sang trực tiếp khi…
      description: Điều kiện riêng, ngoài các trường hợp mặc định (muốn gặp người nhà, khẩn cấp, AI không giúp được).
      selector:
        text:
    trusted:
      name: Người tin cậy
      description: Tin cậy thì AI không bị dặn kiểu «người gọi/nhắn chưa xác thực».
      selector:
        boolean:
    reply_ai:
      name: AI trả lời tin nhắn
      description: AI trả lời tin chữ (và tin thoại nếu voice_text) của người/nhóm này. Cần chọn pipeline hoặc agent.
      selector:
        boolean:
    voice_text:
      name: Tin thoại thành chữ (Zalo STT)
      description: Tin thoại 1-1 được Zalo STT chuyển thành chữ và bắn sự kiện zalo_call_voice_text.
      selector:
        boolean:
    connect:
      name: Nối thiết bị nhà
      description: never = không nối gì (mặc định, người lạ không nghe/thấy được nhà). voice = khi chuyển máy chỉ nối loa + mic đã chọn bên dưới. always = nối luôn cả camera (cuộc thoại thì nâng lên video). Chỉ nối thứ ĐÃ CHỌN, chỉ KHI CHUYỂN MÁY (AI giữ máy thì chưa nối); ô trống là không nối, không rơi về mặc định.
      default: never
      selector:
        select:
          options:
          - never
          - voice
          - always
    speaker:
      name: Loa
      description: media_player phát tiếng người gọi (trống = mặc định của set_default_devices).
      selector:
        entity:
          domain: media_player
    mic:
      name: Mic
      description: Camera hoặc vệ tinh Assist lấy tiếng gửi cho người gọi (trống = mặc định).
      selector:
        entity:
          domain:
          - camera
          - assist_satellite
    mic_url:
      name: Mic từ URL
      description: Gõ tay nếu mic không có trong danh sách (rtsp/http/rtmp).
      selector:
        text:
    camera:
      name: Camera
      description: Camera phát hình khi cuộc gọi video (trống = mặc định).
      selector:
        entity:
          domain: camera
    volume:
      name: Âm lượng loa (%)
      description: 0 = giữ nguyên.
      selector:
        number:
          min: 0
          max: 100
          mode: slider
          unit_of_measurement: '%'
    echo_guard:
      name: Chống vọng
      description: Chống vọng khi mic và loa cùng thiết bị.
      selector:
        select:
          options:
          - auto
          - 'on'
          - duplex
          - 'off'
remove_rule:
  name: Xoá quy tắc
  description: Xoá quy tắc của một threadID hoặc của một nhóm (groups / contacts / strangers). Người đó quay về «không làm gì».
  fields:
    scope:
      name: Áp cho
      description: thread / groups / contacts / strangers.
      required: true
      selector:
        select:
          options:
          - thread
          - groups
          - contacts
          - strangers
    thread_id:
      name: ThreadID (gõ tay)
      description: Tuỳ chọn.
      selector:
        text:
list_rules:
  name: Xem các quy tắc
  description: Trả về mọi quy tắc đang đặt (theo threadID, nhóm, danh bạ, người lạ).
list_contacts:
  name: Xem danh bạ Zalo
  description: Trả về bạn bè và nhóm (id, tên) của tài khoản trong app, để lấy threadID cho set_rule.
get_default_devices:
  name: Xem mic/loa/camera mặc định
  description: Trả về cài đặt thiết bị mặc định hiện tại (đặt bằng set_default_devices).
end_call:
  name: Kết thúc cuộc gọi
  description: Kết thúc (hoặc huỷ khi còn đổ chuông) cuộc gọi đang có.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để kết thúc cuộc gọi gần nhất.
      selector:
        text: null

alert_call:
  name: Gọi cảnh báo
  description: Gọi thoại hoặc video để BÁO một cảnh báo - AI đọc nội dung (bằng giọng của pipeline) rồi nối thẳng loa/mic/camera nhà đã cài, không hỏi, không trò chuyện. Chưa cài thiết bị nào thì chỉ đọc rồi cúp (không tự nối gì). Muốn AI trò chuyện thì dùng "Gọi điện" (make_call) với AI.
  fields:
    thread_id:
      name: Mã hội thoại (threadId)
      description: UserId của người nhận cảnh báo (gọi 1-1).
      required: true
      example: "6643404425553198601"
      selector:
        text: null
    message:
      name: Nội dung cảnh báo
      description: Câu AI đọc ngay khi người nhận nghe máy.
      required: true
      selector:
        text:
          multiline: true
    type:
      name: Thoại hay video
      description: user = thoại, video = video. Video thì nối camera nhà (nếu đã cài) sau khi đọc.
      default: user
      selector:
        select:
          options:
          - user
          - video
    pipeline:
      name: Assist pipeline (giọng đọc)
      description: Chọn từ danh sách. Bỏ trống = pipeline của quy tắc threadID này (set_rule); không có thì giọng TTS mặc định của HA.
      selector:
        assist_pipeline: null
    speaker:
      name: Loa nhà (nối sau khi đọc)
      description: media_player phát tiếng người nhận. Bỏ trống = loa của quy tắc threadID (set_rule, khi bật home_devices). Không cài thì KHÔNG nối loa.
      selector:
        entity:
          domain: media_player
    mic:
      name: Mic nhà (nối sau khi đọc)
      description: Camera hoặc vệ tinh Assist lấy tiếng gửi cho người nhận. Bỏ trống = của quy tắc. Không cài thì KHÔNG nối mic.
      selector:
        entity:
          domain:
          - camera
          - assist_satellite
    mic_url:
      name: Mic từ URL (nối sau khi đọc)
      description: rtsp/rtsps/http/https/rtmp hoặc luồng PCM của loa R1. Thắng ô Mic.
      selector:
        text: null
    camera:
      name: Camera video (nối sau khi đọc)
      description: Camera HA phát hình lên cuộc gọi video. Bỏ trống = của quy tắc. Không cài thì KHÔNG gửi hình.
      selector:
        entity:
          domain: camera
    connect:
      name: Nối thiết bị nhà khi chuyển máy
      description: never = không nối gì. voice = chỉ loa + mic. always = nối cả camera (thoại thì nâng lên video). Bỏ trống = theo quy tắc của threadID (set_rule); không có quy tắc thì voice nếu lời gọi nêu thiết bị, không thì never.
      selector:
        select:
          options:
          - never
          - voice
          - always
    volume:
      name: Âm lượng loa trong cuộc gọi
      description: 1-100 % đặt khi nối loa, trả lại mức cũ khi cúp. Bỏ trống = của quy tắc.
      selector:
        number:
          min: 0
          max: 100
          mode: slider
          unit_of_measurement: '%'
    repeat:
      name: Đọc mấy lần
      description: Số lần đọc cảnh báo (1-3).
      default: 1
      selector:
        number:
          min: 1
          max: 3
          mode: box
    tts_engine:
      name: Giọng đọc (TTS) riêng
      description: Thực thể tts.* dùng thay giọng của pipeline. Bỏ trống = giọng của pipeline.
      selector:
        entity:
          domain: tts
    language:
      name: Ngôn ngữ
      description: Ngôn ngữ TTS (ví dụ vi). Bỏ trống = của pipeline / HA.
      selector:
        text:
    peer_name:
      name: Tên hiển thị
      description: Tên người nhận hiện trong nhật ký cuộc gọi (bỏ trống = dùng mã).
      selector:
        text: null
'''

if __name__ == "__main__":
    main()
