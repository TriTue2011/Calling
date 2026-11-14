"""Luồng VIDEO của cuộc gọi (hình ta phát lên điện thoại, báo camera bật/tắt, xin/đồng ý chuyển thoại → video). Tách từ server.py 14/11/2026."""
import json
import threading
import time

from .. import signaling as signaling_mod
from .. import video_tx as video_tx_mod
from ._srv import srv


VIDEO_SENDERS = {}               # call_id -> video_tx.VideoSender


# Hinh chi duoc phat sau khoang cho nay ke tu luc nghe may. Do 10/11/2026 tren dien thoai
# that: bat hinh NGAY luc nghe may thi tin hieu «camera bat» (12006) toi truoc buoc xac nhan
# nghe may (answerack) nen dien thoai bo qua — hinh nhay mot lan roi mat. Bat tay sau 2 s
# (kich ban 01:40) thi hinh len on dinh.
VIDEO_START_DELAY_S = 2.0


# Bao «camera bat» (12006) CHI MOT LAN la hay hut: dien thoai co the chua san sang nhan luc ta vua nghe may (13/11: bao luc +2 giay sau answerack,
# dien thoai van giu «BenBap dang tat camera» du nhan du goi hinh, TWCC ok lost=0). Gui lai theo nhip thua dan cho toi khi hinh dung; trang thai la
# idempotent (isOnCam=1 nhieu lan khong hai gi).
CAMERA_STATE_REPEAT = (2.0, 4.0, 8.0, 15.0)


CAMERA_STATE_KEEP_SECONDS = 20.0


def _stop_video(call_id):
    sender = VIDEO_SENDERS.pop(str(call_id), None)
    if sender is not None:
        sender.stop()
    return sender


def _send_camera_inband(call_id, cam_on):
    """Bao camera bat/tat NGAY TRONG kenh relay UDP (ReqForward sub 7/8) — duong Zalo PC that dung (khong co 12006 qua HTTPS)."""
    try:
        tr = srv()._transport_for_call(call_id)
        ok = bool(tr is not None and tr.send_camera_state(bool(cam_on)))
        srv()._log_call("camera state inband call_id=%s on=%s ok=%s" % (call_id, bool(cam_on), ok))
        return ok
    except Exception as e:  # noqa: BLE001 - best-effort
        srv()._log_call("camera state inband call_id=%s on=%s ok=False error=%s" % (call_id, bool(cam_on), str(e)[:100]))
        return False


def _send_camera_state_async(call_id, thread_id, cam_on):
    """Bao dien thoai camera cua ta bat/tat: trong kenh relay UDP (ReqForward sub 7/8, nhu Zalo PC that) VA 12006 qua HTTPS (giu nhu cu).
    Chay luong rieng, khong nem loi: hinh van gui duoc du bao that bai, chi la dien thoai khong ve."""
    _send_camera_inband(call_id, cam_on)
    def run():
        sess = srv().STATE.session
        if not sess or not sess.get("zpw_sek") or not sess.get("zpw_enk"):
            srv()._log_call("camera state call_id=%s ok=False error=no_session"
                      % call_id)
            return
        try:
            transport = srv().make_transport(sess["zpw_sek"])
            sig = signaling_mod.Signaling(transport, sess["device_id"],
                                          sess["zpw_enk"])
            _resp = sig.conf(thread_id, call_id, cam=1 if cam_on else 0)
            srv()._log_call("camera state call_id=%s on=%s ok=True body=%s phan_hoi=%s"
                      % (call_id, bool(cam_on),
                         json.dumps({"calleeId": str(thread_id), "callId": call_id, "isOnCam": 1 if cam_on else 0, "isOnMic": -1}, sort_keys=True),
                         json.dumps(_resp, ensure_ascii=False, sort_keys=True, default=str)[:300]))
        except Exception as e:  # noqa: BLE001 - best-effort
            srv()._log_call("camera state call_id=%s on=%s ok=False error=%s"
                      % (call_id, bool(cam_on), str(e)[:120]))
    threading.Thread(target=run, daemon=True).start()


def _repeat_camera_state(call_id, sender, delays=CAMERA_STATE_REPEAT, keep=CAMERA_STATE_KEEP_SECONDS, sleep=time.sleep):
    def run():
        waits = list(delays)
        while True:
            sleep(waits.pop(0) if waits else keep)
            if VIDEO_SENDERS.get(str(call_id)) is not sender:        # hinh da dung / cuoc goi da ket thuc / thay nguon
                return
            _send_camera_state_async(call_id, srv()._thread_of_call(call_id), True)
    threading.Thread(target=run, daemon=True, name="camera-state-repeat").start()


def _start_video(call_id, source, params=None):
    """Phat hinh `source` len cuoc goi (+ bao camera bat). Nem ValueError/RuntimeError."""
    transport = srv()._transport_for_call(call_id)
    if transport is None:
        raise RuntimeError("no_live_transport")
    cfg = dict(srv().STATE.devices.get()["video"])
    cfg.update({k: v for k, v in (params or {}).items() if k in cfg})
    _stop_video(call_id)
    sender = video_tx_mod.VideoSender(
        transport.send_video_frame, source=source or "test",
        width=int(cfg["width"]), height=int(cfg["height"]),
        fps=int(cfg["fps"]), bitrate_kbps=int(cfg["bitrate_kbps"]), log=srv()._log_call)
    sender.start()
    VIDEO_SENDERS[str(call_id)] = sender
    _send_camera_state_async(call_id, srv()._thread_of_call(call_id), True)
    _repeat_camera_state(call_id, sender)
    srv()._log_call("video start call_id=%s source=%s" % (
        call_id, "test" if (source or "test") == "test" else "stream"))
    return sender


def _send_a2v_async(call_id, thread_id, status):
    """Xin (status 1) hoac dong y (status 2) chuyen thoai -> video; 12056."""
    def run():
        sess = srv().STATE.session
        if not sess or not sess.get("zpw_sek") or not sess.get("zpw_enk"):
            srv()._log_call("audio2video call_id=%s ok=False error=no_session"
                      % call_id)
            return
        try:
            transport = srv().make_transport(sess["zpw_sek"])
            sig = signaling_mod.Signaling(transport, sess["device_id"],
                                          sess["zpw_enk"])
            _resp = sig.audio_to_video(thread_id, call_id, status)
            srv()._log_call("audio2video call_id=%s status=%s ok=True phan_hoi=%s"
                      % (call_id, status, json.dumps(_resp, ensure_ascii=False, sort_keys=True, default=str)[:400]))
        except Exception as e:  # noqa: BLE001 - best-effort
            srv()._log_call("audio2video call_id=%s status=%s ok=False error=%s inner=%s"
                      % (call_id, status, str(e)[:160], json.dumps(getattr(e, "inner", None), ensure_ascii=False, default=str)[:300]))
    threading.Thread(target=run, daemon=True).start()
