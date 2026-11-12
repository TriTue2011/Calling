"""Dang nhap QR doc co getServerInfo (authen.trusted_device) va bao loi ro rang (12/11/2026).

Do tren may chu Zalo that: {qr_format_trust_device:0, self_g:0, logo_qr:0} -> Zalo PC dung QR loai cu, giong app. App KHONG duoc im lang
neu Zalo bat co khac: phai ghi nhat ky, hien canh bao o /api/qr/status, va khi quet loi thi noi ro nguyen nhan bang tieng Viet.
Doc co khong duoc lam hong dang nhap (that bai -> known=False, van thu loai cu).
Run: python3 tests/test_qr_server_flags.py
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
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


def test_fetch_server_flags_all_modes():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        t = app_server.make_transport()
        mock.server_info_mode = "old"
        f = qr_login.fetch_server_flags(t, "dev-1", "pc")
        assert f["known"] and not (f["qr_format_trust_device"] or f["self_g"] or f["logo_qr"]), f
        assert qr_login.flags_warning(f) == "" and "ảnh QR do máy chủ cấp" in qr_login.describe_server_flags(f)
        mock.server_info_mode = "trust"
        f = qr_login.fetch_server_flags(t, "dev-1", "pc")
        assert f["known"] and f["qr_format_trust_device"] is True, f
        assert "thiết bị tin cậy" in qr_login.flags_warning(f) and "qr_format_trust_device=1" in qr_login.describe_server_flags(f)
        mock.server_info_mode = "self_g"
        f = qr_login.fetch_server_flags(t, "dev-1", "pc")
        assert f["self_g"] is True and "self_g=1" in qr_login.flags_warning(f), f
        mock.server_info_mode = "absent"           # may chu khong gui nhanh authen: PC coi la 0/0/0
        f = qr_login.fetch_server_flags(t, "dev-1", "pc")
        assert f["known"] and not f["qr_format_trust_device"] and "authen.trusted_device" in f["detail"], f
        mock.server_info_mode = "error"            # HTTP 500: khong nem loi, known=False
        f = qr_login.fetch_server_flags(t, "dev-1", "pc")
        assert f["known"] is False and "Chưa đọc được cờ" in qr_login.describe_server_flags(f), f
    finally:
        mock.stop()


def test_login_still_works_and_status_exposes_flags():
    for mode, expect_trust in (("trust", True), ("error", False), ("old", False)):
        mock = MockZalo().start()
        try:
            patch_domains(mock)
            app_server.PARAM_CIPHER_KEY = None
            mock.server_info_mode = mode
            state = app_server.AppState(tempfile.mkdtemp())
            assert state.start_qr() is True
            wait_for(lambda: state.qr_status()["state"] == "done", what="dang nhap xong (mode=%s)" % mode)
            st = state.qr_status()
            assert "server_flags" in st and st["server_flags"]["qr_format_trust_device"] is expect_trust, (mode, st)
            assert ("warning" in st) is expect_trust, (mode, st)
            saved = state.store.load()
            if mode == "error":
                assert saved["trusted_device"]["qr_format_trust_device"] is False      # khong biet: giu mac dinh
            else:
                assert saved["trusted_device"]["qr_format_trust_device"] is expect_trust, saved["trusted_device"]
            state.stop_sync()
        finally:
            mock.stop()


def test_trust_flow_error_is_explained_in_vietnamese():
    mock = MockZalo().start()
    real = qr_login.wait_scan
    try:
        patch_domains(mock)
        app_server.PARAM_CIPHER_KEY = None
        mock.server_info_mode = "trust"

        def boom(*a, **k):
            raise qr_login.TrustFlowRequired("scan event carries trust link data")
        qr_login.wait_scan = boom
        state = app_server.AppState(tempfile.mkdtemp())
        assert state.start_qr() is True
        wait_for(lambda: state.qr_status()["state"] == "error", what="trang thai error")
        err = state.qr_status()["error"]
        assert "thiết bị tin cậy" in err and "qr_format_trust_device=1" in err and "app chưa hỗ trợ" in err, err
    finally:
        qr_login.wait_scan = real
        mock.stop()


def test_empty_qr_image_is_a_clear_error():
    def fake(url, timeout=30):
        return 200, {"error_code": 0, "data": {"base64_qr": "", "chk_wait_scan": "http://x/a", "chk_wait_cfirm": "http://x/b",
                                                "qr_retry": 1, "qr_timeout": 5}}
    try:
        qr_login.fetch_qr(fake, "dev-1", "pc", [], param_cipher_key=None)
        raise AssertionError("phai nem LoginError")
    except qr_login.LoginError as e:
        assert "không trả ảnh QR" in str(e), e


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL QR FLAGS TESTS PASSED")
