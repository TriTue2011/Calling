"""Sinh danh muc 96 service cho tich hop HA `zalo_call` tu danh muc cua
chinh app (zalo_pc_app.services.build_catalog) — de services.yaml va
catalog.json KHONG bao gio lech voi app. Chay tu thu muc zalo-pc-app:

    python3 tools/gen_ha_catalog.py

Ghi: ../custom_components/zalo_call/catalog.json va services.yaml.
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
OUT = os.path.join(os.path.dirname(ROOT), "custom_components", "zalo_call")
sys.path.insert(0, ROOT)

from zalo_pc_app import services as S  # noqa: E402

# 11 service gui tin: truong rieng cua tich hop (khong co trong catalog app).
CHAT_FIELDS = {
    "send_message": [("message", "Nội dung tin nhắn", True)],
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


def _field_entry(svc, f, meta):
    m = dict(_lookup(svc, f["key"], meta))
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
        if name in have or name in S.OPS or name in (
                "make_call", "answer_call", "reject_call", "end_call"):
            continue
        fields = [{"key": f["name"], "label": f["name"], "required": bool(f["required"]),
                   "description": ((f.get("description") or f["name"]) + " (" + f["type"] + ")")[:200]}
                  for f in a.get("args", [])]
        if a["mode"] == "raw":
            fields.append({"key": "params", "label": "params", "required": True,
                           "description": "JSON đúng như zca-js gửi (API này có biểu thức phức tạp).",
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
        f.write("# SINH TU DONG bang zalo-pc-app/tools/gen_ha_catalog.py — dung sua tay.\n")
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
      description: auto = tự chọn theo kết quả thật (mặc định); off = RTP trần; key = khoá tự sinh (thử).
      default: auto
      selector:
        select:
          options:
          - auto
          - 'off'
          - key
    speaker:
      name: Loa (ghi đè mặc định)
      description: media_player phát tiếng bên kia. Bỏ trống = dùng loa mặc định, nhập rỗng/không chọn
        = không phát cho cuộc này.
      selector:
        entity:
          domain: media_player
    mic:
      name: Mic từ camera (ghi đè mặc định)
      description: Camera có mic (lấy tiếng từ stream của nó).
      selector:
        entity:
          domain: camera
    mic_url:
      name: Mic từ URL bất kỳ (ghi đè mặc định)
      description: rtsp/rtsps/http/https/rtmp. Thắng ô "Mic từ camera".
      selector:
        text: null
    camera:
      name: Camera video (ghi đè mặc định)
      description: Chỉ ghi nhận; app chưa truyền hình trong cuộc gọi.
      selector:
        entity:
          domain: camera
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
      description: media_player phát tiếng bên kia. Bỏ trống = dùng loa mặc định, nhập rỗng/không chọn
        = không phát cho cuộc này.
      selector:
        entity:
          domain: media_player
    mic:
      name: Mic từ camera (ghi đè mặc định)
      description: Camera có mic (lấy tiếng từ stream của nó).
      selector:
        entity:
          domain: camera
    mic_url:
      name: Mic từ URL bất kỳ (ghi đè mặc định)
      description: rtsp/rtsps/http/https/rtmp. Thắng ô "Mic từ camera".
      selector:
        text: null
    camera:
      name: Camera video (ghi đè mặc định)
      description: Chỉ ghi nhận; app chưa truyền hình trong cuộc gọi.
      selector:
        entity:
          domain: camera
reject_call:
  name: Từ chối cuộc gọi đến
  description: Từ chối cuộc gọi đang đổ chuông.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để từ chối cuộc gọi đến hiện tại.
      selector:
        text: null
end_call:
  name: Kết thúc cuộc gọi
  description: Kết thúc (hoặc huỷ khi còn đổ chuông) cuộc gọi đang có.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để kết thúc cuộc gọi gần nhất.
      selector:
        text: null
'''

if __name__ == "__main__":
    main()
