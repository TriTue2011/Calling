"""Luồng THOẠI/ÂM THANH của cuộc gọi (mic nhà → điện thoại, loa nhà ← điện thoại, chống vọng, bộ canh media chết). Tách từ server.py 14/11/2026."""
import os
import threading
import time
from .. import audio_rx as audio_rx_mod
from .. import audio_tx as audio_tx_mod

import queue
import re
from .. import audio_gain as audio_gain_mod
from .. import call_audio as call_audio_mod
from .. import chat as chat_mod
from ._srv import srv


AUDIO_SENDERS = {}               # call_id -> audio_tx.AudioSender (mic len cuoc goi)


SPEAKER_SINKS = {}               # call_id -> audio_rx.AudioSink (loa truc tiep)


ECHO_GUARDS = {}                 # call_id -> audio_rx.EchoGuard (mic nin khi loa phat)


CALL_GAIN = {}                   # call_id -> {"mic": %, "speaker": %}: am luong chinh giua cuoc goi (giu qua cac lan mo lai mic/loa)


def _gain_of(call_id, target):
    """Mức hiện hành (%): nút −/+ của người dùng thắng; chưa chỉnh thì theo quy tắc HA (`mic_gain`/`speaker_gain` của cuộc gọi); không có thì 100."""
    mine = CALL_GAIN.get(str(call_id), {}).get(target)
    if mine is not None:
        return mine
    rule = srv()._devices_for_call(call_id).get(target + "_gain")
    return rule if isinstance(rule, int) and rule > 0 else audio_gain_mod.DEFAULT_PERCENT


def _set_gain(call_id, target, level=None, step=None):
    """Dat am luong mic|speaker cua cuoc goi: `level` (%) tuyet doi, hoac `step` (+/-%) so voi muc hien tai. Ghi nho cho ca cuoc goi
    va ap ngay vao mic/loa dang chay. Nem ValueError neu target sai / thieu level va step / khong phai so. Tra ve muc moi (%)."""
    if target not in ("mic", "speaker"):
        raise ValueError("target phai la mic hoac speaker")
    if level is None and step is None:
        raise ValueError("thieu level hoac step")
    if level is not None:
        new = audio_gain_mod.clamp_percent(level)
    else:
        if isinstance(step, bool):
            raise ValueError("step phai la so")
        try:
            delta = int(round(float(step)))
        except (TypeError, ValueError):
            raise ValueError("step phai la so") from None
        new = audio_gain_mod.clamp_percent(_gain_of(call_id, target) + delta)
    CALL_GAIN.setdefault(str(call_id), {})[target] = new
    live = (AUDIO_SENDERS if target == "mic" else SPEAKER_SINKS).get(str(call_id))
    if live is not None:
        live.gain = new
    return new


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
    sink.gain = _gain_of(call_id, "speaker")
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
    sender.gain = _gain_of(call_id, "mic")
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


