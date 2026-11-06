"""Tin nhan thoai: doi sang AAC truoc khi gui qua duong hai buoc
(upload chunked 12060/12063 + asyncfile/msg 11777/13001).

Goc Node.js (voiceMessage.test.js): pin doi so ffmpeg, doi WAV
sang dung dinh dang tin thoai Zalo (AAC-LC 16 kHz mono 64 kbps
ADTS), tai len roi sendVoice, loi ro khi khong co URL. O day pin
Y HET cho duong PC — vi duong upload-manager cua bundle cung doi
file AAC (fileType "aac"|"amr", async tra {aac, amr}): doi so
`-ac 1 -ar 16000 -c:a aac -b:a 64k -f adts` giong he Node.js, khong
con lech codec nhu thoi voicemp3 (voicemp3 bat MP3 va tra 133 —
duong do da ngung dung vi bundle khong goi sendVoice, xem
test_voice_112.py).

Mock kiem chung doc lap (ffmpeg that neu co, khong thi dung run
inject + bo qua test can ffmpeg that). Khong dang nhap that,
khong gui tin that.
"""

import json
import os
import shutil
import struct
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
# `-ac 1 -ar 16000 -c:a aac -b:a 64k -f adts` — duong upload-manager
# cua bundle cung doi file AAC (fileType aac/amr), khong con lech
# codec nhu thoi voicemp3 (libmp3lame/mp3); o day MP3 van pin
# `-ac 1 -ar 16000 -c:a libmp3lame -b:a 64k -f mp3` CONG
# `-write_xing 1` (loi 112 vong 2, xem ffmpeg_args()).

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
    assert "-ac 1 -ar 16000 -c:a libmp3lame -b:a 64k -write_xing 1 " \
        "-f mp3" in joined, joined
    assert seen["args"][-1] == "pipe:1", seen["args"]
    assert "-i" in seen["args"] and "pipe:0" in seen["args"], seen


def test_ffmpeg_args_aac_match_nodejs_params():
    seen = {}

    def fake_run(binary, args, data, timeout_s):
        seen["args"] = args
        seen["binary"] = binary
        return b"\xff\xf1FAKEAAC"

    out = voice_mod.to_zalo_voice_aac(
        b"\x1a\x45\xdf\xa3" + b"\x00" * 10, run=fake_run)
    assert out == b"\xff\xf1FAKEAAC", out
    joined = " ".join(seen["args"])
    assert "-ac 1 -ar 16000 -c:a aac -b:a 64k -f adts" in joined, \
        joined
    assert seen["args"][-1] == "pipe:1", seen["args"]
    assert "-i" in seen["args"] and "pipe:0" in seen["args"], seen


# -- nhan dang AAC (ADTS) -------------------------------------------------

def test_is_aac_sniff():
    # ADTS sync: FF F1 (MPEG-4, khong CRC) / FF F9 (co CRC).
    assert voice_mod.is_aac(b"\xff\xf1\x50\x80\x00\x1f\xfc"
                            + b"\x00" * 10) is True
    assert voice_mod.is_aac(b"\xff\xf9\x50\x80\x00\x1f\xfc"
                            + b"\x00" * 10) is True
    # MP3 (ID3 / frame sync), WebM, MP4 (ftyp — chua phai ADTS),
    # OGG, WAV, rong: khong phai AAC ADTS.
    assert voice_mod.is_aac(b"ID3\x04\x00\x00\x00\x00\x00\x00") is False
    assert voice_mod.is_aac(b"\xff\xfb\x90\x00" + b"\x00" * 10) is False
    assert voice_mod.is_aac(b"\x1a\x45\xdf\xa3" + b"\x00" * 10) is False
    assert voice_mod.is_aac(b"\x00\x00\x00\x18ftypmp42") is False
    assert voice_mod.is_aac(b"OggS" + b"\x00" * 10) is False
    assert voice_mod.is_aac(b"RIFF\x00\x00\x00\x00WAVE") is False
    assert voice_mod.is_aac(b"") is False
    assert voice_mod.is_aac(None) is False


