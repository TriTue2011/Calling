"""ffmpeg_log: stderr của ffmpeg con được giữ lại (đã che khoá/mật khẩu), bộ gửi ghi log khi ffmpeg thoát ngoài ý muốn."""
import io
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from zalo_pc_app import ffmpeg_log, video_tx


class _Proc:
    """Process giả: stdout rỗng (ffmpeg chết ngay), stderr có lỗi kèm URL chứa mật khẩu và khoá."""
    def __init__(self, err):
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(err)
        self.returncode = 1

    def poll(self):
        return self.returncode

    def kill(self):
        pass


class _BlockingProc:
    """ffmpeg đang chạy bình thường: stdout chặn tới khi bị kill."""
    def __init__(self):
        self._ev = threading.Event()
        self.returncode = None
        outer = self

        class _Out:
            def read(self, n):
                outer._ev.wait(5)
                return b""
        self.stdout = _Out()
        self.stderr = io.BytesIO(b"")

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9
        self._ev.set()


class FfmpegLogTests(unittest.TestCase):
    def test_redact_che_mat_khau_va_khoa(self):
        t = ffmpeg_log.redact("rtsp://admin:S3cret@172.16.10.200:8554/x: 401 ; http://h/api/mic?k=ABC123&z=1")
        self.assertNotIn("S3cret", t)
        self.assertNotIn("ABC123", t)
        self.assertIn("172.16.10.200", t)

    def test_tail_giu_dong_cuoi_va_che_bi_mat(self):
        p = _Proc(b"line1\nrtsp://u:pw@h/s: Server returned 401 Unauthorized\n")
        tail = ffmpeg_log.StderrTail(p)
        tail._thread.join(2)
        self.assertIn("401 Unauthorized", tail.text())
        self.assertNotIn("pw@", tail.text())

    def test_process_gia_khong_stderr_khong_loi(self):
        class P:  # khong co stderr
            stdout = io.BytesIO(b"")
        self.assertEqual(ffmpeg_log.StderrTail(P()).text(), "")

    def test_video_sender_ghi_log_khi_ffmpeg_chet_ngay_kem_ly_do(self):
        logs = []
        s = video_tx.VideoSender(lambda au, key: True, source="rtsp://u:pw@h/s", log=logs.append,
                                 popen=lambda *a, **k: _Proc(b"rtsp://u:pw@h/s: Server returned 401 Unauthorized (authorization failed)\n"))
        s.start()
        s._thread.join(3)
        time.sleep(0.2)
        self.assertEqual(len(logs), 1, logs)
        self.assertIn("rc=1", logs[0])
        self.assertIn("401", logs[0])
        self.assertNotIn("pw@", logs[0])
        self.assertIn("401", s.status()["ffmpeg_err"])

    def test_dung_co_chu_y_khong_ghi_log_loi(self):
        logs = []
        s = video_tx.VideoSender(lambda au, key: True, log=logs.append, popen=lambda *a, **k: _BlockingProc())
        s.start()
        s.stop()
        time.sleep(0.2)
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
