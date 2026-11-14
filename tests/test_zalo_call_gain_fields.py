"""Độ to phần mềm mic/loa (mic_gain, speaker_gain) đi từ quy tắc HA tới app (14/11/2026) — logic thuần, không cần Home Assistant.
Nạp riêng từng hàm cần kiểm từ mã nguồn để chạy được cả khi không có HA/pytest-homeassistant.
Run: python3 tests/test_zalo_call_gain_fields.py"""
import ast
import importlib.util
import os
import sys

CC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components", "zalo_call")


def load_rules():
    sys.modules.setdefault("custom_components", type(sys)("custom_components"))
    spec = importlib.util.spec_from_file_location("zc_rules_gain", os.path.join(CC, "rules.py"))
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except ImportError:
        return None
    return m


def pick(path, names, extra=None):
    """Lấy nguyên văn các hàm/hằng `names` từ file mã nguồn (AST) và chạy trong một không gian riêng."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
            or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in names for t in n.targets))]
    ns = {"Any": object, "annotations": None}
    ns.update(extra or {})
    exec(compile(ast.Module(body=keep, type_ignores=[]), path, "exec"), ns)
    return ns


def test_rules_normalize_accepts_clamps_and_rejects_gain():
    rules = load_rules()
    if rules is None:
        print("SKIP: rules.py cần gói Home Assistant")
        return
    base = {"scope": "thread"}
    r = rules.normalize(dict(base, mic_gain=150, speaker_gain="220"))
    assert r["mic_gain"] == 150 and r["speaker_gain"] == 220
    assert rules.normalize(dict(base, mic_gain=999))["mic_gain"] == 300           # trần 300%
    assert rules.normalize(dict(base, mic_gain=-5))["mic_gain"] == 0              # sàn 0 (= giữ nguyên)
    assert rules.normalize(dict(base))["mic_gain"] == 0                           # mặc định giữ nguyên
    try:
        rules.normalize(dict(base, mic_gain="abc"))
    except rules.RuleError:
        pass
    else:
        raise AssertionError("mic_gain rác phải bị từ chối")


def test_connect_parts_carry_their_own_gain_only():
    src = os.path.join(CC, "call_voice.py")
    rules_ns = {"parse_connect": lambda v: [p for p in (v if isinstance(v, list) else [v] if v else [])]}
    ns = pick(src, {"_DEVICE_KEYS", "_PART_KEYS", "devices_for_mode", "rule_devices", "rule_devices_now"}, rules_ns)
    full = {"speaker": "media_player.r1", "mic": "assist_satellite.r1", "camera": "camera.pk", "volume": 20, "mic_gain": 150, "speaker_gain": 200}
    out = ns["rule_devices"](dict(full, connect=["mic"]))
    assert out == {"mic": "assist_satellite.r1", "mic_gain": 150}, out                # chỉ mic được nối: chỉ độ to MIC đi cùng
    out = ns["rule_devices"](dict(full, connect=["speaker"]))
    assert out == {"speaker": "media_player.r1", "volume": 20, "speaker_gain": 200}, out
    out = ns["rule_devices_now"](dict(full, connect_now=["mic", "speaker", "camera"]))
    assert out["mic_gain"] == 150 and out["speaker_gain"] == 200 and out["camera"] == "camera.pk", out
    assert ns["rule_devices"](dict(full, connect=["camera"])) == {"camera": "camera.pk"}    # chỉ camera: không kèm độ to
    assert ns["rule_devices"]({"mic_gain": 150, "connect": ["mic"]}) == {}              # có độ to mà chưa chọn mic: không nối gì


def test_services_and_bridge_know_the_new_fields():
    svc = open(os.path.join(CC, "services.py"), encoding="utf-8").read()
    assert svc.count('vol.Optional("mic_gain")') == 2 and svc.count('vol.Optional("speaker_gain")') == 2     # lược đồ dịch vụ thiết bị + lược đồ quy tắc
    assert '"mic_gain", "speaker_gain")' in svc                                         # khoá cho phép trong _RULE_FIELDS và _explicit_devices
    br = open(os.path.join(CC, "bridge.py"), encoding="utf-8").read()
    assert 'for key, field in (("mic_gain", "mic_url"), ("speaker_gain", "speaker_url"))' in br


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ALL GAIN FIELD TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