def test_needs_aac_transcode():
    aac = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 10
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 10
    assert voice_mod.needs_aac_transcode("voice.aac", "audio/aac",
                                         aac) is False
    # Noi dung quyet dinh, khong phai ten: blob webm dat ten .aac
    # van phai doi (dung truong hop trinh duyet dat ten sai).
    assert voice_mod.needs_aac_transcode("voice.aac", "audio/aac",
                                         webm) is True
    assert voice_mod.needs_aac_transcode("voice.webm", "audio/webm",
                                         webm) is True
    # MP4 chua AAC ben trong nhung khong phai ADTS tho -> van doi.
    assert voice_mod.needs_aac_transcode(
        "voice.mp4", "audio/mp4",
        b"\x00\x00\x00\x18ftypmp42") is True


def test_already_aac_passes_through_without_ffmpeg():
    def exploding_run(*args):
        raise AssertionError("ffmpeg khong duoc goi voi file AAC")

    aac = b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\x00" * 100
    out, name, mime, converted = voice_mod.ensure_voice_aac(
        "voice.aac", "audio/aac", aac, run=exploding_run)
    assert out == aac and name == "voice.aac", (name, converted)
    assert mime == "audio/aac" and converted is False, converted


# -- doi that bang ffmpeg that (AAC) --------------------------------------

def test_transcode_webm_opus_to_aac_real_ffmpeg():
    if not FFMPEG:
        print("SKIP test_transcode_webm_opus_to_aac_real_ffmpeg "
              "(no ffmpeg)")
        return
    webm = make_fixture("rec.webm",
                        ["-c:a", "libopus", "-b:a", "32k"])
    assert webm and not voice_mod.is_aac(webm), len(webm or b"")
    aac = voice_mod.to_zalo_voice_aac(webm)
    assert voice_mod.is_aac(aac), aac[:16]
    assert decode_ok(aac), "ffmpeg khong giai ma duoc AAC vua doi"
    assert len(aac) > 500, len(aac)


def test_transcode_mp4_to_aac_real_ffmpeg():
    if not FFMPEG:
        print("SKIP test_transcode_mp4_to_aac_real_ffmpeg "
              "(no ffmpeg)")
        return
    mp4 = make_fixture("rec.mp4", ["-c:a", "aac", "-b:a", "64k"])
    assert mp4 and not voice_mod.is_aac(mp4), len(mp4 or b"")
    aac = voice_mod.to_zalo_voice_aac(mp4)
    assert voice_mod.is_aac(aac), aac[:16]
    assert decode_ok(aac), "ffmpeg khong giai ma duoc AAC vua doi"


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
    """File that mock Zalo nhan duoc o voice/upload gan nhat:
    (filename, bytes cua chunkContent)."""
    for path, raw in reversed(mock.seen_post_raw):
        if path != "/api/message/voice/upload":
            continue
        ctype = ""
        for p, _qs, headers in reversed(mock.seen):
            if p == path and "Content-Type" in headers:
                ctype = headers["Content-Type"]
                break
        _fields, files = chat_mod.parse_multipart(raw, ctype)
        assert "chunkContent" in files, files.keys()
        return files["chunkContent"][0], files["chunkContent"][2]
    raise AssertionError("mock khong nhan duoc voice/upload nao")


