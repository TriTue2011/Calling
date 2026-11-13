"""Hẹn thu hồi sau N giây, ttl theo cuộc trò chuyện (sửa 801 ảnh nhóm), xoá tin đúng kiểu, tự xoá đúng máy chủ.
Chạy: python3 tests/test_recall_and_ttl.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import conv_ttl, protocol, recall_queue, server, services  # noqa: E402


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _queue(undo, clock):
    path = os.path.join(tempfile.mkdtemp(prefix="rcl-"), "q.json")
    return recall_queue.RecallQueue(path, undo, clock=clock, log=lambda m: None), path


def test_parse_after_accepts_seconds_and_rejects_nonsense():
    P = recall_queue.parse_after
    assert P(None) == 0 and P("") == 0 and P(0) == 0 and P("45") == 45 and P(12.9) == 12
    for bad in ("abc", -1, recall_queue.MAX_AFTER_SECONDS + 1):
        try:
            P(bad)
        except ValueError:
            continue
        raise AssertionError("phai tu choi %r" % (bad,))


def test_due_items_are_recalled_and_future_ones_wait():
    calls, clock = [], Clock()
    q, _ = _queue(lambda *a: calls.append(a), clock)
    at = q.add("user", "T1", "M1", "C1", 20)
    assert at == 1020.0 and q.add("user", "T1", "M2", "C2", 0) == 0 and q.add("user", "T1", "", "C3", 5) == 0
    clock.t = 1019
    assert q.run_due() == 0 and calls == []
    clock.t = 1020
    assert q.run_due() == 1 and calls == [("user", "T1", "M1", "C1")] and q.pending() == []


def test_queue_survives_restart_and_file_is_private():
    clock = Clock()
    q, path = _queue(lambda *a: None, clock)
    q.add("group", "G", "M9", "C9", 30)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    calls = []
    q2 = recall_queue.RecallQueue(path, lambda *a: calls.append(a), clock=clock, log=lambda m: None)
    clock.t = 1031
    assert q2.run_due() == 1 and calls == [("group", "G", "M9", "C9")]


def test_not_logged_in_keeps_item_and_real_errors_are_dropped_after_three_tries():
    clock = Clock()
    state = {"mode": "notready", "n": 0}

    def undo(*a):
        state["n"] += 1
        if state["mode"] == "notready":
            raise recall_queue.NotReady("chua dang nhap")
        raise RuntimeError("zalo loi")
    q, _ = _queue(undo, clock)
    q.add("user", "T", "M", "C", 1)
    clock.t = 1002
    assert q.run_due() == 0 and len(q.pending()) == 1 and q.pending()[0]["attempts"] == 0
    state["mode"] = "error"
    for expected_left in (1, 1, 0):
        clock.t += 10
        q.run_due()
        assert len(q.pending()) == expected_left
    assert state["n"] == 1 + recall_queue.MAX_ATTEMPTS


def test_conv_ttl_returns_group_ttl_caches_and_retries_after_failure():
    clock, calls = Clock(), {"n": 0, "fail": True}
    logs = []

    def fetch():
        calls["n"] += 1
        if calls["fail"]:
            raise RuntimeError("chua dang nhap")
        return {"3295299208151385728": 86400000, 1: "604800000"}
    c = conv_ttl.ConvTtl(fetch, cache_seconds=600, clock=clock, log=logs.append)
    assert c.get("3295299208151385728") == 0 and c.get("x") == 0 and calls["n"] == 1 and len(logs) == 1      # lỗi: 0, chỉ log một lần, chưa gọi lại
    calls["fail"] = False
    clock.t += 31                                                                                           # sau 30 giây thử lại
    assert c.get("3295299208151385728") == 86400000 and c.get("1") == 604800000 and c.get("khac") == 0
    n = calls["n"]
    clock.t += 500
    c.get("1")
    assert calls["n"] == n                                                                                  # còn trong 10 phút: dùng bộ nhớ
    clock.t += 200
    c.get("1")
    assert calls["n"] == n + 1


def test_delete_body_uses_message_objects_and_session_uid():
    p = {"msg_id": "8483927661425", "cli_msg_id": "1794552489499", "only_me": False, "_imei": "IMEI", "_uid": "365685311"}
    body = services._b_delete_msg(p, "6643404425553198601", "user")
    assert body["msgs"] == [{"cliMsgId": "1794552489499", "globalMsgId": "8483927661425", "ownerId": "365685311", "destId": "6643404425553198601"}]
    assert body["onlyMe"] == 0 and body["toid"] == "6643404425553198601" and body["imei"] == "IMEI" and "grid" not in body
    g = services._b_delete_msg(dict(p, only_me=True, owner_id="999"), "G1", "group")
    assert g["grid"] == "G1" and g["onlyMe"] == 1 and g["msgs"][0]["ownerId"] == "999"
    try:
        services._b_delete_msg({"msg_id": "1", "cli_msg_id": "2", "_imei": "I"}, "T", "user")
    except ValueError:
        pass
    else:
        raise AssertionError("thieu ownerId phai bao loi")


def test_auto_delete_uses_web_host_and_numeric_is_group():
    assert services._b_auto_delete({"ttl": 86400000}, "G", "group")["isGroup"] == 1
    assert services._b_auto_delete({"ttl": 0}, "U", "user")["isGroup"] == 0
    assert services._DOMAINS["convers_web"]() == protocol.CONVERS_WEB_DOMAIN == "https://tt-convers-wpa.chat.zalo.me"
    assert services.OPS["get_auto_delete_chat"]["domain"] == "convers_web" and services.OPS["update_auto_delete_chat"]["domain"] == "convers_web"


def test_schedule_recall_uses_message_id_from_zalo_reply():
    added, real = [], server.STATE

    class Stub:
        class recall:
            @staticmethod
            def add(*a):
                added.append(a)
                return 1234.0
    server.STATE = Stub
    try:
        assert server._schedule_recall("user", "T", {"data": {"msgId": 55}, "client_id": 77}, 20) == 1234.0
        assert added == [("user", "T", 55, 77, 20)]
        assert server._schedule_recall("user", "T", {"data": {"msgId": 55}}, 0) == 0
        assert server._schedule_recall("user", "T", {"data": {}, "client_id": 1}, 20) == 0 and len(added) == 1     # không có mã tin: không hẹn mù
    finally:
        server.STATE = real


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL RECALL/TTL TESTS PASSED")
