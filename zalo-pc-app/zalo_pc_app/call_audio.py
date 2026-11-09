"""Cau noi am thanh cuoc goi giua app va thiet bi BAT KY (loa/mic cua HA,
trinh duyet, may khac) — app khong biet thiet bi la gi, chi phat/nhan PCM.

Ra  (loa):  GET  /api/call/audio/out/<token>   -> WAV 16 kHz mono PCM16, phat
            lien tuc (am thanh ben kia; khung im lang khi chua co goi nao de
            thiet bi phat khong bi ngat luong). Thiet bi (media_player) khong
            co cookie nen dung TOKEN ngau nhien theo cuoc goi.
Vao (mic):  POST /api/call/audio/in/<call_id>  <- PCM16 16 kHz mono tho, boi
            so 640 byte (20 ms/khung). Dung cookie dang nhap app nhu moi
            /api/* khac.

Token chi duoc cap cho phien dang nhap (qua /api/calls) va het hieu luc khi
cuoc goi ket thuc. Chi giu trong bo nho. Khong ghi token vao log.
"""

import secrets
import struct
import threading

RATE = 16000
FRAME_BYTES = 640                  # 20 ms PCM16 mono @ 16 kHz
MAX_IN_BYTES = 64000               # ~2 s mot lan POST
SILENCE = bytes(FRAME_BYTES)


def wav_header(rate=RATE, channels=1, bits=16):
    """Header WAV cho luong KHONG biet do dai (kich thuoc 0xFFFFFFFF)."""
    block = channels * bits // 8
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * block,
                          block, bits)
            + b"data" + struct.pack("<I", 0xFFFFFFFF))


class CallAudioTokens:
    """token <-> call_id, trong bo nho, thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._by_token = {}
        self._by_call = {}

    def token_for(self, call_id):
        key = str(call_id)
        with self._lock:
            token = self._by_call.get(key)
            if token is None:
                token = secrets.token_urlsafe(24)
                self._by_call[key] = token
                self._by_token[token] = key
            return token

    def call_for(self, token):
        with self._lock:
            return self._by_token.get(token)

    def drop(self, call_id):
        with self._lock:
            token = self._by_call.pop(str(call_id), None)
            if token is not None:
                self._by_token.pop(token, None)


def split_frames(data):
    """(cac khung day du 640 byte, so byte le bi bo)."""
    n = len(data) // FRAME_BYTES
    frames = [bytes(data[i * FRAME_BYTES:(i + 1) * FRAME_BYTES])
              for i in range(n)]
    return frames, len(data) - n * FRAME_BYTES


def feed_frames(engine, data):
    """Dua PCM mic vao cuoc goi. Tra ve (so khung da gui, so loi, loi cuoi)."""
    frames, _rest = split_frames(data)
    sent = errors = 0
    last = ""
    for frame in frames:
        try:
            engine.send_pcm(frame)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - bao cao, khong ngat luong
            errors += 1
            last = str(exc)[:120]
    return sent, errors, last


def stream_out(engine, write, is_live, frame_timeout=0.02):
    """Ghi WAV lien tuc cho den khi `is_live()` sai hoac `write` loi.

    Co khung that thi gui ngay; khong co thi gui khung im lang sau
    `frame_timeout` de thiet bi phat khong bi can luong."""
    write(wav_header())
    while is_live():
        frame = engine.read_frame(timeout=frame_timeout)
        write(frame if frame is not None else SILENCE)
