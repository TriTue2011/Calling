"""Che do SRTP "auto": nho cach nao tung nhan duoc goi that tu ben kia.

Khong tin tuyet doi vao zca-js: hai che do (RTP tran / khoa tu sinh) chua
duoc may that xac nhan, nen server tu hoc tu ket qua cuoc goi da nghe may.
"""

import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

from zalo_pc_app import server as sv  # noqa: E402
from zalo_pc_app import srtp_mode  # noqa: E402


def _store(tmp=None):
    d = tmp or tempfile.mkdtemp()
    return srtp_mode.SrtpModeStore(os.path.join(d, "srtp_mode.json")), d


def test_default_is_off_and_failure_flips_success_sticks():
    st, _ = _store()
    assert st.pick() == "off"
    assert st.record("off", False) == "key"        # off hong -> thu key
    assert st.record("key", True) == "key"         # key duoc -> giu
    assert st.record("key", False) == "off"        # key hong -> quay lai off
    assert st.record("off", True) == "off"
    # Hong o che do KHONG phai che do uu tien thi khong doi y.
    assert st.record("key", False) == "off"
    assert st.record("zzz", False) == "off"        # che do la bi bo qua


def test_persists_and_survives_corrupt_file():
    st, d = _store()
    st.record("off", False)
    again, _ = _store(d)
    assert again.pick() == "key"
    assert again.snapshot()["history"][-1]["ok"] is False
    path = os.path.join(d, "srtp_mode.json")
    for junk in ("{khong phai json", json.dumps({"preferred": "xyz"}),
                 json.dumps(["list"]), ""):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(junk)
        assert srtp_mode.SrtpModeStore(path).pick() == "off", junk


def test_history_is_bounded_and_has_no_secret_fields():
    st, _ = _store()
    for i in range(60):
        st.record("off", i % 2 == 0)
    snap = st.snapshot()
    assert len(snap["history"]) <= 20
    assert set(snap["history"][0]) == {"mode", "ok", "at"}


class _FakeEndpoints:
    def __init__(self, counters):
        self.counters = counters

    def active_record(self, call_id):
        c = self.counters
        return {"transport": types.SimpleNamespace(
            status=lambda: {"counters": c})}


def _judge(mode, counters, answered=100.0, ended=110.0, source="auto"):
    st, _ = _store()
    sv.STATE = types.SimpleNamespace(srtp_modes=st)
    sv._CALL_SRTP["7"] = (mode, source)
    real = sv.media_endpoints.ENDPOINTS
    sv.media_endpoints.ENDPOINTS = _FakeEndpoints(counters)
    try:
        sv._evaluate_srtp_outcome({"call_id": 7, "answered_at": answered,
                                   "ended_at": ended})
    finally:
        sv.media_endpoints.ENDPOINTS = real
    return st


def test_answered_but_nothing_received_marks_mode_bad():
    st = _judge("off", {"rtp_rx": 0, "rtp_rx_dropped": 0, "p2p_media_rx": 0})
    assert st.pick() == "key"
    assert st.snapshot()["history"][-1] == {
        "mode": "off", "ok": False, "at": st.snapshot()["history"][-1]["at"]}


def test_key_mode_dropped_packets_do_not_count_as_received():
    # Toan bo goi bi loai (HMAC sai) = khong phai bang chung cua che do dung.
    st = _judge("key", {"rtp_rx": 40, "rtp_rx_dropped": 40, "p2p_media_rx": 0})
    assert st.pick() == "off"
    st = _judge("key", {"rtp_rx": 40, "rtp_rx_dropped": 0, "p2p_media_rx": 0})
    assert st.pick() == "key" and st.snapshot()["history"][-1]["ok"] is True


def test_short_or_unanswered_calls_are_not_judged():
    for kw in (dict(answered=100.0, ended=103.0),      # nghe 3 s: qua ngan
               dict(answered=None, ended=110.0)):      # chua nghe may
        st = _judge("off", {"rtp_rx": 0}, **kw)
        assert st.snapshot()["history"] == [], kw
        assert st.pick() == "off"
    assert "7" not in sv._CALL_SRTP                    # va khong ro ri bo nho


def test_forced_mode_beats_auto_and_env():
    st, _ = _store()
    st.record("off", False)                            # auto se chon "key"
    sv.STATE = types.SimpleNamespace(srtp_modes=st)
    old = os.environ.pop("ZALO_PC_SRTP", None)
    try:
        assert sv._srtp_mode_for_call({}) == ("key", "auto")
        assert sv._srtp_mode_for_call({"srtp": "OFF"}) == ("off", "forced")
        os.environ["ZALO_PC_SRTP"] = "key"
        assert sv._srtp_mode_for_call({}) == ("key", "forced")
        assert sv._srtp_mode_for_call({"srtp": "off"}) == ("off", "forced")
        os.environ["ZALO_PC_SRTP"] = "bậy"
        assert sv._srtp_mode_for_call({}) == ("key", "auto")
    finally:
        os.environ.pop("ZALO_PC_SRTP", None)
        if old is not None:
            os.environ["ZALO_PC_SRTP"] = old


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL SRTP MODE TESTS PASSED")
