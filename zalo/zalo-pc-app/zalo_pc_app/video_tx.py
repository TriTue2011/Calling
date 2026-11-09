"""Phat hinh len cuoc goi: ffmpeg (libx264) -> khung H.264 Annex-B -> transport.

Nguon (`source`):
  "test"            hinh kiem tra (lavfi testsrc2), chay dung nhip thuc;
  rtsp:// rtsps://  luong camera (go2rtc / camera HA), mo bang TCP;
  http(s):// rtmp://  luong mang khac;
  duong dan tep     phat lap lai.

Dau ra x264 profile baseline, khong B-frame, moi khung bat dau bang AUD (de tach
khung), SPS/PPS lap lai o moi khung khoa; khung khoa moi `gop_seconds` giay
(ffmpeg khong ep duoc khung khoa giua chung, nen khi dien thoai doi PLI phai
cho khung khoa ke tiep). Ham `send_frame(annexb, key)` do ben goi cung cap
(`Udp4200Transport.send_video_frame`). Khong ghi URL (co the chua mat khau)
vao log.
"""

import shutil
import subprocess
import threading
import time


def _nal_types(buf):
    """Tap kieu NAL trong mot khung Annex-B (sau moi ma 00 00 01)."""
    out, i = set(), 0
    while True:
        i = buf.find(b"\x00\x00\x01", i)
        if i < 0 or i + 3 >= len(buf):
            return out
        out.add(buf[i + 3] & 0x1F)
        i += 3


class AccessUnitSplitter:
    """Tach luong Annex-B thanh cac khung theo NAL AUD (loai 9)."""

    _AUD = b"\x00\x00\x01\x09"

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data):
        """Them du lieu; tra danh sach khung da day du (khung dang do giu lai)."""
        self._buf += data
        out = []
        while True:
            first = self._buf.find(self._AUD)
            if first < 0:
                break
            nxt = self._buf.find(self._AUD, first + 4)
            if nxt < 0:
                break
            end = nxt - 1 if self._buf[nxt - 1] == 0 else nxt
            start = first - 1 if first > 0 and self._buf[first - 1] == 0 else first
            out.append(bytes(self._buf[start:end]))
            del self._buf[:end]
        # Bo rac truoc AUD dau tien (neu luong bat dau giua chung).
        if not out and len(self._buf) > (1 << 22):
            del self._buf[:-4]
        return out


def is_key_frame(au):
    """Khung khoa = co NAL IDR (5) hoac SPS (7)."""
    types = _nal_types(au)
    return 5 in types or 7 in types


def build_ffmpeg_args(source, width=640, height=360, fps=15, bitrate_kbps=300,
                      gop_seconds=1.0, ffmpeg="ffmpeg"):
    src = str(source or "test")
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if src == "test":
        args += ["-re", "-f", "lavfi", "-i",
                 "testsrc2=size=%dx%d:rate=%d" % (width, height, fps)]
    elif src.startswith(("rtsp://", "rtsps://")):
        args += ["-rtsp_transport", "tcp", "-i", src]
    elif src.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        args += ["-i", src]
    else:
        args += ["-re", "-stream_loop", "-1", "-i", src]
    vf = ("scale=%d:%d:force_original_aspect_ratio=decrease,"
          "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,fps=%d,format=yuv420p"
          % (width, height, width, height, fps))
    gop = max(1, int(round(fps * gop_seconds)))
    args += ["-an", "-vf", vf, "-c:v", "libx264", "-profile:v", "baseline",
             "-level", "3.1", "-preset", "veryfast", "-tune", "zerolatency",
             "-b:v", "%dk" % bitrate_kbps, "-maxrate", "%dk" % bitrate_kbps,
             "-bufsize", "%dk" % max(bitrate_kbps, 100),
             "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
             "-bf", "0", "-x264-params", "aud=1:repeat-headers=1",
             "-f", "h264", "pipe:1"]
    return args


class VideoSender:
    def __init__(self, send_frame, source="test", width=640, height=360,
                 fps=15, bitrate_kbps=300, gop_seconds=1.0, popen=None):
        self._send = send_frame
        self._args = build_ffmpeg_args(source, width, height, fps,
                                       bitrate_kbps, gop_seconds)
        self._popen = popen or subprocess.Popen
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self.frames = 0
        self.keys = 0
        self.skipped = 0
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
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        splitter = AccessUnitSplitter()
        try:
            while not self._stop.is_set():
                data = self._proc.stdout.read(65536)
                if not data:
                    break
                for au in splitter.feed(data):
                    key = is_key_frame(au)
                    try:
                        if self._send(au, key):
                            self.frames += 1
                            self.keys += 1 if key else 0
                        else:
                            self.skipped += 1
                    except Exception as exc:  # noqa: BLE001 - tiep tuc khung sau
                        self.errors += 1
                        self.last_error = str(exc)[:80]
        finally:
            self.alive = False
            self._kill()

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
        if self._thread is not None:
            self._thread.join(timeout=2)

    def status(self):
        return {"alive": self.alive, "frames": self.frames, "keys": self.keys,
                "skipped_before_key": self.skipped, "errors": self.errors,
                "last_error": self.last_error,
                "seconds": (round(time.time() - self.started_at, 1)
                            if self.started_at else 0)}
