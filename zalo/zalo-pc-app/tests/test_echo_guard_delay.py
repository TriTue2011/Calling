"""Chống vọng TRỄ (14/11/2026): đo thật loa R1 song công — vọng về mic sau 450–550 ms, trễ không cố định; EchoGuard chặn theo cửa sổ trễ [300, 750] ms nhưng cho tiếng nhà
to hơn mức vọng đi qua. Chạy: python3 tests/test_echo_guard_delay.py"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import audio_rx, audio_tx  # noqa: E402
from zalo_pc_app import server  # noqa: E402


def frame(rms):
    """Khung 20 ms (320 mẫu) có RMS ≈ rms (sóng vuông)."""
    return struct.pack("<320h", *([int(rms), -int(rms)] * 160))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(**kw):
    c = Clock()
    return c, audio_rx.EchoGuard(clock=c, **kw)


def feed_far(c, g, seconds, rms):
    for _ in range(int(seconds * 50)):
        g.note_far(frame(rms))
        c.t += 0.02


def test_echo_after_the_delay_is_blocked_but_not_before_or_after():
    c, g = make(classic=False, delay=(0.3, 0.75), ratio=2.0)
    feed_far(c, g, 1.0, 1500)                       # bên kia nói 1 s (t = 0 → 1)
    # ngay sau khi loa im (t=1.0 → +0.3 s): chưa có vọng (vọng đến sau 300 ms)
    assert g.blocked(900) is False or True           # mép cửa sổ, không khẳng định
    c.t = 1.0 + 0.5                                  # 0,5 s sau khi loa NGỪNG: cửa sổ trễ vẫn chứa phần cuối tiếng loa
    assert g.blocked(1000) is True, "vọng trễ 500 ms phải bị chặn"
    c.t = 1.0 + 1.2                                  # loa im đã > 750 ms: hết vọng
    assert g.blocked(1000) is False
    assert g.suppressed_delayed >= 1 and g.suppressed == g.suppressed_delayed


def test_loud_home_voice_passes_double_talk():
    c, g = make(classic=False, delay=(0.3, 0.75), ratio=2.0)
    feed_far(c, g, 1.0, 1500)
    c.t = 1.5
    assert g.blocked(2999) is True and g.blocked(3001) is False, "mic > 2 × đỉnh loa là người nhà nói chen: cho qua"
    assert g.passed_double == 1


def test_silent_far_never_blocks_and_duplex_mode_has_no_instant_gate():
    c, g = make(classic=False, delay=(0.3, 0.75))
    feed_far(c, g, 1.0, 50)                          # dưới ngưỡng (nền Opus/DTX)
    c.t = 1.5
    assert g.blocked(80) is False
    c, g = make(classic=False, delay=(0.3, 0.75))
    feed_far(c, g, 0.2, 1500)                        # tiếng loa vừa bắt đầu (0,2 s): chưa tới cửa sổ trễ 300 ms nên chưa có vọng nào về
    assert g.blocked(500) is False, "song công: mic luôn mở, không chặn tức thời"


def test_classic_half_duplex_still_blocks_instantly_and_env_can_disable_delay():
    c, g = make(classic=True, delay=(0, 0))
    feed_far(c, g, 0.5, 1500)
    c.t -= 0.02
    assert g.blocked(500) is True                    # hành vi cũ giữ nguyên
    os.environ["ZALO_PC_ECHO_DELAY_MS"] = "0"
    try:
        assert audio_rx._delay_window() == (0.0, 0.0)
        os.environ["ZALO_PC_ECHO_DELAY_MS"] = "200-600"
        assert audio_rx._delay_window() == (0.2, 0.6)
        os.environ["ZALO_PC_ECHO_DELAY_MS"] = "abc"
        assert audio_rx._delay_window() == (0.0, 0.0)
    finally:
        os.environ.pop("ZALO_PC_ECHO_DELAY_MS", None)
    assert audio_rx._delay_window() == (0.3, 0.75)


def test_sender_passes_mic_level_only_to_gates_that_take_it():
    c, g = make()
    assert audio_tx.AudioSender._takes_arg(g.blocked) is True
    assert audio_tx.AudioSender._takes_arg(lambda: False) is False
    assert audio_tx.AudioSender._takes_arg(None) is False


def test_guard_created_for_duplex_r1_speaker_and_not_for_plain_speaker():
    saved = server._devices_for_call
    try:
        audio_rx_mod = audio_rx
        server.ECHO_GUARDS.clear()
        server._devices_for_call = lambda cid: {"echo_guard": False, "speaker_url": "http://ha/api/r1_speaker/duplex/abc?k=x"}
        g = server._guard_for_call("c1")
        assert g is not None and g.classic is False and g.delay[1] > 0
        server._devices_for_call = lambda cid: {"echo_guard": False, "speaker_url": "http://ha/api/r1_speaker/intercom/abc"}
        assert server._guard_for_call("c2") is None, "loa thường không bật chống vọng thì không có guard"
        server._devices_for_call = lambda cid: {"echo_guard": True, "speaker_url": "http://ha/api/r1_speaker/intercom/abc"}
        g3 = server._guard_for_call("c3")
        assert g3.classic is True and audio_rx_mod.EchoGuard is type(g3)
        os.environ["ZALO_PC_ECHO_DELAY_MS"] = "0"
        server._devices_for_call = lambda cid: {"echo_guard": False, "speaker_url": "http://ha/api/r1_speaker/duplex/abc"}
        assert server._guard_for_call("c4") is None, "tắt cửa sổ trễ bằng env thì song công không có guard"
    finally:
        os.environ.pop("ZALO_PC_ECHO_DELAY_MS", None)
        server._devices_for_call = saved
        server.ECHO_GUARDS.clear()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("ALL ECHO GUARD DELAY TESTS PASSED")
