"""Phan thuan cua cau noi am thanh cuoc goi — KHONG import Home Assistant,
nen test duoc ngoai HA (tests/test_zalo_call_bridge.py).

- derive_state: trang thai cuoc goi cho automation (ringing / answered /
  declined / no_answer / missed / ended / incoming / error) tu su kien app.
- pick_devices: thiet bi mac dinh + ghi de theo tung cuoc goi.
- label / entity_of_label: nhan tuy chon cua cac o chon thiet bi.
- r1_mic_url / dahua_mic_url / mic_format_for_url: nguon mic tu loa R1, camera
  Imou/Dahua, URL bat ky (app tu ffmpeg doc, HA khong con bom tieng).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Mapping
from urllib.parse import quote, urlsplit, urlunsplit

ALLOWED_SCHEMES = ("rtsp", "rtsps", "http", "https", "rtmp", "rtmps")
DEVICE_KEYS = ("speaker", "mic", "mic_url", "camera")
LABEL_SEP = " · "
R1_MIC_PATH = "/api/r1_speaker/mic/"

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
                 "answered": "answered", "error": "error",
                 "video_request": "video_request"}          # người gọi xin chuyển cuộc thoại sang video (HA quyết định)


def derive_state(payload: Mapping[str, Any]) -> str | None:
    """Trang thai de automation dung; None neu khong nhan ra."""
    status = str(payload.get("status") or "")
    if status == "ended":
        return END_REASON_STATE.get(str(payload.get("end_reason") or ""),
                                    "ended")
    return _STATUS_STATE.get(status)


_ENTITY_RE = re.compile(r"[a-z_]+\.[a-z0-9_]+")


def candidates(value: Any) -> list[str]:
    """Thiet bi du phong: nhieu thuc the cach nhau bang dau phay theo thu tu uu tien («loa_chinh, loa_phu»). Chuoi khong phai danh sach
    thuc the (URL, nhan co dau phay) thi la mot gia tri duy nhat."""
    v = str(value or "").strip()
    if "," not in v or "://" in v:
        return [v] if v else []
    parts = [p.strip() for p in v.split(",") if p.strip()]
    return parts if parts and all(_ENTITY_RE.fullmatch(entity_of_label(p)) for p in parts) else [v]


def first_alive(value: Any, alive: Callable[[str], bool] | None) -> str:
    """Thiet bi con hoat dong DAU TIEN trong danh sach du phong; khong cai nao hoat dong thi lay cai dau (loi se hien khi noi nhu cu)."""
    cands = candidates(value)
    if len(cands) <= 1 or alive is None:
        return cands[0] if cands else ""
    return next((c for c in cands if alive(entity_of_label(c))), cands[0])


def pick_devices(defaults: Mapping[str, Any],
                 override: Mapping[str, Any] | None = None,
                 alive: Callable[[str], bool] | None = None) -> dict[str, str]:
    """Thiet bi cho mot cuoc goi: ghi de > mac dinh > khong co.

    Khoa vang hoac None -> dung mac dinh; chuoi RONG -> chu dong KHONG dung
    thiet bi do cho cuoc goi nay. Loa/mic/camera co the la DANH SACH du phong (cach nhau bang dau phay): lay cai con hoat dong dau tien
    (`alive(entity_id)` False khi thuc the khong ton tai, unavailable hoac unknown)."""
    override = override or {}
    out: dict[str, str] = {}
    for key in DEVICE_KEYS:
        # Mic/loa/camera KHÔNG còn mặc định (14/11/2026): chỉ có thiết bị do quy tắc/automation (ghi đè) chọn; không chọn = không nối.
        val = str(override[key]).strip() if key in override and override[key] is not None else ""
        out[key] = first_alive(val, alive) if key != "mic_url" else val
    return out


def explicit_off(override: Mapping[str, Any] | None, keys: tuple[str, ...],
                 devices: Mapping[str, str]) -> bool:
    """Cuoc goi nay chu dong tat nhom thiet bi `keys`: co ghi de cho nhom do
    nhung khong con thiet bi nao (ghi de rong)."""
    return bool(override) and any(k in override for k in keys) \
        and not any(devices.get(k) for k in keys)


def label(entity_id: str, friendly: str | None) -> str:
    """Nhan hien tren o chon: "Ten · entity_id" (hoac entity_id neu khong co ten)."""
    name = (friendly or "").strip()
    return "%s%s%s" % (name, LABEL_SEP, entity_id) if name and name != entity_id \
        else entity_id


def entity_of_label(text: str) -> str:
    """entity_id tu nhan (phan sau dau ' · ' cuoi cung)."""
    return (text or "").rsplit(LABEL_SEP, 1)[-1].strip()


def valid_url(url: str) -> bool:
    parts = urlsplit(url or "")
    return parts.scheme.lower() in ALLOWED_SCHEMES and bool(parts.netloc) \
        and " " not in url and "\n" not in url


LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def localize_url(url: str, host: str) -> str:
    """Doi dia chi may CUC BO (localhost, 127.0.0.1...) trong `url` thanh `host`.

    Luong camera ma HA tra ve (vd go2rtc rtsp://u:p@localhost:8554/x) chi dung duoc tu
    chinh may HA; app chay o container/may khac phai goi qua dia chi LAN cua may HA."""
    parts = urlsplit(url or "")
    if not host or (parts.hostname or "").lower() not in LOOPBACK_HOSTS:
        return url
    userinfo = parts.netloc.rpartition("@")[0]
    netloc = (userinfo + "@" if userinfo else "") + host \
        + (":%d" % parts.port if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def host_of(base_url: str) -> str:
    """Ten may trong mot URL co so (vd http://172.16.10.200:8123 -> 172.16.10.200)."""
    return urlsplit(base_url or "").hostname or ""


def mic_format_for_url(url: str) -> str:
    """s16le16k cho luong PCM tho (mic loa R1), con lai auto."""
    return "s16le16k" if R1_MIC_PATH in (url or "") else "auto"


def r1_mic_url(base: str, entry_id: str, key: str) -> str:
    """Luong mic loa R1 (PCM16 mono 16 kHz tho) cua tich hop r1_speaker."""
    return "%s%s%s?k=%s" % (base.rstrip("/"), R1_MIC_PATH,
                            quote(entry_id, safe=""), quote(key, safe=""))


def dahua_mic_url(options: Mapping[str, Any], data: Mapping[str, Any]) -> str:
    """mic_url cua mot entry dahua_talk (options thang data)."""
    return str(options.get("mic_url") or data.get("mic_url") or "").strip()


def intercom_url(base: str, domain: str, entry_id: str, key: str, kind: str = "intercom") -> str:
    """Duong day tieng vao loa: «cua bo dam» (kind=intercom, A-law 8 kHz, nua cong: HA tu tat mic
    khi dang phat) hoac phien song cong cua R1 (kind=duplex, PCM16 16 kHz tho, mic van mo)."""
    return "%s/api/%s/%s/%s?k=%s" % (base.rstrip("/"), domain, kind,
                                     quote(entry_id, safe=""), quote(key, safe=""))


_DEVICE_URL = re.compile(r"/api/(r1_speaker|dahua_talk)/(?:mic|intercom|duplex)/([^/?#]+)")


def device_of_url(url: str) -> tuple[str, str] | None:
    """(tich hop, entry_id) tu URL mic/bo dam cua r1_speaker/dahua_talk, hoac None."""
    m = _DEVICE_URL.search(url or "")
    return (m.group(1), m.group(2)) if m else None


def speaker_kind(mode: str, domain: str) -> str:
    """Duong day tieng vao loa: «duplex» khi che do duplex, HOAC che do auto voi loa R1 (13/11/2026: nua cong chan 39% khung mic nha khi dien thoai noi,
    nghe «tam tit»; phien song cong cua R1 co khu vong phan mem + loc giong nguoi — song_cong.py — nen mic van mo nhu mot chiec dien thoai).
    Ep nua cong cho R1: dat echo_guard = on trong quy tac/mac dinh. Loa khac (camera Imou/Dahua): luon bo dam nua cong."""
    if domain != "r1_speaker":
        return "intercom"
    return "duplex" if mode in ("duplex", "auto") else "intercom"


def echo_guard_on(mode: str, same_device: bool, speaker_url: str = "") -> bool:
    """App co chan mic khi loa phat khong: on = luon; off va duplex = khong (duplex de loa R1 tu
    khu vong, mic van mo); auto = chi khi mic va loa cung mot thiet bi VA loa khong dung phien
    song cong cua R1 (phien song cong tu khu vong nen khong chan mic)."""
    if mode == "on":
        return True
    if mode in ("off", "duplex"):
        return False
    if "/duplex/" in (speaker_url or ""):
        return False
    return bool(same_device)


class PushPolicy:
    """Khi nao phai dua lai thiet bi mac dinh cho app: chua dua duoc lan nao / lan truoc loi,
    hoac app vua song lai sau khi mat ket noi (khoi dong lai, doi mang)."""

    def __init__(self) -> None:
        self.pushed_ok = False
        self._down = False

    def poll(self, ok: bool) -> bool:
        """Goi sau MOI lan hoi app (ok = hoi duoc). True = nen dua lai mac dinh ngay."""
        if not ok:
            self._down = True
            return False
        need = self._down or not self.pushed_ok
        self._down = False
        return need

    def pushed(self, ok: bool) -> None:
        self.pushed_ok = bool(ok)


def audio_out_url(base: str, token: str) -> str:
    return "%s/api/call/audio/out/%s" % (base.rstrip("/"), token)
