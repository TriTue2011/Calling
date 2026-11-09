"""Kenh ctrl (99101) phai chay de gui file/ghi am — loi live 07/11:
"gui file chua nhan duoc URL file — kenh ctrl (99101) chua chay".

Goc (xem code server.py start_sync / CtrlPoller):
  D1. start_sync chi refresh getLoginInfo khi thieu poll_msg_urls
      hoac zpw_enk — phien cu co msg URLs + enk nhung KHONG co
      poll_ctl_urls thi khong refresh, kenh ctrl khong bao gio mo
      (chi log "khong co zpw_ctrs_new"), sync van bao "running".
  D2. Khi sync da chay, start_sync tra True ngay ma khong kiem tra
      kenh ctrl; vong retry nen chi goi start_sync khi sync is None;
      POST /api/sync/retry cung goi start_sync. Nen kenh ctrl chet
      (KickOut -69) thi khong co duong nao khoi dong lai no trong
      khi sync van chay.
  D3. sync_status() tra "running" chi can sync poller ton tai, bat
      ke kenh ctrl — /api/status khong noi ro kenh ctrl xuong.

Mock/offline hoan toan: khong dang nhap that, khong goi that.
"""

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import session as session_mod  # noqa: E402

FILE_URL = "https://f1-file-dl.zdn.vn/test.docx"


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


def kept_state(tmp, poll_msg_urls, poll_ctl_urls, enk):
    """AppState voi phien cu da luu: zpw_sek con han, poll URLs /
    zpw_enk tuy theo truong hop."""
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


def test_kept_session_with_msg_urls_but_no_ctl_urls_refreshes_and_starts_ctrl():
    """D1: phien cu co msg URLs + enk nhung KHONG co ctl URLs thi
    start_sync phai refresh getLoginInfo de lay ctl URLs roi mo ca
    hai kenh (sync + ctrl), chu khong phai chi mo sync roi de kenh
    ctrl chet im (feeder_running False -> send_file loi)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"], [],
                           TEST_SESSION_KEY)
        assert state.sync_status() == "stopped"
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        # Refresh da chay (lay ctl URLs ve) va luu xuong session.
        assert len(logininfo_hits(mock)) == 1, mock.seen
        saved = state.store.load()
        assert saved["poll_ctl_urls"] == [mock.base + "/lp-ctl"], saved
        # Kenh ctrl phai chay: registry duoc nap.
        assert state.ctrl is not None, "kenh ctrl khong duoc tao"
        assert state.file_async.feeder_running is True
        assert state.voice_async.feeder_running is True
        state.stop_sync()
    finally:
        mock.stop()


def test_ctrl_dead_while_sync_running_restarts_on_start_sync():
    """D2: kenh ctrl chet (dung) trong khi sync van chay thi goi
    start_sync() lai phai khoi dong lai kenh ctrl (khong phai tra
    True ngay ma de kenh ctrl chet)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"],
                           [mock.base + "/lp-ctl"],
                           TEST_SESSION_KEY)
        assert state.start_sync() is True
        assert state.ctrl is not None
        assert state.file_async.feeder_running is True
        old_ctrl = state.ctrl
        # Gia lap kenh ctrl chet (KickOut/dung): poller dung, con
        # tro state.ctrl van tro toi poller chet (nhu khi run()
        # thoat vi KickOut), sync van chay.
        old_ctrl.stop()
        assert state.file_async.feeder_running is False
        assert state.sync is not None
        assert state.sync_status() == "running"
        # Goi lai start_sync: phai khoi dong lai kenh ctrl.
        assert state.start_sync() is True
        assert state.ctrl is not old_ctrl, "kenh ctrl khong duoc tao moi"
        assert state.file_async.feeder_running is True
        assert state.voice_async.feeder_running is True
        state.stop_sync()
    finally:
        mock.stop()


