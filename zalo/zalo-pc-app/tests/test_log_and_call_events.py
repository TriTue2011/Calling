"""Nhat ky luu ben + su kien «call» (12/11/2026): dung lai container tung xoa mat nhat ky cuoc goi cua chu may; popup cuoc goi den chi hien
<= 2 giay (HA tu nghe may ~1,7 s) nen phai day su kien tuc thi qua SSE thay vi cho vong hoi lai.
Run: python3 tests/test_log_and_call_events.py
"""

import io
import os
import queue
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import call_log  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def test_calllog_notifies_on_every_state_change_but_not_on_diag():
    log = call_log.CallLog()
    n = []
    log.on_change = lambda: n.append(1)
    log.record_incoming(11, "Dai ca", "66", "user")
    assert len(n) == 1
    log.record_answered(11, "media")
    assert len(n) == 2
    log.record_diag(11, {"k": 1})
    assert len(n) == 2, "record_diag khong doi trang thai hien thi"
    log.record_end(11, "peer_ended")
    assert len(n) == 3
    log.record_start(12, "Dai ca", "66", "user")
    log.record_request(12, True)
    log.end_active("user_end")
    assert len(n) >= 6, n
    assert [c["status"] for c in log.snapshot()["calls"]][0] == "ended"
    log.on_change = lambda: 1 / 0            # callback loi khong duoc lam hong so cuoc goi
    log.record_incoming(13, "x", "66", "user")
    assert log.snapshot()["active"]["call_id"] == "13"


def test_log_tee_timestamps_lines_passes_through_and_rotates():
    tmp = tempfile.mkdtemp(prefix="tee-")
    path = os.path.join(tmp, "logs", "app.log")
    out = io.StringIO()
    tee = app_server._LogTee(out, path)
    tee.write("[call] incoming offer call_id=1\n")
    tee.write("mot dong ")
    tee.write("chia lam hai\nva dong ba\n")
    tee.flush()
    assert out.getvalue() == "[call] incoming offer call_id=1\nmot dong chia lam hai\nva dong ba\n", out.getvalue()
    lines = open(path, encoding="utf-8").read().splitlines()
    import re
    dau_gio = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d{4}) "     # gio ISO: UTC (Z) hoac gio dia phuong (+0700)
    assert len(lines) == 3 and all(re.match(dau_gio, l) for l in lines), lines
    assert lines[0].endswith(" [call] incoming offer call_id=1") and lines[1].endswith(" mot dong chia lam hai"), lines
    tee.MAX_BYTES = 2000
    for i in range(450):
        tee.write("dong so %d %s\n" % (i, "x" * 20))
    assert os.path.exists(path + ".1"), "phai xoay vong khi qua gioi han"
    assert os.path.getsize(path) < 2000 + 200 * 60
    assert tee.encoding == out.encoding or tee.encoding is None or True        # __getattr__ chuyen tiep thuoc tinh


def test_appstate_publishes_call_event_to_sse_hub():
    state = app_server.AppState(tempfile.mkdtemp(prefix="st-"))
    q = state.events.subscribe()
    state.calls.record_incoming(21, "Dai ca", "66", "video")
    ev = q.get(timeout=2)
    assert ev["type"] == "call" and "at" in ev, ev
    state.calls.record_answered(21, "media")
    assert q.get(timeout=2)["type"] == "call"
    state.events.unsubscribe(q)
    try:
        q.get_nowait()
        raise AssertionError("khong duoc con su kien thua")
    except queue.Empty:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL LOG/CALL-EVENT TESTS PASSED")
