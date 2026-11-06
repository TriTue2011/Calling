"""Chuyen doi file ghi am cua trinh duyet sang dung dinh dang tin
thoai truoc khi gui qua duong hai buoc (upload chunked 12060/12063
+ asyncfile/msg 11777/13001).

GOC NODE.JS (tai lieu tham chieu CHINH — chi dao 2026-11-05 23:05):
zalobot-embedded/utils/voiceAac.js (commit 34ed43b) + test/
voiceMessage.test.js + api/zalo/zalo.js::sendVoiceByAccount. Node.js
lam nhu sau, va module nay GIU NGUYEN cac diem do:

  * Cong cu: ffmpeg (binary qua env FFMPEG_BIN, mac dinh "ffmpeg");
    zalobot Dockerfile cai ffmpeg bang `apk add ffmpeg`.
  * Tham so am thanh: mono, 16 kHz, ~64 kbps
    (`-vn -ac 1 -ar 16000 -b:a 64k`).
  * Header Xing/Info mang thoi luong (`-write_xing 1` + ghi ra FILE
    TAM, loi 112 vong 2, 2026-11-06): ffmpeg ghi ra PIPE thi MP3
    KHONG co header Xing/Info — ffprobe chi doan duoc thoi luong tu
    bitrate (2.09 s cho file 2.00 s that; doc qua pipe thi
    Duration: N/A) — va `-write_xing 1` cung KHONG cuu duoc pipe
    (muxer can seek lui de dien so frame/byte, pipe khong seek
    duoc; da kiem chung: pipe+flag van 16749 byte, khong header).
    Cung doi so ghi ra FILE (seekable) thi CO header Info o frame
    dau (flags=0xf, frames=58, bytes=16992) va doc dung 2.00 s.
    Client that ghi am native phai dua mot FILE cho sendVoice
    (bundle `u.append("fileContent", t)`), nen file cua no mang
    header Xing/Info nhu moi file MP3 ghi ra dia. Vi vay duong that
    o day ghi ra file tam trong thu muc tam (xoa ngay sau khi doc,
    TemporaryDirectory) thay vi stdout pipe; input van qua stdin
    pipe. Output byte-giong-het ban ghi ra file (17037 byte cho
    cung input 2 s). Tham so am thanh (16 kHz / 64 kbps / mono) thi KHONG co bang chung doi
    chieu truc tiep tu client PC: bundle khong co code ghi am
    (khong MediaRecorder/getUserMedia o bat cu chunk JS nao), chi
    co ffmpeg+LAME o phia native (Lavf58.45.100/Lavc58.91/
    LAME3.100) ma khong lo ti le lay mau; 16 kHz/64k/mono la lay tu
    file thoai AAC that tren duong mobile (25/09/2026), chua duoc
    xac minh cho duong MP3 PC — giu nguyen vi khong co bang chung
    nguoc, khong doi theo doan.
  * Timeout chuyen doi mac dinh 60 s (env VOICE_CONVERT_TIMEOUT_MS).
  * Loi ro rang, khong gui tin rong khi chuyen doi / tai len that
    bai; file tam (output ffmpeg) duoc xoa ngay sau khi doc xong
    (TemporaryDirectory).
  * Test mock ffmpeg bang cach inject ham chay (Node.js inject
    execFileAsync; o day inject `run`).

DIEM LECH CU — DA DAO NGUOC (2026-11-06, vong 112c):
Truoc day dich o day la MP3 (`-c:a libmp3lame -f mp3`) vi endpoint
voicemp3 (11148) / sendmp3 (11169) tu choi bat cu thu gi khong
phai MP3 — loi that 2026-11-05 23:03: inner error_code=133 "Ban
chi co the tai tap tin co dinh dang sau : MP3". NHUNG doc bundle
PC 26.11.10 ky lai cho thay sendVoice truc tiep KHONG CO caller
nao trong app (xem chat.send_voice): duong truc tiep la code chet,
va live 2026-11-06 08:36 +07 van tra 112 sau khi da sua clientId.
Duong that la upload-manager hai buoc (12060/12063 + asyncfile/
msg) — no doi file AAC (fileType "aac"|"amr", async tra {aac,
amr}), giong het Node.js. Nen dich o day BAY GIO LA AAC-LC ADTS
(`-c:a aac -f adts`), Y HET Node.js, khong con lech codec. Cac ham
MP3 cu van giu lai (de test + tai lieu hoa loi 133 cu), nhung
khong con duoc route sendvoice dung.
"""

import os
import shutil
import subprocess
import tempfile

