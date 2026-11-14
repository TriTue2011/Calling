"""Điều khiển thiết bị GIỮA cuộc gọi (/api/call/video, /api/call/media, /api/call/upgrade_video): nơi DUY NHẤT chạm cả mic, loa và hình trong cùng một yêu cầu (target = mic|speaker|video|both|upgrade|accept_video). Tách từ server.py 14/11/2026."""
import re
from ..calls import video as video_calls

from ._srv import srv


class MediaControl:
    """Phương thức của Handler thuộc trục này (gộp vào Handler bằng kế thừa)."""

    def _handle_call_media(self, path, body):
        """Dieu khien mic / hinh cua cuoc goi dang song.

        /api/call/video          {action: start|stop|status, source, width, height,
                                  fps, bitrate_kbps}
        /api/call/media          {action: start|stop|status, target: mic|video|speaker|both,
                                  mic_url, mic_format, camera_url, speaker_url}  (thieu thi dung mac dinh)
        /api/call/upgrade_video  {camera_url?}  chuyen cuoc goi THOAI sang VIDEO
        """
        snap = srv().STATE.calls.snapshot()
        live = snap["active"]
        call_id = srv()._coerce_call_id(body.get("call_id", ""))
        if call_id is None and live is not None:
            call_id = int(live["call_id"])
        if call_id is None:
            return self._send_json({"ok": False, "error": "no_live_call"})
        action = str(body.get("action") or "start").lower()

        def vstat():
            sd = srv().VIDEO_SENDERS.get(str(call_id))
            return sd.status() if sd else None

        def mstat():
            sd = srv().AUDIO_SENDERS.get(str(call_id))
            return sd.status() if sd else None

        def sstat():
            sd = srv().SPEAKER_SINKS.get(str(call_id))
            return sd.status() if sd else None

        if action not in ("start", "stop", "status"):
            return self._send_json({"error": "action_khong_hop_le"}, status=400)
        if path == "/api/call/video":
            target = "video"
        elif path == "/api/call/media":
            target = str(body.get("target") or "both").lower()
        else:
            target = "upgrade"
        if action == "status":
            return self._send_json({"ok": True, "call_id": call_id,
                                    "video": vstat(), "mic": mstat(),
                                    "speaker": sstat()})
        if action == "stop":
            if target in ("video", "both"):
                if srv()._stop_video(call_id) is not None:
                    video_calls._send_camera_state_async(
                        call_id, srv()._thread_of_call(call_id), False)
            if target in ("mic", "both"):
                srv()._stop_mic(call_id)
            if target in ("speaker", "both"):
                srv()._stop_speaker(call_id)
            return self._send_json({"ok": True, "call_id": call_id,
                                    "video": vstat(), "mic": mstat(),
                                    "speaker": sstat()})
        # Nối thiết bị GIỮA cuộc gọi (HA chuyển máy từ AI sang trực tiếp): bộ thiết bị đưa kèm thành thiết bị riêng của cuộc gọi này (đủ
        # bốn nhóm, nhóm không cài = "off" → không rơi về mặc định); có nhóm nào thì nối nhóm đó.
        if any(k in body for k in srv()._CALL_DEVICE_KEYS):
            srv()._CALL_DEVICES.pop(str(call_id), None)
            srv()._remember_call_devices(call_id, body)
            # "off" = nhóm này không cài: đã ghi vào thiết bị riêng của cuộc gọi (rỗng), nay bỏ khỏi body để không bị coi là URL.
            body = {k: v for k, v in body.items() if not (k in ("mic_url", "speaker_url", "camera_url") and str(v).strip().lower() == "off")}
        if target == "accept_video":
            # Đồng ý lời xin chuyển sang video của người gọi (HA quyết định); camera_url trống = chỉ đồng ý, không gửi hình trong nhà.
            entry = next((c for c in snap["calls"] if str(c["call_id"]) == str(call_id)), None)
            if entry is None or entry["status"] != "answered":
                return self._send_json({"ok": False, "error": "chua_nghe_may"})
            srv()._send_a2v_async(call_id, srv()._thread_of_call(call_id), 2)
            src = str(body.get("camera_url") or "")
            if src:
                try:
                    srv()._start_video(call_id, src)
                except (ValueError, RuntimeError) as exc:
                    return self._send_json({"ok": False, "error": str(exc)[:120]})
            return self._send_json({"ok": True, "call_id": call_id, "video": vstat(), "mic": mstat(), "speaker": sstat()})
        cfg = srv()._devices_for_call(call_id)
        try:
            if target == "upgrade":
                entry = next((c for c in snap["calls"]
                              if str(c["call_id"]) == str(call_id)), None)
                if entry is None or entry["status"] != "answered":
                    return self._send_json({"ok": False,
                                            "error": "chua_nghe_may"})
                srv()._send_a2v_async(call_id, srv()._thread_of_call(call_id), 1)
                src = str(body.get("camera_url") or body.get("source")
                          or cfg["camera_url"] or "test")
                srv()._start_video(call_id, src)
            else:
                if target in ("mic", "both"):
                    src = str(body.get("mic_url")
                              or (body.get("source") if target == "mic" else "")
                              or cfg["mic_url"] or "")
                    if src:
                        srv()._start_mic(call_id, src,
                                   str(body.get("mic_format") or cfg["mic_format"]))
                if target in ("speaker", "both"):
                    spk = str(body.get("speaker_url")
                              or (body.get("source") if target == "speaker" else "")
                              or cfg.get("speaker_url") or "")
                    if spk:
                        if not re.match(r"^https?://\S+$", spk):
                            raise ValueError("speaker_url phai la URL http(s)")
                        srv()._start_speaker(call_id, spk)
                    elif target == "speaker":
                        raise ValueError("chua_co_speaker_url")
                if target in ("video", "both"):
                    src = str(body.get("camera_url") or body.get("source")
                              or cfg["camera_url"] or "")
                    if src or target == "video":
                        params = {k: body[k] for k in
                                  ("width", "height", "fps", "bitrate_kbps")
                                  if k in body}
                        srv()._start_video(call_id, src or "test", params)
        except (ValueError, RuntimeError) as exc:
            return self._send_json({"ok": False, "error": str(exc)[:120]})
        return self._send_json({"ok": True, "call_id": call_id,
                                "video": vstat(), "mic": mstat(),
                                "speaker": sstat()})
