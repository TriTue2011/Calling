"""Luồng VIDEO của cuộc gọi (hình ta phát lên điện thoại, báo camera bật/tắt, xin/đồng ý chuyển thoại → video). Tách từ server.py 14/11/2026."""
import json
import threading
import time

from .. import signaling as signaling_mod
from .. import video_tx as video_tx_mod
from .. import webhooks as webhooks_mod
import queue
import shutil
import subprocess
import urllib.request
from .. import ffmpeg_log as ffmpeg_log_mod
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


class VideoCalls:
    """Phương thức của AppState thuộc trục này (gộp vào AppState bằng kế thừa)."""

    def _on_camera_toggle(self, event):
        """Su kien onoff_camera cua ben kia (act "1" / "onoff_camera", params.type 1 = bat, 0 = tat). Bat camera khi cuoc dang THOAI = loi xin chuyen sang
        video: xu ly nhu loi xin (status 1) de HA/quy tac quyet dinh dong y hay khong; cuoc da la video hoac tat camera thi chi ghi nhat ky."""
        call_id = int(event["call_id"])
        def _obj(x):                     # data / params cua Zalo co the la CHUOI JSON
            if isinstance(x, str):
                try:
                    x = json.loads(x)
                except ValueError:
                    return {}
            return x if isinstance(x, dict) else {}
        data = _obj(event.get("data"))
        params = _obj(data.get("params"))
        try:
            cam_on = int(params.get("type", data.get("type", 0))) == 1
        except (TypeError, ValueError):
            cam_on = False
        entry = next((c for c in srv().STATE.calls.snapshot()["calls"] if str(c["call_id"]) == str(call_id)), None)
        already_video = bool(entry is not None and (entry.get("video") or entry.get("is_video") or entry.get("call_type") == "video"))
        srv()._log_call("call_event camera call_id=%s %s%s" % (call_id, "bat" if cam_on else "tat", " (cuoc da la video)" if already_video else ""))
        srv()._send_camera_inband(call_id, str(call_id) in srv().VIDEO_SENDERS)       # zca-js: bên kia đổi camera thì gửi lại trạng thái camera của ta ngay
        if not cam_on or already_video:
            return
        self._on_video_request(dict(event, data=dict(data, params=dict(params, status=1))))

    def _on_video_request(self, event):
        """Dien thoai xin chuyen cuoc goi THOAI dang dien ra sang VIDEO (12056).
        status 1 = loi xin: neu bat `auto_video_on_request` thi sau `auto_video_delay`
        giay (0 = ngay) dong y (status 2) va, neu co camera mac dinh, phat hinh —
        chi khi luc do cuoc goi van dang noi may. status 2 = dong y loi xin cua ta."""
        call_id = int(event["call_id"])
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        params = data.get("params") if isinstance(data.get("params"), dict) else data
        try:
            status = int(params.get("status", data.get("status", 1)))
        except (TypeError, ValueError):
            status = 1
        srv()._log_call("video request call_id=%s status=%s" % (call_id, status))
        if status == 1:
            # Báo cho HA (zalo_call_call_state state=video_request) để quy tắc/blueprint quyết định đồng ý hay không.
            try:
                entry = next((c for c in srv().STATE.calls.snapshot()["calls"] if str(c["call_id"]) == str(call_id)), None)
                if entry is not None:
                    webhooks_mod.dispatch_call_event(srv().STATE.webhook_dispatcher, entry, (srv().STATE.session or {}).get("uid", ""),
                                                     extra={"status": "video_request",
                                                            "contact_status": self.contact_status("user", entry["thread_id"])})
            except Exception:  # noqa: BLE001 - báo HA là best-effort
                pass
        cfg = srv()._devices_for_call(call_id)
        if status != 1 or not cfg["auto_video_on_request"]:
            return
        delay = int(cfg.get("auto_video_delay") or 0)

        def accept():
            entry = next((c for c in srv().STATE.calls.snapshot()["calls"]
                          if str(c["call_id"]) == str(call_id)), None)
            if entry is None or entry["status"] != "answered":
                srv()._log_call("video auto call_id=%s bo qua (cuoc goi da het)"
                          % call_id)
                return
            srv()._send_a2v_async(call_id, entry["thread_id"], 2)
            cam = srv()._devices_for_call(call_id)["camera_url"]
            if cam:
                try:
                    srv()._start_video(call_id, cam)
                except (ValueError, RuntimeError) as exc:
                    srv()._log_call("video auto call_id=%s error=%s"
                              % (call_id, str(exc)[:80]))

        if delay <= 0:
            accept()
        else:
            srv()._log_call("video auto call_id=%s se dong y sau %ds" % (call_id, delay))
            timer = threading.Timer(delay, accept)
            timer.daemon = True
            timer.start()


