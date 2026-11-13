"""Chọn kiểu đăng nhập lúc quét QR: «web» (zpw_type 30/ver 695) hay «pc» (24/693)."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import protocol, qr_login  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def _reset():
    protocol.set_client("web")


def test_set_client_changes_common_params_at_call_time():
    _reset()
    assert protocol.common_params() == {"zpw_ver": 695, "zpw_type": 30}
    assert protocol.set_client("pc") == "pc"
    assert protocol.common_params() == {"zpw_ver": 693, "zpw_type": 24} and protocol.client_name() == "pc"
    assert protocol.set_client("khong-co") == "pc"          # tên lạ: giữ nguyên
    assert protocol.set_client(None) == "pc"
    assert protocol.set_client("web") == "web" and protocol.common_params()["zpw_type"] == 30
    _reset()


def _state():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-kind-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    app_server.PARAM_CIPHER_KEY = "TEST_PARAM_KEY_32_CHARS_LONG_XXX"
    return app_server.AppState(tmp)


def _wait(state, want, secs=10):
    end = time.time() + secs
    while time.time() < end and state.qr_state not in want:
        time.sleep(0.05)
    return state.qr_state


def test_qr_with_pc_uses_pc_values_and_saves_client_in_session():
    _reset()
    st = _state()
    seen = {}
    orig = (qr_login.fetch_server_flags, qr_login.fetch_qr, qr_login.wait_scan, qr_login.wait_confirm, st._fetch_login_info)
    try:
        qr_login.fetch_server_flags = lambda *a, **k: (seen.setdefault("flags_client", protocol.client_name()) and {"known": False})
        qr_login.fetch_qr = lambda *a, **k: (seen.setdefault("qr_client", protocol.client_name()) and
                                              {"base64_qr": "AAAA", "qr_timeout": 90, "qr_retry": 1})
        qr_login.wait_scan = lambda *a, **k: {}
        qr_login.wait_confirm = lambda *a, **k: {"uid": "111", "dkey": "d", "phonenum": "84900000000", "zpw_sek": "s", "zpw_kt": "k"}
        st._fetch_login_info = lambda *a, **k: {"zpw_enk": "", "config": {}}
        st.start_sync = lambda *a, **k: None
        assert st.start_qr("pc") is True
        assert _wait(st, ("done", "error")) == "done", st.qr_error
        assert seen == {"flags_client": "pc", "qr_client": "pc"}, seen
        assert st.session["client"] == "pc" and protocol.client_name() == "pc"
        assert st.qr_status()["client"] == "pc"
        saved = json.load(open(os.path.join(os.environ["ZALO_PC_DATA_DIR"], "session.json")))
        assert saved["client"] == "pc"
    finally:
        (qr_login.fetch_server_flags, qr_login.fetch_qr, qr_login.wait_scan, qr_login.wait_confirm, st._fetch_login_info) = orig
        _reset()


def test_failed_qr_restores_previous_client():
    _reset()
    st = _state()
    orig = qr_login.fetch_server_flags
    try:
        def boom(*a, **k):
            assert protocol.client_name() == "pc"           # trong lúc lấy QR đã đặt kiểu pc
            raise RuntimeError("mạng hỏng")
        qr_login.fetch_server_flags = boom
        st.start_qr("pc")
        assert _wait(st, ("error", "done")) == "error"
        time.sleep(0.2)
        assert protocol.client_name() == "web", "QR hỏng phải trả về kiểu cũ"
    finally:
        qr_login.fetch_server_flags = orig
        _reset()


def test_start_qr_without_or_with_bad_client_keeps_current():
    _reset()
    st = _state()
    orig = qr_login.fetch_server_flags
    try:
        qr_login.fetch_server_flags = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dừng"))
        for bad in (None, "", "linux"):
            st.thread = None
            st.start_qr(bad)
            _wait(st, ("error",))
            time.sleep(0.2)
            assert st.qr_client is None and protocol.client_name() == "web", bad
    finally:
        qr_login.fetch_server_flags = orig
        _reset()


def test_session_client_is_applied_on_startup():
    _reset()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-kind2-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    with open(os.path.join(tmp, "session.json"), "w") as f:
        json.dump({"uid": "1", "zpw_sek": "x", "client": "pc", "status": "da_dang_nhap"}, f)
    app_server.AppState(tmp)
    try:
        assert protocol.client_name() == "pc"
    finally:
        _reset()


def test_http_route_passes_client_from_json_body_and_does_not_hang():
    """POST /api/qr/new {"client":"pc"} qua đường HTTP thật: do_POST đã đọc thân, route không được đọc lần hai (treo)."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    _reset()
    st = _state()
    app_server.STATE = st
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    orig = qr_login.fetch_server_flags
    qr_login.fetch_server_flags = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dừng"))
    try:
        for body, want in (({"client": "pc"}, "pc"), ({}, None)):
            st.thread = None
            req = urllib.request.Request(base + "/api/qr/new", data=json.dumps(body).encode(), method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=8) as r:       # treo -> timeout -> test hỏng
                assert json.loads(r.read().decode())["ok"] is True
            assert st.qr_client == want, (body, st.qr_client)
            _wait(st, ("error",))
            time.sleep(0.2)
    finally:
        qr_login.fetch_server_flags = orig
        httpd.shutdown()
        _reset()


