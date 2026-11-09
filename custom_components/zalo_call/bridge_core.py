"""Phan thuan cua cau noi am thanh cuoc goi — KHONG import Home Assistant,
nen test duoc ngoai HA (tests/test_custom_bridge_core.py).

- derive_state: trang thai cuoc goi cho automation (ringing / answered /
  declined / no_answer / missed / ended / incoming / error) tu su kien app.
- pick_devices: thiet bi mac dinh (tuy chon tich hop) + ghi de theo tung
  cuoc goi ("bat ky thiet bi nao").
- ffmpeg_args: doc mic tu nguon bat ky (stream camera, URL) -> PCM16 16 kHz.
"""
from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit

CHUNK_BYTES = 3200                 # 100 ms PCM16 mono @ 16 kHz (5 khung 20 ms)
ALLOWED_SCHEMES = ("rtsp", "rtsps", "http", "https", "rtmp")
DEVICE_KEYS = ("speaker", "mic", "mic_url", "camera")

# Ly do ket thuc (app: webhooks.build_call_event "end_reason") -> trang thai.
END_REASON_STATE = {
    "ring_timeout": "no_answer",        # goi di, ben kia khong nghe may
    "peer_declined": "declined",        # goi di, ben kia tu choi
    "missed": "missed",                 # goi den, ta khong nghe
    "user_rejected": "rejected",        # goi den, ta tu choi
    "peer_ended": "ended",
    "user_end": "ended",
    "superseded_by_new_call": "ended",
    "server_rejected": "error",
}
_STATUS_STATE = {"incoming": "incoming", "sent": "ringing",
                 "answered": "answered", "error": "error"}


def derive_state(payload: Mapping[str, Any]) -> str | None:
    """Trang thai de automation dung; None neu khong nhan ra."""
    status = str(payload.get("status") or "")
    if status == "ended":
        return END_REASON_STATE.get(str(payload.get("end_reason") or ""),
                                    "ended")
    return _STATUS_STATE.get(status)


def pick_devices(defaults: Mapping[str, Any],
                 override: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Thiet bi cho mot cuoc goi: ghi de > mac dinh > khong co.

    Khoa vang hoac None -> dung mac dinh; chuoi RONG -> chu dong KHONG dung
    thiet bi do cho cuoc goi nay."""
    override = override or {}
    out: dict[str, str] = {}
    for key in DEVICE_KEYS:
        if key in override and override[key] is not None:
            out[key] = str(override[key]).strip()
        else:
            out[key] = str(defaults.get(key) or "").strip()
    return out


def mic_source_kind(devices: Mapping[str, str]) -> tuple[str, str] | None:
    """("url", url) neu co mic_url, ("camera", entity_id) neu co mic, else None.
    mic_url thang mic (mic_url la cach 'bat ky thiet bi' qua URL)."""
    if devices.get("mic_url"):
        return "url", devices["mic_url"]
    if devices.get("mic"):
        return "camera", devices["mic"]
    return None


def ffmpeg_args(source: str) -> list[str]:
    """Lenh ffmpeg doc am thanh tu `source` -> PCM16 mono 16 kHz tren stdout.

    Chi nhan URL mang (rtsp/rtsps/http/https/rtmp): khong cho duong dan tep
    hay giao thuc cuc bo, de dich vu khong bi dung doc tep tuy y."""
    parts = urlsplit(source or "")
    if parts.scheme.lower() not in ALLOWED_SCHEMES or not parts.netloc:
        raise ValueError("nguon mic phai la URL %s, nhan: %r"
                         % ("/".join(ALLOWED_SCHEMES), parts.scheme))
    args = ["-nostdin", "-loglevel", "error"]
    if parts.scheme.lower() in ("rtsp", "rtsps"):
        args += ["-rtsp_transport", "tcp"]
    args += ["-i", source, "-vn", "-ac", "1", "-ar", "16000",
             "-f", "s16le", "pipe:1"]
    return args


def audio_out_url(base: str, token: str) -> str:
    return "%s/api/call/audio/out/%s" % (base.rstrip("/"), token)
