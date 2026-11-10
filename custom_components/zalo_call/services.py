"""Đăng ký 96 service Zalo + ~260 API zca-js + make_call / end_call.

Danh mục nằm trong catalog.json, SINH từ chính app
(`zalo/zalo-pc-app/tools/gen_ha_catalog.py`) nên không bao giờ lệch với app.
Bốn nhóm cách gọi: svc (POST /api/svc/<action>), chat (khung chat),
view (danh bạ), acct (webhook/tài khoản do tích hợp tự trả lời).
"""
from __future__ import annotations

import json
import mimetypes
import os
from typing import Any, Callable

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZaloCallApi, ZaloCallError
from .bridge_core import entity_of_label
from .const import DOMAIN, ECHO_MODES

MAX_FILE = 100 * 1024 * 1024
_ANY = cv.match_all


def _load_catalog() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "catalog.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _api(hass: HomeAssistant, call: ServiceCall) -> tuple[Any, ZaloCallApi]:
    runtimes = hass.data.get(DOMAIN, {})
    wanted = call.data.get("entry_id")
    for eid, rt in runtimes.items():
        if hasattr(rt, "api") and (wanted is None or wanted == eid):
            return rt, rt.api
    raise ServiceValidationError("Chưa có tích hợp Zalo Call nào đang chạy")


async def _read_source(hass: HomeAssistant, src: str) -> tuple[str, bytes, str]:
    """Đọc tệp từ đường dẫn HA (phải nằm trong thư mục được phép) hoặc URL."""
    src = str(src).strip()
    if src.startswith(("http://", "https://")):
        session = async_get_clientsession(hass)
        try:
            async with session.get(src) as r:
                if r.status != 200:
                    raise ServiceValidationError("Tải %s lỗi HTTP %s" % (src, r.status))
                data = await r.content.read(MAX_FILE + 1)
        except OSError as err:
            raise ServiceValidationError("Không tải được %s: %s" % (src, err)) from err
        name = os.path.basename(src.split("?", 1)[0]) or "file"
    else:
        if not hass.config.is_allowed_path(src):
            raise ServiceValidationError(
                "Đường dẫn %s không nằm trong thư mục được phép "
                "(allowlist_external_dirs)" % src)

        def _read() -> bytes:
            with open(src, "rb") as f:
                return f.read(MAX_FILE + 1)
        try:
            data = await hass.async_add_executor_job(_read)
        except OSError as err:
            raise ServiceValidationError("Không đọc được %s: %s" % (src, err)) from err
        name = os.path.basename(src)
    if len(data) > MAX_FILE:
        raise ServiceValidationError("Tệp lớn hơn 100 MB")
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return name, data, mime


def _split(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in str(value or "").split(",") if p.strip()]


async def _do_chat(hass: HomeAssistant, api: ZaloCallApi, e: dict, d: dict) -> Any:
    name = e["name"]
    tid = str(d["thread_id"])
    ttype = d.get("type") or "user"
    if name.endswith("_to_user"):
        ttype = "user"
    elif name.endswith("_to_group"):
        ttype = "group"
    if name == "send_message":
        return await api.thread_send(ttype, tid, str(d["message"]))
    if name == "send_link":
        return await api.thread_sendlink(ttype, tid, str(d["link"]),
                                         str(d.get("message") or ""))
    if name == "send_voice":
        fn, data, mime = await _read_source(hass, d["file"])
        return await api.thread_sendvoice(ttype, tid, fn, data, mime)
    if name == "send_card":
        raise ServiceValidationError(
            "send_card chưa hỗ trợ: app Zalo PC chưa có đường gửi danh thiếp")
    if name in ("send_images_to_user", "send_images_to_group"):
        results = []
        for src in _split(d["files"]):
            fn, data, mime = await _read_source(hass, src)
            results.append(await api.thread_sendfile(ttype, tid, fn, data, mime,
                                                     "photo"))
        return {"sent": len(results)}
    # send_file / send_image / send_image_to_* / send_video
    kind = "photo" if "image" in name else "file"
    fn, data, mime = await _read_source(hass, d["file"])
    return await api.thread_sendfile(ttype, tid, fn, data, mime, kind)


