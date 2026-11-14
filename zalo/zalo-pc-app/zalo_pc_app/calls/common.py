"""Việc DÙNG CHUNG của mọi cuộc gọi (đánh dấu nghe máy, kết thúc, ghi lịch sử, dọn media, thiết bị riêng của cuộc gọi). Các trục (video/voice/incoming/outgoing) gọi vào đây qua srv(). Tách từ server.py 14/11/2026."""
import json
import re
import threading
import time
from .. import devices as devices_mod
from .. import engine_seam
from .. import media_endpoints
from .. import signaling as signaling_mod
from .. import webhooks as webhooks_mod

from ._srv import srv


def _terminate_call(call_id, reason, sess, group_data=None,
                    group_partners=None):
    """End one call completely: local log + webhook + wire signal +
    transport stop. `reason` is the true end reason recorded in the
    entry's detail ("user_end" / "ring_timeout" /
    "superseded_by_new_call"). Returns (ended_entry_or_None, signal,
    zalo_ok, zalo_error, data).

    Local-first (§7m): the entry is marked ended BEFORE the wire
    signal is attempted, so a slow or rejected Zalo signal never
    leaves the call stuck on "ringing". A wire failure is appended
    to the detail as "<reason>; zalo_<signal>: <error>" so the
    reason survives (the 2026-11-07 live test could not tell a
    user-ended call from a cut-off one precisely because no end
    carried a reason).
    """
    snap = srv().STATE.calls.snapshot()
    before = None
    for c in snap["calls"]:
        if str(c["call_id"]) == str(call_id) \
                and c["status"] in ("sent", "answered"):
            before = c
            break
    if before is None:
        return None, "none", False, "no_live_call", {}
    srv()._disarm_ring_timer(call_id)
    ended = srv().STATE.calls.record_end(call_id, reason)
    if ended is None:
        return None, "none", False, "no_live_call", {}
    webhooks_mod.dispatch_call_event(
        srv().STATE.webhook_dispatcher, ended, (sess or {}).get("uid", ""))
    signal, zalo_ok, zalo_error, data = "none", True, "", {}
    if sess is not None:
        signal, zalo_ok, zalo_error, data = srv()._send_end_signal(
            before, sess, group_data, group_partners)
    else:
        zalo_ok, zalo_error = False, "no_session"
    if not zalo_ok and signal != "none":
        srv().STATE.calls.record_end_error(
            int(ended["call_id"]),
            "%s; zalo_%s: %s" % (reason, signal, zalo_error))
    # Phase 2: stop the media engine + the relay transport for this
    # call (best-effort; a stuck UDP socket must not leave the call
    # half-alive after it ends).
    _cleanup_call_media(ended)
    srv()._log_call("end call_id=%s reason=%s duration=%.0fs "
              "zalo_signal=%s zalo_ok=%s%s"
              % (ended["call_id"], reason,
                 max(0.0, float(ended.get("ended_at") or 0)
                     - float(ended.get("started_at") or 0)),
                 signal, zalo_ok,
                 (" zalo_error=" + zalo_error) if zalo_error else ""))
    return ended, signal, zalo_ok, zalo_error, data


