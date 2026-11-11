"""Sinh TÀI LIỆU dịch vụ của tích hợp zalo_call từ chính services.yaml (nguồn duy nhất, không bao giờ lệch):

  * docs/DICH-VU.md      — MỌI dịch vụ: mô tả, mã YAML đủ mọi ô, bảng các ô, giải thích từng lựa chọn của từng ô chọn;
  * README.md            — hai khối giữa cặp dấu ``<!-- DICH-VU:LOI:BEGIN/END -->`` (dịch vụ cuộc gọi, AI, cảnh báo, quy tắc, đủ mã và giải thích)
                           và ``<!-- DICH-VU:CHI-MUC:BEGIN/END -->`` (bảng chỉ mục mọi dịch vụ).

Chạy từ zalo/zalo-pc-app:  python3 tools/gen_service_docs.py   (sau khi chạy gen_ha_catalog.py).
Test ``tests/test_zalo_call_docs.py`` so tài liệu với kết quả sinh ra: sửa services.yaml mà quên chạy lại bộ này sẽ báo lỗi."""
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
COMP = os.path.join(REPO, "custom_components", "zalo_call")
sys.path.insert(0, HERE)

import ha_option_notes  # noqa: E402

CORE_CALL = ["make_call", "alert_call", "answer_call", "reject_call", "end_call", "say_in_call", "take_over_call", "upgrade_to_video", "start_call_video",
             "stop_call_video", "start_call_mic", "stop_call_mic", "set_default_devices", "get_default_devices"]
CORE_RULE = ["set_rule", "remove_rule", "list_rules", "list_contacts"]
GROUP_TITLES = {
    "tin_nhan": "Tin nhắn", "khac": "Tài khoản và webhook", "ho_so": "Hồ sơ và bạn bè", "nhom": "Nhóm", "sticker": "Sticker", "nhac": "Nhắc hẹn",
    "hoi_thoai": "Hội thoại", "nhan": "Nhãn và «đang nhập»", "zca_auth": "Phiên và xác thực (nâng cao)", "zca_chat": "Chat (nâng cao)",
    "zca_group": "Nhóm (nâng cao)", "zca_friend": "Bạn bè (nâng cao)", "zca_profile": "Hồ sơ (nâng cao)", "zca_sync": "Đồng bộ (nâng cao)",
    "zca_zcloud": "Zalo Cloud", "zca_call": "Cuộc gọi theo thư viện zca-js (nâng cao)", "zca_media": "Phương tiện", "zca_sticker": "Sticker (nâng cao)",
    "zca_board": "Ghi chú, bình chọn, việc cần làm", "zca_business": "Zalo Business (OA)",
}
BEGIN = "<!-- DICH-VU:%s:BEGIN -->"
END = "<!-- DICH-VU:%s:END -->"


def load():
    with open(os.path.join(COMP, "services.yaml"), encoding="utf-8") as fh:
        services = yaml.safe_load(fh)
    with open(os.path.join(COMP, "catalog.json"), encoding="utf-8") as fh:
        catalog = {e["name"]: e for e in json.load(fh)}
    return services, catalog


