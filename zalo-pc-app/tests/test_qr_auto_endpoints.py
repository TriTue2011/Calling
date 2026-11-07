"""Sau khi quet QR xong, app PHAI tu dong lay poll URLs + mo kenh
sync (99100) + kenh ctrl (99101) — khong can thao tac tay them
(yeu cau cung cua user 23:24 07/11: "da quet QR thi phai auto
tat ca chu").

Goc (bundle compact-app-pc @11816376): client resolve
{config: e.data.data, UIN: e.data.data.dkey,
 decryptKey: e.data.data.zpw_enk} — toan bo data CHINH LA config;
 zpw_chts_new / zpw_ctrs_new o TOP-LEVEL cua data, khong phai
 duoi data.config. App cu chi doc data.config nen tren response
 that khong bao gio thay poll URLs (live 2026-11-07: QR xong,
 getLoginInfo thanh cong, nhung "khong co zpw_chts_new" mai, ca
 hai kenh khong mo duoc). Mock cu cung sai theo shape do nen
 test van xanh — mock nay da sua ve shape that.

Mock/offline hoan toan: khong dang nhap that, khong goi that.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import protocol, qr_login  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base


def wait_for(fn, timeout=15, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(0.2)
    raise AssertionError("timeout waiting for %s" % what)


def full_grant(mock):
    """reqqr -> scan -> confirm qua mock; tra grant (co zpw_sek)."""
    from mock_server import MockZalo as _M  # noqa
    import json
    import urllib.error
    import urllib.request

    def http_get(url, timeout=30):
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:
                return e.code, {}

    t = http_get
    qr = qr_login.fetch_qr(t, "dev-1", "testhost", [])
    qr_login.wait_scan(t, qr, trust_enabled=False)
    return qr_login.wait_confirm(t, qr)


def test_fetch_login_info_reads_top_level_endpoints():
    """Shape that: zpw_chts_new / zpw_ctrs_new o TOP-LEVEL cua
    data — _fetch_login_info phai tra ve chung."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = app_server.AppState(tempfile.mkdtemp())
        grant = full_grant(mock)
        info = state._fetch_login_info(grant, "dev-1", "testhost")
        assert info["zpw_enk"] == TEST_SESSION_KEY, info
        assert info["dkey"] == "dkey-test", info
        assert info["poll_msg_urls"] == [mock.base + "/lp-msg"], info
        assert info["poll_ctl_urls"] == [mock.base + "/lp-ctl"], info
        assert info["config"]["zpw_ws"] == "wss://mock.invalid/ws", info
        assert info["config"]["zpw_service_map_new"]["reaction"] \
            == mock.base, info
    finally:
        mock.stop()


def test_fetch_login_info_nested_config_fallback():
    """Shape cu (poll URLs duoi data.config) van doc duoc nho
    fallback — khong pha vo tuong thich nguoc."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        mock.logininfo_mode = "nested_config"
        state = app_server.AppState(tempfile.mkdtemp())
        grant = full_grant(mock)
        info = state._fetch_login_info(grant, "dev-1", "testhost")
        assert info["poll_msg_urls"] == [mock.base + "/lp-msg"], info
        assert info["poll_ctl_urls"] == [mock.base + "/lp-ctl"], info
        assert info["config"]["zpw_ws"] == "wss://mock.invalid/ws", info
    finally:
        mock.stop()


def test_no_endpoints_records_response_shape():
    """Server tra thanh cong nhung khong cap poll URLs o dau ca:
    start_sync False + sync_error no_endpoints + ghi lai HINH
    DANG response (ten key cua data/config, khong ghi gia tri)
    de lan sau doc log la biet ngay server tra gi."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        mock.logininfo_mode = "no_endpoints"
        state = app_server.AppState(tempfile.mkdtemp())
        grant = full_grant(mock)
        info = state._fetch_login_info(grant, "dev-1", "testhost")
        assert info["poll_msg_urls"] == [], info
        assert info["poll_ctl_urls"] == [], info
        assert "zpw_chts_new" not in info.get("_data_keys", []), info
        assert "zpw_chts_new" not in info.get("_config_keys", []), info
        assert "zpw_enk" in info.get("_data_keys", []), info
        # Di qua start_sync: no_endpoints + debug duoc luu tren state.
        from zalo_pc_app import session as session_mod
        sess = session_mod.new_session("dev-1", "testhost")
        sess.update({"uid": "10001", "dkey": "dkey-test",
                     "zpw_sek": "sek-test",
                     "zpw_enk": TEST_SESSION_KEY,
                     "poll_msg_urls": [], "poll_ctl_urls": [],
                     "status": session_mod.STATUS_LOGGED_IN})
        state.store.save(sess)
        state.session = sess
        assert state.start_sync() is False
        assert state.sync_status() == "no_endpoints", state.sync_status()
        assert state.sync_error == "no_endpoints_from_server", \
            state.sync_error
        debug = state.sync_debug
        assert "zpw_chts_new" not in debug.get("logininfo_data_keys",
                                               []), debug
        assert "zpw_enk" in debug.get("logininfo_data_keys", []), debug
        assert state.public_status().get("sync_debug") == debug, \
            state.public_status()
    finally:
        mock.stop()


def test_qr_login_auto_starts_sync_and_ctrl():
    """Dau moi: quet QR xong (worker chay nen) -> phien moi duoc
    luu VOI poll URLs -> ca hai kenh sync + ctrl tu mo, khong
    can goi tay them. Day la yeu cau cung cua user."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = app_server.AppState(tempfile.mkdtemp())
        assert state.start_qr() is True
        wait_for(lambda: state.qr_status()["state"] == "done",
                 timeout=15, what="QR worker done")
        assert state.sync_status() == "running", state.sync_status()
        assert state.ctrl is not None, "kenh ctrl khong tu mo sau QR"
        assert state.file_async.feeder_running is True
        assert state.voice_async.feeder_running is True
        saved = state.store.load()
        assert saved["poll_msg_urls"] == [mock.base + "/lp-msg"], saved
        assert saved["poll_ctl_urls"] == [mock.base + "/lp-ctl"], saved
        assert saved["zpw_enk"] == TEST_SESSION_KEY, saved
        state.stop_sync()
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL QR-AUTO-ENDPOINT TESTS PASSED")
