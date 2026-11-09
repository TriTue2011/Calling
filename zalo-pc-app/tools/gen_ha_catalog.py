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
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    lines = ["# SINH TU DONG bang zalo-pc-app/tools/gen_ha_catalog.py — dung sua tay.\n"]
    for e in out:
        lines.append("%s:\n" % e["name"])
        lines.append("  name: %s\n" % json.dumps(e["label"], ensure_ascii=False))
        desc = e["label"] + (" (không hoàn tác được)" if e["danger"] else "")
        lines.append("  description: %s\n" % json.dumps(desc, ensure_ascii=False))
        lines.append("  fields:\n")
        if e["thread"] != "none" and e["kind"] in ("svc", "chat"):
            lines.append("    thread_id:\n      name: Mã hội thoại (threadId)\n"
                         "      description: UserId (1-1) hoặc GroupId (nhóm).\n"
                         "      required: true\n      selector:\n        text:\n")
            lines.append("    type:\n      name: Loại hội thoại\n"
                         "      description: user = 1-1, group = nhóm.\n"
                         "      default: user\n      selector:\n        select:\n"
                         "          options: [user, group]\n")
        for f in e["fields"]:
            lines.append("    %s:\n      name: %s\n      required: %s\n"
                         "      selector:\n        text:\n"
                         % (f["key"], json.dumps(f["label"], ensure_ascii=False),
                            "true" if f["required"] else "false"))
        if not e["fields"] and (e["thread"] == "none" or e["kind"] not in ("svc", "chat")):
            lines[-1] = lines[-1]  # service khong tham so
    # service rieng cua tich hop (cuoc goi)
    lines.append(EXTRA_YAML)
    with open(os.path.join(OUT, "services.yaml"), "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print("ok: %d service" % len(out))


EXTRA_YAML = '''make_call:
  name: Gọi điện
  description: Gọi thoại hoặc video cho một người hay nhóm.
  fields:
    thread_id:
      name: Mã hội thoại (threadId)
      required: true
      selector:
        text:
    type:
      name: Loại cuộc gọi
      description: user = thoại 1-1, video = video 1-1, group = nhóm.
      default: user
      selector:
        select:
          options: [user, video, group]
    peer_name:
      name: Tên hiển thị
      selector:
        text:
end_call:
  name: Kết thúc cuộc gọi
  description: Kết thúc (hoặc huỷ khi còn đổ chuông) cuộc gọi đang có.
  fields:
    call_id:
      name: Mã cuộc gọi
      description: Bỏ trống để kết thúc cuộc gọi gần nhất.
      selector:
        text:
'''

if __name__ == "__main__":
    main()
