"""Tin giữ chỗ (sender "me") bị bỏ khi bản Zalo dội lại đã tới — ảnh/chữ gửi từ HA không còn hiện trùng (14/11/2026).
Số đo thật: 'go2rtc_cua_gui3.jpg' (giữ chỗ, client_id 1794623123415) và bản dội lại (raw.cliMsgId 1794623123415) cùng nằm trong lịch sử.
Run: python3 tests/test_merge_placeholder.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import chat as chat_mod  # noqa: E402


def placeholder(cid, kind="photo", name="a.jpg"):
    return {"id": cid, "client_id": cid, "sender_id": "me", "text": name, "time": 100, "kind": kind, "file_name": name, "direction": "out", "status": "sent"}


def echo(mid, cli, kind="photo"):
    return {"id": mid, "sender_id": "475796162066271393", "direction": "out", "is_self": True, "time": 100, "kind": kind, "file_url": "https://f.zdn.vn/x.jpg",
            "raw": {"msgId": mid, "cliMsgId": cli}}


def test_placeholder_dropped_when_echo_arrives_but_unrelated_kept():
    cached = [placeholder("1794623123415"), placeholder("1794623999999", "text", "chưa dội lại"), echo("8486717425094", "1794623123415")]
    merged, _ = chat_mod.merge_messages([], cached, 50)
    ids = [m["id"] for m in merged]
    assert "1794623123415" not in ids and "8486717425094" in ids, ids              # bản giữ chỗ có bản thật → bỏ
    assert "1794623999999" in ids, ids                                              # chưa có bản dội lại → GIỮ (khỏi mất tin vừa gửi)


def test_text_placeholder_also_dropped_and_fresh_wins():
    fresh = [echo("8486717337412", "1794623122334", "text")]
    cached = [placeholder("1794623122334", "text", "🔔 Phát hiện chuyển động!")]
    merged, _ = chat_mod.merge_messages(fresh, cached, 50)
    assert [m["id"] for m in merged] == ["8486717337412"], merged                   # chữ lặp trước đây hiện hai lần


def test_messages_from_other_people_never_dropped():
    other = {"id": "7", "client_id": "1794623123415", "sender_id": "2005600327393091310", "time": 100, "kind": "text", "text": "x"}
    merged, _ = chat_mod.merge_messages([], [other, echo("8", "1794623123415")], 50)
    assert {m["id"] for m in merged} == {"7", "8"}, merged                          # chỉ bỏ tin giữ chỗ của CHÍNH MÌNH (sender "me")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ALL MERGE PLACEHOLDER TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
