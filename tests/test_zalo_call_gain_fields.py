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


def test_outgoing_call_devices_come_from_the_rule_without_ai_and_only_when_ha_did_not_connect():
    src = os.path.join(CC, "call_voice.py")
    rules = load_rules()
    if rules is None:
        print("SKIP: rules.py cần gói Home Assistant")
        return
    rules_ns = {"parse_connect": rules.parse_connect}                                  # parse_connect THẬT (đổi «voice» thành mic + loa, «ai» thành tất cả)
    ns = pick(src, {"_DEVICE_KEYS", "_PART_KEYS", "devices_for_mode", "rule_devices", "rule_devices_now", "outgoing_devices", "outgoing_should_apply"}, rules_ns)
    od, ap = ns["outgoing_devices"], ns["outgoing_should_apply"]
    house = {"speaker": "media_player.r1_loa", "mic": "assist_satellite.r1", "camera": "camera.go2rtc_phong_khach", "volume": 22, "mic_gain": 150}
    # «nối ngay» + «khi chuyển máy» đều dùng được: người gọi chính là người nói
    out = od(dict(house, connect=["mic"], connect_now=["camera", "speaker"]))
    assert out["mic"] == "assist_satellite.r1" and out["camera"] == "camera.go2rtc_phong_khach" and out["speaker"] == "media_player.r1_loa", out
    assert out["mic_gain"] == 150 and out["volume"] == 22, out                        # độ to đi cùng nhóm thiết bị
    # quy tắc có AI: gọi đi vẫn nối mic + loa thật (không có AI giữ máy)
    out = od(dict(house, ai=True, connect=["ai"], connect_now=[]))
    assert out.get("mic") and out.get("speaker") and "camera" not in out, out
    assert od(dict(house, connect=[], connect_now=[])) == {}                          # quy tắc không cài nối gì: không nối
    assert od({}) == {}
    # chỉ áp cho cuộc gọi 1-1 ĐI chưa có thiết bị
    assert ap("video", "7", set(), False) is True and ap("user", "7", set(), False) is True
    assert ap("group", "7", set(), False) is False                                    # nhóm: không
    assert ap("video", "7", {"7"}, False) is False                                    # cuộc gọi ĐẾN đã có đường nghe máy riêng
    assert ap("video", "7", set(), True) is False                                     # HA (make_call) đã nối thiết bị: không nối lần hai


def test_bridge_has_devices_and_call_voice_wires_outgoing_by_rule():
    cv = open(os.path.join(CC, "call_voice.py"), encoding="utf-8").read()
    assert "rt.bridge.has_devices(cid)" in cv and "_connect_outgoing_by_rule(hass, rt, cid, payload)" in cv
    br = open(os.path.join(CC, "bridge.py"), encoding="utf-8").read()
    assert "def has_devices(self, call_id" in br


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
