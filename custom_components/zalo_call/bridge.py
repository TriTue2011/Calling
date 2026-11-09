"""Cau noi am thanh cuoc goi giua app Zalo va thiet bi BAT KY trong HA.

Loa: app phat WAV lien tuc (GET /api/call/audio/out/<token>); ta bao
`media_player.play_media` toi loa da chon nen thiet bi nao la media_player
cung phat duoc. Mic: ffmpeg doc stream cua camera (hoac URL bat ky) ra PCM
16 kHz roi POST tung goi 100 ms vao app (/api/call/audio/in/<call_id>).

Thiet bi mac dinh o tuy chon tich hop; moi cuoc goi co the ghi de bang cac
truong cua service make_call / answer_call. Camera cho VIDEO: app CHUA co
media video, nen hien chi duoc ghi nhan vao su kien, chua truyen hinh.
Khong ghi URL mic (co the chua mat khau) vao log hay su kien.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components import camera as ha_camera
from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import ZaloCallApi, ZaloCallError
from .bridge_core import (CHUNK_BYTES, audio_out_url, ffmpeg_args,
                          mic_source_kind, pick_devices)
from .const import CONF_CAMERA, CONF_MIC, CONF_MIC_URL, CONF_SPEAKER

_LOGGER = logging.getLogger(__name__)
_PENDING_TTL = 120.0


class _Running:
    def __init__(self, devices: dict[str, str]) -> None:
        self.devices = devices
        self.task: asyncio.Task | None = None
        self.speaker_started = False


class CallAudioBridge:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 api: ZaloCallApi) -> None:
        self.hass, self.entry, self.api = hass, entry, api
        self._pending: dict[str, tuple[float, dict]] = {}
        self._running: dict[str, _Running] = {}

    def defaults(self) -> dict[str, Any]:
        o = self.entry.options
        return {"speaker": o.get(CONF_SPEAKER), "mic": o.get(CONF_MIC),
                "mic_url": o.get(CONF_MIC_URL), "camera": o.get(CONF_CAMERA)}

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

    def devices_for(self, call_id: Any) -> dict[str, str]:
        return pick_devices(self.defaults(), self._take(call_id))

    async def start(self, call_id: Any) -> dict[str, str]:
        key = str(call_id)
        if key in self._running:
            return self._running[key].devices
        devices = self.devices_for(call_id)
        run = _Running(devices)
        self._running[key] = run
        try:
            media = await self.api.call_media(call_id)
        except ZaloCallError as err:
            _LOGGER.warning("Khong lay duoc media cuoc goi %s: %s", key, err)
            return devices
        token = (media or {}).get("audio_token")
        if not token:
            _LOGGER.warning("Cuoc goi %s chua co media (chua noi may?)", key)
            return devices
        if devices["speaker"]:
            await self.hass.services.async_call(
                "media_player", "play_media",
                {"entity_id": devices["speaker"],
                 "media_content_id": audio_out_url(self.api.url, token),
                 "media_content_type": "audio/wav"}, blocking=False)
            run.speaker_started = True
        source = mic_source_kind(devices)
        if source:
            run.task = self.hass.async_create_background_task(
                self._pump_mic(call_id, source), "zalo_call mic %s" % key)
        if devices["camera"]:
            _LOGGER.info("Camera %s duoc chon cho cuoc goi %s nhung app chua "
                         "co media video", devices["camera"], key)
        return devices

    async def stop(self, call_id: Any) -> None:
        run = self._running.pop(str(call_id), None)
        if run is None:
            return
        if run.task is not None:
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        if run.speaker_started and run.devices["speaker"]:
            try:
                await self.hass.services.async_call(
                    "media_player", "media_stop",
                    {"entity_id": run.devices["speaker"]}, blocking=False)
            except HomeAssistantError as err:
                _LOGGER.debug("Khong dung duoc loa: %s", err)

    async def async_shutdown(self) -> None:
        for key in list(self._running):
            await self.stop(key)

    async def _pump_mic(self, call_id: Any, source: tuple[str, str]) -> None:
        kind, ref = source
        try:
            url = ref if kind == "url" else \
                await ha_camera.async_get_stream_source(self.hass, ref)
            if not url:
                _LOGGER.warning("Camera %s khong co stream de lay mic", ref)
                return
            args = ffmpeg_args(url)
        except (ValueError, HomeAssistantError) as err:
            _LOGGER.warning("Nguon mic khong dung duoc: %s", err)
            return
        proc = await asyncio.create_subprocess_exec(
            get_ffmpeg_manager(self.hass).binary, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            while True:
                chunk = await proc.stdout.readexactly(CHUNK_BYTES)
                try:
                    await self.api.audio_in(call_id, chunk)
                except ZaloCallError as err:
                    # 409 = app chua gan xong media: bo goi, thu lai goi sau.
                    if err.status != 409:
                        _LOGGER.warning("Gui mic loi: %s", err)
                        await asyncio.sleep(1)
        except asyncio.IncompleteReadError:
            _LOGGER.info("ffmpeg dung (nguon mic het hoac loi)")
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