def test_zalo_logout_clears_zalo_session_but_keeps_app_login_route():
    """POST /api/zalo/logout xoá phiên Zalo, KHÔNG thu hồi cookie app (để màn hình QR hiện, không văng ra /login)."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    _reset()
    st = _state()
    st.session = {"uid": "1", "zpw_sek": "x", "client": "web", "status": "da_dang_nhap"}
    app_server.STATE = st
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/api/zalo/logout" % httpd.server_address[1], data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=8) as r:
            assert json.loads(r.read().decode())["ok"] is True
            assert "Set-Cookie" not in r.headers, "không được xoá cookie đăng nhập app"
        assert st.session is None
    finally:
        httpd.shutdown()
        _reset()


def test_restart_replaces_pending_qr_and_stale_worker_stays_silent():
    """Bấm Quay lại rồi chọn kiểu khác khi QR cũ còn chờ quét: QR mới lấy ngay theo kiểu mới; luồng cũ (còn kẹt ở long-poll) thoát
    im lặng, KHÔNG ghi đè trạng thái/kiểu và KHÔNG tạo phiên."""
    import threading
    _reset()
    st = _state()
    release_old = threading.Event()
    calls = []
    orig = (qr_login.fetch_server_flags, qr_login.fetch_qr, qr_login.wait_scan, qr_login.wait_confirm, st._fetch_login_info)
    try:
        qr_login.fetch_server_flags = lambda *a, **k: {"known": False}

        def fake_qr(*a, **k):
            calls.append(protocol.client_name())
            return {"base64_qr": "QR%d" % len(calls), "qr_timeout": 90, "qr_retry": 1}
        qr_login.fetch_qr = fake_qr

        def fake_wait_scan(*a, **k):
            if len(calls) == 1:
                release_old.wait(5)          # QR đầu: kẹt chờ quét
                raise qr_login.QRExpired("hết hạn")      # khi được thả: báo hết hạn (nếu không im lặng sẽ ghi state=expired)
            return {}
        qr_login.wait_scan = fake_wait_scan
        qr_login.wait_confirm = lambda *a, **k: {"uid": "9", "dkey": "d", "phonenum": "84", "zpw_sek": "s", "zpw_kt": "k"}
        st._fetch_login_info = lambda *a, **k: {"zpw_enk": "", "config": {}}
        st.start_sync = lambda *a, **k: None
        assert st.start_qr("web", restart=True) is True
        end = time.time() + 5
        while time.time() < end and not calls:
            time.sleep(0.02)
        assert calls == ["web"]
        assert st.start_qr("pc") is False, "không restart thì vẫn từ chối khi QR đang chạy (hành vi cũ)"
        assert st.start_qr("pc", restart=True) is True
        assert _wait(st, ("done", "error")) == "done", st.qr_error
        assert calls == ["web", "pc"] and st.session["client"] == "pc" and protocol.client_name() == "pc"
        release_old.set()                    # thả luồng cũ: phải im lặng
        time.sleep(0.4)
        assert st.qr_state == "done" and st.session["client"] == "pc" and protocol.client_name() == "pc", (st.qr_state, protocol.client_name())
    finally:
        release_old.set()
        (qr_login.fetch_server_flags, qr_login.fetch_qr, qr_login.wait_scan, qr_login.wait_confirm, st._fetch_login_info) = orig
        _reset()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL QR CLIENT KIND TESTS PASSED")
