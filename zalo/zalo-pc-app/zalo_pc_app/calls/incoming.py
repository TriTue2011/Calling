"""Luồng cuộc gọi ĐẾN (offer từ điện thoại → đổ chuông → nghe máy / từ chối khi bận → kết thúc). Tách từ server.py 14/11/2026."""
import json
import time
import os
import threading
from .. import ctrl_poll as ctrl_poll_mod
from .. import media_endpoints
from .. import signaling as signaling_mod
from .. import webhooks as webhooks_mod

from ._srv import srv


def _send_ringring_async(call_id, thread_id):
    """Best-effort ringring (11302, bundle wZ ringRingVoiceCall):
    the callee reports ringing to the caller. Runs on a daemon
    thread so it never blocks the ctrl poller — the call_event
    callback runs on the poller's thread, and a slow signaling
    round-trip there would stall the whole ctrl channel. The
    session is read fresh from STATE; without one the ring is
    skipped (logged, not fatal: the incoming entry is still
    recorded). Only for 1-1 calls. On success the entry's diag
    gains incoming_ringring_sent=True, so POST /api/call/answer
    knows it does not need to ring again."""
    sess = srv().STATE.session
    if not sess or not sess.get("zpw_sek") or not sess.get("zpw_enk"):
        srv()._log_call("ringring call_id=%s ok=False error=no_session"
                  % call_id)
        return
    try:
        transport = srv().make_transport(sess["zpw_sek"])
        sig = signaling_mod.Signaling(transport, sess["device_id"],
                                      sess["zpw_enk"])
        sig.ringring(thread_id, call_id)
        srv().STATE.calls.record_diag(
            call_id, {"incoming_ringring_sent": True})
        srv()._log_call("ringring call_id=%s ok=True" % call_id)
    except Exception as e:  # noqa: BLE001 - best-effort
        srv()._log_call("ringring call_id=%s ok=False error=%s"
                  % (call_id, e))


def _offer_extend(event):
    """extendData bên gọi khai trong sự kiện cuộc gọi đến. Các lớp data / params / extendData có thể là dict HOẶC chuỗi JSON (tuỳ máy và
    phiên bản Zalo), nên mở từng lớp. Trả {} nếu không có."""
    def unwrap(o):
        if isinstance(o, (str, bytes)):
            try:
                o = json.loads(o)
            except ValueError:
                return {}
        return o if isinstance(o, dict) else {}
    d = unwrap(event.get("data"))
    return unwrap(unwrap(d.get("params")).get("extendData")) or unwrap(d.get("extendData"))


def _reject_signals(sess, caller_id, call_id, decline=True):
    """Tu choi cuoc goi DEN nhu Zalo PC that (engine-core.js `reject`): 11303 voi status 3, codec "[]\n", extendData "{}\n", dia chi rong,
    phien cua tin cuoc goi den. Loi thi roi ve cach zca-js rejectIncomingCall: cancel 11305 roi endcall 11306 (moi cai best-effort).
    -> (ok, loi cuoi)."""
    zalo_ok, zalo_error = True, ""
    _info = srv()._INCOMING_INFO.pop(str(call_id), None) or {}
    if decline:                              # bận (decline=False) giữ cách cũ cancel + endcall để người gọi nhận báo máy bận
        try:
            transport = srv().make_transport(sess["zpw_sek"])
            sig = signaling_mod.Signaling(transport, sess["device_id"], sess["zpw_enk"])
            sig.answer(caller_id, call_id, 3, "[]\n", "", "", _info.get("session") or "", "{}\n")
            return True, ""
        except Exception as e:  # noqa: BLE001 - rơi về cách cũ
            srv()._log_call("reject call_id=%s 11303(status 3) failed: %s -> cancel+endcall" % (call_id, str(e)[:120]))
    for signal in ("cancel", "endcall"):
        try:
            transport = srv().make_transport(sess["zpw_sek"])
            sig = signaling_mod.Signaling(transport, sess["device_id"], sess["zpw_enk"])
            if signal == "cancel":
                # callerId = the CALLER (peer), callType = the 1-1 audio enum (1), like _send_end_signal.
                sig.cancel(caller_id, call_id, srv()._type_request_for("user"))
            else:
                sig.endcall(caller_id, call_id)
        except Exception as e:  # noqa: BLE001 - best-effort
            zalo_ok, zalo_error = False, str(e)
    return zalo_ok, zalo_error


