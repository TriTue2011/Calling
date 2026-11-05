"""Chuyen doi file ghi am cua trinh duyet sang dung dinh dang tin
thoai truoc khi gui qua voicemp3/sendmp3 (11148/11169).

GOC NODE.JS (tai lieu tham chieu CHINH — chi dao 2026-11-05 23:05):
zalobot-embedded/utils/voiceAac.js (commit 34ed43b) + test/
voiceMessage.test.js + api/zalo/zalo.js::sendVoiceByAccount. Node.js
lam nhu sau, va module nay GIU NGUYEN cac diem do:

  * Cong cu: ffmpeg (binary qua env FFMPEG_BIN, mac dinh "ffmpeg");
    zalobot Dockerfile cai ffmpeg bang `apk add ffmpeg`.
  * Tham so am thanh: mono, 16 kHz, ~64 kbps
    (`-vn -ac 1 -ar 16000 -b:a 64k`).
  * Timeout chuyen doi mac dinh 60 s (env VOICE_CONVERT_TIMEOUT_MS).
  * Loi ro rang, khong gui tin rong khi chuyen doi / tai len that
    bai; file tam phai duoc xoa (o day khong tao file tam: dung
    stdin/stdout pipe nen khong co gi de don).
  * Test mock ffmpeg bang cach inject ham chay (Node.js inject
    execFileAsync; o day inject `run`).

DIEM LECH DUY NHAT — VA LY DO (ghi ro, khong tu doan):
Node.js dich sang AAC-LC ADTS (.aac) vi duong cua no la zca-js:
`api.uploadAttachment([file.aac])` roi `api.sendVoice({voiceUrl})`
— dien thoai nguoi nhan tu tai file tu URL do; tin thoai that cua
Zalo (do 25/09/2026) la AAC-LC 16 kHz mono ~64 kbps ADTS tren
f*-voice-aac-dl.zdn.vn. Duong PC thi KHAC: endpoint voicemp3
(11148) / sendmp3 (11169) nhan truc tiep file multipart va TU
CHOI bat cu thu gi khong phai MP3 — bang chung truc tiep la loi
that gap tren may chu 2026-11-05 23:03: inner error_code=133
"Ban chi co the tai tap tin co dinh dang sau : MP3". Vi vay dich
o day la MP3 (`-c:a libmp3lame -f mp3`), giu nguyen cac tham so
am thanh cua Node.js (mono 16 kHz 64 kbps). Neu sau nay duong
upload-then-sendVoice bang URL (SERVICE-MAP.md #33: upload thoai
12060/12063, "thu tu dung chua lan") duoc lan tren phien PC thi
moi xet lai AAC theo Node.js; hien tai MP3 la dinh dang duy nhat
endpoint nay chap nhan.
"""

import os
import shutil
import subprocess

# Tham so am thanh — GIONG Node.js (voiceAac.js): mono, 16 kHz,
# ~64 kbps. Chi codec/container khac (libmp3lame/mp3 thay cho
# aac/adts) vi voicemp3 bat buoc MP3 (xem docstring module).
VOICE_CHANNELS = 1
VOICE_SAMPLE_RATE = 16000
VOICE_BITRATE = "64k"
VOICE_CODEC = "libmp3lame"
VOICE_FORMAT = "mp3"
VOICE_FILENAME = "voice.mp3"
VOICE_MIME = "audio/mpeg"
DEFAULT_TIMEOUT_MS = 60000


class VoiceTranscodeError(RuntimeError):
    """Chuyen doi sang MP3 that bai — message du ro de UI hien
    thang cho nguoi dung (ghi am / chuyen doi / tai len / gui)."""


def _positive_int(value, fallback):
    try:
        parsed = int(str(value or ""), 10)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def find_ffmpeg(ffmpeg_bin=None):
    """Binary ffmpeg: env FFMPEG_BIN (giong Node.js) hoac tham so,
    roi PATH. Tra ve duong dan hoac None."""
    name = ffmpeg_bin or os.environ.get("FFMPEG_BIN") or "ffmpeg"
    if os.path.sep in name:
        return name if (os.path.isfile(name)
                        and os.access(name, os.X_OK)) else None
    return shutil.which(name)


def ffmpeg_args():
    """Danh sach doi so ffmpeg — test pin giong cach Node.js pin
    `-ac 1 -ar 16000 -c:a aac -b:a 64k -f adts` (voiceMessage.test.js):
    o day `-ac 1 -ar 16000 -c:a libmp3lame -b:a 64k -f mp3`."""
    return ["-hide_banner", "-loglevel", "error", "-y",
            "-i", "pipe:0",
            "-vn", "-ac", str(VOICE_CHANNELS),
            "-ar", str(VOICE_SAMPLE_RATE),
            "-c:a", VOICE_CODEC, "-b:a", VOICE_BITRATE,
            "-f", VOICE_FORMAT, "pipe:1"]