class VoiceHandler:
    """Phương thức của Handler thuộc trục này (gộp vào Handler bằng kế thừa)."""

    def _serve_call_audio_tap(self, token):
        """Nhu /api/call/audio/out nhung doc BAN SAO khung (tap) — dung cho nguoi nghe thu hai (AI trong cuoc goi) ma khong
        tranh khung voi loa."""
        call_id = srv().STATE.audio_tokens.call_for(token)
        if call_id is None:
            return self._send_json({"error": "token_khong_hop_le"}, status=404)
        engine = srv()._engine_for_call(call_id)
        if engine is None or not hasattr(engine, "add_tap"):
            return self._send_json({"error": "chua_co_media"}, status=409)
        tap = engine.add_tap()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def write(chunk):
            self.wfile.write(chunk)
            self.wfile.flush()

        def read():
            try:
                return tap.get_nowait()
            except queue.Empty:
                return None

        def live():
            return (srv().STATE.audio_tokens.call_for(token) is not None and srv()._engine_for_call(call_id) is engine)

        try:
            call_audio_mod.stream_out(engine, write, live, read=read, depth=tap.qsize)
        except OSError:
            pass
        finally:
            engine.remove_tap(tap)

    def _serve_call_audio_out(self, token):
        """Phat lien tuc am thanh ben kia (WAV 16 kHz mono) cho mot thiet
        bi bat ky. Xac thuc bang token cua cuoc goi, khong dung cookie."""
        call_id = srv().STATE.audio_tokens.call_for(token)
        if call_id is None:
            return self._send_json({"error": "token_khong_hop_le"},
                                   status=404)
        engine = srv()._engine_for_call(call_id)
        if engine is None:
            return self._send_json({"error": "chua_co_media"}, status=409)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def write(chunk):
            self.wfile.write(chunk)
            self.wfile.flush()

        def live():
            return (srv().STATE.audio_tokens.call_for(token) is not None
                    and srv()._engine_for_call(call_id) is engine)

        try:
            call_audio_mod.stream_out(engine, write, live)
        except OSError:
            pass            # thiet bi ngat ket noi: binh thuong

    def _handle_call_say(self):
        """POST /api/call/say (multipart: file, call_id?) — phat mot doan am thanh (mp3/wav/ogg... do HA tao bang TTS) len
        cuoc goi DANG NOI qua cung duong mic (thay nguon mic hien tai). Tra ngay khi bat dau phat; nguoi goi poll
        /api/call/media {action: status}: mic.alive=false la phat xong."""
        if self._require_app_login() is None:
            return self._unauthorized()
        if self._require_login() is None:
            return self._send_json({"error": "chua_dang_nhap"}, status=401)
        raw = self._read_raw()
        if len(raw) > srv().SAY_MAX_BYTES + 4096:
            return self._send_json({"error": "am_thanh_qua_lon"}, status=413)
        fields, files = chat_mod.parse_multipart(raw, self.headers.get("Content-Type") or "")
        f = (files or {}).get("file")
        fname, _mime, data = f if f else ("", "", b"")
        if not data:
            return self._send_json({"ok": False, "error": "thieu_file"}, status=400)
        if len(data) > srv().SAY_MAX_BYTES:
            return self._send_json({"error": "am_thanh_qua_lon"}, status=413)
        snap = srv().STATE.calls.snapshot()
        call_id = srv()._coerce_call_id(fields.get("call_id", ""))
        entry = next((c for c in snap["calls"] if call_id is not None and str(c["call_id"]) == str(call_id)), None) \
            if call_id is not None else snap["active"]
        if entry is None or entry["status"] != "answered":
            return self._send_json({"ok": False, "error": "chua_nghe_may"})
        call_id = int(entry["call_id"])
        ext = os.path.splitext(str(fname or ""))[1].lower()
        if not re.match(r"^\.[a-z0-9]{1,5}$", ext):
            ext = ".bin"
        folder = os.path.join(srv().STATE.data_dir, "say")
        try:
            os.makedirs(folder, exist_ok=True)
            srv()._prune_say_files(folder)
            path = os.path.join(folder, "%s-%d%s" % (call_id, int(time.time() * 1000), ext))
            with open(path, "wb") as fh:
                fh.write(data)
            srv()._start_mic(call_id, path, "auto", loop=False, echo_gate=False)   # MOT lan, khong lap, KHONG gate chong vong
        except (ValueError, RuntimeError, OSError) as exc:
            return self._send_json({"ok": False, "error": str(exc)[:120]})
        return self._send_json({"ok": True, "call_id": call_id, "bytes": len(data)})

    def _handle_call_audio_in(self, call_id):
        """Nhan PCM16 16 kHz mono (boi so 640 byte) tu mic cua thiet bi bat
        ky va dua vao cuoc goi. Can dang nhap app."""
        if self._require_app_login() is None:
            return self._unauthorized()
        engine = srv()._engine_for_call(call_id)
        if engine is None:
            return self._send_json({"ok": False, "error": "chua_co_media"},
                                   status=409)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return self._send_json({"ok": False, "error": "thieu_noi_dung"},
                                   status=400)
        if length > call_audio_mod.MAX_IN_BYTES:
            return self._send_json({"ok": False, "error": "qua_lon"},
                                   status=413)
        data = self.rfile.read(length)
        sent, errors, last = call_audio_mod.feed_frames(engine, data)
        return self._send_json({"ok": errors == 0, "frames": sent,
                                "errors": errors, "last_error": last})
