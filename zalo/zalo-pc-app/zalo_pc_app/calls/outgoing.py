"""Luồng cuộc gọi ĐI (requestcall 11300 → request 11301 → hẹn giờ đổ chuông → xác nhận trả lời 11304). Tách từ server.py 14/11/2026."""
import os
import threading
import time
from .. import call_errors
from .. import engine_seam
from .. import media_endpoints
from .. import signaling as signaling_mod
from .. import webhooks as webhooks_mod

from ._srv import srv


def _ring_timeout_fire(call_id):
    """Background ring-timeout: a call still ringing after
    RING_TIMEOUT_SECONDS ends itself (cancel on the wire, reason
    ring_timeout). The live entry is re-checked first — a stale
    timer (call already ended, or superseded by another call) is a
    no-op, so a call can never be ended twice. An ANSWERED call
    is never ring-timed-out (2026-11-08 fix): the timer is disarmed
    on answer, and this check is the second layer — a stale timer
    firing late must not kill a connected call. The session is read
    fresh from STATE: without one (logged out mid-ring) the call
    still ends locally so it never stays "connecting" forever."""
    _disarm_ring_timer(call_id)
    snap = srv().STATE.calls.snapshot()
    active = snap.get("active")
    if active is None or str(active["call_id"]) != str(call_id):
        return
    if active.get("status") == "answered":
        return
    sess = srv().STATE.session
    if not sess or not sess.get("zpw_sek"):
        sess = None
    diag = active.get("diag") or {}
    ended, signal, zalo_ok, zalo_error, _data = srv()._terminate_call(
        call_id, "ring_timeout", sess)
    if ended is None:
        return
    # One-line diagnosis summary: a single line from `docker logs`
    # carries everything the no-ring question needs (11300/11301
    # status, the relay addresses actually used, the cancel
    # outcome) — the user pastes this line alone and the cause can
    # be judged from it.
    srv()._log_call("timeout-summary call_id=%s peer=%s toId=%s "
              "step1_status=%s step2_status=%s request_sent=%s "
              "rtp=%s rtcp=%s duration=%.0fs zalo_signal=%s "
              "zalo_ok=%s%s"
              % (ended["call_id"], ended.get("peer", ""),
                 ended.get("thread_id", ""),
                 diag.get("step1_status"), diag.get("step2_status"),
                 ended.get("request_sent"),
                 diag.get("rtp"), diag.get("rtcp"),
                 max(0.0, float(ended.get("ended_at") or 0)
                     - float(ended.get("started_at") or 0)),
                 signal, zalo_ok,
                 (" zalo_error=" + zalo_error) if zalo_error else ""))


def _arm_ring_timer(call_id):
    """Arm the ring timeout for a call whose step 2 was sent (the
    peer is ringing from now). Daemon thread: it must never block
    process exit. The handle is kept in _RING_TIMERS so answering
    can disarm it (2026-11-08 fix); re-arming replaces a stale
    handle for the same call_id."""
    timer = threading.Timer(srv().RING_TIMEOUT_SECONDS,
                            _ring_timeout_fire, [call_id])
    timer.daemon = True
    with srv()._RING_TIMERS_LOCK:
        old = srv()._RING_TIMERS.pop(str(call_id), None)
        srv()._RING_TIMERS[str(call_id)] = timer
    if old is not None:
        try:
            old.cancel()
        except Exception:  # noqa: BLE001 - cancel is best-effort
            pass
    timer.start()


def _disarm_ring_timer(call_id):
    """Cancel + forget the ring timer for a call (on answer, and
    when the call ends any other way). Best-effort, never raises;
    a timer that already fired is a harmless no-op."""
    with srv()._RING_TIMERS_LOCK:
        timer = srv()._RING_TIMERS.pop(str(call_id), None)
    if timer is not None:
        try:
            timer.cancel()
        except Exception:  # noqa: BLE001 - cancel is best-effort
            pass