def is_mp3(data):
    """Nhan MP3 that qua magic bytes: header ID3, hoac frame sync
    MPEG audio (11 bit 1 + MPEG version + Layer III/I/II). Du de
    phan biet voi webm (EBML 1A 45 DF A3), mp4 (ftyp), ogg, wav."""
    if not data or len(data) < 3:
        return False
    if data[:3] == b"ID3":
        return True
    if len(data) < 2 or data[0] != 0xFF or (data[1] & 0xE0) != 0xE0:
        return False
    # Byte 2: version (bit 4-3 != 01 reserved) + layer (bit 2-1 != 00).
    version = (data[1] >> 3) & 0x03
    layer = (data[1] >> 1) & 0x03
    return version != 0x01 and layer != 0x00


def _default_run(binary, args, data, timeout_s):
    """Chay ffmpeg that: doc stdin, lay mp3 o stdout. Loi tra ve
    stderr (cat ngan, khong bao gom du lieu am thanh)."""
    try:
        proc = subprocess.run(
            [binary] + args, input=data, timeout=timeout_s,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise VoiceTranscodeError(
            "khong tim thay ffmpeg (FFMPEG_BIN=%s): cai ffmpeg "
            "vao image/server de gui tin nhan thoai" % binary)
    except subprocess.TimeoutExpired:
        raise VoiceTranscodeError(
            "chuyen file ghi am sang MP3 het thoi gian (>%ds)"
            % timeout_s)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise VoiceTranscodeError(
            "ffmpeg chuyen sang MP3 that bai (exit %d)%s"
            % (proc.returncode,
               (": " + detail[-300:]) if detail else ""))
    if not proc.stdout:
        raise VoiceTranscodeError(
            "ffmpeg tra ve file MP3 rong")
    return proc.stdout


def to_zalo_voice_mp3(data, ffmpeg_bin=None, timeout_ms=None,
                      run=None):
    """Doi bytes am thanh bat ky (webm/opus cua Chrome, mp4/aac cua
    Safari, wav...) sang MP3 mono 16 kHz 64 kbps — dung dinh dang
    voicemp3 chap nhan. `run` de test inject (giong Node.js inject
    execFileAsync). Tra ve bytes MP3."""
    if not data:
        raise VoiceTranscodeError("file ghi am rong, khong co gi de gui")
    binary = find_ffmpeg(ffmpeg_bin)
    if binary is None:
        raise VoiceTranscodeError(
            "khong tim thay ffmpeg (FFMPEG_BIN=%s): cai ffmpeg vao "
            "image/server de gui tin nhan thoai"
            % (ffmpeg_bin or os.environ.get("FFMPEG_BIN")
               or "ffmpeg"))
    timeout_s = _positive_int(
        timeout_ms if timeout_ms is not None else
        os.environ.get("VOICE_CONVERT_TIMEOUT_MS"),
        DEFAULT_TIMEOUT_MS) / 1000.0
    runner = run or _default_run
    try:
        return runner(binary, ffmpeg_args(), data, timeout_s)
    except VoiceTranscodeError:
        raise
    except subprocess.CalledProcessError as e:
        raise VoiceTranscodeError(
            "ffmpeg chuyen sang MP3 that bai (exit %s)"
            % e.returncode)
    except subprocess.TimeoutExpired:
        raise VoiceTranscodeError(
            "chuyen file ghi am sang MP3 het thoi gian (>%ds)"
            % timeout_s)
    except FileNotFoundError:
        raise VoiceTranscodeError(
            "khong tim thay ffmpeg (FFMPEG_BIN=%s): cai ffmpeg "
            "vao image/server de gui tin nhan thoai" % binary)
    except OSError as e:
        raise VoiceTranscodeError(
            "khong chay duoc ffmpeg: %s" % e)


def needs_transcode(filename, mime, data):
    """File da la MP3 thi gui thang (khong ton ffmpeg); con lai
    (webm/mp4/wav/...) thi phai doi. Nhan dang theo NOI DUNG truoc
    (magic bytes), ten/mime chi la goi y — trinh duyet co the dat
    ten .mp3 cho blob webm."""
    if data and is_mp3(data):
        return False
    if data:
        # Co noi dung ma khong phai MP3 -> doi, ke ca khi ten/mime
        # noi la .mp3 (trinh duyet co the dat ten sai cho blob webm).
        return True
    name = (filename or "").lower()
    if name.endswith(".mp3"):
        return False
    return (mime or "").lower() not in ("audio/mpeg", "audio/mp3")


def ensure_voice_mp3(filename, mime, data, ffmpeg_bin=None,
                     timeout_ms=None, run=None):
    """Dam bao file gui qua voicemp3 la MP3. Tra ve (bytes, ten
    file, mime, da_chuyen_doi: bool). File MP3 that tra nguyen;
    file khac duoc doi bang ffmpeg truoc khi gui."""
    if not needs_transcode(filename, mime, data):
        return data, VOICE_FILENAME, VOICE_MIME, False
    mp3 = to_zalo_voice_mp3(data, ffmpeg_bin=ffmpeg_bin,
                            timeout_ms=timeout_ms, run=run)
    return mp3, VOICE_FILENAME, VOICE_MIME, True
