"""Loi goi 114 (2026-11-05 17:31, chay that): bam goi mot ban be 1-1
tren ban cb57faa -> dong ho chay toi 00:03 roi bao "Loi goi:
response inner error_code=114 Tham so khong hop le". Request toi
noi (envelope dung, danh ba 60/6 chay that) nen nghi pham la BODY
cua requestcall (11300).

Nguyen nhan goc (bundle PC that, compact-app-pc, lop wZ +
ZaloCall.exe — xem §7k bao-cao.md):
  (1) typeRequest=0: khong ton tai trong tu vung loai cuoc goi cua
      client that — makeCall gui len native: 1-1 audio=1, 1-1
      video=3, nhom audio=5, nhom video=6; signal 401 mang gia tri
      do ve thanh `type` -> typeRequest. Code cu gui 0.
  (2) callId dang CHUOI 13 chu so (String(Date.now())): native luu
      callId dang uint32 (`_initCallConfig ... callId = %u`), nen
      tren day phai la JSON NUMBER trong khoang uint32.
codec "[]" GIU NGUYEN: do la fallback co ghi trong chinh code client
that (codec: n ?? "[]") khi native khong dua danh sach codec; calleeId
GIU NGUYEN dang chuoi: threadId 19 chu so vuot qua gioi han so
nguyen an toan cua JS (2**53) nen renderer that BUOC phai mang no
dang chuoi neu khong muon mat chinh xac.

Mock tai hien loi that: body cu -> inner 114 (khong phai assertion
cua mock), body moi -> qua. Cac test nay PHAI FAIL o code cu
(typeRequest 0 / callId chuoi) va PASS o code moi.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import signaling  # noqa: E402

CALL_ID = 1762345678  # epoch seconds — fits uint32, like the real client


def _sig(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    t = app_server.make_transport("sek-test")
    return signaling.Signaling(t, "dev-1", TEST_SESSION_KEY)


def _expect_114(fn):
    """Run fn(); it must raise RuntimeError carrying the real
    server's inner 114 text, exactly as the live failure showed."""
    try:
        fn()
    except RuntimeError as exc:
        assert "inner error_code=114" in str(exc), exc
        assert "Tham số không hợp lệ" in str(exc), exc
        return
    raise AssertionError("expected inner error_code=114, call succeeded")


def test_old_body_1_1_gets_114():
    """Body cu y het ban cb57faa: typeRequest 0 + callId chuoi 13 chu
    so -> server that tra inner 114. Day la tai hien loi user gap."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        _expect_114(lambda: sig.request_call("20001", "1762345678901",
                                             None, 0))
    finally:
        mock.stop()


def test_new_body_1_1_ok():
    """Body moi: typeRequest 1 (1-1 audio) + callId so uint32 -> qua,
    va body gui di khop client that (calleeId chuoi, codec "[]")."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        data = sig.request_call("20001", CALL_ID, None, 1)
        assert data["body"]["calleeId"] == "20001", data
        assert data["body"]["callId"] == CALL_ID, data
        assert isinstance(data["body"]["callId"], int), data
        assert data["body"]["typeRequest"] == 1, data
        assert data["body"]["codec"] == "[]", data
        assert data["body"]["imei"] == "dev-1", data
    finally:
        mock.stop()


def test_type_request_0_alone_gets_114():
    """Chi rieng typeRequest 0 (callId da dung) cung du de 114 —
    chung minh 0 la gia tri khong hop le, khong phai do callId."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        _expect_114(lambda: sig.request_call("20001", CALL_ID, None, 0))
    finally:
        mock.stop()


def test_string_call_id_alone_gets_114():
    """Chi rieng callId chuoi (typeRequest da dung) cung du de 114 —
    chung minh callId phai la so JSON, khong phai chuoi."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        _expect_114(lambda: sig.request_call("20001", str(CALL_ID),
                                             None, 1))
    finally:
        mock.stop()


def test_old_body_group_gets_114():
    """Goi nhom cu: typeRequest 0 + callId chuoi -> 114 (giong 1-1)."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        _expect_114(lambda: sig.request_call_group(
            "30001", "call-g1", 0, None, ["20001", "20002"]))
    finally:
        mock.stop()


def test_new_body_group_ok():
    """Goi nhom moi: typeRequest 5 (nhom audio) + callId so -> qua,
    body dung dang {groupId, callId, typeRequest, data, partners}."""
    mock = MockZalo().start()
    try:
        sig = _sig(mock)
        data = sig.request_call_group("30001", CALL_ID, 5, None,
                                      ["20001", "20002"])
        assert data["body"]["groupId"] == "30001", data
        assert data["body"]["callId"] == CALL_ID, data
        assert isinstance(data["body"]["callId"], int), data
        assert data["body"]["typeRequest"] == 5, data
        assert data["body"]["partners"] == ["20001", "20002"], data
        assert "imei" not in data["body"], data  # bundle: no imei
    finally:
        mock.stop()


def test_server_normalizes_old_ui_payload():
    """Phong thu o server: UI cu gui call_id chuoi mili-giay +
    type_request 0 thi server phai chuan hoa (callId so uint32,
    typeRequest 1) truoc khi gui Zalo, va tra ve call_id hieu luc
    de UI dung cung id do cho /api/call/end.

    (2026-11-09, deep comparison §5.1): callId khong con lay tu UI
    nua — server cap tu counter noi bo bat dau 1 (nhu engine dung
    `lock xadd`), bo qua moi gia tri UI gui len (epoch seconds,
    chuoi mili-giay, rac, thieu, vuot uint32)."""
    from zalo_pc_app.server import _normalize_call_id, _type_request_for

    app_server._CALL_ID_COUNTER = 0
    # Bat ky gia tri UI nao cung cho ra id counter tiep theo.
    assert _normalize_call_id(str(int(time.time() * 1000))) == 1
    assert _normalize_call_id(1762345678) == 2
    assert _normalize_call_id("c9") == 3
    assert _normalize_call_id("") == 4
    assert _normalize_call_id(None) == 5
    assert _normalize_call_id(2 ** 32) == 6
    assert _normalize_call_id(0) == 7
    assert _normalize_call_id(-5) == 8
    # Hai tap lien tiep khong bao gio trung id.
    app_server._CALL_ID_COUNTER = 0
    first = _normalize_call_id(1762345678)
    second = _normalize_call_id(1762345678)
    assert (first, second) == (1, 2), (first, second)
    assert _type_request_for("user") == 1
    assert _type_request_for("group") == 5
    assert _type_request_for(None) == 1
    assert _type_request_for("") == 1


if __name__ == "__main__":
    failed = []
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed.append(fn.__name__)
            print("FAIL", fn.__name__, exc)
    print("%d/%d tests passed" % (len(tests) - len(failed), len(tests)))
    raise SystemExit(1 if failed else 0)