def _one_line(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _cell(text) -> str:
    return _one_line(text).replace("|", "\\|")


def _kind(fv) -> str:
    sel = fv.get("selector") or {}
    return next(iter(sel)) if sel else "text"


def _options(fv) -> list:
    return ((fv.get("selector") or {}).get("select") or {}).get("options") or []


def _val(o):
    return o["value"] if isinstance(o, dict) else o


def _scalar(value) -> object:
    """Chuỗi toàn chữ số (1, 0, 3600, -1) viết thành số trong ví dụ; còn lại giữ chuỗi."""
    return int(value) if isinstance(value, str) and re.fullmatch(r"-?\d+", value) and not value.startswith("0") or value == "0" else value


def example(fid, fv):
    kind, sel = _kind(fv), (fv.get("selector") or {})
    if "default" in fv:
        return fv["default"]
    if "example" in fv:
        return fv["example"]
    if kind == "select":
        opts = [_val(o) for o in _options(fv)]
        multi = sel["select"].get("multiple")
        return [_scalar(v) for v in opts[:2]] if multi else _scalar(opts[0])
    if kind == "boolean":
        return False
    if kind == "number":
        n = sel["number"]
        return n.get("min", 0)
    if kind == "entity":
        dom = (sel["entity"] or {}).get("domain") if isinstance(sel["entity"], dict) else None
        dom = dom[0] if isinstance(dom, list) else (dom or "sensor")
        return "%s.vi_du" % dom
    if kind == "assist_pipeline":
        return "Chatgpt"
    if kind == "conversation_agent":
        return "conversation.vi_du"
    if kind == "object":
        return {}
    return "..."


def _yaml_scalar(v) -> str:
    return json.dumps(v, ensure_ascii=False) if not isinstance(v, bool) else ("true" if v else "false")


def render_service(sid, svc, catalog) -> str:
    name, desc = svc.get("name") or sid, _one_line(svc.get("description"))
    fields = {k: v for k, v in (svc.get("fields") or {}).items() if _kind(v) != "config_entry"}
    out = ['<a id="%s"></a>' % sid, "#### %s — `zalo_call.%s`" % (name, sid), ""]
    if (catalog.get(sid) or {}).get("danger"):
        out += ["> ⚠️ **Dịch vụ nguy hiểm**: xoá hoặc đổi dữ liệu thật trên tài khoản Zalo. Kiểm kỹ trước khi cho automation chạy.", ""]
    out += [desc, "", "**Mã dịch vụ** (đủ mọi ô; ô «tuỳ chọn» bỏ đi được):", "", "```yaml", "action: zalo_call.%s" % sid]
    if fields:
        out.append("data:")
        width = max(len("%s: %s" % (k, _yaml_scalar(example(k, v)))) for k, v in fields.items())
        for k, v in fields.items():
            line = "  %s: %s" % (k, _yaml_scalar(example(k, v)))
            out.append("%s  # %s - %s" % (line.ljust(width + 2), "bắt buộc" if v.get("required") else "tuỳ chọn", _cell(v.get("name"))[:60]))
    out += ["```", ""]
    if fields:
        out += ["| Ô | Tên hiển thị | Bắt buộc | Ý nghĩa |", "|---|---|---|---|"]
        for k, v in fields.items():
            out.append("| `%s` | %s | %s | %s |" % (k, _cell(v.get("name")), "có" if v.get("required") else "không", _cell(v.get("description"))))
        out.append("")
    sel_fields = [(k, v) for k, v in fields.items() if _kind(v) == "select"]
    if sel_fields:
        out.append("**Các lựa chọn:**")
        out.append("")
        for k, v in sel_fields:
            multi = v["selector"]["select"].get("multiple")
            out.append("- **%s** (`%s`)%s" % (_cell(v.get("name")), k, " - chọn được nhiều ô cùng lúc" if multi else ""))
            expl = ha_option_notes.explain(sid, k, _options(v))
            for o in _options(v):
                val = str(_val(o))
                out.append("  - `%s`: %s" % (val, expl.get(val, "(chưa có giải thích)")))
        out.append("")
    return "\n".join(out)


def _first_sentence(text, limit=110) -> str:
    t = _one_line(text)
    return (t[:limit].rsplit(" ", 1)[0] + "...") if len(t) > limit else t


def build():
    """{'docs/DICH-VU.md': nội dung, 'loi': khối README dịch vụ cuộc gọi/quy tắc, 'chi_muc': khối README chỉ mục}."""
    services, catalog = load()
    missing = [s for s in CORE_CALL + CORE_RULE if s not in services]
    assert not missing, "dịch vụ lõi không có trong services.yaml: %s" % missing
    core = set(CORE_CALL + CORE_RULE)
    groups = {}                                           # tiêu đề nhóm -> [id dịch vụ]
    groups["Cuộc gọi, AI và cảnh báo"] = list(CORE_CALL)
    groups["Quy tắc cho cuộc gọi đến và tin nhắn"] = list(CORE_RULE)
    for sid in services:
        if sid in core:
            continue
        g = (catalog.get(sid) or {}).get("group")
        groups.setdefault(GROUP_TITLES.get(g, "Khác"), []).append(sid)
    docs = ["# Danh mục dịch vụ Zalo Call", "",
            "> **Tệp này được SINH TỰ ĐỘNG** từ `custom_components/zalo_call/services.yaml` bằng `zalo/zalo-pc-app/tools/gen_service_docs.py`; đừng sửa tay.", "",
            "Mọi dịch vụ gọi bằng `action: zalo_call.<tên>` (Công cụ nhà phát triển → Hành động, hoặc trong automation). Ô `entry_id` có ở mọi dịch vụ "
            "(chọn tài khoản Zalo) và **chỉ cần khi bạn có nhiều tài khoản**, nên các ví dụ bỏ qua. Dịch vụ đánh dấu ⚠️ xoá hoặc đổi dữ liệu thật.",
            "", "Có **%d dịch vụ**. Hướng dẫn các trường hợp dùng cuộc gọi, AI, cảnh báo và quy tắc: xem [README](../README.md).  " % len(services), ""]
    docs.append("## Mục lục")
    docs.append("")
    for title, ids in groups.items():
        docs.append("- **%s** (%d): %s" % (title, len(ids), ", ".join("[`%s`](#%s)" % (i, i) for i in ids)))
    docs.append("")
    for title, ids in groups.items():
        docs += ["## %s" % title, ""]
        for sid in ids:
            docs += [render_service(sid, services[sid], catalog), "---", ""]
    loi = ["### Dịch vụ cuộc gọi, AI và cảnh báo", ""] + [render_service(s, services[s], catalog) + "\n" for s in CORE_CALL] + \
          ["### Dịch vụ quy tắc cho cuộc gọi đến và tin nhắn", ""] + [render_service(s, services[s], catalog) + "\n" for s in CORE_RULE]
    rows = ["| Dịch vụ | Mã | Làm gì |", "|---|---|---|"]
    for title, ids in groups.items():
        rows.append("| **%s** | | |" % title)
        for sid in ids:
            rows.append("| [%s](docs/DICH-VU.md#%s) | `zalo_call.%s` | %s |" % (_cell(services[sid].get("name") or sid), sid, sid,
                                                                                _cell(_first_sentence(services[sid].get("description")))))
    return {"docs/DICH-VU.md": "\n".join(docs).rstrip("\n") + "\n", "loi": "\n".join(loi).rstrip("\n"), "chi_muc": "\n".join(rows)}


def splice(readme: str, tag: str, body: str) -> str:
    b, e = BEGIN % tag, END % tag
    i, j = readme.index(b) + len(b), readme.index(e)
    return readme[:i] + "\n\n" + body + "\n\n" + readme[j:]


def main():
    out = build()
    with open(os.path.join(REPO, "docs", "DICH-VU.md"), "w", encoding="utf-8") as fh:
        fh.write(out["docs/DICH-VU.md"])
    path = os.path.join(REPO, "README.md")
    with open(path, encoding="utf-8") as fh:
        readme = fh.read()
    if BEGIN % "LOI" in readme:
        readme = splice(splice(readme, "LOI", out["loi"]), "CHI-MUC", out["chi_muc"])
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(readme)
    print("ok: %d dịch vụ" % out["chi_muc"].count("`zalo_call."))


if __name__ == "__main__":
    main()