async def _do_acct(hass, rt, api: ZaloCallApi, e: dict, d: dict) -> Any:
    name = e["name"]
    status = rt.coordinator.data["status"] if rt.coordinator.data else await api.status()
    if name in ("get_logged_accounts", "get_account_details"):
        acct = {"uid": status.get("uid"), "phone": status.get("phonenum"),
                "logged_in": bool(status.get("login"))}
        return [acct] if name == "get_logged_accounts" else acct
    if name in ("get_account_webhooks", "get_account_webhook"):
        return await api.get_webhooks()
    if name == "set_account_webhook":
        cfg = dict(await api.get_webhooks())
        for k in ("message_webhook_url", "group_event_webhook_url",
                  "reaction_webhook_url", "call_webhook_url"):
            if k in d:
                cfg[k] = str(d[k] or "")
        return await api.set_webhooks(cfg)
    if name == "delete_account_webhook":
        cfg = dict(await api.get_webhooks())
        for k in list(cfg):
            if k.endswith("_webhook_url"):
                cfg[k] = ""
        return await api.set_webhooks(cfg)
    if name == "get_login_qr":
        return await api.qr_new()
    raise ServiceValidationError(
        "%s không áp dụng: app Zalo PC dùng một tài khoản và không có proxy" % name)


def _make_handler(hass: HomeAssistant, e: dict) -> Callable:
    async def handler(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        d = {k: v for k, v in call.data.items() if k != "entry_id"}
        try:
            if e["kind"] in ("svc", "zca"):     # zca: app tu chuyen sang bo goi chung
                res = await api.svc(e["action"], d)
            elif e["kind"] == "chat":
                res = await _do_chat(hass, api, e, d)
            elif e["kind"] == "view":
                contacts = await api.contacts()
                res = contacts.get("friends" if e["name"] == "get_all_friends"
                                   else "groups", contacts)
            else:
                res = await _do_acct(hass, rt, api, e, d)
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}
    return handler


def _schema(e: dict) -> vol.Schema:
    fields: dict = {vol.Optional("entry_id"): cv.string}
    if e["thread"] != "none" and e["kind"] in ("svc", "chat"):
        fields[vol.Required("thread_id")] = cv.string
        fields[vol.Optional("type", default="user")] = vol.In(["user", "group"])
    for f in e["fields"]:
        key = vol.Required(f["key"]) if f["required"] else vol.Optional(f["key"])
        fields[key] = _ANY
    return vol.Schema(fields, extra=vol.ALLOW_EXTRA)


