"""Cầu nối thiết bị cuộc gọi giữa app Zalo và Home Assistant.

- Loa: app phát WAV liên tục (GET /api/call/audio/out/<token>); ta bảo
  `media_player.play_media` tới loa đã chọn nên thiết bị nào là media_player
  cũng phát được.
- Mic / camera: HA PHÂN GIẢI thực thể (camera, vệ tinh Assist của camera Imou
  hay loa R1, hoặc URL) ra URL luồng rồi đưa cho app; app tự dùng ffmpeg đọc và
  phát lên cuộc gọi (không bơm tiếng qua HA nữa). URL gửi kèm lời gọi
  (make_call / answer_call) hoặc đẩy làm mặc định cho app.
- Mặc định nằm ở các thực thể select/text/switch của tích hợp
  (`devices.DeviceDefaults`); mỗi cuộc gọi ghi đè bằng trường của service.
Không ghi URL mic/camera (có thể chứa mật khẩu) vào log hay sự kiện.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components import camera as ha_camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import ZaloCallApi, ZaloCallError
from .bridge_core import (audio_out_url, dahua_mic_url, entity_of_label,
                          explicit_off, mic_format_for_url, pick_devices,
                          r1_mic_url, valid_url)
from .const import CONF_HA_URL
from .devices import DeviceDefaults

_LOGGER = logging.getLogger(__name__)
_PENDING_TTL = 120.0


class _Running:
    def __init__(self, devices: dict[str, str]) -> None:
        self.devices = devices
        self.speaker_started = False


class CallAudioBridge:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 api: ZaloCallApi, defaults: DeviceDefaults) -> None:
        self.hass, self.entry, self.api, self.defaults = hass, entry, api, defaults
        self._pending: dict[str, tuple[float, dict]] = {}
        self._running: dict[str, _Running] = {}

    # -- thiet bi cua mot cuoc goi -----------------------------------------
    def remember(self, call_id: Any, override: dict[str, Any]) -> None:
        """Thiet bi ghi de cho cuoc goi sap noi may. call_id None = cuoc goi
        ke tiep (chua biet ma luc goi service)."""
        self._pending[str(call_id) if call_id is not None else "*"] = (
            time.monotonic(), dict(override))

    def _take(self, call_id: Any) -> dict[str, Any] | None:
        now = time.monotonic()
        self._pending = {k: v for k, v in self._pending.items()
                         if now - v[0] < _PENDING_TTL}
        item = self._pending.pop(str(call_id), None) \
            or self._pending.pop("*", None)
        return item[1] if item else None

    def devices_for(self, override: dict[str, Any] | None = None) -> dict[str, str]:
        return pick_devices(self.defaults.data, override)

    # -- phan giai thuc the -> URL luong -----------------------------------
    def _ha_base(self) -> str:
        base = self.entry.options.get(CONF_HA_URL)
        if base:
            return str(base)
        try:
            return get_url(self.hass, allow_external=False, allow_cloud=False)
        except NoURLAvailableError:
            return ""

    async def async_camera_url(self, entity_id: str) -> str:
        """Stream cua mot camera HA (RTSP/go2rtc...), rong neu khong co."""
        try:
            return await ha_camera.async_get_stream_source(self.hass, entity_id) or ""
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Camera %s khong co stream: %s", entity_id, err)
            return ""

    async def async_mic_source(self, devices: dict[str, str]) -> tuple[str, str]:
        """(url, dinh_dang) cua mic: mic_url thang thuc the `mic`."""
        if devices.get("mic_url"):
            url = devices["mic_url"]
            return (url, mic_format_for_url(url)) if valid_url(url) else ("", "auto")
        entity_id = entity_of_label(devices.get("mic", ""))
        if not entity_id:
            return "", "auto"
        domain = entity_id.split(".", 1)[0]
        if domain == "camera":
            url = await self.async_camera_url(entity_id)
            return (url, "auto") if valid_url(url) else ("", "auto")
        if domain == "assist_satellite":
            url = await self._satellite_mic_url(entity_id)
            return (url, mic_format_for_url(url)) if valid_url(url) else ("", "auto")
        _LOGGER.warning("Khong lay duoc mic tu %s (chi ho tro camera, "
                        "assist_satellite hoac URL)", entity_id)
        return "", "auto"

    async def _satellite_mic_url(self, entity_id: str) -> str:
        """Mic cua mot vệ tinh Assist: loa R1 (luong PCM cua r1_speaker) hoac camera
        Imou/Dahua (mic_url cua dahua_talk); dung dang ky thuc the de biet cua ai."""
        ent = er.async_get(self.hass).async_get(entity_id)
        cfg = self.hass.config_entries.async_get_entry(ent.config_entry_id) \
            if ent and ent.config_entry_id else None
        if cfg is None:
            return ""
        if cfg.domain == "dahua_talk":
            return dahua_mic_url(cfg.options, cfg.data)
        if cfg.domain == "r1_speaker":
            key = str(cfg.data.get("intercom_key") or "")
            base = self._ha_base()
            if not key or not base:
                _LOGGER.warning("Loa R1 %s chua co khoa mic hoac HA chua co dia chi noi bo",
                                entity_id)
                return ""
            return r1_mic_url(base, cfg.entry_id, key)
        return ""

    async def async_resolve(self, devices: dict[str, str]) -> dict[str, str]:
        """Thiet bi -> truong gui cho app: mic_url, mic_format, camera_url (rong = khong dung)."""
        mic_url, mic_fmt = await self.async_mic_source(devices)
        cam_id = entity_of_label(devices.get("camera", ""))
        cam_url = await self.async_camera_url(cam_id) if cam_id else ""
        return {"mic_url": mic_url, "mic_format": mic_fmt, "camera_url": cam_url}

    # -- app -----------------------------------------------------------------
    async def async_call_fields(self, override: dict[str, Any] | None) -> dict[str, str]:
        """Truong thiet bi dinh kem make_call/answer_call (mic_url, mic_format, camera_url).

        Khong ghi de: dung ban phan giai cua mac dinh. Ghi de co gia tri: dung gia
        tri do. Ghi de RONG cho nhom do (mic / camera) va khong con nguon nao: gui
        "off" de app TAT thiet bi do cho rieng cuoc goi nay."""
        devices = self.devices_for(override)
        res = await self.async_resolve(devices)
        out: dict[str, str] = {}
        for field, keys in (("mic_url", ("mic", "mic_url")), ("camera_url", ("camera",))):
            if res[field]:
                out[field] = res[field]
            elif explicit_off(override, keys, devices):
                out[field] = "off"
        if out.get("mic_url", "off") != "off":
            out["mic_format"] = res["mic_format"]
        return out

    async def async_push_defaults(self) -> None:
        """Dua mac dinh da phan giai cho app (WebUI hien thong nhat; cuoc goi nghe may
        ngoai HA, hoac ben kia xin len video, cung dung dung nguon)."""
        res = await self.async_resolve(self.devices_for())
        try:
            await self.api.devices_set({
                "mic_url": res["mic_url"], "mic_format": res["mic_format"],
                "camera_url": res["camera_url"],
                "auto_mic": bool(self.defaults.get("auto_mic")),
                "auto_video_on_request": bool(self.defaults.get("auto_video")),
                "auto_video_delay": int(self.defaults.get("auto_video_delay") or 0)})
        except ZaloCallError as err:
            _LOGGER.warning("Khong dua duoc thiet bi mac dinh cho app: %s", err)

    # -- loa -----------------------------------------------------------------
    async def start(self, call_id: Any) -> dict[str, str]:
        key = str(call_id)
        if key in self._running:
            return self._running[key].devices
        devices = self.devices_for(self._take(call_id))
        run = _Running(devices)
        self._running[key] = run
        speaker = entity_of_label(devices["speaker"])
        if not speaker:
            return devices
        try:
            media = await self.api.call_media_status(call_id)
        except ZaloCallError as err:
            _LOGGER.warning("Khong lay duoc media cuoc goi %s: %s", key, err)
            return devices
        token = (media or {}).get("audio_token")
        if not token:
            _LOGGER.warning("Cuoc goi %s chua co media (chua noi may?)", key)
            return devices
        await self.hass.services.async_call(
            "media_player", "play_media",
            {"entity_id": speaker,
             "media_content_id": audio_out_url(self.api.url, token),
             "media_content_type": "audio/wav"}, blocking=False)
        run.speaker_started = True
        return devices

    async def stop(self, call_id: Any) -> None:
        run = self._running.pop(str(call_id), None)
        if run is None or not run.speaker_started:
            return
        try:
            await self.hass.services.async_call(
                "media_player", "media_stop",
                {"entity_id": entity_of_label(run.devices["speaker"])},
                blocking=False)
        except HomeAssistantError as err:
            _LOGGER.debug("Khong dung duoc loa: %s", err)

    async def async_shutdown(self) -> None:
        for key in list(self._running):
            await self.stop(key)
