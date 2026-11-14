"""Sự kiện cuộc gọi ĐẾN cũ do Zalo phát lại sau khi app khởi động lại (14/11/2026) phải bị bỏ qua — không tạo «cuộc gọi đến» mới, không nghe máy tự động, không webhook.
Run: python3 tests/test_incoming_stale.py"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_server import MockZalo  # noqa: E402
from test_call_cases import _event, _mock, _api  # noqa: E402
from test_call_ringing import _run  # noqa: E402
from test_call_incoming_zca import _capture_call_webhooks  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app.calls import incoming  # noqa: E402


def _with_ts(ev, age_s):
    ev = dict(ev)
    ev["data"] = {"callId": str(ev["call_id"]), "ts": str(int((time.time() - age_s) * 1000))}
    return ev


def test_event_age_reads_ms_from_data_or_params_and_ignores_junk():
    now = 2_000_000_000.0
    assert abs(incoming.event_age_seconds({"data": {"ts": "1999999000000"}}, now=now) - 1000) < 1
    assert abs(incoming.event_age_seconds({"data": {"params": {"ts": 1999999900000}}}, now=now) - 100) < 1
    assert abs(incoming.event_age_seconds({"data": '{"params": "{\\"ts\\": 1999999990000}"}'}, now=now) - 10) < 1
    for junk in ({}, {"data": None}, {"data": {"ts": ""}}, {"data": {"params": {"ts": 1}}}, {"data": "khong json"}, {"data": {"ts": "abc"}}):
        assert incoming.event_age_seconds(junk, now=now) is None, junk


def test_replayed_old_request_is_ignored_but_fresh_and_undated_are_accepted():
    mock = _mock()

    def check(base, mock, endpoints):
        sent = _capture_call_webhooks(app_server.STATE)
        old = _with_ts(_event(1763900001), 600)             # 10 phút trước = phát lại sau khởi động
        app_server.STATE._on_ctrl_call_event(old)
        time.sleep(0.4)
        calls = _api(base, "GET", "/api/calls")[1]["calls"]
        assert not any(str(c["call_id"]) == "1763900001" for c in calls), calls
        assert not [p for p in sent if p["type"] == "call.incoming"], sent
        app_server.STATE._on_ctrl_call_event(_with_ts(_event(1763900002), 5))    # mới 5 s: nhận
        app_server.STATE._on_ctrl_call_event(_event(1763900003))                 # không có ts: nhận như cũ
        time.sleep(0.6)
        ids = {str(c["call_id"]) for c in _api(base, "GET", "/api/calls")[1]["calls"]}
        assert "1763900002" in ids and "1763900003" in ids, ids

    _run(mock, check)


def test_threshold_zero_disables_the_filter():
    mock = _mock()
    old_v = incoming.INCOMING_MAX_AGE_SECONDS

    def check(base, mock, endpoints):
        incoming.INCOMING_MAX_AGE_SECONDS = 0
        app_server.STATE._on_ctrl_call_event(_with_ts(_event(1763900011), 600))
        time.sleep(0.5)
        ids = {str(c["call_id"]) for c in _api(base, "GET", "/api/calls")[1]["calls"]}
        assert "1763900011" in ids, ids

    try:
        _run(mock, check)
    finally:
        incoming.INCOMING_MAX_AGE_SECONDS = old_v


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("ALL INCOMING STALE TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
