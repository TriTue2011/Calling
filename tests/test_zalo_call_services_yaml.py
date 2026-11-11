"""services.yaml cua tich hop zalo_call phai doc duoc voi HA.

HA bo CA tep neu mot service co `fields:` rong/null ("expected a mapping at
'x.fields'") — khi do MOI service mat truong nhap tren giao dien. Test nay
giu cho bo sinh (zalo/zalo-pc-app/tools/gen_ha_catalog.py) khong tai phat loi do.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMP = os.path.join(HERE, "..", "custom_components", "zalo_call")

try:
    import yaml
except ImportError:                                   # PyYAML chi la cong cu dev
    yaml = None


def _load():
    with open(os.path.join(COMP, "services.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_every_service_has_mapping_fields():
    y = _load()
    bad = [k for k, v in y.items() if not isinstance(v.get("fields"), dict)]
    assert not bad, "fields khong phai mapping: %s" % bad


def test_every_catalog_service_is_declared():
    y = _load()
    with open(os.path.join(COMP, "catalog.json"), encoding="utf-8") as f:
        names = [e["name"] for e in json.load(f)]
    missing = [n for n in names + ["make_call", "answer_call", "reject_call",
                                   "end_call", "voice_to_text", "upgrade_to_video",
                                   "start_call_video", "stop_call_video",
                                   "start_call_mic", "stop_call_mic",
                                   "set_default_devices"] if n not in y]
    assert not missing, missing


def test_every_field_is_described_and_account_selectable():
    y = _load()
    for svc, v in y.items():
        assert "entry_id" in v["fields"], svc
        for fname, f in v["fields"].items():
            assert f.get("description"), (svc, fname)
            assert isinstance(f.get("selector"), dict), (svc, fname)


def test_every_zca_service_routes_to_an_app_api():
    """Moi service kind `zca` cua HA phai goi duoc mot API co that trong app
    (POST /api/svc/<action> -> zca_api.registry), neu khong HA co service chet."""
    sys.path.insert(0, os.path.join(HERE, "..", "zalo", "zalo-pc-app"))
    from zalo_pc_app import zca_api, services as S
    with open(os.path.join(COMP, "catalog.json"), encoding="utf-8") as f:
        cat = json.load(f)
    zca = [e for e in cat if e["kind"] == "zca"]
    assert len(zca) > 200, len(zca)
    for e in zca:
        assert zca_api.registry().get(e["action"]) is not None, e["action"]
        assert e["action"] not in S.OPS, e["action"]      # khong de len 96 dich vu PC
    # tong: 96 dich vu PC + API zca con lai = du 333 API cua zca-js
    pc_names = {e["name"] for e in cat if e["kind"] != "zca"}
    covered = {a["name"] for a in zca_api.catalog()["apis"]
               if zca_api._snake(a["name"]) in pc_names
               or zca_api._snake(a["name"]) in {x["action"] for x in zca}}
    assert len(covered) >= 300, len(covered)


if __name__ == "__main__":
    if yaml is None:
        print("SKIP: can PyYAML")
        sys.exit(0)
    for _n, _f in list(globals().items()):
        if _n.startswith("test_"):
            _f()
            print("PASS", _n)
    print("ALL SERVICES.YAML TESTS PASSED")


# Dich vu goi / AI / canh bao / quy tac: TEN o va nhan o chon phai de hieu - khong dung thuat ngu ky thuat lam ten (gen_ha_catalog + ha_plain_words).
_FRIENDLY = ("make_call", "answer_call", "alert_call", "set_rule", "remove_rule", "take_over_call", "list_rules", "list_contacts")
_JARGON = ("threadid", "pipeline", "agent", "stt", "tts", "handover", "ghi đè", "ghi de", "stream", "rtp", "sessid", "srtp ", "webhook")


def _visible_texts(svc):
    yield svc["name"]
    for f in svc.get("fields", {}).values():
        yield f.get("name", "")
        sel = (f.get("selector") or {}).get("select") or {}
        for o in sel.get("options") or []:
            if isinstance(o, dict):
                yield o.get("label", "")


def test_call_services_use_plain_words_in_names_and_option_labels():
    y = _load()
    bad = [(k, t) for k in _FRIENDLY for t in _visible_texts(y[k]) if any(j in t.lower() for j in _JARGON)]
    assert not bad, "ten/nhan co thuat ngu kho hieu: %s" % bad


def test_connect_is_tick_boxes_mic_speaker_camera_ai_with_labels_in_every_call_service():
    y = _load()
    for k in ("make_call", "answer_call", "alert_call", "set_rule"):
        sel = y[k]["fields"]["connect"]["selector"]["select"]
        assert sel["multiple"] is True and [o["value"] for o in sel["options"]] == ["mic", "speaker", "camera", "ai"], k
        assert all(o["label"] for o in sel["options"])
    assert "after" in y["alert_call"]["fields"] and "type" in y["make_call"]["fields"] and "default" not in y["make_call"]["fields"]["type"]
    for f in ("announce", "announce_to", "announce_text"):
        assert f in y["set_rule"]["fields"]
