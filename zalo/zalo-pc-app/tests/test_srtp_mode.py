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


def test_default_is_sess_and_failure_flips_success_sticks():
    st, _ = _store()
    assert st.pick() == "sess"
    assert st.record("sess", False) == "off"       # sess hong -> thu off
    assert st.record("off", True) == "off"         # off duoc -> giu
    assert st.record("off", False) == "sess"       # off hong -> quay lai sess
    assert st.record("sess", True) == "sess"
    # Hong o che do KHONG phai che do uu tien thi khong doi y.
    assert st.record("key", False) == "sess"
    assert st.record("zzz", False) == "sess"       # che do la bi bo qua


def test_old_schema_preference_is_discarded():
    # File cu (hoc khi chi co hai che do off/key) ghim "key": khong duoc giu.
    d = tempfile.mkdtemp()
    path = os.path.join(d, "srtp_mode.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"preferred": "key", "history": [
            {"mode": "off", "ok": False, "at": 1}]}, fh)
    st = srtp_mode.SrtpModeStore(path)
    assert st.pick() == "sess"
    assert st.snapshot()["history"][0]["mode"] == "off"   # lich su van giu
    st.record("sess", True)
    assert srtp_mode.SrtpModeStore(path).pick() == "sess"


def test_persists_and_survives_corrupt_file():
    st, d = _store()
    st.record("sess", False)
    again, _ = _store(d)
    assert again.pick() == "off"
    assert again.snapshot()["history"][-1]["ok"] is False
    path = os.path.join(d, "srtp_mode.json")
    for junk in ("{khong phai json", json.dumps({"preferred": "xyz"}),
                 json.dumps(["list"]), ""):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(junk)
        assert srtp_mode.SrtpModeStore(path).pick() == "sess", junk


def test_history_is_bounded_and_has_no_secret_fields():
    st, _ = _store()
    for i in range(60):
        st.record("sess", i % 2 == 0)
    snap = st.snapshot()
    assert len(snap["history"]) <= 20
    assert set(snap["history"][0]) == {"mode", "ok", "at"}


class _FakeEndpoints:
    def __init__(self, counters, sample=None):
        self.counters = counters
        self.sample = sample

    def active_record(self, call_id):
        c, smp = self.counters, self.sample
        return {"transport": types.SimpleNamespace(
            status=lambda: {"counters": c, "rx_sample": smp})}


def _judge(mode, counters, answered=100.0, ended=110.0, source="auto",
           sample=None):
    st, _ = _store()
    sv.STATE = types.SimpleNamespace(srtp_modes=st)
    sv._CALL_SRTP["7"] = (mode, source)
    real = sv.media_endpoints.ENDPOINTS
    sv.media_endpoints.ENDPOINTS = _FakeEndpoints(counters, sample)
    try:
        sv._evaluate_srtp_outcome({"call_id": 7, "answered_at": answered,
                                   "ended_at": ended})
    finally:
        sv.media_endpoints.ENDPOINTS = real
    return st


def test_answered_but_nothing_received_is_weak_evidence_and_does_not_flip_the_proven_default():
    """Su co 11/11: mot cuoc AI im lang (khong nhan goi nao) khong duoc lam sess bi bo (cuoc ke tiep gui RTP tran, dien thoai khong nghe)."""
    st = _judge("sess", {"rtp_rx": 0, "rtp_rx_dropped": 0, "p2p_media_rx": 0})
    assert st.pick() == "sess"                                                    # mot lan yeu: khong doi
    last = st.snapshot()["history"][-1]
    assert last["mode"] == "sess" and last["ok"] is False and last["weak"] is True


def test_weak_failures_flip_only_after_three_in_a_row_a_success_resets_and_off_failure_returns_at_once():
    st, _ = _store()
    assert st.record("sess", False, strong=False) == "sess" and st.record("sess", False, strong=False) == "sess"
    assert st.record("sess", True) == "sess"                                      # thanh cong: dem lai tu dau
    assert st.record("sess", False, strong=False) == "sess" and st.record("sess", False, strong=False) == "sess"
    assert st.record("sess", False, strong=False) == "off"                        # ba lan yeu LIEN TIEP moi doi
    assert st.record("off", False, strong=False) == "sess"                        # che do khong mac dinh hong: ve mac dinh ngay
    assert st.record("sess", False, strong=True) == "off"                         # that bai MANH (goi toi, HMAC sai): doi ngay


def test_key_mode_dropped_packets_do_not_count_as_received():
    # Toan bo goi bi loai (HMAC sai) = khong phai bang chung cua che do dung.
    st = _judge("sess", {"rtp_rx": 40, "rtp_rx_dropped": 40, "p2p_media_rx": 0})
    assert st.pick() == "off"                                                     # goi toi nhung HMAC sai: that bai MANH, doi ngay
    st = _judge("sess", {"rtp_rx": 40, "rtp_rx_dropped": 0, "p2p_media_rx": 0})
    assert st.pick() == "sess" and st.snapshot()["history"][-1]["ok"] is True


def test_off_mode_needs_plain_looking_payloads_to_count_as_success():
    rx = {"rtp_rx": 40, "rtp_rx_dropped": 0}
    # Ben kia gui ban ma: o che do "off" van "nhan duoc" 40 goi nhung byte
    # dau ngau nhien -> that bai, lan sau auto thu "key".
    st = _judge("off", rx, sample={"n": 20, "toc_agree": 0.1, "head": []})
    assert st.pick() == "sess" and st.snapshot()["history"][-1]["ok"] is False
    # Opus tran (byte dau on dinh) -> thanh cong, giu "off".
    st = _judge("off", rx, sample={"n": 20, "toc_agree": 0.95, "head": []})
    assert st.pick() == "off" and st.snapshot()["history"][-1]["ok"] is True
    # Qua it mau -> chua ket luan, KHONG ghi nho (khoi khoa nham vao "off").
    st = _judge("off", rx, sample={"n": 3, "toc_agree": 1.0, "head": []})
    assert st.snapshot()["history"] == [] and st.pick() == "sess"
    # Che do "sess": xac thuc HMAC la bang chung du, khong can mau.
    st = _judge("sess", rx, sample=None)
    assert st.pick() == "sess" and st.snapshot()["history"][-1]["ok"] is True


def test_short_or_unanswered_calls_are_not_judged():
    for kw in (dict(answered=100.0, ended=103.0),      # nghe 3 s: qua ngan
               dict(answered=None, ended=110.0)):      # chua nghe may
        st = _judge("off", {"rtp_rx": 0}, **kw)
        assert st.snapshot()["history"] == [], kw
        assert st.pick() == "sess"
    assert "7" not in sv._CALL_SRTP                    # va khong ro ri bo nho


def test_forced_mode_beats_auto_and_env():
    st, _ = _store()
    st.record("sess", False)                           # auto se chon "off"
    sv.STATE = types.SimpleNamespace(srtp_modes=st)
    old = os.environ.pop("ZALO_PC_SRTP", None)
    try:
        assert sv._srtp_mode_for_call({}) == ("off", "auto")
        assert sv._srtp_mode_for_call({"srtp": "OFF"}) == ("off", "forced")
        assert sv._srtp_mode_for_call({"srtp": "Sess"}) == ("sess", "forced")
        os.environ["ZALO_PC_SRTP"] = "key"
        assert sv._srtp_mode_for_call({}) == ("key", "forced")
        assert sv._srtp_mode_for_call({"srtp": "off"}) == ("off", "forced")
        os.environ["ZALO_PC_SRTP"] = "bậy"
        assert sv._srtp_mode_for_call({}) == ("off", "auto")
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
