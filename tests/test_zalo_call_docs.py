"""Tài liệu dịch vụ (docs/DICH-VU.md và hai khối của README) phải khớp services.yaml, và mọi lựa chọn của mọi ô chọn đều có lời giải thích."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(REPO, "zalo", "zalo-pc-app", "tools"))

import pytest  # noqa: E402

yaml = pytest.importorskip("yaml")
import gen_service_docs as G  # noqa: E402
import ha_option_notes as N  # noqa: E402


def _read(*p):
    with open(os.path.join(REPO, *p), encoding="utf-8") as fh:
        return fh.read()


def test_docs_and_readme_blocks_are_up_to_date_with_services_yaml():
    out = G.build()
    assert _read("docs", "DICH-VU.md") == out["docs/DICH-VU.md"], "docs/DICH-VU.md lệch services.yaml: chạy tools/gen_service_docs.py"
    readme = _read("README.md")
    for tag, key in (("LOI", "loi"), ("CHI-MUC", "chi_muc")):
        b, e = G.BEGIN % tag, G.END % tag
        body = readme[readme.index(b) + len(b):readme.index(e)].strip("\n")
        assert body == out[key], f"khối {tag} của README lệch services.yaml: chạy tools/gen_service_docs.py"


def test_every_option_of_every_select_field_is_explained():
    services, _ = G.load()
    thieu = []
    for sid, svc in services.items():
        for fid, fv in (svc.get("fields") or {}).items():
            opts = G._options(fv)
            if G._kind(fv) != "select":
                continue
            expl = N.explain(sid, fid, opts)
            thieu += [(sid, fid, str(G._val(o))) for o in opts if str(G._val(o)) not in expl]
    assert not thieu, "lựa chọn chưa có giải thích (thêm vào tools/ha_option_notes.py): %s" % thieu[:10]


def test_all_services_are_listed_core_ones_have_full_code_and_links_resolve():
    services, _ = G.load()
    readme, docs = _read("README.md"), _read("docs", "DICH-VU.md")
    for sid in services:
        assert f"`zalo_call.{sid}`" in readme and f'<a id="{sid}"></a>' in docs, sid
    for sid in G.CORE_CALL + G.CORE_RULE:
        assert f"action: zalo_call.{sid}\n" in readme, f"README thiếu mã đầy đủ của {sid}"
    for link in re.findall(r"\]\((docs/[^)#]+)", readme):
        assert os.path.exists(os.path.join(REPO, link)), link
