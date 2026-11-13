"""Bao «camera bat» phai duoc gui lai nhieu lan trong cuoc goi (13/11: gui mot lan thi dien thoai giu «dang tat camera»).
Chay: python3 tests/test_camera_state_repeat.py"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import server  # noqa: E402


def _run(senders_after, delays=(1.0, 2.0), keep=9.0):
    sent, sleeps, done = [], [], threading.Event()
    sender = object()
    server.VIDEO_SENDERS["777"] = sender
    orig_async, orig_thread = server._send_camera_state_async, server._thread_of_call
    server._send_camera_state_async = lambda cid, tid, on: sent.append((cid, tid, on))
    server._thread_of_call = lambda cid: "peer"
    try:
        def fake_sleep(sec):
            sleeps.append(sec)
            if len(sleeps) == senders_after:                       # sau N lan ngu thi hinh dung
                server.VIDEO_SENDERS.pop("777", None)
        t = {}
        orig_thread_cls = server.threading.Thread

        class Sync:                                                 # chay dong bo de test khong phu thuoc thoi gian
            def __init__(self, target=None, **kw): t["f"] = target

            def start(self): t["f"](); done.set()
        server.threading.Thread = Sync
        try:
            server._repeat_camera_state("777", sender, delays=delays, keep=keep, sleep=fake_sleep)
        finally:
            server.threading.Thread = orig_thread_cls
        assert done.is_set()
    finally:
        server._send_camera_state_async, server._thread_of_call = orig_async, orig_thread
        server.VIDEO_SENDERS.pop("777", None)
    return sent, sleeps


def test_resends_with_growing_gaps_then_steady_until_video_stops():
    sent, sleeps = _run(senders_after=4)
    assert sleeps == [1.0, 2.0, 9.0, 9.0], sleeps                  # 2 lan thua dan roi theo nhip `keep`
    assert sent == [("777", "peer", True)] * 3, sent               # 3 lan gui: lan ngu thu 4 thay hinh da dung -> thoat, khong gui


def test_stops_immediately_when_video_already_stopped():
    sent, sleeps = _run(senders_after=1)
    assert sleeps == [1.0] and sent == [], (sleeps, sent)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CAMERA-STATE-REPEAT TESTS PASSED")
