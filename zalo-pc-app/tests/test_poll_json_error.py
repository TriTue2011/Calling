"""Poll tra ve khong phai JSON — loi live 08/11 sau deploy 1043836.

Log that (container zalo-zalo-pc-1, 08:16 08/11): ca hai poller
(sync 99100 + ctrl 99101) cung bao
  "[sync-poll] sync_poll: poll loi mang: JSONDecodeError; retry sau 3s"
  "[ctrl-poll] ctrl_poll: poll loi mang: JSONDecodeError; retry sau 3s"
  ... backoff tang dan toi 60s va van loi.
File gui OK ngay truoc do (nho 967 B + APK 20,8 MB, deu `-> ok`),
sync xu ly duoc tin offline — kenh vua chay tot thi dot nhien
poll tra ve khong phai JSON.

Goc (xem code):
  G1. Transport (`server._Transport._request`) parse JSON truc tiep
      tren body 200 (`json.loads`): body khong phai JSON -> bare
      `JSONDecodeError` vang ra ngoai; poller goi chung la "poll loi
      mang: JSONDecodeError" — khong ai biet server tra ve gi
      (HTML? rong? trang loi?), status bao nhieu.
  G2. Poller retry mu mai voi cung URL cu: khong bao gio refresh
      endpoints khi loi keo dai; vong retry nen (`_sync_retry_loop`)
      chi goi start_sync() khi `self.sync is None`, nhung poller
      ket trong backoff van giu `self.sync` nen khong bao gio duoc
      mo lai.
  G3. `sync_status()` tra "running" chi can poller ton tai, khong
      kiem tra thread con song khong — app bao "running" trong khi
      khong co tin/event nao ve. (ctrl_status thi da kiem tra
      is_alive tu ban 9463ee0; SyncPoller chua co is_alive.)
  G4. 401/403 (phien het han) bi doi xu nhu loi mang thuong:
      "network status=401" roi retry mu, thay vi bao ro "phien het
      han — quet QR lai" va dung retry.

Ban sua phai: transport nem NonJsonResponse mang status + preview
body (<=100 ky tu, khong log noi dung tin/secret); body rong
(200 + rong) coi nhu "empty" (poll lai ngay, khong backoff);
401/403 danh dau auth_failed va bao ro phien het han; sau N loi
lien tiep poller tu dung de AppState mo lai voi endpoints moi;
sync_status/ctrl_status phan biet running/stopped/auth_failed;
loi hien ro tren /api/status.

Mock/offline hoan toan: khong dang nhap that, khong goi that.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import session as session_mod  # noqa: E402
from zalo_pc_app import sync_poll as sync_poll_mod  # noqa: E402
from zalo_pc_app.ctrl_poll import CtrlPoller, VoiceAsyncRegistry  # noqa: E402
from zalo_pc_app.sync_poll import NonJsonResponse, SyncPoller  # noqa: E402

POLL_URLS = ["http://127.0.0.1:9/lp-msg"]
ENK = "test-enk"


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


def kept_state(tmp, poll_msg_urls, poll_ctl_urls, enk):
    """AppState voi phien cu da luu (giong test_file_ctrl_restart)."""
    state = app_server.AppState(tmp)
    sess = session_mod.new_session("dev-1", "testhost")
    sess.update({
        "uid": "10001", "dkey": "dkey-test",
        "phonenum": "+84000000000",
        "zpw_sek": "sek-test", "zpw_kt": "kt-test",
        "zpw_enk": enk,
        "poll_msg_urls": list(poll_msg_urls),
        "poll_ctl_urls": list(poll_ctl_urls),
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


class _FakeResp:
    """Gia lap urllib response: status + body bytes, dung duoc
    trong `with urllib.request.urlopen(...) as resp:`."""

    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _ScriptedHttpGet:
    """http_get gia lap: tra ve / nem theo kich ban (list cac
    ("ok", (status, payload)) hoac ("raise", exc)); het kich ban
    thi tra envelope rong (200, data="") mai."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, url, timeout=30):
        with self._lock:
            self.calls += 1
            if self.script:
                kind, value = self.script.pop(0)
            else:
                kind, value = "ok", (200, {"error_code": 0,
                                           "data": ""})
        if kind == "raise":
            raise value
        return value


def _non_json_exc(body="<!DOCTYPE html><html><body>error</body></html>"):
    return NonJsonResponse(200, body)