def _send_answerack_async(call_id, thread_id):
    """Best-effort answerack (11304, bundle wZ sendAnswerACKCall):
    the caller ACKs the callee's answer. Runs on a daemon thread
    so it never blocks the caller — the first-media hook runs on
    the transport's receiver thread, and a 30s signaling round-trip
    there would stall media reception. The session is read fresh
    from STATE; without one the ACK is skipped (logged, not fatal:
    the call is already marked answered). Only for 1-1 calls."""
    sess = srv().STATE.session
    if not sess or not sess.get("zpw_sek") or not sess.get("zpw_enk"):
        srv()._log_call("answerack call_id=%s ok=False error=no_session"
                  % call_id)
        return
    try:
        transport = srv().make_transport(sess["zpw_sek"])
        sig = signaling_mod.Signaling(transport, sess["device_id"],
                                      sess["zpw_enk"])
        sig.answer_ack(thread_id, call_id)
        srv()._log_call("answerack call_id=%s ok=True" % call_id)
    except Exception as e:  # noqa: BLE001 - best-effort
        srv()._log_call("answerack call_id=%s ok=False error=%s"
                  % (call_id, e))


EXTEND_PROFILES = ("native", "pc", "zca")


def _extend_profile_for_call(body):
    """Hồ sơ extendData của cuộc gọi đi: body `extend_profile` > env
    ZALO_PC_EXTEND_PROFILE > "native" (mặc định: y hệt engine zcall-native của
    Zalo-Linux, đã chạy thật với điện thoại — xem media_endpoints.native_extend_data).
    "pc" = bộ cũ (newZrtc=0), "zca" = bộ của zca-js."""
    want = str((body or {}).get("extend_profile")
               or os.environ.get("ZALO_PC_EXTEND_PROFILE") or "native").strip().lower()
    return want if want in EXTEND_PROFILES else "native"


