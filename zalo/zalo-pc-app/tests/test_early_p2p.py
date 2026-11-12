"""Khai P2P kiểu engine thật trong lệnh nghe máy gọn: chỉ khi điện thoại cũng khai sP2P 1 kèm ứng viên và transport có ứng viên của ta.
Run: python3 tests/test_early_p2p.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import incoming_call  # noqa: E402


class FakeTransport:
    def __init__(self, mine):
        self.mine, self.set_to, self.hosts = mine, None, None

    def local_p2p_candidates(self, hosts):
        self.hosts = hosts
        return list(self.mine)

    def set_p2p_candidates(self, cands):
        self.set_to = cands


OFFER = {"sP2P": 1, "p2p": [{"ip": "25.5.54.99", "port": 41572, "type": 0}, "rac", {"ip": "9.200.39.87", "port": 4}], "negoVidQual": 1}


def test_declares_p2p_like_the_real_engine_when_phone_declares_it():
    ext = {"sP2P": 0, "p2p": [], "numServers": 0}
    tr = FakeTransport([{"ip": "172.16.10.200", "port": 50000, "type": 0}])
    n = incoming_call.early_p2p(ext, tr, OFFER, ["172.16.10.200"])
    assert n == 1 and ext["sP2P"] == 1 and ext["p2p"] == [{"ip": "172.16.10.200", "port": 50000, "type": 0}] and ext["numServers"] == 0, ext
    assert tr.set_to == [OFFER["p2p"][0], OFFER["p2p"][2]], "chi ung vien dang dict cua dien thoai (bo muc rac)"
    assert tr.hosts == ["172.16.10.200"]


def test_does_nothing_without_phone_p2p_or_without_our_candidates_or_bad_input():
    base = {"sP2P": 0, "p2p": []}
    for offer in (None, {}, {"sP2P": 0, "p2p": [{"ip": "1.1.1.1", "port": 1}]}, {"sP2P": 1, "p2p": []}, {"sP2P": 1, "p2p": ["x"]}):
        ext = dict(base)
        assert incoming_call.early_p2p(ext, FakeTransport([{"ip": "a", "port": 1}]), offer, []) == 0 and ext == base, offer
    ext = dict(base)
    assert incoming_call.early_p2p(ext, FakeTransport([]), OFFER, []) == 0 and ext == base, "ta khong co ung vien"
    assert incoming_call.early_p2p(dict(base), None, OFFER, []) == 0 and incoming_call.early_p2p(dict(base), object(), OFFER, []) == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL EARLY P2P TESTS PASSED")
