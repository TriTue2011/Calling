"""Loa truc tiep: dua tieng ben kia thang vao «cua bo dam» cua thiet bi, va chong vong.

Bo dam (R1, camera Imou/Dahua qua tich hop HA) nhan luong A-law 8 kHz bang
`POST /api/<tich hop>/intercom/<id>?k=<khoa>` — duong go2rtc cung dung. App chay ffmpeg:
PCM16 16 kHz (stdin) -> A-law 8 kHz -> POST. Khong qua may phat nhac (DLNA) nen khong
co bo dem vai giay.

Phien song cong cua R1 (`POST /api/r1_speaker/duplex/<id>?k=`): nhan PCM16 16 kHz tho (khong
A-law), mic van mo, loa R1 tu khu vong. Mic cua R1 PHAI duoc mo sau khi phien nay bat dau (neu
khong HA tra luong mic tho chua khu vong): `DUPLEX_SETTLE_SECONDS` la thoi gian cho do.

Chong vong (`EchoGuard`): mic va loa cung mot thiet bi (R1) thi mic thu lai tieng loa roi
gui nguoc cho ben kia. Khi loa dang phat tieng that thi tam NGUNG gui mic
(nua song cong, nhu bo dam); het tieng `hold` giay thi gui lai.

Khong ghi URL (co khoa/mat khau) vao log hay trang thai.
"""

import math
import shutil
import struct
import subprocess
import threading
import time

from . import audio_gain, call_audio, ffmpeg_log

RMS_THRESHOLD = 180.0       # duoi muc nay coi la im lang (nen cua luong Opus/DTX)
HOLD_SECONDS = 0.25         # het tieng that van chan mic them chung nay (duoi vong phong). 0,5 -> 0,25 (13/11): chu may bao mic loa chuyen qua lai bi tre
LEVEL_EDGES = (100, 180, 300, 500, 1000)   # ranh gioi cac bac RMS cua tieng ben kia (khung loa)
DUPLEX_SETTLE_SECONDS = 0.8  # cho phien song cong cua R1 mo xong roi moi mo mic


def frame_rms(frame):
    n = len(frame) // 2
    if not n:
        return 0.0
    vals = struct.unpack("<%dh" % n, frame[:n * 2])
    return math.sqrt(sum(v * v for v in vals) / n)


class EchoGuard:
    """Chan mic trong luc loa phat tieng that. `note_far` goi cho MOI khung loa ra;
    `blocked` hoi mic co phai nin khong. Thread-safe vi chi doi mot so thuc."""

    def __init__(self, threshold=RMS_THRESHOLD, hold=HOLD_SECONDS, clock=time.monotonic):
        self.threshold, self.hold, self._clock = threshold, hold, clock
        self._until = 0.0
        self.suppressed = 0
        self.levels = [0] * (len(LEVEL_EDGES) + 1)    # so khung loa theo muc RMS (do nen tieng ben kia de biet nguong co hop khong)

    def note_far(self, frame):
        rms = frame_rms(frame)
        self.levels[sum(1 for e in LEVEL_EDGES if rms >= e)] += 1
        if rms >= self.threshold:
            self._until = self._clock() + self.hold

    def blocked(self):
        if self._clock() < self._until:
            self.suppressed += 1
            return True
        return False


def is_duplex_url(url):
    """URL phien song cong cua R1 (nhan PCM16 16 kHz tho)."""
    return "/api/r1_speaker/duplex/" in str(url or "")


def build_ffmpeg_args(url, ffmpeg="ffmpeg"):
    """stdin PCM16 16 kHz mono -> POST (chunked) toi `url`: A-law 8 kHz cho cua bo dam,
    PCM16 16 kHz tho cho phien song cong cua R1."""
    head = [ffmpeg, "-hide_banner", "-loglevel", "error",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-probesize", "32", "-analyzeduration", "0",
            "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", "-"]
    if is_duplex_url(url):
        out = ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "s16le"]
    else:
        out = ["-ac", "1", "-ar", "8000", "-c:a", "pcm_alaw", "-f", "alaw"]
    return head + out + ["-flush_packets", "1", "-method", "POST", "-chunked_post", "1",
                         "-content_type", "application/octet-stream", url]


class AudioSink:
    def __init__(self, engine, url, guard=None, popen=None, clock=time.monotonic,
                 sleep=time.sleep, log=None):
        self._log = log
        self._tail = None
        self._engine = engine
        self._args = build_ffmpeg_args(url)
        self.target = url               # de nhan ra cung dich (KHONG ghi ra log/trang thai: co khoa)
        self._guard = guard
        self.gain = audio_gain.DEFAULT_PERCENT   # % am luong loa (100 = giu nguyen), doi duoc giua cuoc goi
        self._popen = popen or subprocess.Popen
        self._clock, self._sleep = clock, sleep
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self.frames = 0
        self.silence = 0                # khung im lang phat ra vi hang doi can (khung den tre / ben kia im)
        self.errors = 0
        self.last_error = ""
        self.started_at = None
        self.alive = False

    def start(self):
        if shutil.which(self._args[0]) is None and self._popen is subprocess.Popen:
            raise RuntimeError("ffmpeg: khong co trong may")
        self._proc = self._popen(self._args, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 bufsize=0)
        self._tail = ffmpeg_log.StderrTail(self._proc)
        self.started_at = time.time()
        self.alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _write(self, frame):
        if self._guard is not None:
            self._guard.note_far(frame)
        silent = frame == call_audio.SILENCE
        try:
            self._proc.stdin.write(audio_gain.apply_gain(frame, self.gain))     # sau note_far: nguong chong vong do tren tieng GOC
            self.frames += 1
            if silent:
                self.silence += 1
        except (OSError, ValueError) as exc:        # ffmpeg dong (thiet bi tu choi / het cho)
            self.errors += 1
            self.last_error = str(exc)[:60]
            raise

    def _run(self):
        try:
            call_audio.stream_out(
                self._engine, self._write,
                lambda: not self._stop.is_set() and self._proc.poll() is None,
                clock=self._clock, sleep=self._sleep, header=False)
        except (OSError, ValueError):
            pass
        finally:
            self.alive = False
            self._kill()
            if self._log is not None and not self._stop.is_set():
                try:
                    self._log("loa ffmpeg thoat ngoai y muon rc=%s frames=%d err=%s"
                              % (self._proc.poll(), self.frames, self.stderr_tail() or "-"))
                except Exception:  # noqa: BLE001 - ghi log khong duoc lam hong luong
                    pass

    def stderr_tail(self):
        return self._tail.text() if self._tail is not None else ""

    def _kill(self):
        proc = self._proc
        if proc is None:
            return
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        ffmpeg_log.kill_and_reap(proc)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._kill()

    def status(self):
        return {"alive": self.alive, "frames": self.frames, "silence": self.silence, "errors": self.errors, "gain": self.gain,
                "last_error": self.last_error,
                "ffmpeg_err": self.stderr_tail(),
                "echo_guard": self._guard is not None,
                "mic_suppressed": self._guard.suppressed if self._guard else 0,
                "far_levels": ("/".join(str(n) for n in self._guard.levels) if self._guard else "-"),   # <100/<180/<300/<500/<1000/>=1000
                "seconds": (round(time.time() - self.started_at, 1)
                            if self.started_at else 0)}
