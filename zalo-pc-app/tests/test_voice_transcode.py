"""Tin nhan thoai: doi sang MP3 truoc khi gui qua voicemp3 (loi 133).

Goc Node.js (voiceMessage.test.js): pin doi so ffmpeg, doi WAV
sang dung dinh dang tin thoai Zalo, tai len roi sendVoice, loi ro
khi khong co URL. O day pin tuong tu cho duong PC — chi khac dich
(MP3 thay cho AAC) vi voicemp3 bat buoc MP3; xem voice_transcode.py.

Mock kiem chung doc lap (ffmpeg that neu co, khong thi dung run
inject + bo qua test can ffmpeg that). Khong dang nhap that,
khong gui tin that.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import voice_transcode as voice_mod  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
TMP = tempfile.mkdtemp(prefix="zalo-voice-mp3-")


def make_fixture(name, fmt_args):
    """Tao file am thanh that (sine 440 Hz, 0.5 s) bang ffmpeg that.
    Tra ve bytes, hoac None neu khong co ffmpeg."""
    if not FFMPEG:
        return None
    path = os.path.join(TMP, name)
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
           "-vn", "-ac", "1", "-ar", "16000"] + fmt_args + [path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    with open(path, "rb") as f:
        return f.read()


def decode_ok(data):
    """ffmpeg that co giai ma duoc bytes nay thanh wav khong?"""
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-i", "pipe:0", "-f", "wav", "pipe:1"],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode == 0 and len(proc.stdout) > 100


# -- nhan dang MP3 -------------------------------------------------------

def test_is_mp3_sniff():
    assert voice_mod.is_mp3(b"ID3\x04\x00\x00\x00\x00\x00\x00") is True
    # Frame sync MPEG1 Layer III: FF FB.
    assert voice_mod.is_mp3(b"\xff\xfb\x90\x00" + b"\x00" * 10) is True
    # WebM (EBML), MP4 (ftyp), OGG, WAV, rong: khong phai MP3.
    assert voice_mod.is_mp3(b"\x1a\x45\xdf\xa3" + b"\x00" * 10) is False
    assert voice_mod.is_mp3(b"\x00\x00\x00\x18ftypmp42") is False
    assert voice_mod.is_mp3(b"OggS" + b"\x00" * 10) is False
    assert voice_mod.is_mp3(b"RIFF\x00\x00\x00\x00WAVE") is False
    assert voice_mod.is_mp3(b"") is False
    assert voice_mod.is_mp3(None) is False


def test_needs_transcode():
    mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00"
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 10
    assert voice_mod.needs_transcode("voice.mp3", "audio/mpeg",
                                     mp3) is False
    # Noi dung quyet dinh, khong phai ten: blob webm dat ten .mp3
    # van phai doi (dung truong hop trinh duyet dat ten sai).
    assert voice_mod.needs_transcode("voice.mp3", "audio/mpeg",
                                     webm) is True
    assert voice_mod.needs_transcode("voice.webm", "audio/webm",
                                     webm) is True
    assert voice_mod.needs_transcode("voice.mp4", "audio/mp4",
                                     b"\x00\x00\x00\x18ftypmp42") is True


# -- doi so ffmpeg: pin giong Node.js pin doi so (voiceMessage.test.js)
# `-ac 1 -ar 16000 -c:a aac -b:a 64k -f adts`; o day codec/container
# la libmp3lame/mp3 vi voicemp3 bat buoc MP3.

def test_ffmpeg_args_match_nodejs_params():
    seen = {}

    def fake_run(binary, args, data, timeout_s):
        seen["args"] = args
        seen["binary"] = binary
        return b"ID3FAKEMP3"

    out = voice_mod.to_zalo_voice_mp3(
        b"\x1a\x45\xdf\xa3" + b"\x00" * 10, run=fake_run)
    assert out == b"ID3FAKEMP3", out
    joined = " ".join(seen["args"])
    assert "-ac 1 -ar 16000 -c:a libmp3lame -b:a 64k -f mp3" in joined, \
        joined
    assert seen["args"][-1] == "pipe:1", seen["args"]
    assert "-i" in seen["args"] and "pipe:0" in seen["args"], seen


# -- doi that bang ffmpeg that -------------------------------------------

def test_transcode_webm_opus_to_mp3_real_ffmpeg():
    if not FFMPEG:
        print("SKIP test_transcode_webm_opus_to_mp3_real_ffmpeg "
              "(no ffmpeg)")
        return
    webm = make_fixture("rec.webm",
                        ["-c:a", "libopus", "-b:a", "32k"])
    assert webm and not voice_mod.is_mp3(webm), len(webm or b"")
    mp3 = voice_mod.to_zalo_voice_mp3(webm)
    assert voice_mod.is_mp3(mp3), mp3[:16]
    assert decode_ok(mp3), "ffmpeg khong giai ma duoc MP3 vua doi"
    assert len(mp3) > 1000, len(mp3)


def test_transcode_mp4_aac_to_mp3_real_ffmpeg():
    if not FFMPEG:
        print("SKIP test_transcode_mp4_aac_to_mp3_real_ffmpeg "
              "(no ffmpeg)")
        return
    mp4 = make_fixture("rec.mp4", ["-c:a", "aac", "-b:a", "64k"])
    assert mp4 and not voice_mod.is_mp3(mp4), len(mp4 or b"")
    mp3 = voice_mod.to_zalo_voice_mp3(mp4)
    assert voice_mod.is_mp3(mp3), mp3[:16]
    assert decode_ok(mp3), "ffmpeg khong giai ma duoc MP3 vua doi"


def test_already_mp3_passes_through_without_ffmpeg():
    def exploding_run(*args):
        raise AssertionError("ffmpeg khong duoc goi voi file MP3")

    mp3 = make_fixture("rec.mp3", ["-c:a", "libmp3lame", "-b:a",
                                   "64k"])
    if mp3 is None:
        mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 100
    out, name, mime, converted = voice_mod.ensure_voice_mp3(
        "voice.mp3", "audio/mpeg", mp3, run=exploding_run)
    assert out == mp3 and name == "voice.mp3", (name, converted)
    assert mime == "audio/mpeg" and converted is False, converted


# -- loi ro rang, khong crash --------------------------------------------

def test_missing_ffmpeg_is_a_clear_error():
    try:
        voice_mod.to_zalo_voice_mp3(b"\x1a\x45\xdf\xa3" + b"\x00" * 10,
                                    ffmpeg_bin="/nonexistent/ffmpeg")
        raise AssertionError("expected VoiceTranscodeError")
    except voice_mod.VoiceTranscodeError as e:
        assert "ffmpeg" in str(e).lower(), e


def test_ffmpeg_failure_is_a_clear_error():
    def failing_run(binary, args, data, timeout_s):
        raise subprocess.CalledProcessError(1, [binary] + args)

    try:
        voice_mod.to_zalo_voice_mp3(b"\x1a\x45\xdf\xa3" + b"\x00" * 10,
                                    run=failing_run)
        raise AssertionError("expected VoiceTranscodeError")
    except voice_mod.VoiceTranscodeError as e:
        assert "ffmpeg" in str(e).lower(), e


def test_ffmpeg_timeout_is_a_clear_error():
    def slow_run(binary, args, data, timeout_s):
        raise subprocess.TimeoutExpired([binary] + args, timeout_s)

    try:
        voice_mod.to_zalo_voice_mp3(b"\x1a\x45\xdf\xa3" + b"\x00" * 10,
                                    run=slow_run)
        raise AssertionError("expected VoiceTranscodeError")
    except voice_mod.VoiceTranscodeError as e:
        assert "thoi gian" in str(e), e


def test_empty_recording_is_a_clear_error():
    try:
        voice_mod.to_zalo_voice_mp3(b"")
        raise AssertionError("expected VoiceTranscodeError")
    except voice_mod.VoiceTranscodeError as e:
        assert "rong" in str(e), e


# -- e2e qua server app that -------------------------------------------
BASE = ""


def api(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def api_json(method, path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    return api(method, path, data, {"Content-Type": "application/json"})


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    chat_mod.CHAT_DOMAIN = mock.base
    chat_mod.FILES_DOMAIN = mock.base
    chat_mod.GROUP_DOMAIN = mock.base


def login_via_mock():
    from mock_server import TEST_PARAM_KEY
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    status, body = api_json("POST", "/api/qr/new", {})
    assert body["ok"] is True
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = api("GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def _uploaded_voice_file(mock):
    """File that mock Zalo nhan duoc o voicemp3 gan nhat:
    (filename, bytes)."""
    for path, raw in reversed(mock.seen_post_raw):
        if path != "/api/message/voicemp3":
            continue
        ctype = ""
        for p, _qs, headers in reversed(mock.seen):
            if p == path and "Content-Type" in headers:
                ctype = headers["Content-Type"]
                break
        _fields, files = chat_mod.parse_multipart(raw, ctype)
        assert "fileContent" in files, files.keys()
        return files["fileContent"][0], files["fileContent"][2]
    raise AssertionError("mock khong nhan duoc voicemp3 nao")


def test_server_transcodes_webm_before_upload():
    """Loi that 2026-11-05 23:03: ghi am webm gui thang -> 133.
    Sau fix: server doi sang MP3 roi moi gui — mock phai nhan
    duoc file voice.mp3 voi noi dung MP3 that."""
    if not FFMPEG:
        print("SKIP test_server_transcodes_webm_before_upload "
              "(no ffmpeg)")
        return
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-voice-test-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        login_via_mock()
        webm = make_fixture("rec.webm",
                            ["-c:a", "libopus", "-b:a", "32k"])
        assert webm and not voice_mod.is_mp3(webm)
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "voice.webm", "audio/webm", webm)])
        status, body = api("POST", "/api/thread/20001/sendvoice",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body.get("converted_to_mp3") is True, body
        assert body["message"]["kind"] == "voice", body
        assert body["message"]["file_name"] == "voice.mp3", body
        filename, uploaded = _uploaded_voice_file(mock)
        assert filename == "voice.mp3", filename
        assert voice_mod.is_mp3(uploaded), uploaded[:16]
        assert decode_ok(uploaded), \
            "MP3 gui len Zalo phai giai ma duoc"
        httpd.shutdown()
    finally:
        mock.stop()


def test_server_mp3_passthrough_and_133_surfaces():
    """(a) File MP3 that gui thang, khong doi; (b) Zalo tra 133 thi
    app tra 502 voi loi chua '133' — UI hien duoc ly do that."""
    if not FFMPEG:
        print("SKIP test_server_mp3_passthrough_and_133_surfaces "
              "(no ffmpeg)")
        return
    global BASE
    mock = MockZalo().start()
    tmp = tempfile.mkdtemp(prefix="zalo-pc-voice-test-")
    try:
        patch_domains(mock)
        state = app_server.AppState(tmp)
        app_server.STATE = state
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
        port = httpd.server_address[1]
        BASE = "http://127.0.0.1:%d" % port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        login_via_mock()
        mp3 = make_fixture("rec.mp3",
                           ["-c:a", "libmp3lame", "-b:a", "64k"])
        assert mp3 and voice_mod.is_mp3(mp3)
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "voice.mp3", "audio/mpeg", mp3)])
        status, body = api("POST", "/api/thread/20001/sendvoice",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body.get("converted_to_mp3") is False, body
        filename, uploaded = _uploaded_voice_file(mock)
        assert filename == "voice.mp3", filename
        assert uploaded == mp3, "MP3 that phai gui nguyen, khong doi"

        # Zalo tu choi (133): app khong gia vo thanh cong.
        mock.voice_upload_mode = "error133"
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "voice.mp3", "audio/mpeg", mp3)])
        status, body = api("POST", "/api/thread/20001/sendvoice",
                           mbody, {"Content-Type": mctype})
        assert status == 502, body
        assert "133" in str(body.get("error", "")), body
        assert "MP3" in str(body.get("error", "")), body
        httpd.shutdown()
    finally:
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VOICE TRANSCODE TESTS PASSED")