def _answer_incoming(sess, body, source="api"):
    """Nghe may cuoc goi DEN: thuc hien o `incoming_call.answer_incoming` (tach rieng khoi cuoc goi di)."""
    from .. import incoming_call
    return incoming_call.answer_incoming(srv(), sess, body, source)


def event_age_seconds(event, now=None):
    """Tuổi (giây) của sự kiện cuộc gọi theo `ts` Zalo ghi trong gói (mili giây, ở data.ts hoặc data.params.ts); None nếu không có/không đọc được."""
    try:
        d = event.get("data")
        d = json.loads(d) if isinstance(d, str) else (d or {})
        pr = d.get("params")
        pr = json.loads(pr) if isinstance(pr, str) else (pr or {})
        for ts in (d.get("ts"), pr.get("ts"), event.get("ts")):
            if ts in (None, ""):
                continue
            v = float(ts)
            if v > 1e11:                      # mili giây
                v /= 1000.0
            if v > 1e9:                       # loại giá trị vô nghĩa (ví dụ ts=1 trong test)
                return (time.time() if now is None else now) - v
    except (TypeError, ValueError, AttributeError):
        pass
    return None


# Zalo PHÁT LẠI các sự kiện cuộc gọi chưa được báo nhận (params.needACK=1; app chưa báo nhận) mỗi lần app khởi động lại: 14/11/2026 08:38 sau khi dựng lại,
# 3 cuộc gọi cũ (08:25–08:28) hiện ra như cuộc gọi đến MỚI, tự nghe máy / báo ra loa / gọi webhook — «tự phát sinh cuộc gọi trong khi không gọi».
# Sự kiện «request» cũ hơn ngưỡng này (giây) bị bỏ qua. ZALO_PC_INCOMING_MAX_AGE, 0 = tắt.
INCOMING_MAX_AGE_SECONDS = float(os.environ.get("ZALO_PC_INCOMING_MAX_AGE", "120") or 0)


