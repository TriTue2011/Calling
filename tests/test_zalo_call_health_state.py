"""Trạng thái sức khoẻ tài khoản từ /api/status. Nạp theo đường dẫn (không kéo homeassistant)."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")
spec = importlib.util.spec_from_file_location("zc_health_state", os.path.join(BASE, "health_state.py"))
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)


def test_online_degraded_logged_out():
    assert hs.account_state({"login": True, "sync": "running", "ctrl": "running"}) == "online"
    for sync, ctrl in (("stopped", "running"), ("running", "no_endpoints"), ("kicked_out", "running"), ("running", None)):
        assert hs.account_state({"login": True, "sync": sync, "ctrl": ctrl}) == "degraded", (sync, ctrl)
    for bad in ({"login": False, "sync": "running", "ctrl": "running"}, {}, None, "x", {"sync": "running"}):
        assert hs.account_state(bad) == "logged_out", bad


def test_attributes_name_the_reason_and_tolerate_missing_or_bad_health():
    st = {"login": False, "sync": "logged_out", "ctrl": "logged_out", "keepalive": {"state": "expired"},
          "health": {"last_session_end": {"t": 5.0, "detail": "remote_revoked"},
                     "events": [{"t": 1.0, "kind": "start", "detail": "v"}, "bo qua", {"t": 2.0, "kind": "session_end", "detail": "remote_revoked"}]}}
    a = hs.attributes(st)
    assert a["last_session_end"].startswith("Bị thu hồi từ xa") and a["last_session_end_at"] == 5.0 and a["keepalive"] == "expired"
    assert [e["kind"] for e in a["recent_events"]] == ["start", "session_end"]
    assert hs.attributes({"health": {"last_session_end": {"detail": "ly_do_la"}}})["last_session_end"] == "ly_do_la"
    for bad in (None, {}, {"health": "x"}, {"health": {"events": None}}, {"keepalive": "x"}):
        assert isinstance(hs.attributes(bad), dict) and "recent_events" in hs.attributes(bad), bad
