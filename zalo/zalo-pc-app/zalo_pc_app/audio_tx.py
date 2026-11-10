"""Phat tieng (mic) len cuoc goi tu mot nguon bat ky: ffmpeg -> PCM16 16 kHz mono
-> `send_pcm` dung nhip 20 ms.

Nguon (`source`):
  "test"             am 440 Hz (kiem tra);
  rtsp:// rtsps://   luong camera / go2rtc (lay tieng cua luong), mo bang TCP;
  http(s):// ...     luong mang khac; neu `fmt` = "s16le16k" thi la PCM16 mono
                     16 kHz tho (vi du mic loa R1: /api/r1_speaker/mic/<id>?k=..);
  duong dan tep      phat lap lai.

Bo gui giu nhip rieng (20 ms theo dong ho): ffmpeg doc luong that co the den
thanh cum, phat ngay se tao jitter (dien thoai bao mang yeu). Khi hang doi
vuot MAX_BACKLOG khung thi bo khung cu. Khong ghi URL (co the chua mat khau)
vao log hay trang thai.
"""

import collections
import shutil
import subprocess
import threading
import time

FRAME_BYTES = 640           # 20 ms PCM16 mono 16 kHz
FRAME_SECONDS = 0.02
MAX_BACKLOG = 10            # > 200 ms ton dong thi bo khung cu (giu do tre thap)
FORMATS = ("auto", "s16le16k")


# Do 10/11 tren luong mic R1 that: ffmpeg mac dinh doi ~3,3 s (do dinh dang) roi xa don gap 4 lan,
# app mat 3 s tiep dau va bo ~150 khung. Co do tre thap dua byte dau ve ~0,25 s va deu dan.
LOW_LATENCY = ["-fflags", "nobuffer", "-flags", "low_delay"]


def build_ffmpeg_args(source, fmt="auto", ffmpeg="ffmpeg"):
    src = str(source or "test")
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if src == "test":
        args += ["-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000"]
    elif src.startswith(("rtsp://", "rtsps://")):
        # Can do ~1 s de nhan ra luong tieng; RTSP khac 0 s se khong thay audio.
        args += ["-rtsp_transport", "tcp"] + LOW_LATENCY \
            + ["-analyzeduration", "1000000", "-probesize", "200000", "-i", src]
    elif src.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        if fmt == "s16le16k":                    # dinh dang da biet: khong can do
            args += LOW_LATENCY + ["-probesize", "32", "-analyzeduration", "0",
                                   "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", src]
        else:
            args += LOW_LATENCY + ["-analyzeduration", "1000000", "-i", src]
    else:
        args += ["-re", "-stream_loop", "-1", "-i", src]
    args += ["-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"]
    return args


class AudioSender:
    def __init__(self, send_pcm, source="test", fmt="auto", popen=None,
                 clock=time.monotonic, sleep=time.sleep):
        if fmt not in FORMATS:
            raise ValueError("fmt khong hop le: %r" % (fmt,))
        self._send = send_pcm
        self._args = build_ffmpeg_args(source, fmt)
        self._popen = popen or subprocess.Popen
        self._clock, self._sleep = clock, sleep
        self._proc = None
        self._queue = collections.deque()
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._threads = []
        self.frames = 0
        self.dropped = 0
        self.errors = 0
        self.last_error = ""
        self.started_at = None
        self.alive = False

    def start(self):
        if shutil.which(self._args[0]) is None and self._popen is subprocess.Popen:
            raise RuntimeError("ffmpeg: khong co trong may")
        self._proc = self._popen(self._args, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=0)
        self.started_at = time.time()
        self.alive = True
        self._threads = [threading.Thread(target=self._read, daemon=True),
                         threading.Thread(target=self._pace, daemon=True)]
        for t in self._threads:
            t.start()

    def _read(self):
        buf = b""
        try:
            while not self._stop.is_set():
                data = self._proc.stdout.read(FRAME_BYTES)
                if not data:
                    break
                buf += data
                while len(buf) >= FRAME_BYTES:
                    frame, buf = buf[:FRAME_BYTES], buf[FRAME_BYTES:]
                    with self._cv:
                        self._queue.append(frame)
                        while len(self._queue) > MAX_BACKLOG:
                            self._queue.popleft()
                            self.dropped += 1
                        self._cv.notify()
        finally:
            self.alive = False
            with self._cv:
                self._cv.notify_all()
            self._kill()

    def _pace(self):
        due = None
        while not self._stop.is_set():
            with self._cv:
                while not self._queue and not self._stop.is_set():
                    if not self.alive:
                        return
                    self._cv.wait(0.2)
                    due = None             # nguon im: tinh lai nhip khi co tieng
                if self._stop.is_set() or not self._queue:
                    continue
                frame = self._queue.popleft()
            now = self._clock()
            if due is None or now - due > 0.1:
                due = now
            elif due > now:
                self._sleep(due - now)
            due += FRAME_SECONDS
            try:
                self._send(frame)
                self.frames += 1
            except Exception as exc:  # noqa: BLE001 - tiep tuc khung sau
                self.errors += 1
                self.last_error = str(exc)[:80]

    def _kill(self):
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def stop(self):
        self._stop.set()
        self._kill()
        with self._cv:
            self._cv.notify_all()
        for t in self._threads:
            t.join(timeout=2)

    def status(self):
        return {"alive": self.alive, "frames": self.frames,
                "dropped": self.dropped, "errors": self.errors,
                "last_error": self.last_error,
                "seconds": (round(time.time() - self.started_at, 1)
                            if self.started_at else 0)}