class IncomingCalls:
    """Phương thức của AppState thuộc trục này (gộp vào AppState bằng kế thừa)."""

    def _on_incoming_call_request(self, event):
        """Cuoc goi den (call_event act "request"): ghi entry
        "incoming" (thay the cuoc live truoc), gui ringring 11302
        best-effort tren daemon thread, day webhook call.incoming.
        Khong arm ring timer — phia goi quyet dinh khi nao dung
        do chuong."""
        call_id = int(event["call_id"])
        caller_id = str(event.get("caller_id") or "")
        peer = event.get("caller_name") or caller_id
        _age = event_age_seconds(event)
        if INCOMING_MAX_AGE_SECONDS > 0 and _age is not None and _age > INCOMING_MAX_AGE_SECONDS:
            srv()._log_call("incoming call_id=%s bo qua (su kien cu %.0fs, Zalo phat lai sau khoi dong; nguong %.0fs)" % (call_id, _age, INCOMING_MAX_AGE_SECONDS))
            return
        snap = srv().STATE.calls.snapshot()
        # Moi call_id chi xu ly MOT lan: Zalo co the gui lai `request`; neu khong, cuoc dang noi bi dat lai thanh "dang chuong"
        # (va tu nghe may se chay lan nua).
        if srv().STATE.calls.has_call(call_id):
            srv()._log_call("incoming call_id=%s bo qua (su kien request lap lai)" % call_id)
            return
        live = snap["active"]
        # BAN chi khi cuoc dang song con media that: ban ghi "answered"/"sent" bi treo (mat su kien ket thuc) khong duoc
        # chan moi cuoc goi den — truong hop do giu hanh vi cu (cuoc moi thay cuoc cu).
        if live is not None and live["status"] in ("answered", "sent") \
                and media_endpoints.ENDPOINTS.active_record(int(live["call_id"])) is not None:
            self._reject_busy(call_id, caller_id, peer)
            return
        try:
            _rtp, _rtcp = event.get("rtp_address"), event.get("rtcp_address")
            if _rtp and _rtcp:
                if len(srv()._INCOMING_RELAY) > 50:
                    srv()._INCOMING_RELAY.clear()
                srv()._INCOMING_RELAY[str(event.get("call_id"))] = (
                    str(_rtp), str(_rtcp))
        except Exception:  # noqa: BLE001
            pass
        # Cuoc goi VIDEO den ghi la "video" (nhu cuoc goi di): truoc day luon "user" nen buoc tu bat camera sau khi nghe may (_auto_media_async chi
        # chay _start_video khi type == "video") khong bao gio chay — dien thoai chi thay «BenBap dang tat camera» (do 12/11 10:02).
        entry = srv().STATE.calls.record_incoming(
            call_id, peer, caller_id, "video" if event.get("is_video") else "user")
        _explicit_key = ctrl_poll_mod.find_srtp_key(event.get("data"))
        # Khong co khoa tuong minh thi dung khoa tu sessId cua chinh su kien
        # (ben goi dung sessId nay; tren may that khong thay khoa nao khac).
        from .. import srtp_pure as _srtp_pure
        _key = _explicit_key or _srtp_pure.key_from_session(
            event.get("session"))
        if _key:
            if len(srv()._INCOMING_SRTP) > 50:
                srv()._INCOMING_SRTP.clear()
            srv()._INCOMING_SRTP[str(call_id)] = _key
        srv().STATE.calls.record_diag(call_id, {
            "incoming_codec": event.get("codec") or "",
            "incoming_srtp_key_present": bool(_explicit_key),
            "incoming_session_present": bool(event.get("session")),
            "incoming_rtp_present": bool(event.get("rtp_address")),
            "incoming_ringring_sent": False})
        try:                               # lưu extendData bên gọi khai để nghe máy trả lời theo đúng máy đó (mỗi điện thoại có thể khác nhau)
            _d = event.get("data")
            _d = json.loads(_d) if isinstance(_d, str) else (_d or {})
            _sess = event.get("session") or (_d.get("session") if isinstance(_d, dict) else None)
            if isinstance(_sess, str) and _sess:
                if len(srv()._INCOMING_INFO) > 50:
                    srv()._INCOMING_INFO.clear()
                srv()._INCOMING_INFO[str(call_id)] = {"session": _sess, "uid_from": srv()._as_uid(_d.get("uidFrom")), "uid_to": srv()._as_uid(_d.get("uidTo"))}
        except Exception:  # noqa: BLE001
            pass
        try:
            _off = _offer_extend(event)
            if _off:
                if len(srv()._INCOMING_OFFER) > 50:
                    srv()._INCOMING_OFFER.clear()
                srv()._INCOMING_OFFER[str(call_id)] = _off
        except Exception:  # noqa: BLE001 - chẩn đoán/thích ứng là best-effort
            pass
        try:                               # điện thoại (bên gọi) khai gì: cắt ngắn chuỗi dài, che khoá/phiên/token (chỉ để chẩn đoán)
            def _shrink(o, name=""):
                if isinstance(o, dict):
                    return {k: _shrink(v, k) for k, v in o.items()}
                if isinstance(o, list):
                    return [_shrink(v, name) for v in o[:6]]
                if isinstance(o, str):
                    if any(w in name.lower() for w in ("sess", "key", "token")):
                        return "<%d ky tu>" % len(o)
                    try:
                        j = json.loads(o)
                        if isinstance(j, (dict, list)):
                            return _shrink(j, name)
                    except ValueError:
                        pass
                    return o if len(o) <= 40 else o[:40] + "..."
                return o
            srv()._log_call("incoming offer call_id=%s event=%s" % (call_id, json.dumps(_shrink({k: v for k, v in event.items() if k != "session"}), ensure_ascii=False)[:6000]))
            try:   # tham so day du cua loi moi (dong tren bi cat o 6000 ky tu): de so cuoc thanh cong voi cuoc -101. Khong ghi session (bi mat).
                def _obj(x):   # params / extendData cua Zalo la CHUOI JSON (khong phai dict): giai ma neu can
                    if isinstance(x, str):
                        try:
                            x = json.loads(x)
                        except ValueError:
                            return {}
                    return x if isinstance(x, dict) else {}
                _d = _obj(event.get("data"))
                _pr = _obj(_d.get("params"))
                _ex = dict(_obj(_pr.get("extendData")))
                _pr = dict(_pr, settings=_obj(_pr.get("settings")) or _pr.get("settings"), fec=_obj(_pr.get("fec")) or _pr.get("fec"))
                for _k in ("p2p", "serverAddr"):
                    if isinstance(_ex.get(_k), list):
                        _ex[_k] = "n=%d" % len(_ex[_k])
                _top = {k: v for k, v in _d.items() if k not in ("session", "params", "codec")}
                _rest = {k: v for k, v in _pr.items() if k not in ("settings", "fec", "extendData")}
                srv()._log_call("offer-params call_id=%s top=%s settings=%s fec=%s ext=%s rest=%s" % (
                    call_id, json.dumps(_top, ensure_ascii=False, sort_keys=True), json.dumps(_pr.get("settings"), ensure_ascii=False, sort_keys=True),
                    json.dumps(_pr.get("fec"), sort_keys=True), json.dumps(_ex, ensure_ascii=False, sort_keys=True), json.dumps(_rest, ensure_ascii=False, sort_keys=True)))
            except Exception:  # noqa: BLE001 - chan doan khong duoc lam hong viec nhan cuoc goi
                pass
        except Exception:  # noqa: BLE001 - chỉ chẩn đoán
            pass
        srv()._log_call("incoming key call_id=%s explicit=%s session_in_event=%s key=%s"
                  % (call_id, bool(_explicit_key), bool(event.get("session")), srv()._key_fp(_key)))
        srv()._log_call("incoming call_id=%s peer=%s thread=%s"
                  % (call_id, peer, caller_id))
        thread = threading.Thread(
            target=_send_ringring_async,
            args=(call_id, caller_id), daemon=True)
        thread.start()
        webhooks_mod.dispatch_call_event(
            srv().STATE.webhook_dispatcher, entry,
            (srv().STATE.session or {}).get("uid", ""),
            extra={"contact_status": self.contact_status("user", caller_id),       # friend / stranger / unknown (khong doan)
                   "call_type_raw": event.get("call_type")})                      # 0 thoai / 1 video theo zca-js (CHUA kiem tren cuoc goi that)

    def _on_incoming_call_ended(self, event, act):
        """Caller ket thuc truoc khi ta tra loi (cancel/end), hoac
        ket thuc mot cuoc dang noi: chi GHI NHAN, khong gui tin
        hieu (phia kia da ket thuc roi). Incoming chua tra loi ->
        "missed" (cuoc goi nho); outgoing/answered -> peer ket
        thuc. Webhook call.ended."""
        call_id = int(event["call_id"])
        snap = srv().STATE.calls.snapshot()
        target = None
        for c in snap["calls"]:
            if str(c["call_id"]) == str(call_id) \
                    and c["status"] in ("incoming", "sent",
                                        "answered"):
                target = c
                break
        if target is None:
            srv()._log_call("call_event %s call_id=%s ignored=no_live"
                      % (act, call_id))
            return
        if target["status"] == "incoming":
            detail = "missed"
        elif act in ("cancel", "cancelcall"):
            detail = "peer_declined"
        else:
            detail = "peer_ended"
        entry = srv().STATE.calls.record_end(call_id, detail)
        if entry is not None:
            srv()._disarm_ring_timer(call_id)
            srv()._cleanup_call_media(entry)
            srv()._log_call("call_event %s call_id=%s ended detail=%s"
                      % (act, call_id, detail))
            webhooks_mod.dispatch_call_event(
                srv().STATE.webhook_dispatcher, entry,
                (srv().STATE.session or {}).get("uid", ""))