def _calls_snapshot_with_media():
    """Call-log snapshot + live media state: every entry whose
    transport is still running gains "media": {"srtp":
    "wired"|"not-wired"} so the UI can report honestly — a
    connected call with srtp "not-wired" is "da noi, chua co
    tieng (thieu khoa SRTP)", not silent voice and not a reason
    to drop the call. Entries without a running transport (ended
    / error) carry no media key."""
    snap = srv().STATE.calls.snapshot()
    for entry in snap["calls"]:
        try:
            record = media_endpoints.ENDPOINTS.active_record(
                entry["call_id"])
        except Exception:  # noqa: BLE001 - media is best-effort
            record = None
        if record is not None:
            media = {"srtp": record.get("srtp", "not-wired")}
            mode = srv()._CALL_SRTP.get(str(entry["call_id"]))
            if mode:
                media["srtp_mode"] = mode[0]
            try:
                counters = record["transport"].status().get("counters") or {}
                media["counters"] = {k: counters.get(k, 0) for k in (
                    "rtp_tx", "keepalive_tx", "rtcp_tx", "rtp_rx",
                    "rtp_rx_dropped", "p2p_media_rx")}
                media["rx_sample"] = record["transport"].status().get(
                    "rx_sample")
            except Exception:  # noqa: BLE001 - chan doan, khong chen ngang
                pass
            # Token phat am thanh theo cuoc goi — chi cap cho phien da dang
            # nhap app (route nay yeu cau cookie), het han khi goi ket thuc.
            media["audio_token"] = srv().STATE.audio_tokens.token_for(
                entry["call_id"])
            _v = srv().VIDEO_SENDERS.get(str(entry["call_id"]))
            _m = srv().AUDIO_SENDERS.get(str(entry["call_id"]))
            media["video"] = _v.status() if _v else None
            media["mic"] = _m.status() if _m else None
            _s = srv().SPEAKER_SINKS.get(str(entry["call_id"]))
            media["speaker"] = _s.status() if _s else None
            media["gain"] = {t: srv()._gain_of(entry["call_id"], t) for t in ("mic", "speaker")}
            entry["media"] = media
    return snap


_CALL_DEVICES = {}               # call_id -> ghi de rieng cua cuoc goi (mic/camera)


_CALL_DEVICE_KEYS = ("mic_url", "mic_format", "camera_url", "speaker_url", "echo_guard")


def _log_media_stats(kind, call_id, obj):
    """Ghi số liệu của một nguồn/đích tiếng khi dừng (khung gửi/nhận, bị chặn, lỗi): để lần sau biết «không ổn định» do đâu."""
    try:
        st = obj.status()
        srv()._log_call("%s stats call_id=%s %s" % (kind, call_id, ", ".join("%s=%s" % (k, str(v)[:60]) for k, v in st.items() if k != "ffmpeg_err" or v)))
    except Exception:  # noqa: BLE001 - ghi nhật ký không được làm hỏng việc dừng
        pass


def _remember_call_devices(call_id, body):
    """Ghi de thiet bi rieng cua cuoc goi (tu body request/answer). Gia tri "off"
    = tat thiet bi do cho cuoc nay (du co mac dinh)."""
    over = {}
    if isinstance(body, dict):
        for key in _CALL_DEVICE_KEYS:
            val = body.get(key)
            if val in (None, ""):
                continue
            if key == "echo_guard":
                over[key] = val is True or str(val).strip().lower() in ("1", "true", "yes", "on")
                continue
            val = str(val).strip()
            if key == "speaker_url":
                if val.lower() == "off":
                    over[key] = ""
                elif re.match(r"^https?://\S+$", val):
                    over[key] = val
                continue
            if key == "mic_format":
                if val in devices_mod.MIC_FORMATS:
                    over[key] = val
            elif val.lower() == "off":
                over[key] = ""
            elif devices_mod.valid_source(val):
                over[key] = val
    if over:
        if len(_CALL_DEVICES) > 50:
            _CALL_DEVICES.clear()
        _CALL_DEVICES[str(call_id)] = over
    return over


_LOGENDCALL_SENT = set()          # call_id da gui logendcall (moi cuoc goi gui dung mot lan)


def _logendcall_status(entry):
    """Trang thai 406 nhu engine Zalo that (engine-core.js `_finish`): 50 da noi may, 103 ta la ben goi va huy / het gio / ket thuc truoc khi
    noi may, 160 tu choi (ta tu choi, hoac ben kia tu choi cuoc ta goi). None = khong gui: cuoc goi den bi nho (nguoi goi huy truoc khi ta nghe),
    bi thay the, hoac bi tu choi vi ban."""
    detail = str(entry.get("detail") or "")
    if detail.startswith("superseded") or detail == "busy_rejected" or (entry.get("type") or "user") == "group":
        return None
    if entry.get("answered_at"):
        return 50
    if entry.get("direction") == "in":
        return 160 if detail.startswith("user_rejected") else None
    return 160 if detail.startswith("peer_declined") else 103


