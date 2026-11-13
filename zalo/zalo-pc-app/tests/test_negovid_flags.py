"""Lệnh nghe máy kiểu gọn phải lặp lại cờ negoVidQual của bên gọi (thiếu thì điện thoại báo «Phiên bản chưa hỗ trợ chuyển video»).
Run: python3 tests/test_negovid_flags.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import incoming_call  # noqa: E402


def test_copies_negovidqual_from_offer_when_missing():
    ext = {"callType": 0, "numServers": 0}
    out = incoming_call.copy_negotiation_flags(ext, {"negoVidQual": 1, "sP2P": 1})
    assert out is ext and ext == {"callType": 0, "numServers": 0, "negoVidQual": 1}, ext      # chi lap lai co thuong luong, khong keo sP2P


def test_keeps_own_value_and_tolerates_missing_or_bad_offer():
    ext = {"negoVidQual": 0}
    incoming_call.copy_negotiation_flags(ext, {"negoVidQual": 1})
    assert ext == {"negoVidQual": 0}, "da co thi giu gia tri cua ta"
    for offer in (None, {}, "x", [1]):
        e = {"a": 1}
        incoming_call.copy_negotiation_flags(e, offer)
        assert e == {"a": 1}, offer
    assert incoming_call.copy_negotiation_flags(None, {"negoVidQual": 1}) is None


def test_video_offer_gets_video_calltype_in_answer_and_voice_stays_voice():
    ext = {"callType": 0}
    incoming_call.copy_negotiation_flags(ext, {"callType": 1})
    assert ext["callType"] == 1, "cuoc goi video den: tra loi callType 1 (20:49 12/11 ta tra 0)"
    ext = {"callType": 0}
    incoming_call.copy_negotiation_flags(ext, {"callType": 0})
    assert ext["callType"] == 0
    for bad in ({}, {"callType": None}, {"callType": "x"}, {"callType": 7}):
        e = {"callType": 0}
        incoming_call.copy_negotiation_flags(e, bad)
        assert e["callType"] == 0, bad


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL NEGOVID TESTS PASSED")
