"""Phân loại lỗi cuộc gọi: theo kiểu ngoại lệ + error_code, không theo chữ. Chạy: python3 tests/test_call_errors.py"""
import os
import socket
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import call_errors  # noqa: E402
from zalo_pc_app.signaling import ServerRejectedError  # noqa: E402


def _rejected(code):
    e = ServerRejectedError("khong lien quan toi phan loai")
    e.inner = {"error_code": code}
    return e


def test_server_rejection_with_minus_101_is_already_answered_and_other_codes_are_server_rejected():
    assert call_errors.classify(_rejected(-101)) == "already_answered"
    assert call_errors.classify(_rejected(114)) == "server_rejected"
    assert call_errors.classify(ServerRejectedError("khong co inner")) == "server_rejected"
    bad = ServerRejectedError("x")
    for inner in (None, "x", {}, {"error_code": "-101"}, {"error_code": True}):
        bad.inner = inner
        assert call_errors.classify(bad) == "server_rejected", inner     # mã không phải số nguyên thật thì không suy diễn


def test_timeouts_and_network_errors_are_told_apart_by_type_not_text():
    assert call_errors.classify(socket.timeout("mot thong bao bat ky")) == "timeout"
    assert call_errors.classify(TimeoutError()) == "timeout"
    assert call_errors.classify(ConnectionResetError("timeout")) == "network"      # chữ «timeout» trong thông báo không đổi kết quả
    assert call_errors.classify(urllib.error.URLError("x")) == "network"
    assert call_errors.classify(OSError("x")) == "network"


def test_everything_else_is_unknown_and_result_is_always_in_the_closed_set():
    for exc in (RuntimeError("lỗi mạng giả"), ValueError("x"), KeyError("k"), Exception()):
        assert call_errors.classify(exc) == "unknown", exc
    for exc in (_rejected(-101), _rejected(5), socket.timeout(), OSError(), RuntimeError()):
        assert call_errors.classify(exc) in call_errors.KINDS


def test_call_log_keeps_error_kind_only_when_given_and_never_loses_raw_detail():
    from zalo_pc_app import call_log
    log = call_log.CallLog()
    log.record_error("c1", "Ban A", "20001", "user", "11300 bi tu choi: status=114", kind="server_rejected")
    log.record_error("c2", "Ban B", "20002", "user", "loi cu khong co kind")
    b, a = log.snapshot()["calls"][:2]                      # snapshot: moi nhat truoc
    assert a["error_kind"] == "server_rejected" and a["detail"].startswith("11300")        # chuoi goc con nguyen de chan doan
    assert "error_kind" not in b and b["detail"] == "loi cu khong co kind"                 # khong kind thi giu hinh dang cu


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CALL-ERRORS TESTS PASSED")
