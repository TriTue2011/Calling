"""Tests for H5 + I1 (security audit, phan B/C): kiem chung phien
Zalo dang song bang keepAlive thay vi chi kiem session.json con
zpw_sek.

Nguon endpoint (khong bia): zca-js auth/keepAlive
(~/workspace/zca-js-softtyos/src/apis/auth/keepAlive.ts) —
GET {zpwServiceMap.chat[0]}/keepalive, params AES {imei}, lenh
11770, tra ve envelope hai lop nhu cac GET post-login khac
(handleZaloResponse mac dinh isEncrypted=true).

  (1) keepAlive thanh cong -> session giu nguyen, status login=true
  (2) keepAlive tra 600 -> sau nguong (2 lan lien tiep) session bi
      xoa + trang thai ve login=false (QR hien lai); 1 lan 600 thi
      chua xoa (cho retry)
  (3) keepAlive loi mang thoang qua -> session khong bi xoa
  (4) op keepAlive dispatch duoc qua POST /api/svc/keepAlive (mock)
  (5) /api/status dung cache keepAlive, khong goi keepAlive moi lan

Khong dang nhap that, khong goi Zalo that: moi thu di qua MockZalo
hoac probe duoc monkeypatch tren AppState.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import services as svc_mod  # noqa: E402
from zalo_pc_app import session as session_mod  # noqa: E402


def http_get(url, cookie="", timeout=15):
    req = urllib.request.Request(url, method="GET")
    if cookie:
        req.add_header("Cookie", "zpw_sek=" + cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def http_post(url, form, cookie="", timeout=15):
    req = urllib.request.Request(url, method="POST",
                                 data=form.encode("utf-8"))
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if cookie:
        req.add_header("Cookie", "zpw_sek=" + cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    protocol.CHAT_DOMAIN = mock.base
    protocol.CONVERS_DOMAIN = mock.base
    protocol.FRIEND_DOMAIN = mock.base
    protocol.ALIAS_DOMAIN = mock.base
    protocol.LABEL_DOMAIN = mock.base
    protocol.BOARD_DOMAIN = mock.base
    protocol.STICKER_DOMAIN = mock.base
    protocol.FILE_DOMAIN = mock.base


def kept_state(tmp, enk=TEST_SESSION_KEY):
    """AppState voi phien cu da luu (giong test_sync_start.kept_state)."""
    state = app_server.AppState(tmp)
    sess = session_mod.new_session("dev-1", "testhost")
    sess.update({
        "uid": "10001", "dkey": "dkey-test",
        "phonenum": "+84000000000",
        "zpw_sek": "sek-test", "zpw_kt": "kt-test",
        "zpw_enk": enk,
        "poll_msg_urls": [], "poll_ctl_urls": [],
        "status": session_mod.STATUS_LOGGED_IN,
    })
    state.store.save(sess)
    state.session = sess
    return state


def wait_for(fn, timeout=10, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(0.1)
    raise AssertionError("timeout waiting for %s" % what)


# ------------------------------------------------------------------ op
def test_keepalive_op_in_catalog():
    spec = svc_mod.OPS.get("keepAlive")
    assert spec is not None, "OPS thieu op keepAlive"
    # Ngoai 96 service addon (giong quote/seen/label update):
    # addon_no None de khong lam lenh total_96.
    assert spec["addon_no"] is None, spec
    assert spec["addon"] == "keepAlive", spec
    assert spec["domain"] == "chat", spec
    assert spec["path"] == "/keepalive", spec
    assert spec["code"] == 11770, spec
    assert spec["method"] == "GET", spec
    assert spec["thread"] == "none", spec
    # Body da xac minh truc tiep tu zca-js keepAlive.ts
    # (GET, params AES {imei}) — khong phai doan.
    assert spec["body_unverified"] is False, spec
    cat = svc_mod.build_catalog()
    assert cat["counts"]["total_96"] == 96, cat["counts"]


def test_keepalive_dispatch_gets_chat_keepalive():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = svc_mod.Services(
            partial(http_get, cookie="<redacted>"),
            partial(http_post, cookie="<redacted>"),
            "dev-1", TEST_SESSION_KEY)
        data = svc.dispatch("keepAlive", {})
        assert data["path"] == "/keepalive", data
        assert data["body"] == {"imei": "dev-1"}, data
        hits = [p for p, _, _ in mock.seen if p == "/keepalive"]
        assert hits, mock.seen
    finally:
        mock.stop()


# ------------------------------------------------------- validation
def test_keepalive_success_keeps_session():
    state = kept_state(tempfile.mkdtemp())
    state._keepalive_probe = lambda sess: {"config_vesion": 1}
    assert state.check_keepalive() is True
    assert state.session is not None, "phien bi xoa sau keepAlive ok"
    assert state.store.exists(), "session.json bi xoa sau keepAlive ok"
    st = state.public_status()
    assert st["login"] is True, st
    assert st["keepalive"]["state"] == "ok", st["keepalive"]
    assert st["keepalive"]["auth_failures"] == 0, st["keepalive"]


def test_keepalive_single_auth_failure_keeps_session():
    state = kept_state(tempfile.mkdtemp())

    def _fail(sess):
        raise svc_mod.ServiceError("keepAlive", 600, "het phien")
    state._keepalive_probe = _fail
    assert state.check_keepalive() is False
    # 1 lan 600: chua du nguong — phien duoc giu de retry lan sau.
    assert state.session is not None, "1 lan 600 da xoa phien"
    assert state.store.exists(), "1 lan 600 da xoa session.json"
    st = state.public_status()
    assert st["login"] is True, st
    assert st["keepalive"]["state"] == "auth_failed", st["keepalive"]
    assert st["keepalive"]["auth_failures"] == 1, st["keepalive"]


def test_keepalive_two_auth_failures_expire_session():
    state = kept_state(tempfile.mkdtemp())

    def _fail(sess):
        raise svc_mod.ServiceError("keepAlive", 600, "het phien")
    state._keepalive_probe = _fail
    assert state.check_keepalive() is False
    assert state.session is not None, "1 lan 600 da xoa phien"
    assert state.check_keepalive() is False
    # 2 lan 600 lien tiep: phien chet that — xoa session + ve QR.
    assert state.session is None, "2 lan 600 van giu phien"
    assert not state.store.exists(), "2 lan 600 van giu session.json"
    st = state.public_status()
    assert st["login"] is False, st
    assert st["keepalive"]["state"] == "expired", st["keepalive"]
    assert st["keepalive"]["auth_failures"] == 2, st["keepalive"]


def test_keepalive_auth_failure_then_success_resets_counter():
    state = kept_state(tempfile.mkdtemp())
    calls = {"n": 0}

    def _probe(sess):
        calls["n"] += 1
        if calls["n"] == 1:
            raise svc_mod.ServiceError("keepAlive", 600, "het phien")
        return {"config_vesion": 1}
    state._keepalive_probe = _probe
    assert state.check_keepalive() is False
    assert state.check_keepalive() is True
    assert state.session is not None, "phien bi xoa du da khoi phuc"
    st = state.public_status()
    assert st["login"] is True, st
    assert st["keepalive"]["state"] == "ok", st["keepalive"]
    assert st["keepalive"]["auth_failures"] == 0, st["keepalive"]


def test_keepalive_transient_network_error_keeps_session():
    state = kept_state(tempfile.mkdtemp())
    state._keepalive_probe = lambda sess: (_ for _ in ()).throw(
        urllib.error.URLError("tam mat mang"))
    assert state.check_keepalive() is False
    assert state.session is not None, "loi mang thoang qua da xoa phien"
    assert state.store.exists(), "loi mang thoang qua da xoa session.json"
    st = state.public_status()
    assert st["login"] is True, st
    assert st["keepalive"]["state"] == "network_error", st["keepalive"]
    assert st["keepalive"]["auth_failures"] == 0, st["keepalive"]


def test_keepalive_http_401_counts_as_auth_failure():
    # Transport that ve HTTP 401: Services._unwrap nem RuntimeError
    # "network status=401" — phai duoc xep loai auth, khong phai mang.
    state = kept_state(tempfile.mkdtemp())
    state._keepalive_probe = lambda sess: (_ for _ in ()).throw(
        RuntimeError("svc GET /keepalive: network status=401"))
    assert state.check_keepalive() is False
    st = state.public_status()
    assert st["keepalive"]["state"] == "auth_failed", st["keepalive"]
    assert st["keepalive"]["auth_failures"] == 1, st["keepalive"]
    assert state.session is not None, "1 lan 401 da xoa phien"


# ------------------------------------------------------------------ HTTP
def _api(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _start_app_server(mock, tmp):
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % port


def _login_via_qr(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            return
        time.sleep(0.5)
    raise AssertionError("qr did not reach done: %s" % last)


def test_keepalive_via_svc_http_api():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-test-")
    mock = MockZalo().start()
    httpd = None
    try:
        patch_domains(mock)
        httpd, base = _start_app_server(mock, tmp)
        # Chua dang nhap: op bi chan 401 nhu moi op svc khac.
        status, body = _api(base, "POST", "/api/svc/keepAlive", {})
        assert status == 401, body
        _login_via_qr(base)
        status, body = _api(base, "POST", "/api/svc/keepAlive", {})
        assert status == 200, body
        assert body["ok"] is True, body
        assert body["data"]["path"] == "/keepalive", body
        # imei = device_id cua phien vua dang nhap qua QR (mock
        # tao UUID), khong phai "dev-1" co dinh nhu test dispatch.
        assert body["data"]["body"] == {
            "imei": app_server.STATE.session["device_id"]}, body
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        mock.stop()


# ------------------------------------------------------------------ cache
def test_status_uses_cache_no_probe_per_call():
    state = kept_state(tempfile.mkdtemp())
    calls = {"n": 0}

    def _probe(sess):
        calls["n"] += 1
        return {"config_vesion": 1}
    state._keepalive_probe = _probe
    # Lan status dau tien: cache trong -> kich probe nen 1 lan.
    st = state.public_status()
    assert st["login"] is True, st
    wait_for(lambda: calls["n"] == 1, timeout=5,
             what="probe keepAlive nen dau tien")
    # Cac lan status tiep theo trong TTL: dung cache, khong goi them.
    for _ in range(3):
        st = state.public_status()
        assert st["login"] is True, st
        assert st["keepalive"]["state"] == "ok", st["keepalive"]
    time.sleep(0.3)
    assert calls["n"] == 1, calls
    # Het TTL: status tiep theo kich probe nen lai 1 lan.
    state._ka_at = 0.0
    state.public_status()
    wait_for(lambda: calls["n"] == 2, timeout=5,
             what="probe keepAlive sau khi het TTL")
    time.sleep(0.2)
    assert calls["n"] == 2, calls


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
    print("ALL PASS")
