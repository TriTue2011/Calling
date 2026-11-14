"""Cảm xúc theo tin (14/11/2026): kho lưu, nhận từ kênh ctrl, route liệt kê cho WebUI.
Run: python3 tests/test_reaction_store.py"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import reaction_store as rs  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def test_store_add_replace_remove_persist_and_thread_isolation():
    d = tempfile.mkdtemp(prefix="zalo-react-")
    path = os.path.join(d, "reactions.json")
    s = rs.ReactionStore(path)
    assert s.add("user", "20001", "m1", "u1", "/-heart") is True
    assert s.add("user", "20001", "m1", "u1", "/-heart") is False                   # trùng: không đổi
    assert s.add("user", "20001", "m1", "u2", ":>") is True
    assert s.add("user", "20001", "m1", "u1", "/-strong") is True                    # u1 đổi biểu tượng
    assert s.add("group", "20001", "m1", "u3", ":o") is True                         # cùng mã nhưng khác loại hội thoại
    assert s.for_thread("user", "20001") == {"m1": {"u1": "/-strong", "u2": ":>"}}
    assert s.for_thread("group", "20001") == {"m1": {"u3": ":o"}}
    s2 = rs.ReactionStore(path)                                                      # nạp lại từ đĩa
    assert s2.for_thread("user", "20001")["m1"]["u2"] == ":>"
    assert s2.add("user", "20001", "m1", "u2", "") is True                           # biểu tượng rỗng = gỡ
    assert "u2" not in s2.for_thread("user", "20001")["m1"]
    assert s2.add("user", "20001", "m1", "u2", "") is False
    for bad in (("", "1", "m", "u", "x"), ("user", "", "m", "u", "x"), ("user", "1", "", "u", "x"), ("user", "1", "m", "", "x")):
        assert s2.add(*bad) is False
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_ctrl_reaction_event_is_stored_and_listed_by_route():
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-react-route-")
    try:
        for mod, names in ((protocol, ("AUTH_DOMAIN", "VOICECALL_DOMAIN", "PROFILE_DOMAIN", "GROUP_DOMAIN")), (chat_mod, ("CHAT_DOMAIN", "FILES_DOMAIN", "GROUP_DOMAIN"))):
            for n in names:
                setattr(mod, n, mock.base)
        app_server.STATE = app_server.AppState(tmp)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        BASE = "http://127.0.0.1:%d" % httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
        api("POST", "/api/qr/new", json.dumps({}).encode(), {"Content-Type": "application/json"})
        deadline, last = time.time() + 20, {}
        while time.time() < deadline:
            _, last = api("GET", "/api/qr/status")
            if last.get("state") == "done":
                break
            time.sleep(0.5)
        assert last.get("state") == "done", last
        st, body = api("GET", "/api/reaction/list?thread_type=user&thread_id=20001")
        assert st == 200 and body["reactions"] == {}, body
        app_server.STATE._on_ctrl_reaction({"threadId": "20001", "msgId": "g1", "uidFrom": "20001", "icon": "/-heart", "type": 0})
        app_server.STATE._on_ctrl_reaction({"threadId": "30001", "msgId": "g9", "uidFrom": "777", "icon": ":>", "type": 1})
        st, body = api("GET", "/api/reaction/list?thread_type=user&thread_id=20001")
        assert body["reactions"] == {"g1": {"20001": "/-heart"}}, body
        st, body = api("GET", "/api/reaction/list?thread_type=group&thread_id=30001")
        assert body["reactions"] == {"g9": {"777": ":>"}}, body
        app_server.STATE._on_ctrl_reaction({"threadId": "20001", "msgId": "g1", "uidFrom": "20001", "icon": "", "type": 0})     # gỡ
        assert api("GET", "/api/reaction/list?thread_type=user&thread_id=20001")[1]["reactions"] == {}
        assert api("GET", "/api/reaction/list?thread_type=xx&thread_id=1")[0] == 400
        httpd.shutdown()
    finally:
        mock.stop()


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
    print("ALL REACTION STORE TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
