"""Sync khoi dong cho phien cu (issue 2 — UI bao "sync chua co").

Phien giu tu truoc (session.json khong co poll_msg_urls, co the
thieu ca zpw_enk) phai mo duoc poller nho refresh getLoginInfo luc
khoi dong — chi khi server that su khong cap endpoint thi moi
no_endpoints (can quet QR lai). Cac loi cu duoc pin o day:

  1. UI tinh: app.html viet san cau "kenh nhan tin (sync) chua co"
     (test JS rieng: tests/test_app_js_sync.js) — o day pin phia
     server: /api/status phai noi dung trang thai that.
  2. start_sync cu giu _sync_lock xuyen suot ca refresh mang trong
     khi _refresh lay self.lock, con public_status lay self.lock
     truoc roi moi lay _sync_lock — mot request /api/status chen
     ngang luc refresh la ket ca hai luong vinh vien.
  3. start_sync cu chan o zpw_enk truoc ca khi refresh, va refresh
     khong luu zpw_enk — phien cu thieu enk khong bao gio sua duoc.
  4. Refresh loi bi nuot im (chi in kieu loi) va sync_status gom
     moi thu ve "no_endpoints" — khong phan biet duoc "refresh loi"
     voi "server khong cap endpoint".

Mock/offline hoan toan: khong dang nhap that, khong goi that.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import session as session_mod  # noqa: E402


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base


def kept_state(tmp, poll_urls, enk):
    """AppState voi phien cu da luu: zpw_sek con han, poll URLs /
    zpw_enk tuy theo truong hop (phien truoc a83d1e6 khong co
    poll_msg_urls; phien luu loi co the thieu ca zpw_enk)."""
    state = app_server.AppState(tmp)
    sess = session_mod.new_session("dev-1", "testhost")
    sess.update({
        "uid": "10001", "dkey": "dkey-test",
        "phonenum": "+84000000000",
        "zpw_sek": "sek-test", "zpw_kt": "kt-test",
        "zpw_enk": enk,
        "poll_msg_urls": list(poll_urls),
        "poll_ctl_urls": [],
        "status": session_mod.STATUS_LOGGED_IN,
    })
    state.store.save(sess)
    state.session = sess
    return state


def logininfo_hits(mock):
    return [(q, h) for (p, q, h) in mock.seen
            if p == "/api/login/getLoginInfo"]


def wait_for(fn, timeout=10, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(0.2)
    raise AssertionError("timeout waiting for %s" % what)


def test_kept_session_with_endpoints_starts_no_refresh():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"], TEST_SESSION_KEY)
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        assert state.public_status()["sync"] == "running"
        # Da co endpoint thi KHONG goi getLoginInfo them.
        assert logininfo_hits(mock) == [], mock.seen
        wait_for(lambda: state.inbox.messages_for("user", "20001"),
                 what="tin den vao Inbox")
        state.stop_sync()
    finally:
        mock.stop()


def test_kept_session_without_endpoints_refresh_starts():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(), [], TEST_SESSION_KEY)
        assert state.sync_status() == "no_endpoints"
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        # Refresh da luu endpoints + enk xuong session.json.
        saved = state.store.load()
        assert saved["poll_msg_urls"] == [mock.base + "/lp-msg"], saved
        assert saved["zpw_enk"] == TEST_SESSION_KEY, saved
        assert len(logininfo_hits(mock)) == 1, mock.seen
        wait_for(lambda: state.inbox.messages_for("user", "20001"),
                 what="tin den vao Inbox")
        state.stop_sync()
    finally:
        mock.stop()


def test_kept_session_missing_enk_refresh_repairs():
    # Phien cu thieu zpw_enk: ban cu tra False ngay truoc ca khi
    # refresh (chan o `not sess.get("zpw_enk")`), nen kenh khong
    # bao gio mo duoc. Ban moi refresh truoc, lay enk ve roi mo.
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(), [], "")
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        assert state.session["zpw_enk"] == TEST_SESSION_KEY
        assert state.store.load()["zpw_enk"] == TEST_SESSION_KEY
        state.stop_sync()
    finally:
        mock.stop()


def test_refresh_fails_102_reports_refresh_failed():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        mock.logininfo_mode = "error102"
        state = kept_state(tempfile.mkdtemp(), [], TEST_SESSION_KEY)
        assert state.start_sync() is False
        assert state.sync is None
        # KHONG phai no_endpoints: refresh loi, chua ket luan duoc
        # la server khong cap endpoint — thu lai duoc.
        assert state.sync_status() == "refresh_failed", state.sync_status()
        assert "102" in state.sync_error, state.sync_error
        st = state.public_status()
        assert st["sync"] == "refresh_failed", st
        assert "102" in st["sync_error"], st
        assert state.session["poll_msg_urls"] == []
        # Thu lai sau khi server het loi thi mo duoc (khong ket cung).
        mock.logininfo_mode = "ok"
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        state.stop_sync()
    finally:
        mock.stop()


def test_genuine_no_endpoints_stays_no_endpoints():
    # Server tra getLoginInfo thanh cong nhung khong co zpw_chts_new:
    # luc nay no_endpoints la that — UI moi duoc bao quet QR lai.
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(), [], TEST_SESSION_KEY)
        state._fetch_login_info = lambda grant, d, c: {
            "zpw_enk": TEST_SESSION_KEY, "config": {},
            "dkey": "dkey-test", "poll_msg_urls": [],
            "poll_ctl_urls": [], "poll_msg_timeout": 30,
            "poll_ctl_timeout": 30}
        assert state.start_sync() is False
        assert state.sync_status() == "no_endpoints", state.sync_status()
        assert state.sync_error == "no_endpoints_from_server", \
            state.sync_error
    finally:
        mock.stop()


def test_sync_status_mapping():
    state = app_server.AppState(tempfile.mkdtemp())
    assert state.sync_status() == "logged_out"
    assert state.public_status()["sync"] == "logged_out"
    state.session = {"uid": "10001", "zpw_sek": "sek-test",
                     "zpw_enk": TEST_SESSION_KEY,
                     "poll_msg_urls": ["https://example.invalid/lp"]}
    # Co endpoint nhung poller chua chay.
    assert state.sync_status() == "stopped"
    # Poller bi da: kicked_out, khong phai running.
    state.sync = _FakePoller(kicked_out=True)
    assert state.sync_status() == "kicked_out"
    state.sync = _FakePoller(kicked_out=False)
    assert state.sync_status() == "running"
    state.sync = None
    state.session = {"uid": "10001", "zpw_sek": "sek-test",
                     "zpw_enk": TEST_SESSION_KEY, "poll_msg_urls": []}
    state.sync_error = ""
    assert state.sync_status() == "no_endpoints"


class _FakePoller:
    def __init__(self, kicked_out):
        self.kicked_out = kicked_out


def test_status_not_blocked_by_refresh_in_flight():
    # Hoi quy deadlock khoa cheo (loi 2): start_sync cu giu
    # _sync_lock trong luc refresh (lay self.lock de luu), con
    # public_status giu self.lock roi cho _sync_lock — hai luong
    # ket nhau vinh vien. Ban moi khong giu khoa nao trong luc
    # goi mang, nen /api/status van tra ngay ca khi refresh
    # dang chay cham.
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(), [], TEST_SESSION_KEY)

        def slow_fetch(grant, device_id, computer):
            time.sleep(1.0)
            return {"zpw_enk": TEST_SESSION_KEY,
                    "config": {"zpw_service_map_new": {},
                               "zpw_ws": ""},
                    "dkey": "dkey-test",
                    "poll_msg_urls": [mock.base + "/lp-msg"],
                    "poll_ctl_urls": [mock.base + "/lp-ctl"],
                    "poll_msg_timeout": 30, "poll_ctl_timeout": 30}

        state._fetch_login_info = slow_fetch
        result = {}
        t = threading.Thread(
            target=lambda: result.__setitem__("ok", state.start_sync()),
            daemon=True)
        t.start()
        # Trong luc refresh dang chay (1 giay), status phai tra
        # ngay — moi lan goi deu duoi 2 giay, khong ket.
        for _ in range(5):
            started = time.time()
            st = state.public_status()
            assert time.time() - started < 2.0, "public_status bi ket"
            assert st["sync"] in ("no_endpoints", "refresh_failed",
                                  "running"), st
            time.sleep(0.1)
        t.join(timeout=5)
        assert result.get("ok") is True, result
        assert state.sync_status() == "running"
        state.stop_sync()
    finally:
        mock.stop()


# -- POST /api/sync/retry qua server app that ---------------------------

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


def api_json(method, path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    return api(method, path, data, {"Content-Type": "application/json"})


def login_via_mock():
    from mock_server import TEST_PARAM_KEY
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    status, body = api_json("POST", "/api/qr/new", {})
    assert body["ok"] is True
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = api("GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def test_sync_retry_endpoint():
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-sync-retry-test-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        login_via_mock()
        assert state.sync_status() == "running"
        status, body = api("GET", "/api/status")
        assert status == 200, body
        assert body["sync"] == "running", body
        assert body["sync_error"] == "", body

        # Dung poller roi thu lai qua endpoint: mo lai duoc.
        state.stop_sync()
        assert state.sync_status() == "stopped"
        state._sync_last_retry_at = 0.0
        status, body = api_json("POST", "/api/sync/retry", {})
        assert status == 200, body
        assert body["ok"] is True, body
        assert body["sync"] == "running", body
        assert state.sync_status() == "running"

        # Bam lien ngay sau do: 429 + retry_after (khong doi Zalo).
        status, body = api_json("POST", "/api/sync/retry", {})
        assert status == 429, body
        assert body["ok"] is False, body
        assert 0 < body["retry_after_seconds"] <= 30, body

        # Bi da: endpoint khong thu lai, bao that.
        state.sync.kicked_out = True
        state._sync_last_retry_at = 0.0
        status, body = api_json("POST", "/api/sync/retry", {})
        assert status == 200, body
        assert body["ok"] is False, body
        assert body["sync"] == "kicked_out", body
        state.sync.kicked_out = False
        state.stop_sync()
        httpd.shutdown()
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL SYNC-START TESTS PASSED")