# -- transport -----------------------------------------------------------

def test_transport_non_json_200_raises_with_preview():
    """G1: 200 + body HTML -> transport phai nem NonJsonResponse
    mang status + preview, thay vi bare JSONDecodeError."""
    transport = app_server._Transport("sek-test")
    real_urlopen = urllib.request.urlopen
    html = b"<!DOCTYPE html><html><body>Bad Gateway</body></html>"
    urllib.request.urlopen = lambda req, timeout=None: _FakeResp(
        200, html)
    try:
        try:
            transport.http_get("http://127.0.0.1:9/lp-msg", timeout=5)
            raise AssertionError("expected NonJsonResponse")
        except NonJsonResponse as e:
            assert e.status == 200, e.status
            assert "<!DOCTYPE html>" in e.preview, e.preview
            assert e.body_len == len(html), e.body_len
            assert e.empty is False
    finally:
        urllib.request.urlopen = real_urlopen


def test_transport_empty_200_body_is_empty_non_json():
    """G1: 200 + body rong -> NonJsonResponse danh dau empty."""
    transport = app_server._Transport("sek-test")
    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=None: _FakeResp(
        200, b"")
    try:
        try:
            transport.http_get("http://127.0.0.1:9/lp-msg", timeout=5)
            raise AssertionError("expected NonJsonResponse")
        except NonJsonResponse as e:
            assert e.status == 200
            assert e.empty is True, e
            assert e.body_len == 0
    finally:
        urllib.request.urlopen = real_urlopen


# -- poller: phan loai loi -------------------------------------------------

def test_sync_non_json_names_status_and_preview():
    """G1: poller gap NonJsonResponse phai loi ro rang co status +
    preview body, khong phai chi ten kieu exception."""
    fake = _ScriptedHttpGet(
        [("raise", _non_json_exc())])
    poller = SyncPoller(fake, POLL_URLS, ENK, "10001")
    try:
        poller.poll_once()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        msg = str(e)
        assert "khong phai JSON" in msg, msg
        assert "status=200" in msg, msg
        assert "<!DOCTYPE html>" in msg, msg
    assert "khong phai JSON" in poller.last_error, poller.last_error
    assert poller.consec_errors == 1, poller.consec_errors


def test_ctrl_non_json_names_status_and_preview():
    """G1, kenh ctrl: cung phan loai nhu kenh sync."""
    fake = _ScriptedHttpGet(
        [("raise", _non_json_exc("<html>Service Unavailable</html>"))])
    poller = CtrlPoller(fake, POLL_URLS, ENK, "10001",
                        VoiceAsyncRegistry())
    try:
        poller.poll_once()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        msg = str(e)
        assert "khong phai JSON" in msg, msg
        assert "status=200" in msg, msg
        assert "Service Unavailable" in msg, msg
    assert poller.consec_errors == 1, poller.consec_errors


def test_sync_empty_body_is_empty_not_error():
    """Body rong (200 + rong) la dang het han cua long-poll: coi
    nhu "empty", poll lai ngay, KHONG dem loi, KHONG backoff."""
    fake = _ScriptedHttpGet(
        [("raise", NonJsonResponse(200, ""))])
    poller = SyncPoller(fake, POLL_URLS, ENK, "10001")
    assert poller.poll_once() == "empty"
    assert poller.consec_errors == 0, poller.consec_errors
    assert poller.last_error == "", poller.last_error


def test_ctrl_empty_body_is_empty_not_error():
    """Kenh ctrl: body rong cung coi nhu "empty"."""
    fake = _ScriptedHttpGet(
        [("raise", NonJsonResponse(200, "   "))])
    poller = CtrlPoller(fake, POLL_URLS, ENK, "10001",
                        VoiceAsyncRegistry())
    assert poller.poll_once() == "empty"
    assert poller.consec_errors == 0, poller.consec_errors


def test_sync_auth_401_marks_auth_failed():
    """G4: 401 phai bao ro 'phien het han' va danh dau auth_failed,
    khong phai 'network status=401' roi retry mu."""
    fake = _ScriptedHttpGet([("ok", (401, {}))])
    poller = SyncPoller(fake, POLL_URLS, ENK, "10001")
    try:
        poller.poll_once()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        msg = str(e)
        assert "phien het han" in msg, msg
        assert "401" in msg, msg
    assert poller.auth_failed is True
    assert poller.consec_errors == 1, poller.consec_errors