# Tham so am thanh — GIONG Node.js (voiceAac.js): mono, 16 kHz,
# ~64 kbps. Cac hang MP3 duoi day la cua duong truc tiep cu
# (voicemp3 bat MP3) — giu lai cho ham MP3 cu + test; duong hai
# buoc hien tai dung hang AAC o duoi (VOICE_AAC_*).
VOICE_CHANNELS = 1
VOICE_SAMPLE_RATE = 16000
VOICE_BITRATE = "64k"
VOICE_CODEC = "libmp3lame"
VOICE_FORMAT = "mp3"
VOICE_FILENAME = "voice.mp3"
VOICE_MIME = "audio/mpeg"
DEFAULT_TIMEOUT_MS = 60000

# Tham so AAC — DUONG HAI BUOC HIEN TAI (giong het Node.js
# voiceAac.js: `-ac 1 -ar 16000 -c:a aac -b:a 64k -f adts`).
VOICE_AAC_CODEC = "aac"
VOICE_AAC_FORMAT = "adts"
VOICE_AAC_FILENAME = "voice.aac"
VOICE_AAC_MIME = "audio/aac"


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


def ffmpeg_args(output="pipe:1"):
    """Danh sach doi so ffmpeg — test pin giong cach Node.js pin
    `-ac 1 -ar 16000 -c:a aac -b:a 64k -f adts` (voiceMessage.test.js):
    o day `-ac 1 -ar 16000 -c:a libmp3lame -b:a 64k -f mp3`, CONG
    `-write_xing 1` (loi 112, vong 2, 2026-11-06). `output` la dich
    ghi MP3: mac dinh "pipe:1" (stdout, cho test inject `run`);
    duong that truyen duong dan FILE TAM (xem to_zalo_voice_mp3):
    chi output la file seekable thi ffmpeg moi ghi duoc header
    Xing/Info mang thoi luong — ghi ra pipe thi khong co header
    du co `-write_xing 1` (muxer can seek lui de dien so frame),
    ffprobe chi doan duoc thoi luong tu bitrate (2.09 s cho file
    2.00 s that; doc qua pipe thi Duration: N/A), trong khi ghi
    ra file thi CO header Info o frame dau va doc dung 2.00 s.
    Khong doi tham so am thanh (van mono 16 kHz 64 kbps)."""
    return ["-hide_banner", "-loglevel", "error", "-y",
            "-i", "pipe:0",
            "-vn", "-ac", str(VOICE_CHANNELS),
            "-ar", str(VOICE_SAMPLE_RATE),
            "-c:a", VOICE_CODEC, "-b:a", VOICE_BITRATE,
            "-write_xing", "1",
            "-f", VOICE_FORMAT, output]


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


def _default_run(binary, args, data, timeout_s, label="MP3"):
    """Chay ffmpeg that: doc stdin; lay output o stdout (neu args ket
    thuc bang "pipe:1") hoac doc lai tu file output (neu args ket
    thuc bang duong dan file — duong that, de MP3 co header
    Xing/Info; xem ffmpeg_args). Loi tra ve stderr (cat ngan, khong
    bao gom du lieu am thanh). `label` chi de hien trong loi
    ("MP3" cu / "AAC" moi)."""
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
            "chuyen file ghi am sang %s het thoi gian (>%ds)"
            % (label, timeout_s))
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise VoiceTranscodeError(
            "ffmpeg chuyen sang %s that bai (exit %d)%s"
            % (label, proc.returncode,
               (": " + detail[-300:]) if detail else ""))
    if args and args[-1] != "pipe:1":
        # Output la file tam: doc lai; stdout luc nay khong dung.
        try:
            with open(args[-1], "rb") as f:
                out = f.read()
        except OSError as e:
            raise VoiceTranscodeError(
                "ffmpeg khong tao duoc file %s (%s)" % (label, e))
        if not out:
            raise VoiceTranscodeError(
                "ffmpeg tra ve file %s rong" % label)
        return out
    if not proc.stdout:
        raise VoiceTranscodeError(
            "ffmpeg tra ve file %s rong" % label)
    return proc.stdout


def to_zalo_voice_mp3(data, ffmpeg_bin=None, timeout_ms=None,
                      run=None):
    """Doi bytes am thanh bat ky (webm/opus cua Chrome, mp4/aac cua
    Safari, wav...) sang MP3 mono 16 kHz 64 kbps — dung dinh dang
    voicemp3 chap nhan. `run` de test inject (giong Node.js inject
    execFileAsync). Tra ve bytes MP3. Duong that (khong inject):
    ffmpeg ghi ra FILE TAM trong thu muc tam (xoa ngay sau khi
    doc), KHONG ghi ra stdout pipe — chi file seekable moi co
    header Xing/Info mang thoi luong (xem ffmpeg_args); input van
    qua stdin pipe nhu cu."""
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
        if run is not None:
            return runner(binary, ffmpeg_args(), data, timeout_s)
        with tempfile.TemporaryDirectory(
                prefix="zalo-voice-") as tmpd:
            out_path = os.path.join(tmpd, VOICE_FILENAME)
            return runner(binary, ffmpeg_args(out_path), data,
                          timeout_s)
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