def _logendcall_async(entry, status=None, rx=0, tx=0):
    """Gui logendcall (11311) cho cuoc goi 1-1 vua ket thuc — Zalo PC luon gui, app chua tung gui (so voi bundle 12/11): thieu no thi lich su chat
    hien cuoc da nghe la «bi nho». Best-effort tren luong nen, moi call_id mot lan, khong lam hong luong ket thuc cuoc goi."""
    st = _logendcall_status(entry) if status is None else status
    sess = srv().STATE.session
    if st is None or not sess:
        return
    key = str(entry.get("call_id"))
    with srv()._LOGENDCALL_LOCK:
        if key in _LOGENDCALL_SENT:
            return
        if len(_LOGENDCALL_SENT) > 200:
            _LOGENDCALL_SENT.clear()
        _LOGENDCALL_SENT.add(key)
    answered_at, ended_at = entry.get("answered_at"), entry.get("ended_at") or time.time()
    duration = int(round(max(0.0, float(ended_at) - float(answered_at)))) if (st == 50 and answered_at) else 0
    role = entry.get("direction") != "in"
    logdata = json.dumps({"Codec": ["opus/16000/1", "20"], "NewZRTC": 1, "RxTotalPkt": int(rx or 0), "SrtpMode": 1,
                          "TxTotalPkt": int(tx or 0), "sysInfo": "zalo-pc-app"}, sort_keys=True, separators=(",", ":"))

    def run():
        try:
            transport = srv().make_transport(sess["zpw_sek"])
            sig = signaling_mod.Signaling(transport, sess["device_id"], sess["zpw_enk"])
            sig.logendcall(entry["thread_id"], int(entry["call_id"]), st, logdata, duration, role)
            srv()._log_call("logendcall call_id=%s status=%s duration=%ss role=%s ok" % (key, st, duration, "caller" if role else "callee"))
        except Exception as exc:  # noqa: BLE001 - chi ghi lich su, khong anh huong cuoc goi
            srv()._log_call("logendcall call_id=%s status=%s FAILED: %s" % (key, st, str(exc)[:140]))
    # Khong daemon: luong ngan (mot GET, timeout 30 s) va khong de no in ra luc interpreter dang tat (loi "could not acquire lock for stdout").
    threading.Thread(target=run, daemon=False).start()


def _cleanup_call_media(entry):
    """Cuoc goi da ket thuc: danh gia ket qua SRTP, dung engine + transport,
    huy token am thanh. Best-effort, khong nem loi."""
    try:
        try:
            _tr = srv()._transport_for_call(entry["call_id"])
            _cnt = dict(getattr(_tr, "counters", {}) or {})
            srv()._log_call("media counters call_id=%s %s" % (entry["call_id"], json.dumps(_cnt, sort_keys=True)[:600]))
            try:
                _ra = getattr(_tr, "_rx_audio", None)
                if _ra is not None and _ra.started:
                    _hi = _ra.cycles + _ra.max_seq
                    srv()._log_call("rx-audio call_id=%s ssrc=%08x base_seq=%d cao_nhat=%d ky_vong=%d nhan=%d mat=%d jitter=%.0f" % (
                        entry["call_id"], _ra.ssrc, _ra.base_seq, _hi, _hi - _ra.base_seq + 1, _ra.received, (_hi - _ra.base_seq + 1) - _ra.received, _ra.jitter))
                _trace = list(getattr(_tr, "_rx_trace", []) or [])
                if _trace:
                    _rows, _prev = [], None
                    for _s, _t, _l, _p, _ms in _trace[:40]:
                        _rows.append("%d/%s/%d/p%d/%s" % (_s, ("+%d" % (_t - _prev[1])) if _prev else "ts0", _l, _p, ("+%dms" % (_ms - _prev[2])) if _prev else "0"))
                        _prev = (_s, _t, _ms)
                    srv()._log_call("rx-trace call_id=%s n=%d (seq/dts/len/pt/dt) %s" % (entry["call_id"], len(_trace), " ".join(_rows)))
            except Exception:  # noqa: BLE001 - chan doan khong duoc lam hong don dep cuoc goi
                pass
            if str(entry.get("detail") or "").startswith("user_rejected"):
                pass                               # tu choi: ham tu choi tu gui logendcall 160 sau khi bao 11303(3)
            else:
                _logendcall_async(entry, rx=_cnt.get("rtp_rx", 0), tx=_cnt.get("rtp_tx", 0))
        except Exception:  # noqa: BLE001 - chi de chan doan / lich su
            pass
        srv()._evaluate_srtp_outcome(entry)
        srv()._stop_video(entry["call_id"])
        srv()._stop_mic(entry["call_id"])
        srv()._stop_speaker(entry["call_id"])
        srv().ECHO_GUARDS.pop(str(entry["call_id"]), None)
        srv().CALL_GAIN.pop(str(entry["call_id"]), None)
        _CALL_DEVICES.pop(str(entry["call_id"]), None)
        engine_seam.SEAM.stop_media()
        media_endpoints.ENDPOINTS.stop_call(int(entry["call_id"]))
        srv().STATE.audio_tokens.drop(entry["call_id"])
    except Exception as exc:  # noqa: BLE001
        srv()._log_call("cleanup media error: %s" % str(exc)[:120])


