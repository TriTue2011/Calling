"""Tin thoại Zalo theo cách zalo cu (zalo_bot voiceAac.js + zca-js sendVoice): tai .aac len NHU TEP THUONG (asyncfile/upload +
event file_done lay URL) roi gui bang `forward` voi msgType 3 — thay cho duong voice/upload 12060/12063 (`fileType: aac`)
ma Zalo tra 114 ngay o buoc tai len (do thay 10/11/2026).

Chay: python3 tests/test_voice_forward.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
import test_voice_112 as v  # noqa: E402  (khuon server/mock dung chung)

AAC = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 100
VOICE_URL = "https://f1-voice-aac-dl.zdn.vn/test.aac"


class FileWaiter:
    def __init__(self, url=VOICE_URL, feeder_running=True):
        self.url, self.feeder_running, self.calls = url, feeder_running, []

    def wait(self, file_id, timeout_s):
        self.calls.append(file_id)
        return {"url": self.url} if self.url else None


def make_chat(mock, waiter, timeout=5.0):
    t = app_server.make_transport("sek-test")
    return chat_mod.Chat(t, "dev-1", TEST_SESSION_KEY, file_async=waiter, file_async_timeout=timeout)


def _forwards(mock):
    return [p for p, _, _ in mock.seen if p.endswith("/forward")]


def test_voice_uploads_as_plain_file_without_filetype_then_forwards():
    mock = MockZalo().start()
    try:
        v.patch_domains(mock)
        waiter = FileWaiter()
        res = make_chat(mock, waiter).send_voice("user", "20001", "voice.aac", AAC, "audio/aac")
        up = mock.file_upload_bodies[0]["body"]
        assert up["fileName"] == "voice.aac" and "fileType" not in up and up["toid"] == "20001", up
        assert waiter.calls == ["file-1"], waiter.calls                 # doi file_done cua CHINH file vua tai len
        fw = mock.voice_forward_bodies[0]["body"]
        assert fw["clientId"] == str(res["client_id"]) == str(up["clientId"]), (fw, up)   # cung clientId de may chu loai trung
        assert res["voice_url"] == VOICE_URL and res["data"]["msgId"] == "msg-voice-1", res
        assert mock.voice_upload_calls == 0, "duong cu voice/upload khong con duoc goi"
        assert mock.file_send_calls == 0, "khong duoc gui them tin tep (asyncfile/msg)"
    finally:
        mock.stop()


def test_voice_name_not_aac_is_normalized():
    mock = MockZalo().start()
    try:
        v.patch_domains(mock)
        make_chat(mock, FileWaiter()).send_voice("user", "20001", "ghi-am.webm", AAC, "audio/aac")
        assert mock.file_upload_bodies[0]["body"]["fileName"] == "voice.aac", mock.file_upload_bodies
    finally:
        mock.stop()


def test_voice_never_forwards_without_a_url():
    """Khong co URL (het gio / khong co waiter / kenh ctrl chua chay) -> loi ro, KHONG forward mu."""
    mock = MockZalo().start()
    try:
        v.patch_domains(mock)
        for waiter, timeout in ((FileWaiter(url=None), 0.5), (None, 30.0), (FileWaiter(feeder_running=False), 30.0)):
            t0 = time.time()
            try:
                make_chat(mock, waiter, timeout).send_voice("user", "20001", "voice.aac", AAC, "audio/aac")
                raise AssertionError("phai loi")
            except chat_mod.ZaloChatError:
                pass
            assert time.time() - t0 < 5.0, "phai loi nhanh, khong doi het timeout dai"
        assert not _forwards(mock), _forwards(mock)
    finally:
        mock.stop()


def test_voice_forward_empty_data_is_an_error_not_fake_success():
    mock = MockZalo().start()
    try:
        v.patch_domains(mock)
        mock.voice_send_mode = "empty"
        try:
            make_chat(mock, FileWaiter()).send_voice("group", "30001", "voice.aac", AAC, "audio/aac")
            raise AssertionError("phai loi")
        except chat_mod.ZaloChatError as e:
            assert "khong co ma tin" in str(e), e
    finally:
        mock.stop()


def test_voice_input_validated_before_any_network_call():
    mock = MockZalo().start()
    try:
        v.patch_domains(mock)
        ch = make_chat(mock, FileWaiter())
        for args, kw in ((("user", "1", "voice.aac", b"", "audio/aac"), {}),
                         (("user", "1", "voice.aac", AAC, "audio/aac"), {"ttl": -5}),
                         (("user", "1", "voice.aac", AAC, "audio/aac"), {"ttl": "abc"})):
            try:
                ch.send_voice(*args, **kw)
                raise AssertionError("phai ValueError")
            except ValueError:
                pass
        assert not mock.seen, mock.seen
    finally:
        mock.stop()


def test_server_sendvoice_route_sends_a_voice_bubble_via_forward():
    """Qua route app: file AAC that gui thang (khong doi ffmpeg) -> 200, kind voice, 1 upload + 1 forward."""
    mock = MockZalo().start()
    try:
        httpd = v._run_server(mock)
        try:
            app_server.STATE.file_async.deliver("file-1", VOICE_URL)
            mbody, mctype = chat_mod.build_multipart({"type": "user"}, [("file", "voice.aac", "audio/aac", v.FAKE_AAC)])
            status, body = v.api("POST", "/api/thread/20001/sendvoice", mbody, {"Content-Type": mctype})
            assert status == 200 and body["ok"] is True and body["message"]["kind"] == "voice", body
            assert body.get("converted_to_aac") is False, body
            assert body.get("voice_url") == VOICE_URL, "tra URL tin thoai de dung cho voice_to_text"
            assert len(mock.voice_forward_bodies) == 1 and mock.voice_upload_calls == 0, mock.voice_forward_bodies
        finally:
            httpd.shutdown()
    finally:
        mock.stop()
        app_server.STATE.stop_sync()


def test_server_sendvoice_without_file_done_event_fails_honestly():
    mock = MockZalo().start()
    try:
        httpd = v._run_server(mock)
        try:
            app_server.STATE.file_async_timeout = 0.5
            mbody, mctype = chat_mod.build_multipart({"type": "user"}, [("file", "voice.aac", "audio/aac", v.FAKE_AAC)])
            status, body = v.api("POST", "/api/thread/20001/sendvoice", mbody, {"Content-Type": mctype})
            assert status == 502 and "URL" in str(body.get("error", "")), (status, body)
            assert not mock.voice_forward_bodies, "khong forward khi chua co URL"
        finally:
            httpd.shutdown()
    finally:
        mock.stop()
        app_server.STATE.stop_sync()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VOICE FORWARD TESTS PASSED")
