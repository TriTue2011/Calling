"""Nhãn nhật ký cuộc gọi `[in|out/voice|video/login=…/call=…]` (14/11/2026): lọc theo hướng, thoại/video, kiểu đăng nhập; nhãn ở CUỐI dòng.
Run: python3 tests/test_call_tags.py"""
import os
import sys
import io
import contextlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import call_log, call_tags, identity_mobile, identity_pc, identity_web, protocol, server  # noqa: E402


def test_tag_axes():
    f = lambda e: call_tags.tag(e, "pc", "web")
    assert f({"direction": "in", "type": "user"}) == "in/voice/login=pc/call=web"
    assert f({"direction": "in", "type": "video"}) == "in/video/login=pc/call=web"
    assert f({"direction": "out", "type": "user"}) == "out/voice/login=pc/call=web"
    assert f({"direction": "out", "type": "video"}) == "out/video/login=pc/call=web"
    assert f({"direction": "out", "type": "group"}).startswith("out/voice/")
    assert f({}) == "in/voice/login=pc/call=web"                         # thiếu trường: mặc định gọi đến/thoại


def test_suffix_only_for_known_calls_and_never_raises():
    known = {"77": {"direction": "out", "type": "video"}}
    s = lambda msg: call_tags.suffix(msg, known.get, "web", "pc")
    assert s("answered call_id=77 source=media") == " [out/video/login=web/call=pc]"
    assert s("answered call_id=99 source=media") == ""                    # chưa có bản ghi: không đoán
    assert s("khong co ma cuoc goi") == ""
    assert call_tags.suffix("call_id=1", lambda _c: 1 / 0, "web", "pc") == ""


def test_call_log_find_returns_copy_newest_first():
    log = call_log.CallLog()
    log.record_start("5", "peer", "t1", "user")
    e = log.find(5)
    assert e["direction"] == "out" and e["call_id"] == "5"
    e["direction"] = "đổi"
    assert log.find("5")["direction"] == "out"                            # bản sao
    assert log.find("404") is None


def test_server_log_line_keeps_prefix_and_appends_tag():
    old_state = server.STATE
    try:
        class S:
            calls = call_log.CallLog()
        S.calls.record_incoming("123", "peer", "t", "video")
        server.STATE = S
        protocol.set_client("pc")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            server._log_call("incoming offer call_id=123 x=1")
            server._log_call("khong call id")
        a, b = buf.getvalue().splitlines()
        assert a.startswith("[call] incoming offer call_id=123 x=1 [in/video/login=pc/call=pc]"), a
        assert b == "[call] khong call id", b
    finally:
        server.STATE = old_state
        protocol.set_client("web")


def test_identity_modules_are_the_single_source():
    assert protocol.CLIENTS["web"] == (identity_web.TYPE, identity_web.VERSION)
    assert protocol.CLIENTS["pc"] == (identity_pc.TYPE, identity_pc.VERSION)
    assert protocol.CALL_CLIENTS["mobile"] == (identity_mobile.TYPE, identity_mobile.VERSION)
    assert identity_pc.USER_AGENT == "ZaloPC-win32-24v693" and identity_web.USER_AGENT == "zalo-pc-qr/1.0"
    protocol.set_client("pc")
    try:
        assert protocol.user_agent() == identity_pc.USER_AGENT
        protocol.set_client("web")
        assert protocol.user_agent() == identity_web.USER_AGENT
    finally:
        protocol.set_client("web")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("ALL CALL TAGS TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
