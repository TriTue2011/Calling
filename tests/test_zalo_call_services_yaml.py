"""services.yaml cua tich hop zalo_call phai doc duoc voi HA.

HA bo CA tep neu mot service co `fields:` rong/null ("expected a mapping at
'x.fields'") — khi do MOI service mat truong nhap tren giao dien. Test nay
giu cho bo sinh (zalo-pc-app/tools/gen_ha_catalog.py) khong tai phat loi do.
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
                                   "end_call"] if n not in y]
    assert not missing, missing


def test_every_field_is_described_and_account_selectable():
    y = _load()
    for svc, v in y.items():
        assert "entry_id" in v["fields"], svc
        for fname, f in v["fields"].items():
            assert f.get("description"), (svc, fname)
            assert isinstance(f.get("selector"), dict), (svc, fname)


if __name__ == "__main__":
    if yaml is None:
        print("SKIP: can PyYAML")
        sys.exit(0)
    for _n, _f in list(globals().items()):
        if _n.startswith("test_"):
            _f()
            print("PASS", _n)
    print("ALL SERVICES.YAML TESTS PASSED")
