"""Nhật ký sức khoẻ + giám sát thu hồi phiên. Không gọi Zalo thật. Chạy: python3 tests/test_account_health.py"""
import json
import os
import stat
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from zalo_pc_app import account_health  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import session as session_mod  # noqa: E402


def _state(tmp):
    state = app_server.AppState(tmp)
    sess = session_mod.new_session("dev-1", "testhost")
    sess.update({"uid": "10001", "dkey": "d", "zpw_sek": "sek-test", "zpw_kt": "k", "zpw_enk": "e",
                 "poll_msg_urls": [], "poll_ctl_urls": [], "status": session_mod.STATUS_LOGGED_IN})
    state.store.save(sess)
    state.session = sess
    return state


def _poller(**kw):
    return types.SimpleNamespace(**dict({"kicked_out": False, "auth_failed": False, "last_error": "", "stop": lambda: None}, **kw))


def test_health_log_persists_rotates_and_is_private():
    tmp = tempfile.mkdtemp(prefix="health-")
    path = os.path.join(tmp, "health.jsonl")
    log = account_health.HealthLog(path, max_events=5)
    for i in range(8):
        log.record("note", "n%d" % i)
    log.record("session_end", "remote_revoked")
    assert [e["detail"] for e in log.summary(3)["events"]][-1] == "remote_revoked"
    assert log.summary()["last_session_end"]["detail"] == "remote_revoked"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    again = account_health.HealthLog(path, max_events=5)                      # khởi động lại: đọc lại từ đĩa, chỉ giữ 5 sự kiện cuối
    assert again.last("session_end")["detail"] == "remote_revoked"
    assert len(again.summary(99)["events"]) == 5
    with open(path, "w", encoding="utf-8") as fh:                              # dòng hỏng không làm sập
        fh.write("khong phai json\n" + json.dumps({"t": 1.0, "kind": "start", "detail": "v"}) + "\n")
    assert account_health.HealthLog(path).last("start")["detail"] == "v"


def test_kicked_out_ends_session_keeps_messages_and_records_reason():
    state = _state(tempfile.mkdtemp(prefix="rev-"))
    state.message_store.set_account("10001")
    state.message_store.record("user", "20001", {"id": "m1", "client_id": "c1", "text": "xin chao", "time": 1, "kind": "text", "is_self": False,
                                                 "sender_id": "20001", "direction": "in"})
    state.sync = _poller(kicked_out=True)
    assert state.check_revoked() == "remote_revoked"
    assert state.session is None and not state.store.exists()                    # phiên bị xoá, QR hiện lại
    assert "Quét QR" in state.qr_error
    assert state.health.last("session_end")["detail"] == "remote_revoked"
    assert len(state.message_store.messages_for("user", "20001")) == 1             # tin vẫn còn (wipe=False)
    assert state.check_revoked() == ""                                           # đã thoát: lần sau không làm gì


def test_auth_failed_on_ctrl_channel_ends_session_with_session_rejected():
    state = _state(tempfile.mkdtemp(prefix="rev-"))
    state.sync = _poller()
    state.ctrl = _poller(auth_failed=True)
    assert state.check_revoked() == "session_rejected"
    assert state.health.last("session_end")["detail"] == "session_rejected"


def test_healthy_or_stopped_channels_never_end_the_session():
    state = _state(tempfile.mkdtemp(prefix="rev-"))
    assert state.check_revoked() == ""                                           # chưa có kênh nào
    state.sync = _poller()                                                       # poller không chạy: "stopped", không phải thu hồi
    assert state.check_revoked() == "" and state.session is not None
    state2 = app_server.AppState(tempfile.mkdtemp(prefix="rev-"))                # chưa đăng nhập
    state2.sync = _poller(kicked_out=True)
    assert state2.check_revoked() == "" and state2.health.last("session_end") is None


def test_explicit_logout_is_recorded_and_status_carries_health_summary():
    state = _state(tempfile.mkdtemp(prefix="rev-"))
    state.logout()
    assert state.health.last("session_end")["detail"] == "local_logout"
    h = state.public_status()["health"]
    assert h["last_session_end"]["detail"] == "local_logout" and h["counts"]["start"] == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL ACCOUNT-HEALTH TESTS PASSED")
