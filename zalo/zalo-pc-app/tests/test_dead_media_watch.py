"""Cuộc gọi ĐẾN không nhận gói nào từ điện thoại sau khi nghe máy -> tự kết thúc (dead_media); có gói thì giữ nguyên."""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import server  # noqa: E402


class _Calls:
    def __init__(self, status):
        self.status = status

    def snapshot(self):
        return {"calls": [{"call_id": 7, "status": self.status}], "active": None}


class _State:
    def __init__(self, status="answered"):
        self.calls, self.session = _Calls(status), {"uid": "1"}


def _run(counters, status="answered", delay=5.0):
    ended, slept = [], []
    st_orig, tr_orig, term_orig, thread_cls = server.STATE, server._transport_for_call, server._terminate_call, server.threading.Thread
    server.STATE = _State(status)
    server._transport_for_call = lambda cid: type("T", (), {"counters": counters})() if counters is not None else None
    server._terminate_call = lambda cid, reason, sess, *a, **k: ended.append((cid, reason))

    class Sync:
        def __init__(self, target=None, **kw):
            self.t = target

        def start(self):
            self.t()
    server.threading.Thread = Sync
    try:
        server._watch_dead_media(7, delay=delay, sleep=lambda s: slept.append(s))
    finally:
        server.STATE, server._transport_for_call, server._terminate_call, server.threading.Thread = st_orig, tr_orig, term_orig, thread_cls
    return ended, slept


def test_ends_call_when_phone_sent_nothing():
    ended, slept = _run({"rtp_rx": 0, "rtcp_rx": 0, "video_rx": 0})
    assert ended == [(7, "dead_media")] and slept == [5.0]


def test_keeps_call_when_any_packet_arrived():
    for k in ("rtp_rx", "video_rx"):
        ended, _ = _run({"rtp_rx": 0, "rtcp_rx": 0, "video_rx": 0, k: 3})
        assert ended == [], k


def test_dropped_rtp_and_rtcp_only_count_as_dead():
    # cuộc 14/11 23:14: 12 gói RTP đều bị loại (SRTP hỏng) + RTCP, không có tiếng nào giải mã được
    ended, _ = _run({"rtp_rx": 12, "rtp_rx_dropped": 12, "rtcp_rx": 2, "video_rx": 0})
    assert ended == [(7, "dead_media")]
    ended, _ = _run({"rtp_rx": 275, "rtp_rx_dropped": 9, "rtcp_rx": 25})
    assert ended == []


def test_ignores_calls_not_answered_anymore_or_without_transport_or_disabled():
    assert _run({"rtp_rx": 0}, status="ended")[0] == []
    assert _run(None)[0] == []
    ended, slept = _run({"rtp_rx": 0}, delay=0)
    assert ended == [] and slept == []                      # 0 = tắt


def test_watch_of_an_earlier_answer_never_ends_a_later_call_with_the_same_id():
    """CI 14/11: bộ canh của test/lần nghe trước thức dậy giữa cuộc gọi SAU dùng lại cùng call_id và kết thúc nhầm (dead_media sau 0,15 s). Mỗi bộ canh
    chỉ được tác động lên ĐÚNG lần nghe máy (answered_at) mà nó được tạo cho."""
    ended = []
    answers = [{"call_id": 7, "status": "answered", "answered_at": 100.0}]

    class Calls:
        def snapshot(self):
            return {"calls": list(answers), "active": None}

    class St:
        calls, session = Calls(), {"uid": "1"}
    st_orig, tr_orig, term_orig, thread_cls = server.STATE, server._transport_for_call, server._terminate_call, server.threading.Thread
    server.STATE = St()
    server._transport_for_call = lambda cid: type("T", (), {"counters": {"rtp_rx": 0}})()
    server._terminate_call = lambda cid, reason, sess, *a, **k: ended.append((cid, reason))
    started = []

    class Deferred:
        def __init__(self, target=None, **kw):
            self.t = target

        def start(self):
            started.append(self.t)
    server.threading.Thread = Deferred
    try:
        server._watch_dead_media(7, delay=5.0, sleep=lambda s: None)       # bộ canh cho lần nghe máy answered_at=100
        answers[:] = [{"call_id": 7, "status": "answered", "answered_at": 250.0}]      # sau đó cùng call_id được nghe LẠI (cuộc mới)
        started[0]()                                                       # bộ canh cũ thức dậy
        assert ended == [], "bộ canh cũ không được kết thúc cuộc gọi mới"
        answers[:] = [{"call_id": 7, "status": "answered", "answered_at": 100.0}]      # cùng lần nghe máy: vẫn kết thúc như thường
        started[0]()
        assert ended == [(7, "dead_media")]
    finally:
        server.STATE, server._transport_for_call, server._terminate_call, server.threading.Thread = st_orig, tr_orig, term_orig, thread_cls


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL DEAD-MEDIA TESTS PASSED")
