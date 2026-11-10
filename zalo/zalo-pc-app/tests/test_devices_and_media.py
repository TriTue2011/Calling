"""Cai dat thiet bi mac dinh, bo gui mic (ffmpeg gia) va diem cat chuyen thoai -> video."""

import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

from zalo_pc_app import audio_tx, devices, protocol  # noqa: E402


def test_mask_and_valid_source():
    assert devices.mask_url("rtsp://u:p4ss@h:8554/x") == "rtsp://u:***@h:8554/x"
    assert devices.mask_url("http://h/api") == "http://h/api"
    assert devices.mask_url("http://ha:8123/api/r1_speaker/mic/E1?k=SECRET&x=1") == \
        "http://ha:8123/api/r1_speaker/mic/E1?k=***&x=1"
    assert devices.mask_url("rtsp://u:p@h/x?token=abc") == "rtsp://u:***@h/x?token=***"
    for ok in ("", "test", "rtsp://h/x", "https://h/x?k=1", "/media/a.wav"):
        assert devices.valid_source(ok), ok
    for bad in ("ftp://h/x", "rm -rf /", "/a/../b", "javascript:1", "rtsp://h x"):
        assert not devices.valid_source(bad), bad


def test_store_defaults_update_validate_and_mask():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "devices.json")
    st = devices.DeviceStore(path)
    assert st.get()["auto_mic"] is True and st.get()["mic_url"] == ""
    st.update({"mic_url": "http://h:8123/api/r1_speaker/mic/x?k=abc",
               "mic_format": "s16le16k",
               "camera_url": "rtsp://u:pw@172.16.10.200:8554/phong-khach-sub",
               "video": {"fps": 99, "width": 800}, "auto_video_on_request": False})
    got = st.get()
    assert got["video"]["fps"] == 30 and got["video"]["width"] == 800   # kep trong gioi han
    assert got["auto_video_on_request"] is False and got["mic_format"] == "s16le16k"
    assert got["auto_video_delay"] == 0
    assert st.update({"auto_video_delay": 9999})["auto_video_delay"] == 120     # kep trong gioi han
    assert st.update({"auto_video_delay": "7"})["auto_video_delay"] == 7
    assert st.update({"auto_video_delay": -5})["auto_video_delay"] == 0
    pub = st.public()
    assert pub["camera_url"] == "rtsp://u:***@172.16.10.200:8554/phong-khach-sub"
    # Che ca khoa trong query; gui lai ban da che van giu khoa that.
    assert "abc" not in st.public()["mic_url"] and st.public()["mic_url"].endswith("?k=***")
    st.update({"mic_url": st.public()["mic_url"]})
    assert st.get()["mic_url"].endswith("?k=abc")
    # Gui lai ban da che thi giu nguyen mat khau that.
    st.update({"camera_url": pub["camera_url"]})
    assert st.get()["camera_url"].endswith("u:pw@172.16.10.200:8554/phong-khach-sub")
    for bad in ({"mic_url": "ftp://x"}, {"mic_format": "mp3"}, {"video": {"fps": "x"}},
                {"auto_video_delay": "abc"}):
        try:
            st.update(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    assert st.get()["camera_url"].startswith("rtsp://")                 # loi khong lam hong
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"                # tep chua mat khau
    again = devices.DeviceStore(path).get()                              # nap lai tu dia
    assert again["mic_url"] == st.get()["mic_url"] and again["video"]["fps"] == 30
    open(path, "w").write("{hong")
    assert devices.DeviceStore(path).get()["mic_url"] == ""              # tep hong -> mac dinh


def test_ffmpeg_args_per_source():
    t = audio_tx.build_ffmpeg_args("test")
    assert "lavfi" in t and t[-1] == "pipe:1" and "s16le" in t
    r = audio_tx.build_ffmpeg_args("rtsp://h/x")
    assert r[r.index("-rtsp_transport") + 1] == "tcp" and "-re" not in r
    assert "nobuffer" in r and r[r.index("-analyzeduration") + 1] == "1000000"   # van nhan ra luong audio
    assert r.index("-analyzeduration") < r.index("-i")                           # tuy chon dat TRUOC -i
    p = audio_tx.build_ffmpeg_args("http://h/mic?k=1", "s16le16k")
    assert p[p.index("-f") + 1] == "s16le" and p.index("-i") > p.index("-ar")
    assert "nobuffer" in p and p[p.index("-probesize") + 1] == "32"               # PCM tho: khong do dinh dang
    assert p[p.index("-analyzeduration") + 1] == "0" and p.index("-probesize") < p.index("-i")
    h = audio_tx.build_ffmpeg_args("http://h/x.mp3")
    assert h.count("-f") == 1 and "-stream_loop" not in h and "-probesize" not in h
    assert "-stream_loop" in audio_tx.build_ffmpeg_args("/media/a.wav")


class _FakeProc:
    def __init__(self, data):
        import io
        self.stdout = io.BytesIO(data)

    def poll(self):
        return 0

    def kill(self):
        pass


def test_audio_sender_paces_frames_and_splits_odd_reads():
    frames = [bytes([i]) * 640 for i in range(1, 11)]
    data = b"".join(frames)
    got = []
    sender = audio_tx.AudioSender(lambda f: got.append((time.monotonic(), f)),
                                  popen=lambda *a, **k: _FakeProc(data))
    sender.start()
    deadline = time.time() + 3
    while len(got) < 10 and time.time() < deadline:
        time.sleep(0.02)
    assert [f for _, f in got] == frames
    gaps = [b[0] - a[0] for a, b in zip(got, got[1:])]
    assert all(g >= 0.012 for g in gaps), gaps          # dung nhip ~20 ms, khong dap mot cuc
    assert sum(gaps) / len(gaps) < 0.04
    assert sender.status()["frames"] == 10 and sender.status()["errors"] == 0
    sender.stop()


def test_audio_sender_drops_oldest_when_backlog_and_counts_errors():
    calls = []

    def send(f):
        calls.append(f[0])
        if len(calls) == 2:
            raise RuntimeError("no relay")
    data = b"".join(bytes([i]) * 640 for i in range(1, 40))
    sender = audio_tx.AudioSender(send, popen=lambda *a, **k: _FakeProc(data),
                                  sleep=lambda s: None)
    sender.start()
    time.sleep(0.5)
    st = sender.status()
    assert st["errors"] == 1 and st["last_error"] == "no relay"
    assert st["dropped"] >= 1 and calls[-1] == 39      # khung cuoi luon toi duoc
    sender.stop()


def test_audio_to_video_request_body():
    assert protocol.vc_a2v(123456789012, 77, 1) == {
        "uidTo": "123456789012", "callId": 77, "status": 1}
    assert protocol.vc_a2v("5", 9, 2)["status"] == 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL DEVICES/MEDIA TESTS PASSED")
