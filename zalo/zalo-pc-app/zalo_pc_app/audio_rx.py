"""Loa truc tiep: dua tieng ben kia thang vao «cua bo dam» cua thiet bi, va chong vong.

Bo dam (R1, camera Imou/Dahua qua tich hop HA) nhan luong A-law 8 kHz bang
`POST /api/<tich hop>/intercom/<id>?k=<khoa>` — duong go2rtc cung dung. App chay ffmpeg:
PCM16 16 kHz (stdin) -> A-law 8 kHz -> POST. Khong qua may phat nhac (DLNA) nen khong
co bo dem vai giay.

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

from . import call_audio

RMS_THRESHOLD = 180.0       # duoi muc nay coi la im lang (nen cua luong Opus/DTX)
HOLD_SECONDS = 0.5          # het tieng that van chan mic them chung nay (duoi vong phong)


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

    def note_far(self, frame):
        if frame_rms(frame) >= self.threshold:
            self._until = self._clock() + self.hold

    def blocked(self):
        if self._clock() < self._until:
            self.suppressed += 1
            return True
        return False


def build_ffmpeg_args(url, ffmpeg="ffmpeg"):
    """stdin PCM16 16 kHz mono -> A-law 8 kHz mono -> POST (chunked) toi `url`."""
    return [ffmpeg, "-hide_banner", "-loglevel", "error",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-probesize", "32", "-analyzeduration", "0",
            "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", "-",
            "-ac", "1", "-ar", "8000", "-c:a", "pcm_alaw", "-f", "alaw",
            "-flush_packets", "1", "-method", "POST", "-chunked_post", "1",
            "-content_type", "application/octet-stream", url]


class AudioSink:
    def __init__(self, engine, url, guard=None, popen=None, clock=time.monotonic,
                 sleep=time.sleep):
        self._engine = engine
        self._args = build_ffmpeg_args(url)
        self._guard = guard
        self._popen = popen or subprocess.Popen
        self._clock, self._sleep = clock, sleep
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self.frames = 0
        self.errors = 0
        self.last_error = ""
        self.started_at = None
        self.alive = False

    def start(self):
        if shutil.which(self._args[0]) is None and self._popen is subprocess.Popen:
            raise RuntimeError("ffmpeg: khong co trong may")
        self._proc = self._popen(self._args, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 bufsize=0)
        self.started_at = time.time()
        self.alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _write(self, frame):
        if self._guard is not None:
            self._guard.note_far(frame)
        try:
            self._proc.stdin.write(frame)
            self.frames += 1
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

    def _kill(self):
        proc = self._proc
        if proc is None:
            return
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._kill()

    def status(self):
        return {"alive": self.alive, "frames": self.frames, "errors": self.errors,
                "last_error": self.last_error,
                "echo_guard": self._guard is not None,
                "mic_suppressed": self._guard.suppressed if self._guard else 0,
                "seconds": (round(time.time() - self.started_at, 1)
                            if self.started_at else 0)}