def test_ctrl_status_exposed_in_public_status():
    """D3: /api/status phai noi ro trang thai kenh ctrl (running /
    no_endpoints / stopped / kicked_out / logged_out), khong phai
    chi bao sync "running" trong khi kenh ctrl xuong."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        # Chua dang nhap.
        fresh = app_server.AppState(tempfile.mkdtemp())
        assert fresh.ctrl_status() == "logged_out", fresh.ctrl_status()
        assert fresh.public_status()["ctrl"] == "logged_out"
        # Co msg URLs nhung server khong cap ctl URLs.
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"], [],
                           TEST_SESSION_KEY)
        state._fetch_login_info = lambda grant, d, c: {
            "zpw_enk": TEST_SESSION_KEY, "config": {},
            "dkey": "dkey-test", "poll_msg_urls": [mock.base + "/lp-msg"],
            "poll_ctl_urls": [], "poll_msg_timeout": 30,
            "poll_ctl_timeout": 30}
        assert state.start_sync() is True
        assert state.sync_status() == "running"
        assert state.ctrl_status() == "no_endpoints", state.ctrl_status()
        assert state.public_status()["ctrl"] == "no_endpoints"
        state.stop_sync()
        # Du endpoint: ctrl chay.
        state2 = kept_state(tempfile.mkdtemp(),
                            [mock.base + "/lp-msg"],
                            [mock.base + "/lp-ctl"],
                            TEST_SESSION_KEY)
        assert state2.start_sync() is True
        assert state2.ctrl_status() == "running", state2.ctrl_status()
        assert state2.public_status()["ctrl"] == "running"
        # Ctrl dung.
        state2.ctrl.stop()
        assert state2.ctrl_status() == "stopped", state2.ctrl_status()
        # Ctrl bi da.
        state2.ctrl.kicked_out = True
        assert state2.ctrl_status() == "kicked_out", state2.ctrl_status()
        state2.stop_sync()
    finally:
        mock.stop()


def test_ctrl_needs_restart_unit():
    """Vong retry nen chi goi start_sync khi sync xuong HOAC kenh
    ctrl can khoi dong lai (sync chay nhung ctrl chet, khong bi
    da)."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"],
                           [mock.base + "/lp-ctl"],
                           TEST_SESSION_KEY)
        # Chua mo kenh: sync chua chay nen khong phai truong hop
        # "ctrl can khoi dong lai" (duong retry sync lo).
        assert state._ctrl_needs_restart() is False
        assert state.start_sync() is True
        # Ca hai kenh chay: khong can khoi dong lai.
        assert state._ctrl_needs_restart() is False
        # Ctrl chet, sync chay: can khoi dong lai.
        state.ctrl.stop()
        assert state._ctrl_needs_restart() is True
        # Ctrl bi da: KHONG tu khoi dong lai (server bao dung).
        state.ctrl.kicked_out = True
        assert state._ctrl_needs_restart() is False
        state.stop_sync()
    finally:
        mock.stop()


class _DeadFileWaiter:
    """Waiter gia: kenh ctrl chua chay (feeder_running False)."""

    feeder_running = False

    def wait(self, file_id, timeout_s):
        raise AssertionError("waiter chet khong duoc goi wait()")


