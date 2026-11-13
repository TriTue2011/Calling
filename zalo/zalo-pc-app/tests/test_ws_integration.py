"""Tích hợp kênh WebSocket vào app: cùng sự kiện từ WebSocket + poll chỉ xử lý một lần, định tuyến đúng bộ poll, WebSocket lỗi/tắt không ảnh hưởng poll,
chống trùng sự kiện cuộc gọi. Không gọi Zalo thật. Chạy: python3 tests/test_ws_integration.py"""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import ctrl_poll as ctrl_mod  # noqa: E402
from zalo_pc_app import event_dedup  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import session as session_mod  # noqa: E402
from zalo_pc_app import sync_poll as sync_mod  # noqa: E402


def _data():
    return {"msgs": [{"msgId": "pm1", "globalMsgId": "g1", "uidFrom": "20001", "idTo": "10001", "content": "Chao", "ts": 1762345700, "dName": "A", "msgType": 0}],
            "groupMsgs": [{"msgId": "gm1", "globalMsgId": "g2", "uidFrom": "20002", "idTo": "30001", "content": {"msg": "Nhom"}, "ts": 1762345710,
                           "dName": "B", "msgType": 0}], "lastActionId": "100"}


def _sync(delivered):
    p = sync_mod.SyncPoller(lambda *a, **k: (200, {}), ["https://x.invalid/lp"], TEST_SESSION_KEY, "10001",
                            on_message=lambda t, tid, m: delivered.append((t, tid, m["id"])), msg_timeout=30)
    return p


def test_sync_handle_decoded_dedups_between_websocket_and_poll_only_when_websocket_is_active():
    delivered, active = [], [False]
    p = _sync(delivered)
    p.dedup, p.dedup_check = event_dedup.EventDedup(), lambda: active[0]
    assert p.handle_decoded(_data(), via="ws") == 2                                    # WebSocket giao trước: xử lý cả 2 tin
    assert len(delivered) == 2
    active[0] = True
    p.handle_decoded(_data(), via="poll")                                              # poll giao lại cùng tin khi WebSocket đang chạy: bỏ
    assert len(delivered) == 2
    active[0] = False
    p.handle_decoded(_data(), via="poll")                                              # WebSocket không chạy: poll giữ nguyên hành vi cũ (Inbox lo chống trùng ở tầng server)
    assert len(delivered) == 4
    p.handle_decoded(_data(), via="ws")                                                # WebSocket giao lại tin đã thấy: luôn bỏ
    assert len(delivered) == 4
    p2_delivered = []
    p2 = _sync(p2_delivered)                                                           # chưa gắn dedup: không đổi gì so với trước
    p2.handle_decoded(_data())
    p2.handle_decoded(_data(), via="ws")
    assert len(p2_delivered) == 4 and p2.cursor.last_action_id == "100"                 # con trỏ vẫn cập nhật từ batch


def test_ctrl_handle_decoded_delivers_call_events_once_across_sources():
    calls = []
    p = ctrl_mod.CtrlPoller(lambda *a, **k: (200, {}), ["https://x.invalid/lp"], TEST_SESSION_KEY, "10001", ctrl_mod.VoiceAsyncRegistry(), ctl_timeout=30,
                            on_call_event=lambda e: calls.append(e["act"]))
    p.dedup, p.dedup_check = event_dedup.EventDedup(), lambda: True
    batch = {"controls": [{"controlId": "c1", "content": {"act_type": "voip", "data": {"act": "ring_ring", "callId": 77}}}]}
    p.handle_decoded(batch, via="ws")
    p.handle_decoded(batch, via="poll")                                                # cùng một cuộc đổ chuông tới từ poll: bỏ
    assert calls == ["ring_ring"]
    other = {"controls": [{"controlId": "c2", "content": {"act_type": "voip", "data": {"act": "end_call", "callId": 77}}}]}
    p.handle_decoded(other, via="poll")
    assert calls == ["ring_ring", "end_call"]                                          # sự kiện khác vẫn đi qua


def _state():
    state = app_server.AppState(tempfile.mkdtemp(prefix="wsint-"))
    sess = session_mod.new_session("dev-1", "testhost")
    sess.update({"uid": "10001", "dkey": "d", "zpw_sek": "sek-test", "zpw_kt": "k", "zpw_enk": TEST_SESSION_KEY,
                 "poll_msg_urls": [], "poll_ctl_urls": [], "status": session_mod.STATUS_LOGGED_IN})
    state.store.save(sess)
    state.session = sess
    return state


class StubListener:
    made = []

    def __init__(self, urls, cookie, ua, on_event, api_version, api_type, ping_seconds=30, on_state=None, log=print, **kw):
        self.args = dict(urls=urls, cookie=cookie, ua=ua, api=(api_version, api_type), ping=ping_seconds)
        self.on_event, self.on_state = on_event, on_state
        self.state, self.active, self.stopped = "idle", True, False
        StubListener.made.append(self)

    def start(self):
        self.state = "connecting"
        return True

    def stop(self):
        self.stopped = True
        self.state = "idle"

    def status(self):
        return {"state": self.state, "active": self.active}