def test_ctrl_auth_403_marks_auth_failed():
    """G4, kenh ctrl: 403 cung la phien het han."""
    fake = _ScriptedHttpGet([("ok", (403, {}))])
    poller = CtrlPoller(fake, POLL_URLS, ENK, "10001",
                        VoiceAsyncRegistry())
    try:
        poller.poll_once()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "phien het han" in str(e), str(e)
    assert poller.auth_failed is True


# -- poller: tu dung sau loi keo dai + hoi phuc ----------------------------

def test_persistent_non_json_stops_sync_poller():
    """G2: loi JSON lien tiep -> poller tu dung (khong retry mu
    mai) de AppState mo lai voi endpoints moi; ghi ro ly do."""
    old_base = sync_poll_mod.RETRY_BASE_SECONDS
    old_max = sync_poll_mod.MAX_CONSEC_ERRORS
    sync_poll_mod.RETRY_BASE_SECONDS = 0.05
    sync_poll_mod.MAX_CONSEC_ERRORS = 3
    fake = _ScriptedHttpGet(
        [("raise", _non_json_exc())] * 50)
    poller = SyncPoller(fake, POLL_URLS, ENK, "10001")
    try:
        assert poller.start() is True
        wait_for(lambda: not poller.is_alive(), timeout=10,
                 what="sync poller to stop itself")
        assert poller.stopped_reason == "persistent_errors", \
            poller.stopped_reason
        assert poller.consec_errors >= 3, poller.consec_errors
        assert "khong phai JSON" in poller.last_error, \
            poller.last_error
    finally:
        sync_poll_mod.RETRY_BASE_SECONDS = old_base
        sync_poll_mod.MAX_CONSEC_ERRORS = old_max
        poller.stop()


def test_persistent_non_json_stops_ctrl_poller():
    """G2, kenh ctrl: cung tu dung sau loi keo dai."""
    from zalo_pc_app import ctrl_poll as ctrl_poll_mod
    old_base = ctrl_poll_mod.RETRY_BASE_SECONDS
    old_max = ctrl_poll_mod.MAX_CONSEC_ERRORS
    ctrl_poll_mod.RETRY_BASE_SECONDS = 0.05
    ctrl_poll_mod.MAX_CONSEC_ERRORS = 3
    fake = _ScriptedHttpGet(
        [("raise", _non_json_exc())] * 50)
    poller = CtrlPoller(fake, POLL_URLS, ENK, "10001",
                        VoiceAsyncRegistry())
    try:
        assert poller.start() is True
        wait_for(lambda: not poller.is_alive(), timeout=10,
                 what="ctrl poller to stop itself")
        assert poller.stopped_reason == "persistent_errors", \
            poller.stopped_reason
    finally:
        ctrl_poll_mod.RETRY_BASE_SECONDS = old_base
        ctrl_poll_mod.MAX_CONSEC_ERRORS = old_max
        poller.stop()


def test_poller_recovers_after_transient_non_json():
    """Loi JSON thoang qua (2 lan) roi poll OK tro lai: poller
    khong chet, dem loi reset ve 0, van nhan tin binh thuong."""
    old_base = sync_poll_mod.RETRY_BASE_SECONDS
    sync_poll_mod.RETRY_BASE_SECONDS = 0.05
    fake = _ScriptedHttpGet(
        [("raise", _non_json_exc()),
         ("raise", _non_json_exc())])
    poller = SyncPoller(fake, POLL_URLS, ENK, "10001")
    try:
        assert poller.start() is True
        wait_for(lambda: fake.calls >= 2, timeout=10,
                 what="two failed polls")
        wait_for(lambda: poller.consec_errors == 0, timeout=10,
                 what="consecutive errors to reset after good poll")
        assert poller.is_alive() is True
        assert poller.last_error == "", poller.last_error
    finally:
        sync_poll_mod.RETRY_BASE_SECONDS = old_base
        poller.stop()


# -- AppState: trang thai + mo lai -----------------------------------------

