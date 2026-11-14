"""Luồng THOẠI/ÂM THANH của cuộc gọi (mic nhà → điện thoại, loa nhà ← điện thoại, chống vọng, bộ canh media chết). Tách từ server.py 14/11/2026."""
import os
import threading
import time
from .. import audio_rx as audio_rx_mod
from .. import audio_tx as audio_tx_mod

from ._srv import srv


AUDIO_SENDERS = {}               # call_id -> audio_tx.AudioSender (mic len cuoc goi)


SPEAKER_SINKS = {}               # call_id -> audio_rx.AudioSink (loa truc tiep)


ECHO_GUARDS = {}                 # call_id -> audio_rx.EchoGuard (mic nin khi loa phat)


def _stop_mic(call_id):
    sender = AUDIO_SENDERS.pop(str(call_id), None)
    if sender is not None:
        srv()._log_media_stats("mic", call_id, sender)
        sender.stop()
    return sender


def _stop_speaker(call_id):
    sink = SPEAKER_SINKS.pop(str(call_id), None)
    if sink is not None:
        srv()._log_media_stats("speaker", call_id, sink)
    if sink is not None:
        sink.stop()
    return sink


def _guard_for_call(call_id):
    """EchoGuard cua cuoc goi (tao khi cai dat bat chong vong), dung chung cho mic va loa."""
    key = str(call_id)
    if key in ECHO_GUARDS:
        return ECHO_GUARDS[key]
    if srv()._devices_for_call(call_id).get("echo_guard"):
        ECHO_GUARDS[key] = audio_rx_mod.EchoGuard()
        return ECHO_GUARDS[key]
    return None


def _start_speaker(call_id, url):
    """Phat tieng ben kia thang vao loa `url` (cua bo dam A-law 8 kHz, hoac phien song cong cua R1
    PCM16 16 kHz). Da chay dung dich thi giu nguyen (dong POST = ket thuc phien song cong cua R1,
    keo theo luong mic). Nem RuntimeError."""
    engine = srv()._engine_for_call(call_id)
    # Tieng dau tien tu dien thoai co the toi truoc khi _answer_incoming kip gan engine (hang chuc ms): co transport roi thi doi engine toi 2 s.
    for _ in range(20):
        if engine is not None or srv()._transport_for_call(call_id) is None:
            break
        time.sleep(0.1)
        engine = srv()._engine_for_call(call_id)
    if engine is None:
        raise RuntimeError("no_live_transport")
    old = SPEAKER_SINKS.get(str(call_id))
    if old is not None and old.alive and getattr(old, "target", None) == url:
        return old
    _stop_speaker(call_id)
    sink = audio_rx_mod.AudioSink(engine, url, guard=_guard_for_call(call_id), log=srv()._log_call)
    sink.start()
    SPEAKER_SINKS[str(call_id)] = sink
    srv()._log_call("speaker sink start call_id=%s echo_guard=%s"
              % (call_id, bool(ECHO_GUARDS.get(str(call_id)))))
    return sink


def _start_mic(call_id, source, fmt="auto", loop=True, echo_gate=True):
    """Phat `source` len cuoc goi; thay bo gui cu. Nem ValueError/RuntimeError."""
    transport = srv()._transport_for_call(call_id)
    if transport is None:
        raise RuntimeError("no_live_transport")
    # Loa la phien song cong cua R1: phai mo phien TRUOC roi moi mo mic, neu khong HA tra luong
    # mic tho (chua khu vong) cho den het cuoc goi.
    spk = srv()._devices_for_call(call_id).get("speaker_url") or ""
    if audio_rx_mod.is_duplex_url(spk) and str(call_id) not in SPEAKER_SINKS:
        _start_speaker(call_id, spk)
        time.sleep(audio_rx_mod.DUPLEX_SETTLE_SECONDS)
    _stop_mic(call_id)
    # Chong vong chi danh cho MIC THAT (mic va loa cung thiet bi). Giong noi TTS (echo_gate=False) khong the gay vong, ma neu bi gate thi
    # moi khung bi chan luc loa phat tieng ben kia -> nghe GIAT CUC (su co 11/11).
    guard = _guard_for_call(call_id) if echo_gate else None
    sender = audio_tx_mod.AudioSender(transport.send_pcm, source=source, fmt=fmt,
                                      gate=guard.blocked if guard else None, log=srv()._log_call, loop=loop)
    sender.start()
    AUDIO_SENDERS[str(call_id)] = sender
    srv()._log_call("mic start call_id=%s source=%s" % (
        call_id, "test" if source == "test" else "stream"))
    return sender


DEAD_MEDIA_SECONDS = float(os.environ.get("ZALO_PC_DEAD_MEDIA_SECONDS", "7") or 0)


def _media_is_dead(counters):
    """Chết = chưa nhận gói tiếng/hình nào GIẢI MÃ ĐƯỢC. rtp_rx đếm cả gói bị loại (xác thực SRTP hỏng) nên trừ rtp_rx_dropped;
    RTCP không tính (điện thoại vẫn gửi RTCP dù không gửi tiếng). Cuộc 14/11 23:14: 12 gói đều bị loại + 2 RTCP, điện thoại
    không gửi tiếng và tự cúp sau 17 giây, mà bộ canh cũ tưởng còn sống."""
    c = counters or {}
    return not (max(0, c.get("rtp_rx", 0) - c.get("rtp_rx_dropped", 0)) or c.get("video_rx", 0))


def _watch_dead_media(call_id, delay=None, sleep=time.sleep):
    """Sau `delay` giây kể từ lúc nghe máy: nếu cuộc vẫn đang nối mà không nhận gói nào từ điện thoại thì kết thúc với lý do dead_media."""
    delay = DEAD_MEDIA_SECONDS if delay is None else delay
    if delay <= 0:
        return None

    def run():
        sleep(delay)
        try:
            live = next((c for c in srv().STATE.calls.snapshot()["calls"]
                         if str(c["call_id"]) == str(call_id) and c["status"] == "answered"), None)
            tr = srv()._transport_for_call(call_id)
            if live is None or tr is None or not _media_is_dead(getattr(tr, "counters", {})):
                return
            srv()._log_call("dead media call_id=%s: %.0fs sau khi nghe may dien thoai chua gui goi nao -> ket thuc de goi lai" % (call_id, delay))
            srv()._terminate_call(int(call_id), "dead_media", srv().STATE.session)
        except Exception as e:  # noqa: BLE001 - bộ canh không được làm hỏng gì
            srv()._log_call("dead media call_id=%s: loi bo canh %s: %s" % (call_id, type(e).__name__, str(e)[:80]))
    t = threading.Thread(target=run, daemon=True, name="dead-media-watch")
    t.start()
    return t