def test_send_file_ctrl_down_error_names_cause_and_fix():
    """Loi gui file khi kenh ctrl xuong phai noi RO nguyen nhan +
    cach sua (trang thai kenh live + huong dan), khong phai chi
    "kenh ctrl chua chay" kho hieu."""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        status = {"ctrl": "stopped", "sync": "running",
                  "sync_error": ""}
        transport = app_server.make_transport("sek-test")
        chat = chat_mod.Chat(
            transport, "dev-1", TEST_SESSION_KEY,
            file_async=_DeadFileWaiter(), file_async_timeout=5.0,
            ctrl_status=lambda: dict(status))
        try:
            chat.send_file("user", "20001", "bao-cao.docx",
                           b"PK\x03\x04" + b"x" * 20,
                           "application/vnd.openxmlformats-officedocument"
                           ".wordprocessingml.document")
            raise AssertionError("expected ZaloChatError")
        except chat_mod.ZaloChatError as e:
            msg = str(e)
            assert "99101" in msg, msg
            assert "fileUrl" in msg, msg
            assert "ctrl=stopped" in msg or "stopped" in msg, msg
            assert "/api/sync/retry" in msg, msg
            assert mock.file_send_calls == 0, mock.file_send_calls
        # Khong co endpoint (server khong cap poll URLs): KHONG bao
        # quet QR lai — quet lai khong sua duoc (app phai tu lay
        # duoc kenh sau QR, dinh chinh user 23:24 07/11); bao app
        # dang tu thu lai + duong thu tay /api/sync/retry.
        status.update({"ctrl": "no_endpoints", "sync": "no_endpoints",
                       "sync_error": "no_endpoints_from_server"})
        try:
            chat.send_file("user", "20001", "bao-cao.docx",
                           b"PK\x03\x04" + b"x" * 20,
                           "application/vnd.openxmlformats-officedocument"
                           ".wordprocessingml.document")
            raise AssertionError("expected ZaloChatError")
        except chat_mod.ZaloChatError as e:
            msg = str(e)
            assert "QR" not in msg, msg
            assert "/api/sync/retry" in msg, msg
        # Phien het han (600): huong dan quet QR lai, noi ro 600.
        status.update({"ctrl": "stopped", "sync": "refresh_failed",
                       "sync_error": "RuntimeError error_code=600"})
        try:
            chat.send_file("user", "20001", "bao-cao.docx",
                           b"PK\x03\x04" + b"x" * 20,
                           "application/vnd.openxmlformats-officedocument"
                           ".wordprocessingml.document")
            raise AssertionError("expected ZaloChatError")
        except chat_mod.ZaloChatError as e:
            msg = str(e)
            assert "QR" in msg, msg
            assert "600" in msg, msg
        # Khong co ham trang thai: loi cu nguyen ven (khong vo).
        chat2 = chat_mod.Chat(
            transport, "dev-1", TEST_SESSION_KEY,
            file_async=_DeadFileWaiter(), file_async_timeout=5.0)
        try:
            chat2.send_file("user", "20001", "bao-cao.docx",
                            b"PK\x03\x04" + b"x" * 20,
                            "application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document")
            raise AssertionError("expected ZaloChatError")
        except chat_mod.ZaloChatError as e:
            assert "kenh ctrl (99101) chua chay" in str(e), str(e)
    finally:
        mock.stop()


def test_send_file_end_to_end_via_live_ctrl_poller():
    """Duong day du: kenh ctrl chay that (poll mock /lp-ctl/),
    event file_done ve -> send_file gui buoc 2 dung voi fileUrl.
    (Can mock tra event file_done qua kenh ctrl — xem
    MockZalo.ctrl_file_url.)"""
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        mock.ctrl_file_url = FILE_URL
        state = kept_state(tempfile.mkdtemp(),
                           [mock.base + "/lp-msg"],
                           [mock.base + "/lp-ctl"],
                           TEST_SESSION_KEY)
        state.file_async_timeout = 10.0
        assert state.start_sync() is True
        assert state.ctrl_status() == "running"
        # Doi poller ctrl nap event file_done vao registry (cache
        # cua bundle: event ve truoc khi wait van duoc nhan).
        wait_for(lambda: state.file_async.wait("file-1", 0.1)
                 is not None, timeout=10,
                 what="event file_done ve registry")
        transport = app_server.make_transport("sek-test")
        chat = chat_mod.Chat(
            transport, "dev-1", TEST_SESSION_KEY,
            file_async=state.file_async, file_async_timeout=10.0)
        res = chat.send_file("user", "20001", "bao-cao.docx",
                             b"PK\x03\x04" + b"x" * 20,
                             "application/vnd.openxmlformats-officedocument"
                             ".wordprocessingml.document")
        assert res["file_id"] == "file-1", res
        assert mock.file_upload_calls == 1, mock.file_upload_calls
        assert mock.file_send_calls == 1, mock.file_send_calls
        sent = mock.file_send_bodies[-1]["body"]
        assert sent["fileUrl"] == FILE_URL, sent
        state.stop_sync()
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL FILE-CTRL-RESTART TESTS PASSED")