# Cuộc gọi ĐẾN mà sau khi nghe máy điện thoại KHÔNG gửi bất kỳ gói nào (rtp/rtcp/video đều 0) là cuộc «chết» (13/11: 12/20 cuộc khi gói đầu chưa tới
# lúc chọn relay; gửi lại InitZRTP không cứu được). Nghe im lặng suốt cuộc thì vô ích và điện thoại báo «kết nối không ổn định» — tự kết thúc sớm
# (lý do «dead_media» đi theo webhook cuộc gọi để HA báo/gọi lại) để người gọi gọi lại ngay. ZALO_PC_DEAD_MEDIA_SECONDS, 0 = tắt.
VIDEO_VIEWERS_MAX = 2


VIDEO_VIEW_LOCK = threading.Lock()


VIDEO_VIEW_COUNT = [0]


# Đo thật 14/11 trong container (ffmpeg 7): `-fflags nobuffer` + pipe H.264 -> KHÔNG ra khung nào; H.264 thô không có dấu thời gian nên bộ lọc fps cũng
# không ra khung -> dùng `-framerate 15` ở đầu vào, `-flags low_delay`, giới hạn dò nhỏ; JPEG cần yuvj420p. 45/45 khung ra.
VIDEO_VIEW_FFMPEG = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-flags", "low_delay", "-probesize", "16384", "-analyzeduration", "100000",
                     "-framerate", "15", "-f", "h264", "-i", "pipe:0", "-vf", "scale=640:-2,format=yuvj420p", "-q:v", "7",
                     "-f", "mpjpeg", "-boundary_tag", "frame", "pipe:1"]


class VideoHandler:
    """Phương thức của Handler thuộc trục này (gộp vào Handler bằng kế thừa)."""

    def _serve_call_video_view(self):
        """Xem hình điện thoại gửi sang (WebUI): khung H.264 đã giải mã SRTP + ghép (udp_transport add_video_tap) -> ffmpeg -> MJPEG nhiều phần
        (multipart/x-mixed-replace) cho thẻ <img>. Mỗi người xem một ffmpeg (tối đa VIDEO_VIEWERS_MAX); ngắt kết nối thì dọn tiến trình."""
        qs = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        call_id = srv()._coerce_call_id((qs.get("call_id") or [""])[0])
        if call_id is None:
            live = srv().STATE.calls.snapshot()["active"]
            call_id = int(live["call_id"]) if live is not None else None
        transport = srv()._transport_for_call(call_id) if call_id is not None else None
        if transport is None or not hasattr(transport, "add_video_tap"):
            return self._send_json({"error": "chua_co_hinh"}, status=409)
        if shutil.which("ffmpeg") is None:
            return self._send_json({"error": "thieu_ffmpeg"}, status=503)
        with VIDEO_VIEW_LOCK:
            if VIDEO_VIEW_COUNT[0] >= VIDEO_VIEWERS_MAX:
                return self._send_json({"error": "qua_nhieu_nguoi_xem"}, status=429)
            VIDEO_VIEW_COUNT[0] += 1
        tap = transport.add_video_tap()
        proc = None
        try:
            proc = subprocess.Popen(VIDEO_VIEW_FFMPEG, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def feed():
                try:
                    while proc.poll() is None:
                        if srv()._transport_for_call(call_id) is not transport:        # cuộc gọi đã kết thúc
                            break
                        try:
                            annexb, _key = tap.get(timeout=1)
                        except queue.Empty:
                            continue
                        proc.stdin.write(annexb)
                except (OSError, ValueError):
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except (OSError, ValueError):
                        pass
            threading.Thread(target=feed, daemon=True, name="video-view-feed").start()
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except OSError:
            pass                            # trình duyệt đóng thẻ: bình thường
        finally:
            transport.remove_video_tap(tap)
            ffmpeg_log_mod.kill_and_reap(proc)
            with VIDEO_VIEW_LOCK:
                VIDEO_VIEW_COUNT[0] -= 1