def test_on_ws_event_routes_to_the_right_poller_and_tolerates_missing_ones():
    state = _state()
    got = []
    mk = lambda name: types.SimpleNamespace(handle_decoded=lambda data, via="poll": got.append((name, data, via)))  # noqa: E731
    state._on_ws_event("sync", {"msgs": []})
    state._on_ws_event("ctrl", {"controls": []})                                     # chưa có bộ poll nào: bỏ qua, không lỗi
    state.sync, state.ctrl = mk("sync"), mk("ctrl")
    state._on_ws_event("sync", {"msgs": [1]})
    state._on_ws_event("ctrl", {"controls": [2]})
    state._on_ws_event("khac", {"x": 1})                                             # loại lạ rơi về ctrl (không bao giờ nổ)
    assert got[:2] == [("sync", {"msgs": [1]}, "ws"), ("ctrl", {"controls": [2]}, "ws")] and len(got) == 3
    assert state.sync.handle_decoded is not None


def test_start_ws_uses_session_endpoint_respects_off_switch_and_never_breaks_polling():
    real = app_server.ws_listener_mod.WsListener
    app_server.ws_listener_mod.WsListener = StubListener
    old_env = os.environ.get("ZALO_PC_WS")
    try:
        StubListener.made = []
        state = _state()
        os.environ["ZALO_PC_WS"] = "off"
        state._start_ws_locked(state.session)
        assert state.ws is None and not StubListener.made                              # công tắc tắt: không mở
        os.environ.pop("ZALO_PC_WS", None)
        state.session["ws_endpoint"] = ["wss://ws1-msg.example/", "wss://ws2.example/"]
        state._start_ws_locked(state.session)
        a = StubListener.made[0].args
        assert a["urls"] == ["wss://ws1-msg.example/", "wss://ws2.example/"] and a["cookie"] == "zpw_sek=sek-test" and a["api"] == (695, 30), a
        assert state.ws is StubListener.made[0] and state._ws_active() is True
        state._start_ws_locked(state.session)
        assert len(StubListener.made) == 1                                             # đang chạy thì không tạo thêm
        state.ws.on_state("connected", "")
        assert state.health.last("ws")["detail"] == "connected"                         # đổi trạng thái được ghi vào nhật ký sức khoẻ
        assert state.public_status()["ws"] == {"state": "connecting", "active": True}
        old = state.ws
        state.stop_sync()
        assert old.stopped and state.ws is None and state.public_status()["ws"] == {"state": "off"}
        state.session["ws_endpoint"] = "wss://chuoi-don.example/"                      # địa chỉ dạng chuỗi (không phải list) cũng được
        state._start_ws_locked(state.session)
        assert StubListener.made[-1].args["urls"] == ["wss://chuoi-don.example/"]
        state.session["ws_endpoint"] = ""
        state.ws = None
        state._start_ws_locked(state.session)                                          # không có địa chỉ: bộ nghe thật tự tắt, không nổ
        app_server.ws_listener_mod.WsListener = real
        state.ws = None
        state._start_ws_locked(state.session)
        assert state.ws is None
        app_server.ws_listener_mod.WsListener = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hong"))
        state.session["ws_endpoint"] = "wss://x.example/"
        state._start_ws_locked(state.session)                                          # dựng bộ nghe nổ: nuốt lỗi, poll không bị ảnh hưởng
        assert state.ws is None
    finally:
        app_server.ws_listener_mod.WsListener = real
        if old_env is None:
            os.environ.pop("ZALO_PC_WS", None)
        else:
            os.environ["ZALO_PC_WS"] = old_env


def test_call_event_dedup_by_act_call_id_and_ts_only():
    state = _state()
    logs = []
    old = app_server._log_call
    app_server._log_call = lambda m: logs.append(m)
    try:
        ev = lambda ts, act="mute_audio": {"act": act, "call_id": 99, "data": {"ts": ts, "params": {"x": 1}}}  # noqa: E731
        state._on_ctrl_call_event(ev("111"))
        state._on_ctrl_call_event(ev("111"))                                           # cùng act + call_id + ts (hai nguồn): chỉ xử lý một lần
        assert sum("call_event raw" in m for m in logs) == 1, logs
        state._on_ctrl_call_event(ev("222"))                                           # ts khác = sự kiện khác (bấm tắt tiếng lần nữa): xử lý
        assert sum("call_event raw" in m for m in logs) == 2
        state._on_ctrl_call_event({"act": "mute_audio", "call_id": 99, "data": {"params": {"ts": "333"}}})
        state._on_ctrl_call_event({"act": "mute_audio", "call_id": 99, "data": {"params": {"ts": "333"}}})   # ts nằm trong params cũng được nhận ra
        assert sum("call_event raw" in m for m in logs) == 3
        same_ts = lambda typ: {"act": "mute_audio", "call_id": 99, "data": {"ts": "444", "params": {"type": typ}}}  # noqa: E731
        state._on_ctrl_call_event(same_ts(0))
        state._on_ctrl_call_event(same_ts(1))                                          # cùng ts nhưng KHÁC nội dung (tắt rồi bật): là hai sự kiện
        assert sum("call_event raw" in m for m in logs) == 5
        state._on_ctrl_call_event(same_ts(1))                                          # lặp y hệt: bỏ
        assert sum("call_event raw" in m for m in logs) == 5
        for _ in range(2):
            state._on_ctrl_call_event({"act": "mute_audio", "call_id": 99, "data": {"params": "chuoi-json"}})  # không có ts: KHÔNG bao giờ bỏ
        assert sum("call_event raw" in m for m in logs) == 7
    finally:
        app_server._log_call = old


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL WS-INTEGRATION TESTS PASSED")