class OutgoingCalls:
    """Phương thức của AppState thuộc trục này (gộp vào AppState bằng kế thừa)."""

    def _api_call_request(self, body):
        """POST /api/call/request: gọi ĐI (11300 requestcall → 11301 request → UDP relay …). Tách khỏi _api_post để gom vào luồng gọi đi."""
        sess = self._require_login()
        if sess is None:
            return self._send_json({"error": "chua_dang_nhap"},
                                   status=401)
        # Log the attempt for the calling monitor (GET /api/calls):
        # the UI sends the peer's display name; the log never
        # carries secrets, only who/when/which thread/result.
        # The requestcall body is built to match the real client
        # (§7k): call_id is minted from the process counter
        # (deep comparison §5.1 — engine: small counter 1, 2,
        # 3, ...; the body's call_id is NOT trusted, like
        # type_request) and type_request is derived from the
        # thread type (1-1 audio=1, group audio=5) — the body's
        # own type_request is NOT trusted (the pre-fix UI sent 0).
        # The effective call_id is returned so the UI uses the
        # same id for /api/call/end (endcall must carry the same
        # callId the requestcall used).
        call_id = srv()._normalize_call_id(body.get("call_id"))
        srv()._remember_call_devices(call_id, body)
        thread_id = body.get("callee_id", "")
        call_type = body.get("type") or "user"
        type_request = srv()._type_request_for(call_type)
        peer = body.get("peer_name") or thread_id
        try:
            transport = srv().make_transport(sess["zpw_sek"])
            sig = signaling_mod.Signaling(transport, sess["device_id"],
                                          sess["zpw_enk"])
            # Calls are addressed by threadID (addon/zca-js model):
            # type "user"  -> 1-1 requestcall (11300), calleeId is
            #   the user threadId; type "group" -> group/requestcall
            #   (12433), groupId is the group threadId. Sending a
            #   group id through the 1-1 endpoint is wrong.
            if call_type == "group":
                data = sig.request_call_group(
                    thread_id,
                    call_id,
                    type_request,
                    body.get("data"),
                    body.get("partners"))
            else:
                # 11300 codec (zca-js: the engine always sends
                # its Opus JSON list here; "[]" is only the
                # factory fallback). An explicit UI codec still
                # wins so a later test can force another list.
                data = sig.request_call(
                    thread_id,
                    call_id,
                    body.get("codec")
                    or media_endpoints.DEFAULT_ZALO_AUDIO_CODEC,
                    type_request)
            # §7l — SECOND STEP, the one the 17:51 live call was
            # missing: after requestcall the real client sends
            # `request` (11301, 1-1) / `group/request` (12434)
            # with the caller's media endpoints, and only then
            # does the server hold a complete invitation for the
            # far end. Without it the requestcall is accepted
            # (no error) but the callee's phone never rings.
            # Phase 2 (stage 2): the endpoints come from the
            # real relay allocation (`media_endpoints`, backed
            # by `Udp4200Transport`) — the 11300 response's
            # `servers` (real shape: list of dicts with
            # `rtcpaddr`/`rtpIPv6`, seen live 2026-11-05;
            # legacy `zrtc_config.servers` string as fallback)
            # / `sessId` (LIVE 2026-11-06: the 11301 token —
            # 115 bytes / 154 chars — there is NO `token` key
            # in the real 11300) / `srtpKey` (LIVE 2026-11-06:
            # the real 11300 carries NO srtpKey, so signaling
            # proceeds handshake-only and voice stays unwired
            # until the key source is found — see
            # `allocation_from_requestcall_data`). When
            # that allocation is missing, `for_call` raises
            # `MissingTransportParam` NAMING the missing
            # parameter instead of returning the phase-1 empty
            # placeholders: the real engine NEVER sends 416
            # with empty addresses, so this app does not
            # either. The step stays BEST-EFFORT: the call is
            # still reported ok (requestcall succeeded) but
            # request_sent=False is returned and logged, so
            # the UI/monitor can tell "invitation may not
            # have been delivered" apart from "fully sent".
            # Media hooks (Opus 16 kHz + SRTP) are best-effort
            # too: `pc_media.media_hooks_for_call` builds them
            # when libopus/libsrtp2 are available; when they
            # are not (the stdlib-only image), the transport
            # still handshakes and the call signals, but voice
            # stays unwired — never a crash, never a lie.
            # Call diagnostics (2026-11-08): step-1 outcome.
            # Log the 11300 shape + status/msg (shape only,
            # never values), and refuse a server-side 11300
            # rejection instead of proceeding to step 2 with
            # garbage. status 0 = accepted (real success case,
            # live 2026-11-06); any other status is a refusal,
            # msg carries the reason; status absent (the mock
            # {"ok": True} shape) = unknown, treated as
            # accepted.
            step1_status, step1_msg = \
                media_endpoints.requestcall_status(data)
            step1_shape = \
                media_endpoints.describe_requestcall_shape(data)
            # rtpIP/rtcpIP values (2026-11-08, step 1): the
            # shape string above never carries values (it is
            # also the API response's data_shape), so the
            # actual designated addresses are appended here,
            # on the LOG line only — relay IPs are public
            # diagnostic info, not secrets, and the live
            # no-ring question needs them visible. The same
            # allocation feeds the step1 diag below.
            try:
                _step1_alloc = media_endpoints.\
                    allocation_from_requestcall_data(data)
            except Exception:  # noqa: BLE001 - log/diag only
                _step1_alloc = {}
            _step1_addrs = ""
            if _step1_alloc.get("rtp_ip") \
                    or _step1_alloc.get("rtcp_ip"):
                _step1_addrs = (" rtpIP=%s rtcpIP=%s" % (
                    _step1_alloc.get("rtp_ip") or "-",
                    _step1_alloc.get("rtcp_ip") or "-"))
            srv()._log_call("step1 call_id=%s status=%s%s %s%s"
                      % (call_id, step1_status,
                         (" msg=" + step1_msg[:120])
                         if step1_msg else "",
                         step1_shape, _step1_addrs))
            if not media_endpoints.requestcall_accepted(data):
                raise RuntimeError(
                    "11300 bi tu choi: status=%s%s" % (
                        step1_status,
                        (" msg=" + step1_msg[:120])
                        if step1_msg else ""))
            # Snapshot the live call first: record_start closes
            # it when a new call supersedes it, and the log must
            # say so (with its duration) instead of letting the
            # earlier call vanish silently. Moved up (was after
            # step 2): the diag + the early end on a rejected
            # step 2 need the entry to exist already.
            prev_active = srv().STATE.calls.snapshot()["active"]
            sent_entry = srv().STATE.calls.record_start(
                call_id, peer, thread_id, call_type)
            srv().STATE.calls.record_diag(
                call_id, {"step1_status": step1_status,
                          "step1_msg": step1_msg[:120]})
            # rtpIP/rtcpIP (2026-11-08, step 1): the relay
            # addresses the 11300 response designates — the
            # step1 log line above carries their values; the
            # diag carries them too, so /api/calls shows which
            # addresses 11300 named (IP:port only, never
            # session/token values). _step1_alloc was computed
            # with the log line above.
            srv().STATE.calls.record_diag(
                call_id, {"rtp_ip": _step1_alloc.get("rtp_ip"),
                          "rtcp_ip": _step1_alloc.get("rtcp_ip")})
            if (prev_active is not None
                    and str(prev_active["call_id"]) != str(call_id)):
                srv()._log_call(
                    "end call_id=%s reason=superseded_by_new_call "
                    "duration=%.0fs" % (
                        prev_active["call_id"],
                        max(0.0, time.time()
                            - float(prev_active["started_at"] or 0))))
                # Withdraw the superseded invitation on the wire
                # AND stop its transport: without a cancel the
                # previous peer keeps ringing (same ghost-call
                # bug as the missing end signal), and for_call
                # started a transport for it that nothing else
                # ever stops. Best-effort; a failure is logged,
                # never breaks the new call.
                media_endpoints.ENDPOINTS.stop_call(
                    int(prev_active["call_id"]))
                _sig, _ok, _err, _data = srv()._send_end_signal(
                    prev_active, sess)
                if _sig != "none":
                    srv()._log_call(
                        "end call_id=%s reason=superseded_by_new_call "
                        "zalo_signal=%s zalo_ok=%s%s"
                        % (prev_active["call_id"], _sig, _ok,
                           (" zalo_error=" + _err) if _err else ""))
            srv()._log_call("start call_id=%s peer=%s thread=%s type=%s"
                      % (call_id, peer, thread_id, call_type))
            request_sent, request_error = True, ""
            server_rejected_step2 = False
            step2_status, step2_msg = None, ""
            step_code = "12434" if call_type == "group" else "11301"
            endpoints = None
            try:
                hooks, _local_key = {}, None
                _alloc = media_endpoints.\
                    allocation_from_requestcall_data(data)
                # Hook ma hoa LUON duoc dung (khong phu thuoc
                # libopus): thieu no thi transport khong gui duoc ca
                # khung im lang giu ket noi va ben nhan bao "tin hieu
                # yeu". Truoc 2026-11-09 hook chi duoc dung khi 11300
                # tra srtp_key — ma server khong bao gio tra.
                _srtp_mode, _srtp_src = srv()._srtp_mode_for_call(body)
                try:
                    from .. import pc_media, srtp_pure
                    if _alloc.get("srtp_key") is not None:
                        _srtp_mode = "server"
                        hooks, _notes = pc_media.hooks_for_call(
                            _alloc["srtp_key"])
                    elif _srtp_mode == "sess" and srtp_pure.\
                            key_from_session(_alloc.get("session")):
                        hooks, _notes = pc_media.hooks_for_call(
                            srtp_pure.key_from_session(
                                _alloc["session"]))
                    elif _srtp_mode == "key":
                        _local_key = srtp_pure.new_master_key_b64()
                        hooks, _notes = pc_media.hooks_for_call(
                            _local_key)
                    else:
                        if _srtp_mode == "sess":
                            _srtp_mode = "off"   # 11300 khong co sessId
                        hooks, _notes = pc_media.hooks_for_call(None)
                    if _srtp_mode in srv().SRTP_MODES:
                        srv()._CALL_SRTP[str(call_id)] = (_srtp_mode, _srtp_src)
                    srv()._log_call("media hooks call_id=%s srtp_mode=%s "
                              "source=%s srtp=%s opus=%s"
                              % (call_id, _srtp_mode, _srtp_src,
                                 _notes["srtp"], _notes["opus"][:90]))
                except Exception as exc:  # noqa: BLE001 - optional
                    hooks, _local_key = {}, None
                    srv()._log_call("media hooks failed call_id=%s: %s"
                              % (call_id, str(exc)[:160]))
                # §7o — local_session / peer_session (2026-11-06):
                # CA HAI lay tu response 11300 (`_alloc`):
                # `local_session` = `fromId`, `peer_session` =
                # `toId` (goi 1-1; goi nhom None) — id 32-bit
                # RIENG do server cap (disassembly: parser
                # 0x71ebd1 doc "fromId" -> resp+0x10,
                # "toId" -> resp+0x14; `_prepareCallConfig,
                # resp` 0x7ed1d0 copy vao CallConfig+0/+4 ->
                # SSRC). KHONG suy tu session uid (uid that la
                # 64-bit — live test 09:23 +07 2026-11-06 da
                # bac; khong low-32/high-32/hash) va KHONG suy
                # tu threadId (threadId 19 chu so khong phai
                # userId cua peer). Thieu fromId -> `for_call`
                # loi trung thuc neu `local_session` + `fromId`,
                # buoc 2 bao request_sent=false. Day la cho duy
                # nhat noi hai gia tri nay vao `for_call`
                # (`ENDPOINTS` la global, khong dat default
                # theo phien — id thay doi theo response).
                # First-media hook (2026-11-08): the first
                # INBOUND media packet (type-04 downlink from the
                # relay, or P2P media) is evidence the peer
                # answered — the captures show inbound media only
                # after an answer (file 1/4) and ZERO inbound in
                # 29.5 s of ringing (file 2) — so the transport
                # marks the call answered through this callback
                # — no sync channel needed. It is a PROXY, not
                # the answer signal itself (that is the peer's
                # answer on voicecall/sync, still unparsed; the
                # explicit path is POST /api/call/answered), and
                # OUTBOUND media proves nothing (file 2: the
                # caller sends type-03 uplink all through
                # ringing with no answer). It runs on the
                # transport's receiver thread; _mark_answered
                # only touches locked state + logging + async
                # webhook, and the answerack goes on a daemon
                # thread, so it never blocks media reception.
                def _on_first_media():
                    srv()._mark_answered(call_id, "media")

                endpoints = media_endpoints.ENDPOINTS.for_call(
                    call_id=call_id, callee_id=thread_id,
                    call_type=call_type, codec=body.get("codec"),
                    local_session=_alloc.get("local_session"),
                    peer_session=(
                        _alloc.get("peer_session")
                        if call_type != "group" else None),
                    requestcall_data=data,
                    is_video=(call_type == "video"),
                    on_first_media=_on_first_media,
                    extend_profile=_extend_profile_for_call(body),
                    **dict(hooks, **(
                        {"srtp_key": _local_key,
                         "advertise_srtp_key": True}
                        if _local_key else {})))
            except Exception as exc:  # noqa: BLE001 - best-effort
                request_sent, request_error = False, str(exc)
            if endpoints is not None:
                # Log what goes into step 2 BEFORE sending: the
                # relay addresses actually used + session
                # presence/length (never the session value) +
                # codec — the live no-ring question ("did 11301
                # carry a real relay?") is answered by this
                # line alone.
                srv()._log_call("step2 send call_id=%s rtp=%s rtcp=%s "
                          "rtp_source=%s session=%s codec=%s extend=%s"
                          % (call_id, endpoints["rtp_address"],
                             endpoints["rtcp_address"],
                             endpoints.get("rtp_source", "selected"),
                             srv()._describe_session_value(
                                 endpoints["session"]),
                             endpoints["codec"],
                             _extend_profile_for_call(body)))
                step2_resp = None
                try:
                    if call_type == "group":
                        step2_resp = sig.send_request_group(
                            thread_id, call_id, type_request,
                            body.get("data"), endpoints["session"],
                            body.get("partners"), thread_id)
                    else:
                        step2_resp = sig.send_request(
                            thread_id, endpoints["rtcp_address"],
                            endpoints["rtp_address"],
                            endpoints["codec"],
                            endpoints["session"], call_id,
                            endpoints["extend_data"])
                    # Step 2 accepted: attach the media engine
                    # to the started transport (best-effort;
                    # never breaks the call when it fails).
                    engine_seam.SEAM.attach_pc_media(
                        media_endpoints.ENDPOINTS.active_record(
                            call_id))
                except signaling_mod.ServerRejectedError as exc:
                    # The server refused step 2 (inner
                    # error_code, e.g. 114): an explicit
                    # refusal, not a network failure — the call
                    # ends early below (server_rejected).
                    request_sent, request_error = False, str(exc)
                    server_rejected_step2 = True
                except Exception as exc:  # noqa: BLE001 - best-effort
                    request_sent, request_error = False, str(exc)
                if step2_resp is not None:
                    # The response itself may carry the refusal
                    # (data-level status, which the envelope
                    # check cannot see): read it, log its shape,
                    # and treat a non-zero status as a rejection.
                    accepted, step2_status, step2_msg = \
                        media_endpoints.request_step_outcome(
                            step2_resp)
                    srv()._log_call("step2 resp call_id=%s %s"
                              % (call_id,
                                 media_endpoints.describe_request_shape(
                                     step2_resp, step_code)))
                    if not accepted:
                        request_sent = False
                        request_error = (
                            "may chu tu choi %s: status=%s%s"
                            % (step_code, step2_status,
                               (" msg=" + step2_msg[:120])
                               if step2_msg else ""))
                        server_rejected_step2 = True
                srv().STATE.calls.record_diag(call_id, {
                    "step2_status": step2_status,
                    "step2_msg": step2_msg[:120],
                    "rtp": endpoints["rtp_address"],
                    "rtcp": endpoints["rtcp_address"],
                    "rtp_source": endpoints.get("rtp_source",
                                                "selected"),
                    "session_present":
                        endpoints["session"] is not None,
                    "session_len": (
                        len(endpoints["session"])
                        if isinstance(endpoints["session"],
                                      (str, bytes, bytearray))
                        else None),
                    "codec": endpoints["codec"]})
            srv().STATE.calls.record_request(call_id, request_sent,
                                       request_error)
            srv()._log_call("step2 call_id=%s request_sent=%s "
                      "step2_status=%s%s"
                      % (call_id, request_sent, step2_status,
                         (" error=" + request_error)
                         if request_error else ""))
            # Ring timeout: if nobody answers within
            # RING_TIMEOUT_SECONDS the call ends itself (cancel
            # on the wire, reason ring_timeout) instead of
            # staying "sent" forever — see _ring_timeout_fire.
            # Only when step 2 was sent: without it the peer
            # never rang, so there is nothing to time out. A
            # server-rejected step 2 never arms the timer
            # either — that call ends early below instead.
            if request_sent and not server_rejected_step2:
                _arm_ring_timer(call_id)
            # WEBHOOK HOOK (webhooks.py): call.sent fires NOW —
            # the app is the source, no sync channel needed.
            # Fire-and-forget: never blocks the call response.
            webhooks_mod.dispatch_call_event(
                srv().STATE.webhook_dispatcher, sent_entry,
                sess.get("uid", ""))
            # The raw 11300 response is NOT returned: it may
            # carry the SRTP key / token / session, which must
            # never reach the browser (or a log). Only its
            # SHAPE (key names + counts) is returned, so the UI
            # can still show what the response carried.
            if server_rejected_step2:
                # The server said no to step 2: withdraw the
                # 11300 invitation with cancel NOW (reason
                # server_rejected) instead of leaving the call
                # "sent" with no timer — the old code left it
                # live forever, and the peer never rang. The
                # call.sent webhook above already fired; the
                # end webhook fires from _terminate_call.
                srv()._terminate_call(call_id, "server_rejected", sess)
                return self._send_json(
                    {"ok": True, "data_shape": step1_shape,
                     "call_id": call_id,
                     "request_sent": False,
                     "request_error": request_error,
                     "ended_reason": "server_rejected"})
            return self._send_json(
                {"ok": True,
                 "data_shape": step1_shape,
                 "call_id": call_id,
                 "request_sent": request_sent,
                 "request_error": request_error})
        except Exception as e:  # noqa: BLE001
            err_entry = srv().STATE.calls.record_error(call_id, peer, thread_id,
                                     call_type, str(e),
                                     kind=call_errors.classify(e))
            srv()._log_call("error call_id=%s peer=%s thread=%s error=%s"
                      % (call_id, peer, thread_id, e))
            # WEBHOOK HOOK (webhooks.py): call.error, same as above.
            webhooks_mod.dispatch_call_event(
                srv().STATE.webhook_dispatcher, err_entry,
                sess.get("uid", ""))
            return self._send_json({"error": str(e)}, status=502)