async def async_register_services(hass: HomeAssistant) -> None:
    catalog = await hass.async_add_executor_job(_load_catalog)
    for e in catalog:
        hass.services.async_register(
            DOMAIN, e["name"], _make_handler(hass, e), schema=_schema(e),
            supports_response=SupportsResponse.OPTIONAL)

    def _device_override(call: ServiceCall) -> dict:
        """Thiet bi ghi de cua service nay (vang = dung mac dinh; "" = tat)."""
        return {k: call.data[k] for k in ("speaker", "mic", "mic_url", "camera")
                if k in call.data}

    async def make_call(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        override = _device_override(call)
        rt.bridge.remember(None, override)
        try:
            fields = await rt.bridge.async_call_fields(override)
            res = await api.call_request(str(call.data["thread_id"]),
                                         call.data.get("type", "user"),
                                         call.data.get("peer_name", ""),
                                         call.data.get("srtp"),
                                         call.data.get("extend_profile"),
                                         fields)
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def answer_call(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        override = _device_override(call)
        rt.bridge.remember(call.data.get("call_id"), override)
        try:
            fields = await rt.bridge.async_call_fields(override)
            res = await api.call_answer(call.data.get("call_id"), fields)
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def reject_call(call: ServiceCall) -> dict:
        _, api = _api(hass, call)
        try:
            res = await api.call_reject(call.data.get("call_id"))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def voice_to_text(call: ServiceCall) -> dict:
        _, api = _api(hass, call)
        try:
            res = await api.voice_to_text(str(call.data["url"]),
                                          float(call.data.get("wait", 25)))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        if res.get("done") and res.get("error"):
            raise HomeAssistantError("Zalo AI không chuyển được giọng nói (mã %s)"
                                     % res["error"])
        return {"req_id": res.get("req_id"), "done": bool(res.get("done")),
                "text": res.get("text", "")}

    async def end_call(call: ServiceCall) -> dict:
        _, api = _api(hass, call)
        try:
            res = await api.call_end(call.data.get("call_id"))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def _camera_url(rt, call: ServiceCall) -> str:
        """URL camera cua service: camera_url thang camera (thuc the) thang mac dinh."""
        if call.data.get("camera_url"):
            return str(call.data["camera_url"]).strip()
        devices = rt.bridge.devices_for(
            {"camera": call.data["camera"]} if "camera" in call.data else None)
        cam = entity_of_label(devices.get("camera", ""))
        return await rt.bridge.async_camera_url(cam) if cam else ""

    def _call_body(call: ServiceCall, **extra: Any) -> dict:
        body = dict(extra)
        if call.data.get("call_id") not in (None, ""):
            body["call_id"] = call.data["call_id"]
        return body

    async def upgrade_to_video(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        url = await _camera_url(rt, call)
        try:
            res = await api.upgrade_video(_call_body(call, **({"camera_url": url} if url else {})))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def start_call_video(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        url = await _camera_url(rt, call)
        try:
            res = await api.media_control(_call_body(
                call, action="start", target="video",
                **({"camera_url": url} if url else {})))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def stop_call_video(call: ServiceCall) -> dict:
        _, api = _api(hass, call)
        try:
            res = await api.media_control(_call_body(call, action="stop", target="video"))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def start_call_mic(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        override = {k: call.data[k] for k in ("mic", "mic_url") if k in call.data}
        url, fmt = await rt.bridge.async_mic_source(rt.bridge.devices_for(override))
        if not url:
            raise ServiceValidationError(
                "Chưa có nguồn mic: chọn Mic mặc định hoặc truyền mic/mic_url hợp lệ")
        try:
            res = await api.media_control(_call_body(
                call, action="start", target="mic", mic_url=url, mic_format=fmt))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def stop_call_mic(call: ServiceCall) -> dict:
        _, api = _api(hass, call)
        try:
            res = await api.media_control(_call_body(call, action="stop", target="mic"))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"result": res}

    async def set_default_devices(call: ServiceCall) -> None:
        rt, _ = _api(hass, call)
        patch = {k: call.data[k] for k in
                 ("speaker", "mic", "mic_url", "camera", "auto_mic", "auto_video",
                  "auto_video_delay", "echo_guard")
                 if k in call.data}
        if patch.get("mic_url") or patch.get("mic"):
            patch.setdefault("mic_url" if patch.get("mic") else "mic", "")
        await rt.defaults.async_set(**patch)
        await rt.bridge.async_push_defaults()

    call_id_only = {vol.Optional("entry_id"): cv.string,
                    vol.Optional("call_id"): vol.Any(int, cv.string)}
    for name, fn, extra in (
            ("upgrade_to_video", upgrade_to_video,
             {vol.Optional("camera"): cv.string, vol.Optional("camera_url"): cv.string}),
            ("start_call_video", start_call_video,
             {vol.Optional("camera"): cv.string, vol.Optional("camera_url"): cv.string}),
            ("stop_call_video", stop_call_video, {}),
            ("start_call_mic", start_call_mic,
             {vol.Optional("mic"): cv.string, vol.Optional("mic_url"): cv.string}),
            ("stop_call_mic", stop_call_mic, {})):
        hass.services.async_register(
            DOMAIN, name, fn, schema=vol.Schema({**call_id_only, **extra}),
            supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "set_default_devices", set_default_devices,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string,
                           vol.Optional("speaker"): cv.string,
                           vol.Optional("mic"): cv.string,
                           vol.Optional("mic_url"): cv.string,
                           vol.Optional("camera"): cv.string,
                           vol.Optional("auto_mic"): cv.boolean,
                           vol.Optional("auto_video"): cv.boolean,
                           vol.Optional("echo_guard"): vol.In(list(ECHO_MODES)),
                           vol.Optional("auto_video_delay"):
                               vol.All(vol.Coerce(int), vol.Range(min=0, max=120))}))

    devices = {vol.Optional("speaker"): cv.string,
               vol.Optional("mic"): cv.string,
               vol.Optional("mic_url"): cv.string,
               vol.Optional("camera"): cv.string}
    hass.services.async_register(
        DOMAIN, "make_call", make_call,
        schema=vol.Schema({
            vol.Optional("entry_id"): cv.string,
            vol.Required("thread_id"): cv.string,
            vol.Optional("type", default="user"): vol.In(["user", "video", "group"]),
            vol.Optional("peer_name"): cv.string,
            vol.Optional("srtp"): vol.In(["sess", "off", "key"]),
            vol.Optional("extend_profile"): vol.In(["native", "pc", "zca"]),
            **devices}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "answer_call", answer_call,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string,
                           vol.Optional("call_id"): vol.Any(int, cv.string),
                           **devices}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "reject_call", reject_call,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string,
                           vol.Optional("call_id"): vol.Any(int, cv.string)}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "voice_to_text", voice_to_text,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string,
                           vol.Required("url"): cv.string,
                           vol.Optional("wait", default=25):
                               vol.All(vol.Coerce(float), vol.Range(min=0, max=60))}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(
        DOMAIN, "end_call", end_call,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string,
                           vol.Optional("call_id"): vol.Any(int, cv.string)}),
        supports_response=SupportsResponse.OPTIONAL)
