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
from .bridge_core import (PushPolicy, audio_out_url, dahua_mic_url, device_of_url, echo_guard_on,
                          entity_of_label, explicit_off, host_of, intercom_url,
                          localize_url, mic_format_for_url, pick_devices, r1_mic_url,
                          valid_url)
from .const import CONF_CALL_VOLUME, CONF_HA_URL, MAX_CALL_VOLUME, TEST_SOURCE
from .devices import DeviceDefaults

_LOGGER = logging.getLogger(__name__)
_PENDING_TTL = 120.0
_PUSH_THIEU_TOI_DA = 30   # so lan thu lai (moi ~10 s, ~5 phut) khi thiet bi da chon chua phan giai duoc
# Loa lam tron am luong theo nac cua no (R1 co 15 nac: dat 0,77 thi bao 0,80): lech it hon mot nac
# thi coi la «chua ai chinh» va van tra lai muc cu. Do 10/11/2026: dung nguong 0,02 thi R1 khong duoc tra.
_VOLUME_TOLERANCE = 0.07


class _Running:
    def __init__(self, devices: dict[str, str]) -> None:
        self.devices = devices
        self.speaker_started = False
        self.volume_restore: tuple[str, float, float] | None = None   # (loa, muc cu, muc da dat)


class CallAudioBridge:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 api: ZaloCallApi, defaults: DeviceDefaults) -> None:
        self.hass, self.entry, self.api, self.defaults = hass, entry, api, defaults
        self._pending: dict[str, tuple[float, dict]] = {}
        self._running: dict[str, _Running] = {}
        self.policy = PushPolicy()
        self._pushing = False
        self._push_thieu_lan = 0

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
        base = self.defaults.get(CONF_HA_URL)
        if base:
            return str(base)
        try:
            return get_url(self.hass, allow_external=False, allow_cloud=False)
        except NoURLAvailableError:
            return ""

    async def async_camera_url(self, entity_id: str) -> str:
        """Stream cua mot camera HA (RTSP/go2rtc...), rong neu khong co."""
        try:
            url = await ha_camera.async_get_stream_source(self.hass, entity_id) or ""
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Camera %s khong co stream: %s", entity_id, err)
            return ""
        # localhost cua HA khong dung duoc tu app: doi sang dia chi LAN cua may HA.
        return localize_url(url, host_of(self._ha_base()))

    async def async_mic_source(self, devices: dict[str, str]) -> tuple[str, str]:
        """(url, dinh_dang) cua mic: mic_url thang thuc the `mic`."""
        if devices.get("mic_url"):
            url = localize_url(devices["mic_url"], host_of(self._ha_base()))
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

    async def async_speaker_sink(self, entity_id: str, mode: str = "auto") -> str:
        """URL de app phat tieng thang vao loa (R1, camera Imou/Dahua), hoac "" (loa khac: dung
        media_player.play_media). Mac dinh la «cua bo dam»; che do duplex + loa R1 -> phien song
        cong cua R1. Khoa lay tu chinh tich hop cua loa."""
        if not entity_id:
            return ""
        ent = er.async_get(self.hass).async_get(entity_id)
        cfg = self.hass.config_entries.async_get_entry(ent.config_entry_id) \
            if ent and ent.config_entry_id else None
        if cfg is None or cfg.domain not in ("r1_speaker", "dahua_talk"):
            return ""
        key = str(cfg.data.get("intercom_key") or "")
        base = self._ha_base()
        if not key or not base:
            _LOGGER.warning("Loa %s chua co khoa bo dam hoac HA chua co dia chi noi bo", entity_id)
            return ""
        kind = "duplex" if (mode == "duplex" and cfg.domain == "r1_speaker") else "intercom"
        return intercom_url(base, cfg.domain, cfg.entry_id, key, kind)

    def _same_device(self, speaker_id: str, mic_id: str, mic_url: str, sink_url: str) -> bool:
        """Mic va loa co cung MOT thiet bi khong (de bat chong vong khi o che do tu dong)."""
        a, b = device_of_url(sink_url), device_of_url(mic_url)
        if a and b:
            return a == b
        if speaker_id and mic_id:
            reg = er.async_get(self.hass)
            s, m = reg.async_get(speaker_id), reg.async_get(mic_id)
            if s and m and s.config_entry_id and s.config_entry_id == m.config_entry_id:
                return True
            return bool(s and m and s.device_id and s.device_id == m.device_id)
        return False

    async def async_resolve(self, devices: dict[str, str],
                            echo_mode: str = "auto") -> dict[str, str]:
        """Thiet bi -> truong gui cho app: mic_url, mic_format, camera_url, speaker_url,
        echo_guard ("true"/"false") (rong = khong dung)."""
        mic_url, mic_fmt = await self.async_mic_source(devices)
        cam_id = entity_of_label(devices.get("camera", ""))
        if cam_id == TEST_SOURCE:
            cam_url = TEST_SOURCE                      # hình kiểm tra: app tự tạo, không cần camera nào
        else:
            cam_url = await self.async_camera_url(cam_id) if cam_id else ""
        spk_id = entity_of_label(devices.get("speaker", ""))
        spk_url = await self.async_speaker_sink(spk_id, echo_mode)
        mic_id = entity_of_label(devices.get("mic", ""))
        echo = echo_guard_on(echo_mode, self._same_device(spk_id, mic_id, mic_url, spk_url)) \
            if spk_url else False
        return {"mic_url": mic_url, "mic_format": mic_fmt, "camera_url": cam_url,
                "speaker_url": spk_url, "echo_guard": "true" if echo else "false"}

    # -- app -----------------------------------------------------------------
    async def async_call_fields(self, override: dict[str, Any] | None) -> dict[str, str]:
        """Truong thiet bi dinh kem make_call/answer_call (mic_url, mic_format, camera_url).

        Khong ghi de: dung ban phan giai cua mac dinh. Ghi de co gia tri: dung gia
        tri do. Ghi de RONG cho nhom do (mic / camera) va khong con nguon nao: gui
        "off" de app TAT thiet bi do cho rieng cuoc goi nay."""
        devices = self.devices_for(override)
        res = await self.async_resolve(devices, str(self.defaults.get("echo_guard") or "auto"))
        out: dict[str, str] = {}
        for field, keys in (("mic_url", ("mic", "mic_url")), ("camera_url", ("camera",)),
                            ("speaker_url", ("speaker",))):
            if res[field]:
                out[field] = res[field]
            elif explicit_off(override, keys, devices):
                out[field] = "off"
        if out.get("mic_url", "off") != "off":
            out["mic_format"] = res["mic_format"]
        if out.get("speaker_url", "off") != "off":
            out["echo_guard"] = res["echo_guard"]
        return out

    async def async_push_defaults(self) -> None:
        """Dua mac dinh da phan giai cho app (WebUI hien thong nhat; cuoc goi nghe may
        ngoai HA, hoac ben kia xin len video, cung dung dung nguon). Loi thi KHONG bo: coordinator
        goi lai o lan hoi app thanh cong ke tiep (PushPolicy)."""
        if self._pushing:
            return
        self._pushing = True
        try:
            await self._async_push()
        finally:
            self._pushing = False

    async def _async_push(self) -> None:
        devices = self.devices_for()
        res = await self.async_resolve(devices, str(self.defaults.get("echo_guard") or "auto"))
        payload = {
            "mic_url": res["mic_url"], "mic_format": res["mic_format"],
            "camera_url": res["camera_url"], "speaker_url": res["speaker_url"],
            "echo_guard": res["echo_guard"] == "true",
            "auto_mic": bool(self.defaults.get("auto_mic")),
            "auto_video_on_request": bool(self.defaults.get("auto_video")),
            "auto_video_delay": int(self.defaults.get("auto_video_delay") or 0)}
        # Thiet bi DA CHON nhung chua phan giai duoc (camera chua nap xong luc HA khoi dong: «Camera not found»):
        # KHONG gui rong de ghi de gia tri dang dung cua app (do 10/11/2026: HA khoi dong lai lam camera mac dinh cua
        # app ve trong). Bo truong do khoi goi (app giu gia tri cu) va danh dau chua xong de coordinator tu thu lai.
        # Chi gui rong khi nguoi dung THAT SU bo chon (khong chon thiet bi nao).
        cam_id = entity_of_label(devices.get("camera", ""))
        mic_id = entity_of_label(devices.get("mic", ""))
        thieu: list[str] = []
        if cam_id and cam_id != TEST_SOURCE and not res["camera_url"]:
            payload.pop("camera_url")
            thieu.append("camera")
        if not devices.get("mic_url") and mic_id.startswith("camera.") and not res["mic_url"]:
            payload.pop("mic_url")
            payload.pop("mic_format")
            thieu.append("mic")
        try:
            await self.api.devices_set(payload)
        except ZaloCallError as err:
            self.policy.pushed(False)
            _LOGGER.warning("Khong dua duoc thiet bi mac dinh cho app (se thu lai): %s", err)
            return
        if not thieu:
            self._push_thieu_lan = 0
            self.policy.pushed(True)
            return
        self._push_thieu_lan += 1
        if self._push_thieu_lan >= _PUSH_THIEU_TOI_DA:
            # Camera bi xoa han / khong bao gio co stream: thoi thu lai, nhung noi ro de nguoi dung sua.
            _LOGGER.warning("Khong phan giai duoc %s da chon sau %d lan thu; giu gia tri cu cua app. Chon lai thiet bi "
                            "hoac kiem tra thuc the.", ", ".join(thieu), self._push_thieu_lan)
            self.policy.pushed(True)
        else:
            self.policy.pushed(False)

    # -- loa -----------------------------------------------------------------
    async def start(self, call_id: Any) -> dict[str, str]:
        key = str(call_id)
        if key in self._running:
            return self._running[key].devices
        override = self._take(call_id)
        devices = self.devices_for(override)
        run = _Running(devices)
        self._running[key] = run
        speaker = entity_of_label(devices["speaker"])
        if not speaker:
            return devices
        await self._async_set_volume(run, speaker, self.volume_for(override))
        if await self.async_speaker_sink(speaker, str(self.defaults.get("echo_guard") or "auto")):
            return devices          # loa truc tiep: app tu day tieng vao bo dam, khong qua play_media
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
        if run is None:
            return
        if run.speaker_started:
            try:
                await self.hass.services.async_call(
                    "media_player", "media_stop",
                    {"entity_id": entity_of_label(run.devices["speaker"])},
                    blocking=False)
            except HomeAssistantError as err:
                _LOGGER.debug("Khong dung duoc loa: %s", err)
        await self._async_restore_volume(run)

    def volume_for(self, override: dict[str, Any] | None) -> int:
        """% am luong loa cho cuoc goi: ghi de cua service > mac dinh; 0 = khong dong vao."""
        raw = (override or {}).get("volume")
        if raw is None:
            raw = self.defaults.get(CONF_CALL_VOLUME)
        try:
            return max(0, min(MAX_CALL_VOLUME, int(raw)))
        except (TypeError, ValueError):
            return 0

    async def _async_set_volume(self, run: _Running, speaker: str, percent: int) -> None:
        """Dat am luong loa luc nghe may, nho muc cu de tra lai khi cuoc goi ket thuc."""
        if percent <= 0:
            return
        state = self.hass.states.get(speaker)
        try:
            old = float(state.attributes.get("volume_level")) if state else None
        except (TypeError, ValueError):
            old = None
        target = round(percent / 100, 2)
        try:
            await self.hass.services.async_call(
                "media_player", "volume_set",
                {"entity_id": speaker, "volume_level": target}, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.warning("Khong dat duoc am luong %s%% cho loa %s: %s", percent, speaker, err)
            return
        if old is not None:
            run.volume_restore = (speaker, old, target)

    async def _async_restore_volume(self, run: _Running) -> None:
        """Tra am luong cu cua loa, tru khi nguoi dung da tu chinh trong luc goi."""
        restore, run.volume_restore = run.volume_restore, None
        if restore is None:
            return
        speaker, old, target = restore
        state = self.hass.states.get(speaker)
        try:
            now = float(state.attributes.get("volume_level")) if state else None
        except (TypeError, ValueError):
            now = None
        if now is not None and abs(now - target) > _VOLUME_TOLERANCE:
            return
        try:
            await self.hass.services.async_call(
                "media_player", "volume_set",
                {"entity_id": speaker, "volume_level": old}, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.debug("Khong tra duoc am luong loa %s: %s", speaker, err)

    async def async_shutdown(self) -> None:
        for key in list(self._running):
            await self.stop(key)