def test_server_transcodes_webm_before_upload():
    """Ghi am webm (MediaRecorder cua Chrome) phai duoc doi sang
    AAC-LC 16 kHz 64 kbps ADTS roi moi upload chunked — mock phai
    nhan duoc file voice.aac voi noi dung AAC that."""
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
        assert webm and not voice_mod.is_aac(webm)
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "voice.webm", "audio/webm", webm)])
        status, body = api("POST", "/api/thread/20001/sendvoice",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body.get("converted_to_aac") is True, body
        assert body["message"]["kind"] == "voice", body
        assert body["message"]["file_name"] == "voice.aac", body
        filename, uploaded = _uploaded_voice_file(mock)
        assert filename == "voice.aac", filename
        assert voice_mod.is_aac(uploaded), uploaded[:16]
        assert decode_ok(uploaded), \
            "AAC gui len Zalo phai giai ma duoc"
        httpd.shutdown()
    finally:
        mock.stop()


def test_server_aac_passthrough():
    """File AAC ADTS that gui thang, khong doi (khong ton ffmpeg);
    duong truc tiep voicemp3 + loi 133 cu khong con ap dung — duong
    hai buoc khong co buoc nao tu choi dinh dang theo kieu 133."""
    if not FFMPEG:
        print("SKIP test_server_aac_passthrough (no ffmpeg)")
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
        aac = make_fixture("rec.aac", ["-c:a", "aac", "-b:a", "64k"])
        assert aac and voice_mod.is_aac(aac)
        mbody, mctype = chat_mod.build_multipart(
            {"type": "user"},
            [("file", "voice.aac", "audio/aac", aac)])
        status, body = api("POST", "/api/thread/20001/sendvoice",
                           mbody, {"Content-Type": mctype})
        assert status == 200 and body["ok"] is True, body
        assert body.get("converted_to_aac") is False, body
        filename, uploaded = _uploaded_voice_file(mock)
        assert filename == "voice.aac", filename
        assert uploaded == aac, "AAC that phai gui nguyen, khong doi"
        httpd.shutdown()
    finally:
        mock.stop()


# -- Xing/Info header: thoi luong MP3 (loi 112, vong 2) ---------------
# PHAT HIEN 2026-11-06: ffmpeg ghi ra PIPE (code cu) thi file
# MP3 KHONG co header Xing/Info — ffprobe phai "Estimating duration
# from bitrate" (2.09 s uoc luong cho file 2.00 s that; doc qua pipe
# thi Duration: N/A). Cung doi so do nhung ghi ra FILE (seekable)
# thi CO header Info o frame dau (flags=0xf, frames=58, bytes=16992)
# va ffprobe doc dung 2.00 s. `-write_xing 1` KHONG cuu duoc pipe
# (muxer can seek lui de dien so frame/byte; da kiem chung pipe+flag
# van 16749 byte, khong header) — phai doi sang ghi ra FILE TAM
# (xoa sau khi doc). Client that ghi am native phai dua mot FILE
# cho sendVoice (bundle `u.append("fileContent", t)` — t la File
# tren dia), nen file cua no (ghi qua file, hoac qua lame truc tiep)
# mang header Xing/Info nhu moi file MP3 ghi ra dia binh thuong;
# file cua ta (ghi qua pipe) thi khong. Server doc thoi luong tu
# Xing/Info se thay file ta khong co thoi luong -> 112 chung chung
# la hop ly. Cac test duoi DO tren code cu (pipe, khong header):
# test args do ngay bang mock; test header/thoi luong do bang
# ffmpeg that.

FFPROBE = shutil.which("ffprobe")


def make_fixture_seconds(name, seconds, fmt_args):
    """Nhu make_fixture nhung cho chon do dai (giay)."""
    if not FFMPEG:
        return None
    path = os.path.join(TMP, name)
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i",
           "sine=frequency=440:duration=%s" % seconds,
           "-vn", "-ac", "1", "-ar", "16000"] + fmt_args + [path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    with open(path, "rb") as f:
        return f.read()


def xing_info_header(data):
    """Header Xing/Info trong frame MP3 dau (sau ID3 neu co):
    tra ve (offset, flags, frames, bytes) hoac None neu khong co.
    Header nam trong frame dau tien, tuc < 512 byte dau file."""
    head = (data or b"")[:1024]
    for tag in (b"Xing", b"Info"):
        off = head.find(tag)
        if off < 0:
            continue
        flags, frames, nbytes = struct.unpack(
            ">III", head[off + 4:off + 16])
        return off, flags, frames, nbytes
    return None


def ffprobe_report(data):
    """Chay ffprobe that len bytes MP3, tra ve (stdout+stderr).
    Ghi ra FILE tam roi moi probe (khong probe qua pipe:0 — doc
    qua pipe thi ffprobe bao 'Duration: N/A' + 'invalid
    concatenated file' du file co header Xing/Info; server nhan
    duoc toan bo file nen probe qua file moi la mo hinh dung)."""
    path = tempfile.mkstemp(prefix="probe-", suffix=".mp3",
                            dir=TMP)[1]
    with open(path, "wb") as f:
        f.write(data)
    proc = subprocess.run(
        [FFPROBE, "-hide_banner", "-i", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (proc.stdout + proc.stderr).decode("utf-8", "replace")


def test_ffmpeg_args_include_write_xing():
    """Pin `-write_xing 1`: pipe output phai mang header Xing/Info
    (xem ghi chu tren). DO tren code cu (thieu flag)."""
    seen = {}

    def fake_run(binary, args, data, timeout_s):
        seen["args"] = args
        return b"ID3FAKEMP3"

    voice_mod.to_zalo_voice_mp3(
        b"\x1a\x45\xdf\xa3" + b"\x00" * 10, run=fake_run)
    joined = " ".join(seen["args"])
    assert "-write_xing 1" in joined, joined
    assert "-ac 1 -ar 16000 -c:a libmp3lame -b:a 64k" in joined, joined


def test_transcode_mp3_has_xing_info_header_real_ffmpeg():
    """MP3 doi that phai co header Xing/Info o frame dau, mang so
    frame dung (do dai that) — DO tren code cu (pipe khong header)."""
    if not FFMPEG:
        print("SKIP test_transcode_mp3_has_xing_info_header_real_ffmpeg "
              "(no ffmpeg)")
        return
    webm = make_fixture_seconds("rec2s.webm", 2,
                                ["-c:a", "libopus", "-b:a", "32k"])
    assert webm and not voice_mod.is_mp3(webm)
    mp3 = voice_mod.to_zalo_voice_mp3(webm)
    assert voice_mod.is_mp3(mp3), mp3[:16]
    found = xing_info_header(mp3)
    assert found is not None, \
        "MP3 gui Zalo phai co header Xing/Info (thoi luong)"
    off, flags, frames, nbytes = found
    assert off < 512, off
    assert flags & 0x1 and frames > 0, (flags, frames)
    # 58 frame x 576 mau @16 kHz ~= 2.09 s (gom delay/padding cua
    # LAME); khong pin so tuyet doi, chi can gan 2.0 s that.
    assert abs(frames * 576 / 16000 - 2.0) < 0.2, frames
    # Truong bytes cua header Xing/Info dem dung so byte am thanh
    # (toan bo file tru header ID3): tinh do dai ID3 tu header that
    # thay vi cung so 45 (tag encoder dai tuy ffmpeg).
    id3_len = 0
    if mp3[:3] == b"ID3":
        id3_len = 10 + (((mp3[6] & 0x7F) << 21)
                        | ((mp3[7] & 0x7F) << 14)
                        | ((mp3[8] & 0x7F) << 7)
                        | (mp3[9] & 0x7F))
    assert nbytes == len(mp3) - id3_len, (nbytes, len(mp3), id3_len)


def test_transcode_duration_exact_not_estimated_real_ffmpeg():
    """ffprobe phai doc DUOC thoi luong chinh xac (2.00 s), khong
    uoc luong tu bitrate — DO tren code cu (2.09 s uoc luong)."""
    if not FFMPEG or not FFPROBE:
        print("SKIP test_transcode_duration_exact_not_estimated_real_ffmpeg "
              "(no ffmpeg/ffprobe)")
        return
    webm = make_fixture_seconds("rec2s-b.webm", 2,
                                ["-c:a", "libopus", "-b:a", "32k"])
    mp3 = voice_mod.to_zalo_voice_mp3(webm)
    report = ffprobe_report(mp3)
    assert "Estimating duration from bitrate" not in report, report
    assert "Duration: 00:00:02.00" in report, report
    assert "16000 Hz, mono" in report and "64 kb/s" in report, report


def test_transcode_short_recording_has_xing_header_real_ffmpeg():
    """Ghi am ngan (0.2 s) cung phai co header Xing/Info + thoi
    luong dung — DO tren code cu (pipe khong header)."""
    if not FFMPEG or not FFPROBE:
        print("SKIP test_transcode_short_recording_has_xing_header_real_ffmpeg "
              "(no ffmpeg/ffprobe)")
        return
    webm = make_fixture_seconds("rec02s.webm", 0.2,
                                ["-c:a", "libopus", "-b:a", "32k"])
    mp3 = voice_mod.to_zalo_voice_mp3(webm)
    assert xing_info_header(mp3) is not None, mp3[:64]
    report = ffprobe_report(mp3)
    assert "Estimating duration from bitrate" not in report, report
    assert "Duration: 00:00:00.20" in report, report


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VOICE TRANSCODE TESTS PASSED")