# -- AAC (duong hai buoc hien tai) ---------------------------------------
# Giong het Node.js voiceAac.js: AAC-LC 16 kHz mono 64 kbps ADTS.
# Duong upload-manager cua bundle doi file AAC (fileType "aac"),
# async tra {aac, amr} — day la dinh dang tin thoai that cua Zalo.


def ffmpeg_args_aac():
    """Danh sach doi so ffmpeg — Y HET Node.js pin trong
    voiceMessage.test.js: `-ac 1 -ar 16000 -c:a aac -b:a 64k
    -f adts`."""
    return ["-hide_banner", "-loglevel", "error", "-y",
            "-i", "pipe:0",
            "-vn", "-ac", str(VOICE_CHANNELS),
            "-ar", str(VOICE_SAMPLE_RATE),
            "-c:a", VOICE_AAC_CODEC, "-b:a", VOICE_BITRATE,
            "-f", VOICE_AAC_FORMAT, "pipe:1"]


def is_aac(data):
    """Nhan AAC ADTS that qua syncword 12 bit (0xFFF) + layer 00.
    Byte 1: 4 bit cao = 1111 (sync), 2 bit layer phai = 00 — nho
    do ma phan biet duoc voi frame MP3 (FF FB: layer = 01). Du de
    phan biet voi webm (EBML), mp4 (ftyp — AAC ben trong nhung
    khong phai ADTS tho), ogg, wav."""
    if not data or len(data) < 2:
        return False
    if data[0] != 0xFF or (data[1] & 0xF0) != 0xF0:
        return False
    layer = (data[1] >> 1) & 0x03
    return layer == 0x00


def to_zalo_voice_aac(data, ffmpeg_bin=None, timeout_ms=None,
                      run=None):
    """Doi bytes am thanh bat ky (webm/opus cua Chrome, mp4/aac cua
    Safari, wav...) sang AAC-LC mono 16 kHz 64 kbps ADTS — dung
    dinh dang duong upload-manager chap nhan. `run` de test inject
    (giong Node.js inject execFileAsync). Tra ve bytes AAC."""
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
    runner = run or (lambda b, a, d, t: _default_run(b, a, d, t, "AAC"))
    try:
        return runner(binary, ffmpeg_args_aac(), data, timeout_s)
    except VoiceTranscodeError:
        raise
    except subprocess.CalledProcessError as e:
        raise VoiceTranscodeError(
            "ffmpeg chuyen sang AAC that bai (exit %s)"
            % e.returncode)
    except subprocess.TimeoutExpired:
        raise VoiceTranscodeError(
            "chuyen file ghi am sang AAC het thoi gian (>%ds)"
            % timeout_s)
    except FileNotFoundError:
        raise VoiceTranscodeError(
            "khong tim thay ffmpeg (FFMPEG_BIN=%s): cai ffmpeg vao "
            "image/server de gui tin nhan thoai" % binary)
    except OSError as e:
        raise VoiceTranscodeError(
            "khong chay duoc ffmpeg: %s" % e)


def needs_aac_transcode(filename, mime, data):
    """File da la AAC ADTS thi gui thang (khong ton ffmpeg); con
    lai (webm/mp4/wav/mp3...) thi phai doi. Nhan dang theo NOI
    DUNG truoc (ADTS sync), ten/mime chi la goi y — trinh duyet co
    the dat ten .aac cho blob webm. MP4 chua AAC ben trong van
    phai doi vi no khong phai ADTS tho."""
    if data and is_aac(data):
        return False
    if data:
        return True
    name = (filename or "").lower()
    if name.endswith(".aac"):
        return False
    return (mime or "").lower() not in ("audio/aac", "audio/mp4a-latm")


def ensure_voice_aac(filename, mime, data, ffmpeg_bin=None,
                     timeout_ms=None, run=None):
    """Dam bao file gui qua duong hai buoc la AAC ADTS. Tra ve
    (bytes, ten file, mime, da_chuyen_doi: bool). File AAC that tra
    nguyen; file khac duoc doi bang ffmpeg truoc khi gui."""
    if not needs_aac_transcode(filename, mime, data):
        return data, VOICE_AAC_FILENAME, VOICE_AAC_MIME, False
    aac = to_zalo_voice_aac(data, ffmpeg_bin=ffmpeg_bin,
                            timeout_ms=timeout_ms, run=run)
    return aac, VOICE_AAC_FILENAME, VOICE_AAC_MIME, True
