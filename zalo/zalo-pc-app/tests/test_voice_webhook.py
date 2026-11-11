"""Tin thoai DEN: webhook message mang kind + voice_url de HA tu goi Zalo STT (voice_to_text). App KHONG tu lam STT."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import server as sv  # noqa: E402
from zalo_pc_app import webhooks as webhooks_mod  # noqa: E402

VOICE = {"id": "v1", "sender_id": "20001", "text": "", "kind": "voice", "file_url": "https://f1-voice-aac-dl.zdn.vn/abc/123",
         "time": 1794356943, "sender_name": "Anh Bi", "direction": "in", "is_self": False}


def _state():
    state = sv.AppState(tempfile.mkdtemp())
    sent = []
    state.webhook_store.save({"message_webhook_url": "https://hook.invalid/m"})
    state.webhook_dispatcher = webhooks_mod.WebhookDispatcher(state.webhook_store, post_fn=lambda url, p: sent.append(p) or 200)
    sv.STATE = state
    return state, sent


def _wait(sent, n=1, t=3.0):
    end = time.time() + t
    while time.time() < end and len(sent) < n:
        time.sleep(0.02)
    return sent


def test_incoming_voice_event_carries_kind_and_voice_url_and_calls_no_stt():
    state, sent = _state()
    called = []
    real = sv.services_mod.handle_svc
    sv.services_mod.handle_svc = lambda *a, **k: called.append(a) or (200, {})
    try:
        state._on_sync_message("user", "20001", dict(VOICE))
        _wait(sent)
        assert len(sent) == 1 and called == [], (sent, called)                      # app không tự STT
        p = sent[0]
        assert p["kind"] == "voice" and p["voice_url"].endswith("/abc/123") and p["content"] == "" and p["thread_id"] == "20001", p
    finally:
        sv.services_mod.handle_svc = real


def test_own_voice_and_text_messages():
    state, sent = _state()
    state._on_sync_message("user", "20001", dict(VOICE, id="own", is_self=True, direction="out"))      # tin tự gửi: không đẩy
    state._on_sync_message("user", "20001", {"id": "t1", "sender_id": "20001", "text": "Chào", "kind": "text", "time": 1, "is_self": False})
    _wait(sent)
    time.sleep(0.2)
    assert len(sent) == 1 and sent[0]["content"] == "Chào" and sent[0]["kind"] == "text" and "voice_url" not in sent[0], sent


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print("PASS", _name)
    print("ALL VOICE-WEBHOOK TESTS PASSED")