def _mark_answered(call_id, source, send_ack=True):
    """Mark a live (ringing) call answered: the peer picked up and
    the call is connected. `source` names how the app learned it
    ("api" = POST /api/call/answered, e.g. from a sync push event;
    "media" = first inbound RTP arrived; "sync" = a call_event
    "answer" on ctrl 99101). Idempotent: marking an
    already-answered call returns it unchanged without re-logging
    or re-ACKing. Returns the entry, or None when there is no live
    call with that id. Side effects on transition: the ring timer
    is disarmed (an answered call is never ring-timed-out), a
    [call] answered line is logged, a call webhook event fires,
    and — for an OUTGOING call only (send_ack=True) — an answerack
    (11304) is sent best-effort on a daemon thread for 1-1 calls.
    An INCOMING call is answered with send_ack=False: the callee
    never sends 11304 — it is the CALLER's signal (zca-js
    acceptIncomingCall sends no answerack; the mock's
    server_call_state confirms 11304 is the caller's ACK of the
    callee's answer). It also starts the P2P hello handshake
    (transport.begin_p2p, best-effort): only now — after the
    answer — does the relay know the peer's address, so only
    now can the hello go to the peer instead of to ourselves
    (2026-11-08, step 3)."""
    snap = srv().STATE.calls.snapshot()
    live = None
    for c in snap["calls"]:
        if str(c["call_id"]) == str(call_id) \
                and c["status"] in ("sent", "answered", "incoming"):
            live = c
            break
    if live is None:
        return None
    if live["status"] == "answered":
        return dict(live)
    entry = srv().STATE.calls.record_answered(call_id, source)
    if entry is None:
        return None
    srv()._disarm_ring_timer(call_id)
    # Start the P2P hello handshake NOW (2026-11-08, step 3):
    # the peer has answered, so the relay knows the peer's
    # address and the type-02 tail is the peer (not us). The
    # transport never hellos on its own any more — before this
    # fix it helloed all through ringing to our own reflexive
    # address (61 hellos in the 30 s pcap). Defensive getattr:
    # an older fake transport without begin_p2p() must not
    # break the answer path.
    try:
        record = media_endpoints.ENDPOINTS.active_record(
            entry["call_id"])
        transport = (record or {}).get("transport")
        begin_p2p = getattr(transport, "begin_p2p", None)
        if callable(begin_p2p):
            begin_p2p()
    except Exception:  # noqa: BLE001 - P2P start is best-effort
        pass
    srv()._log_call("answered call_id=%s source=%s"
              % (entry["call_id"], source))
    webhooks_mod.dispatch_call_event(
        srv().STATE.webhook_dispatcher, entry,
        (srv().STATE.session or {}).get("uid", ""))
    if (entry.get("type") or "user") != "group":
        srv()._auto_media_async(entry["call_id"])
    if (entry.get("direction") or "") == "in" and (entry.get("type") or "user") != "group":
        srv()._watch_dead_media(entry["call_id"])
    if send_ack and (entry.get("type") or "user") != "group":
        thread = threading.Thread(
            target=srv()._send_answerack_async,
            args=(int(entry["call_id"]), entry["thread_id"]),
            daemon=True)
        thread.start()
    return entry