def test_dead_sync_poller_reports_stopped_and_restarts():
    """G3: poller sync chet (thread dung) thi sync_status() phai
    la 'stopped' (khong phai 'running'), va start_sync() phai mo
    lai poller moi; kenh ctrl dang chay thi khong mo trung."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"],
                           [mock.base + "/lp-ctl"],
                           TEST_SESSION_KEY)
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        assert state.ctrl_status() == "running"
        old_sync = state.sync
        old_ctrl = state.ctrl
        assert old_sync.is_alive() is True
        old_sync.stop()
        wait_for(lambda: not old_sync.is_alive(), timeout=5,
                 what="old sync thread to die")
        assert state.sync_status() == "stopped", \
            state.sync_status()
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        assert state.sync is not old_sync
        assert state.sync.is_alive() is True
        # Kenh ctrl van song thi khong tao trung.
        assert state.ctrl is old_ctrl, "kenh ctrl bi tao trung"
        assert state.ctrl.is_alive() is True
        state.stop_sync()
    finally:
        mock.stop()


def test_auth_failed_blocks_blind_respawn_and_reports():
    """G4, muc AppState: poller chet vi 401 thi sync_status() la
    'auth_failed', start_sync() KHONG mo lai mu (phien het han,
    can quet QR lai), trang thai giu nguyen de user thay ro."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"],
                           [mock.base + "/lp-ctl"],
                           TEST_SESSION_KEY)
        assert state.start_sync() is True
        # Mo phong trang thai poller chet vi 401: DUNG thread
        # truoc (thread dang chay voi mock tra success se xoa
        # last_error moi lan poll OK), roi gán co + loi cuoi
        # nhu khi poller vua nhan 401 lien tiep. Phat hien 401
        # that duoc test o muc poller (test_sync_auth_401...).
        state.sync.stop()
        wait_for(lambda: not state.sync.is_alive(), timeout=5,
                 what="auth-failed sync thread to die")
        state.sync.auth_failed = True
        state.sync.last_error = ("poll: phien het han (HTTP 401) "
                                 "- quet QR lai")
        assert state.sync_status() == "auth_failed", \
            state.sync_status()
        assert "phien het han" in state.sync_error, state.sync_error
        assert state.start_sync() is False
        assert state.sync_status() == "auth_failed"
        state.stop_sync()
    finally:
        mock.stop()


def test_ctrl_error_in_public_status():
    """Chan doan kenh ctrl phai hien tren /api/status
    (ctrl_error), khong chi sync_error."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"],
                           [mock.base + "/lp-ctl"],
                           TEST_SESSION_KEY)
        assert state.start_sync() is True
        assert state.ctrl_status() == "running"
        state.ctrl.stop()
        state.ctrl.last_error = (
            "ctrl_poll: poll tra ve khong phai JSON (status=200, "
            "body='<!DOCTYPE html>')")
        wait_for(lambda: not state.ctrl.is_alive(), timeout=5,
                 what="ctrl thread to die")
        assert state.ctrl_status() == "stopped", state.ctrl_status()
        status = state.public_status()
        assert "ctrl_error" in status, status
        assert "khong phai JSON" in status["ctrl_error"], status
        state.stop_sync()
    finally:
        mock.stop()


def test_retry_loop_respawns_dead_sync_poller():
    """G2, end-to-end tu phuc hoi: vong retry nen phai mo lai
    poller sync da chet (voi endpoints moi) ma khong can user
    bam retry hay restart."""
    mock = MockZalo().start()
    old_check = app_server.SYNC_RETRY_CHECK_SECONDS
    old_interval = app_server.SYNC_RETRY_INTERVAL_SECONDS
    app_server.SYNC_RETRY_CHECK_SECONDS = 0.2
    app_server.SYNC_RETRY_INTERVAL_SECONDS = 300
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"],
                           [mock.base + "/lp-ctl"],
                           TEST_SESSION_KEY)
        assert state.start_sync() is True
        old_sync = state.sync
        assert state.start_sync_retry_thread() is True
        old_sync.stop()
        wait_for(lambda: not old_sync.is_alive(), timeout=5,
                 what="old sync thread to die")
        assert state.sync_status() == "stopped"
        wait_for(lambda: state.sync is not None
                 and state.sync is not old_sync
                 and state.sync.is_alive(), timeout=10,
                 what="retry loop to respawn sync poller")
        assert state.sync_status() == "running"
        state.stop_sync()
    finally:
        app_server.SYNC_RETRY_CHECK_SECONDS = old_check
        app_server.SYNC_RETRY_INTERVAL_SECONDS = old_interval
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL POLL JSON ERROR TESTS PASSED")
