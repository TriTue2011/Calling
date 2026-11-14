"""Đăng ký 96 service Zalo + ~260 API zca-js + make_call / end_call.

Danh mục nằm trong catalog.json, SINH từ chính app
(`zalo/zalo-pc-app/tools/gen_ha_catalog.py`) nên không bao giờ lệch với app.
Bốn nhóm cách gọi: svc (POST /api/svc/<action>), chat (khung chat),
view (danh bạ), acct (webhook/tài khoản do tích hợp tự trả lời).
"""
from __future__ import annotations

import json
import logging
import mimetypes
import random
import os
import time
from typing import Any, Callable

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZaloCallApi, ZaloCallError
from .bridge_core import entity_of_label
from .call_voice import DEFAULT_GREETING, HELD_DEVICES, Plan, async_accept_video, explicit_devices, async_say, async_take_over, devices_for_mode, plan_from_service
from .rules import MAX_NOTE_LEN, parse_tags, CALL_TYPES, CONNECT, CONNECT_PARTS, MAX_ANNOUNCE_REPEAT, VIDEO_REQUEST, ECHO as RULE_ECHO, parse_connect, RULES_KEY, RuleError, SCOPES, get_rules, normalize as normalize_rule, resolve as resolve_rule, validate_scope
from .const import CONF_TEXT_AI_SMART, CONF_TEXT_AUTO_EMOJI, DOMAIN, ECHO_MODES, TEXT_STYLE_KEYS
from .styler import async_markup_for
from .video_urls import local_to_public, sibling_thumb_candidates
from .album import album_plan, is_album_photo
from .call_voice import async_tts_audio
from .compat import rename_aliases, unknown_keys

_LOGGER = logging.getLogger(__name__)

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
    if src.startswith("media-source://"):                  # kho phương tiện của HA (kể cả giọng TTS): như zalo_bot cũ
        from homeassistant.components import media_source
        from homeassistant.components.media_player import async_process_play_media_url
        try:
            play = await media_source.async_resolve_media(hass, src, None)
        except Exception as err:  # noqa: BLE001 - mọi lỗi của nguồn phương tiện thành lỗi dễ hiểu
            raise ServiceValidationError("Không mở được %s: %s" % (src, err)) from err
        url = async_process_play_media_url(hass, play.url)
        session = async_get_clientsession(hass)
        try:
            async with session.get(url) as r:
                if r.status != 200:
                    raise ServiceValidationError("Tải %s lỗi HTTP %s" % (src, r.status))
                data = await r.content.read(MAX_FILE + 1)
        except OSError as err:
            raise ServiceValidationError("Không tải được %s: %s" % (src, err)) from err
        if len(data) > MAX_FILE:
            raise ServiceValidationError("Tệp lớn hơn 100 MB")
        name = os.path.basename(url.split("?", 1)[0]) or "media"
        return name, data, (getattr(play, "mime_type", "") or mimetypes.guess_type(name)[0] or "application/octet-stream")
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


async def _public_url(hass: HomeAssistant, src: str) -> str | None:
    """Địa chỉ công khai để Zalo tải: URL http(s) giữ nguyên; tệp trong HA (www / thư mục media) đổi thành địa chỉ ngoài của HA
    (media có chữ ký hạn 1 giờ); không đổi được (ngoài thư mục cho phép, không có tệp, HA chưa có địa chỉ ngoài) thì None."""
    src = str(src).strip()
    if src.startswith(("http://", "https://")):
        return src
    if not hass.config.is_allowed_path(src) or not await hass.async_add_executor_job(os.path.isfile, src):
        return None
    from datetime import timedelta
    from homeassistant.components.http.auth import async_sign_path
    from homeassistant.helpers.network import NoURLAvailableError, get_url
    try:
        base = get_url(hass, allow_internal=False, allow_ip=False, prefer_external=True)
    except NoURLAvailableError:
        return None
    return local_to_public(src, www_dir=hass.config.path("www"), media_dirs=hass.config.media_dirs, base_url=base,
                           sign=lambda p: async_sign_path(hass, p, timedelta(hours=1)))


async def _send_video(hass: HomeAssistant, api: ZaloCallApi, ttype: str, tid: str, d: dict) -> Any:
    """Video THẬT (khung phát được trong chat) như zalo_bot cũ; không có địa chỉ công khai thì gửi dạng tệp đính kèm như trước."""
    src = str(d["file"]).strip()
    video_url = await _public_url(hass, src)
    if not video_url:
        _LOGGER.warning("send_video: %s không có địa chỉ công khai (cần URL http(s), hoặc tệp trong www / thư mục media và HA có địa chỉ ngoài): "
                        "gửi dạng tệp đính kèm", src)
        fn, data, mime = await _read_source(hass, src)
        return await api.thread_sendfile(ttype, tid, fn, data, mime, "file", d.get("recall_after"),
                                         {"ttl": int(float(d["ttl"]))} if d.get("ttl") else None)
    thumb = str(d.get("thumbnail") or "").strip()
    if not thumb and not src.startswith(("http://", "https://")):
        for cand in sibling_thumb_candidates(src):                  # ảnh bìa cạnh video: <tên>_thumb.jpg do bản thiết kế camera tạo sẵn
            if await hass.async_add_executor_job(os.path.isfile, cand):
                thumb = cand
                break
    thumb_url = (await _public_url(hass, thumb)) if thumb else None
    return await api.thread_sendvideo(ttype, tid, video_url, thumb_url or "", str(d.get("message") or ""),
                                      d.get("width"), d.get("height"), d.get("duration"), d.get("recall_after"), d.get("ttl"))


async def _send_images(hass: HomeAssistant, api: ZaloCallApi, ttype: str, tid: str, d: dict) -> Any:
    """Nhiều ảnh MỘT LÚC thành một album (như zalo_bot cũ / zca-js): các ảnh jpg/png/webp cùng mang một groupLayoutId, idInGroup 0..N-1.
    Đọc hết ảnh trước khi gửi để một ảnh hỏng không làm album gửi dở."""
    srcs = _split(d["files"])
    if not srcs:
        raise ServiceValidationError("Chưa có ảnh nào để gửi")
    items = [await _read_source(hass, s) for s in srcs]
    plan = album_plan([(fn, mime) for fn, _data, mime in items], int(time.time() * 1000))
    ttl = {"ttl": int(float(d["ttl"]))} if d.get("ttl") else {}
    for (fn, data, mime), fields in zip(items, plan):
        await api.thread_sendfile(ttype, tid, fn, data, mime, "photo", d.get("recall_after"), {**ttl, **(fields or {})} or None)
    return {"sent": len(items), "album": sum(1 for f in plan if f)}


async def _send_quote(api: ZaloCallApi, ttype: str, tid: str, d: dict) -> Any:
    """send_message có `quote` (như zalo_bot cũ: {content, uidFrom, msgId, cliMsgId, msgType, ts}): trả lời kèm trích dẫn bằng quote_message của app.
    Kiểu chữ (đậm, màu…) không áp dụng cho tin trích dẫn."""
    q = d["quote"]
    if isinstance(q, str):
        try:
            q = json.loads(q)
        except ValueError:
            q = None
    if not isinstance(q, dict):
        raise ServiceValidationError("quote phải là đối tượng {content, uidFrom, msgId, cliMsgId, msgType, ts}")
    missing = [k for k in ("uidFrom", "msgId") if q.get(k) in (None, "")]
    if missing:
        raise ServiceValidationError("quote thiếu %s: cần mã người gửi (uidFrom) và mã tin (msgId) để trích dẫn" % ", ".join(missing))
    content = q.get("content")
    if isinstance(content, dict):
        content = content.get("msg") or content.get("title") or ""
    mtype = q.get("msgType")
    try:
        ts = int(float(q.get("ts") or 0))
    except (TypeError, ValueError):
        ts = 0
    body = {"thread_id": tid, "type": ttype, "text": str(d["message"]), "qmsg_owner": str(q["uidFrom"]), "msg_id": str(q["msgId"]),
            "qmsg_cli_id": str(q.get("cliMsgId") or 0), "qmsg_type": int(mtype) if str(mtype).isdigit() else 1, "qmsg_ts": ts,
            "qmsg": str(content or "")}
    if d.get("ttl"):
        body["ttl"] = int(float(d["ttl"]))
    return await api.svc("quote_message", body)


async def _do_chat(hass: HomeAssistant, api: ZaloCallApi, e: dict, d: dict) -> Any:
    name = e["name"]
    tid = str(d["thread_id"])
    ttype = d.get("type") or "user"
    if name.endswith("_to_user"):
        ttype = "user"
    elif name.endswith("_to_group"):
        ttype = "group"
    if name == "send_message":
        if d.get("quote"):
            return await _send_quote(api, ttype, tid, d)
        return await api.thread_send(ttype, tid, str(d["message"]), d.get("format"),
                                     d.get("auto_emphasis"), d.get("emoji"),
                                     d.get("auto_emoji"), d.get("zalo_emoji"), d.get("style"), d.get("ai_markup"),
                                     d.get("mentions"), d.get("recall_after"), d.get("ttl"))
    if name == "send_link":
        return await api.thread_sendlink(ttype, tid, str(d["link"]),
                                         str(d.get("message") or ""), d.get("recall_after"), str(d.get("thumbnail") or ""), d.get("ttl"))
    if name == "send_voice":
        text = str(d.get("message") or "").strip()
        if text:                                           # chữ -> giọng đọc của TTS trong HA (như zalo_bot cũ; có chữ thì chữ thắng tệp)
            try:
                ext, data = await async_tts_audio(hass, text, d.get("tts_entity"), d.get("language"), d.get("options"))
            except Exception as err:  # noqa: BLE001 - lỗi TTS (không có thực thể, quá hạn…) thành lỗi dễ hiểu
                raise ServiceValidationError("TTS không đọc được: %s" % err) from err
            fn = "tts.%s" % (ext or "mp3")
            mime = mimetypes.guess_type(fn)[0] or "audio/mpeg"
        elif d.get("file"):
            fn, data, mime = await _read_source(hass, d["file"])
        else:
            raise ServiceValidationError("send_voice cần `message` (chữ để TTS đọc) hoặc `file` (tệp, URL hoặc media-source://)")
        return await api.thread_sendvoice(ttype, tid, fn, data, mime, d.get("recall_after"))
    if name == "send_video":
        return await _send_video(hass, api, ttype, tid, d)
    if name == "send_card":
        raise ServiceValidationError(
            "send_card chưa hỗ trợ: app Zalo PC chưa có đường gửi danh thiếp")
    if name in ("send_images_to_user", "send_images_to_group"):
        return await _send_images(hass, api, ttype, tid, d)
    # send_file / send_image / send_image_to_* / send_video
    kind = "photo" if "image" in name else "file"
    fn, data, mime = await _read_source(hass, d["file"])
    fields: dict[str, Any] = {"ttl": int(float(d["ttl"]))} if d.get("ttl") else {}
    caption = str(d.get("message") or "").strip()
    if caption:
        # Chú thích (như zalo_bot cũ / zca-js): ảnh đơn mang chú thích theo ảnh (desc); tệp khác thì tin chữ đi TRƯỚC rồi mới tới tệp.
        if kind == "photo" and is_album_photo(fn, mime):
            fields["desc"] = caption
        else:
            await api.thread_send(ttype, tid, caption, recall_after=d.get("recall_after"), ttl=d.get("ttl"))
    return await api.thread_sendfile(ttype, tid, fn, data, mime, kind, d.get("recall_after"), fields or None)


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


async def _sticker_by_keyword(api: ZaloCallApi, d: dict) -> dict:
    """send_sticker: co sticker_id thi gui thang; khong thi bat buoc co keyword -> search_sticker roi chon (first | random)."""
    if d.get("sticker_id"):
        return {k: v for k, v in d.items() if k not in ("keyword", "pick")}
    kw = str(d.get("keyword") or "").strip()
    if not kw:
        raise ServiceValidationError("send_sticker cần sticker_id (kèm cate_id) hoặc keyword")
    found = await api.svc("search_sticker", {"keyword": kw, "limit": 20})
    found = [x for x in (found if isinstance(found, list) else []) if isinstance(x, dict) and x.get("sticker_id")]
    if not found:
        raise ServiceValidationError("Không tìm thấy sticker nào cho từ khoá %r" % kw)
    pick = random.choice(found) if d.get("pick") == "random" else found[0]
    out = {k: v for k, v in d.items() if k not in ("keyword", "pick")}
    out.update(sticker_id=pick["sticker_id"], cate_id=pick.get("cate_id"), sticker_type=pick.get("type"))
    return {k: v for k, v in out.items() if v is not None}


def _with_text_style(rt, d: dict) -> dict:
    """send_message: kiểu chữ = mặc định trên thiết bị, trường nào có trong lời gọi thì ghi đè mặc định. Chỉ gửi ``style`` khi có mục nào bật."""
    out = {k: v for k, v in d.items() if k not in {f for _, _, f in TEXT_STYLE_KEYS.values()}}
    style = {}
    for key, (name, options, field) in TEXT_STYLE_KEYS.items():
        val = d.get(field)
        style[name] = str(val).strip().lower() if val not in (None, "") else rt.defaults.get(key)
        if style[name] not in options:
            raise ServiceValidationError("%s phải là một trong: %s" % (field, ", ".join(options)))
    if any(style[n] != "off" for n in ("size", "color", "bold", "italic", "underline", "heading")):
        out["style"] = style
    # auto_emoji: trường của lời gọi (true/false) ghi đè công tắc «Chữ: tự thêm emoji» trên thiết bị; bỏ trống = theo công tắc.
    flag = d.get("auto_emoji")
    flag = bool(rt.defaults.get(CONF_TEXT_AUTO_EMOJI)) if flag in (None, "") else (str(flag).strip().lower() not in ("false", "0", "off", "no"))
    out.pop("auto_emoji", None)
    if flag:
        out["auto_emoji"] = True
    return out


def _make_handler(hass: HomeAssistant, e: dict) -> Callable:
    async def handler(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        d = {k: v for k, v in call.data.items() if k != "entry_id"}
        extra_keys = unknown_keys(d, {f["key"] for f in e["fields"]})
        if extra_keys:                       # trước đây bị bỏ lặng lẽ (ttl, quote, thumbnail_url của zalo_bot cũ biến mất không dấu vết)
            _LOGGER.warning("%s: bỏ qua khoá không có trong dịch vụ này: %s", e["name"], ", ".join(extra_keys))
        try:
            if e["name"] == "get_stickers" and d.get("query"):
                return {"result": await api.svc("search_sticker", {"keyword": str(d["query"]), "limit": int(d.get("limit") or 20)})}
            if e["name"] == "send_sticker":
                d = await _sticker_by_keyword(api, d)
            if e["name"] == "send_message":
                d = _with_text_style(rt, d)
                # «auto» theo ngữ cảnh: có mục auto/emoji thì nhờ trợ lý đánh dấu; app chỉ nhận khi chữ không đổi (không thì dùng quy tắc cứng).
                smart = d.pop("ai_style", None)
                smart = bool(rt.defaults.get(CONF_TEXT_AI_SMART)) if smart in (None, "") else (str(smart).strip().lower() not in ("false", "0", "off", "no"))
                if smart and not d.get("quote") and str(d.get("format") or "plain") in ("plain", "markdown") and not d.get("emoji") and not d.get("zalo_emoji"):
                    markup = await async_markup_for(hass, rt.defaults, str(d.get("message") or ""), d.get("style"), d.get("auto_emoji"))
                    if markup:
                        d["ai_markup"] = markup
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
    known = {f["key"] for f in e["fields"]}
    inner = vol.Schema(fields, extra=vol.ALLOW_EXTRA)
    return vol.All(lambda data: rename_aliases(e["name"], data, known), inner)       # tên trường zalo_bot cũ -> tên của zalo_call


async def async_register_services(hass: HomeAssistant) -> None:
    catalog = await hass.async_add_executor_job(_load_catalog)
    for e in catalog:
        hass.services.async_register(
            DOMAIN, e["name"], _make_handler(hass, e), schema=_schema(e),
            supports_response=SupportsResponse.OPTIONAL)

    def _device_override(call: ServiceCall, plan=None) -> dict:
        """Thiet bi ghi de luc NGHE MAY (vang = dung mac dinh; "" = tat). Cuoc goi AI/canh bao giu may: tat het, chi noi khi chuyen may
        (thiet bi da cai nam trong plan.connect)."""
        if plan is not None and (plan.ai or plan.alert):          # AI giữ máy: chỉ nối ngay thứ đã tích «nối ngay», còn lại chờ người nhà nói trực tiếp
            return explicit_devices(plan.connect_now) if plan.connect_now else dict(HELD_DEVICES)
        return {k: call.data[k] for k in ("speaker", "mic", "mic_url", "camera", "volume", "mic_gain", "speaker_gain")
                if k in call.data}

    async def make_call(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        plan = _build_plan(rt, call.data)                         # lỗi cấu hình thì báo TRƯỚC khi gọi
        override = _device_override(call, plan)
        rt.bridge.remember(None, override)
        try:
            fields = await rt.bridge.async_call_fields(override)
            ctype = _call_type(call.data, plan)
            if plan is not None:
                plan.video = ctype == "video"
            res = await api.call_request(str(call.data["thread_id"]),
                                         ctype,
                                         call.data.get("peer_name", ""),
                                         call.data.get("srtp"),
                                         call.data.get("extend_profile"),
                                         fields)
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        _register_voice_plan(rt, (res or {}).get("call_id"), plan)
        return {"result": res}

    async def answer_call(call: ServiceCall) -> dict:
        rt, api = _api(hass, call)
        plan = _build_plan(rt, call.data)
        override = _device_override(call, plan)
        rt.bridge.remember(call.data.get("call_id"), override)
        try:
            fields = await rt.bridge.async_call_fields(override)
            res = await api.call_answer(call.data.get("call_id"), fields)
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        _register_voice_plan(rt, (res or {}).get("call_id") or call.data.get("call_id"), plan)
        return {"result": res}

    async def alert_call(call: ServiceCall) -> dict:
        """Cuộc gọi CẢNH BÁO (tách riêng khỏi make_call): đọc `message` bằng giọng pipeline rồi nối thẳng thiết bị nhà ĐÃ CÀI. Thiết bị lấy từ
        trường speaker/mic/camera của lời gọi, không có thì từ quy tắc threadID (theo `connect`); không có nữa thì chỉ đọc rồi cúp."""
        rt, api = _api(hass, call)
        data = call.data
        thread = str(data["thread_id"])
        rule = resolve_rule(get_rules(rt.defaults), thread, "user", None) or {}
        pipeline = _pipeline_id_of(data["pipeline"]) if data.get("pipeline") else (rule.get("pipeline") or "")
        plan = Plan(message=str(data["message"]).strip(), repeat=int(data.get("repeat") or 1), alert=True, hangup=True,
                    engine=data.get("tts_engine") or None, language=data.get("language") or None, pipeline_id=pipeline or None,
                    thread_id=thread, after=data.get("after") or "", connect=_connect_for(data, rule, allow_ai=False, alert=True)[0])
        if not plan.message:
            raise ServiceValidationError("message (nội dung cảnh báo) không được trống")
        rt.bridge.remember(None, dict(HELD_DEVICES))                  # lúc nghe máy mọi thiết bị nhà TẮT; chỉ nối sau khi đọc cảnh báo
        try:
            fields = await rt.bridge.async_call_fields(dict(HELD_DEVICES))
            ctype = _call_type(data, plan)
            plan.video = ctype == "video"
            res = await api.call_request(thread, ctype, data.get("peer_name", ""), None, None, fields)
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        _register_voice_plan(rt, (res or {}).get("call_id"), plan)
        return {"result": res}

    def _pipeline_id_of(value: str) -> str:
        """id pipeline từ id hoặc tên (không phân biệt hoa thường). Không có thì báo lỗi (không đoán)."""
        from homeassistant.components.assist_pipeline import pipeline as pipeline_mod
        v = (value or "").strip()
        if not v:
            return ""
        pls = pipeline_mod.async_get_pipelines(hass)
        for p in pls:
            if v == p.id or v.lower() == p.name.lower():
                return p.id
        raise ServiceValidationError("Không có Assist pipeline «%s»" % v)

    def _pipeline_name(pid: str) -> str:
        from homeassistant.components.assist_pipeline import pipeline as pipeline_mod
        return next((p.name for p in pipeline_mod.async_get_pipelines(hass) if p.id == pid), pid)

    _RULE_FIELDS = ("name", "answer", "answer_delay", "call_types", "ai", "pipeline", "agent", "greeting", "handover_rule", "trusted",
                    "reply_ai", "voice_text", "reply_trigger", "reply_senders", "reply_quote", "reply_prefix", "announce", "announce_to", "announce_text", "announce_repeat", "announce_volume", "connect", "connect_now", "video_request", "speaker", "mic", "mic_url", "camera", "volume", "mic_gain", "speaker_gain", "echo_guard")

    def _rules_copy(rt) -> dict:
        r = get_rules(rt.defaults)
        return {"threads": {k: dict(v) for k, v in r["threads"].items()}, "groups": dict(r["groups"]), "contacts": dict(r["contacts"]),
                "strangers": dict(r["strangers"]), "tags": {k: dict(v) for k, v in r["tags"].items()},
                "contact_meta": {k: dict(v) for k, v in r["contact_meta"].items()}}

    def _show(rule: dict) -> dict:
        return {**rule, "pipeline": _pipeline_name(rule["pipeline"]) if rule.get("pipeline") else ""}

    async def set_rule(call: ServiceCall) -> dict:
        """Quy tắc xử lý cuộc gọi đến / tin nhắn theo threadID (người hoặc nhóm), theo nhóm người trong danh bạ, người lạ, hoặc mọi nhóm.
        Trường nào không nêu thì giữ như cũ (quy tắc mới: mặc định TẮT hết). Không có quy tắc = không làm gì."""
        rt, _ = _api(hass, call)
        scope = call.data["scope"]
        try:
            tid = validate_scope(scope, call.data.get("thread_id"), call.data.get("tag"))
        except RuleError as err:
            raise ServiceValidationError(str(err)) from err
        rules = _rules_copy(rt)
        old = rules["threads"].get(tid) if scope == "thread" else rules["tags"].get(tid) if scope == "tag" else (rules[scope] or None)
        data = {k: call.data[k] for k in _RULE_FIELDS if k in call.data}
        if "pipeline" in data:
            data["pipeline"] = _pipeline_id_of(data["pipeline"])
        try:
            rule = normalize_rule(data, old)
        except RuleError as err:
            raise ServiceValidationError(str(err)) from err
        if scope == "thread":
            rules["threads"][tid] = rule
        elif scope == "tag":
            rules["tags"][tid] = rule
        else:
            rules[scope] = rule
        await rt.defaults.async_set(**{RULES_KEY: rules})
        return {"scope": scope, "thread_id": tid if scope == "thread" else "", "tag": tid if scope == "tag" else "", "rule": _show(rule)}

    async def remove_rule(call: ServiceCall) -> dict:
        rt, _ = _api(hass, call)
        scope = call.data["scope"]
        try:
            tid = validate_scope(scope, call.data.get("thread_id"), call.data.get("tag"))
        except RuleError as err:
            raise ServiceValidationError(str(err)) from err
        rules = _rules_copy(rt)
        if scope == "thread":
            removed = rules["threads"].pop(tid, None) is not None
        elif scope == "tag":
            removed = rules["tags"].pop(tid, None) is not None
        else:
            removed = bool(rules[scope])
            rules[scope] = {}
        await rt.defaults.async_set(**{RULES_KEY: rules})
        return {"scope": scope, "thread_id": tid if scope == "thread" else "", "tag": tid if scope == "tag" else "", "removed": removed}

    async def set_contact_tags(call: ServiceCall) -> dict:
        """Gắn thẻ và/hoặc ghi chú cho một người (hoặc nhóm). Thẻ có quy tắc riêng (set_rule scope = tag) thì mọi người mang thẻ đó dùng quy tắc ấy.
        Không nêu `tags` / `note` thì giữ nguyên; `tags` rỗng = gỡ hết thẻ."""
        rt, _ = _api(hass, call)
        try:
            tid = validate_scope("thread", call.data["thread_id"])
        except RuleError as err:
            raise ServiceValidationError(str(err)) from err
        rules = _rules_copy(rt)
        meta = dict(rules["contact_meta"].get(tid) or {})
        if "tags" in call.data:
            meta["tags"] = parse_tags(call.data["tags"])
        if "note" in call.data:
            meta["note"] = str(call.data["note"] or "").strip()[:MAX_NOTE_LEN]
        if meta.get("tags") or meta.get("note"):
            rules["contact_meta"][tid] = {"tags": meta.get("tags") or [], "note": meta.get("note") or ""}
        else:
            rules["contact_meta"].pop(tid, None)
        await rt.defaults.async_set(**{RULES_KEY: rules})
        out = rules["contact_meta"].get(tid) or {"tags": [], "note": ""}
        return {"thread_id": tid, "tags": out["tags"], "note": out["note"]}

    async def list_rules(call: ServiceCall) -> dict:
        rt, _ = _api(hass, call)
        r = get_rules(rt.defaults)
        return {"threads": {k: _show(v) for k, v in r["threads"].items()}, "groups": _show(r["groups"]) if r["groups"] else None,
                "contacts": _show(r["contacts"]) if r["contacts"] else None, "strangers": _show(r["strangers"]) if r["strangers"] else None,
                "tags": {k: _show(v) for k, v in r["tags"].items()}, "contact_meta": {k: dict(v) for k, v in r["contact_meta"].items()}}

    async def list_contacts(call: ServiceCall) -> dict:
        """Danh bạ Zalo của app (id + tên) để lấy threadID cho set_rule."""
        _, api = _api(hass, call)
        try:
            data = await api.contacts() or {}
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        pick = lambda part: [{"id": str(r.get("id")), "name": str(r.get("name") or "")} for r in (data.get(part) or {}).get("rows", [])]  # noqa: E731
        return {"friends": pick("friends"), "groups": pick("groups")}

    async def get_default_devices(call: ServiceCall) -> dict:
        rt, _ = _api(hass, call)
        return {k: rt.defaults.get(k) for k in ("auto_mic", "auto_video", "video_consent", "auto_video_delay",
                                                  "call_volume", "echo_guard", "ha_url")}

    async def take_over_call(call: ServiceCall) -> dict:
        """Tiếp quản cuộc gọi đang do AI/thông báo giữ: dừng AI, trả mic nhà về."""
        rt, _ = _api(hass, call)
        try:
            return await async_take_over(rt, call.data.get("call_id"))
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err

    async def accept_video(call: ServiceCall) -> dict:
        """Đồng ý lời xin chuyển cuộc thoại sang video của người gọi (camera trống = chỉ đồng ý, không gửi hình trong nhà)."""
        rt, api = _api(hass, call)
        call_id = call.data.get("call_id")
        try:
            if call_id in (None, ""):
                active = (await api.calls() or {}).get("active")
                if not active or active.get("status") != "answered":
                    raise ZaloCallError("Không có cuộc gọi nào đang nói")
                call_id = active["call_id"]
            await async_accept_video(rt, call_id, call.data.get("camera") or "")
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"call_id": str(call_id), "accepted": True, "camera": bool(call.data.get("camera"))}

    async def say_in_call(call: ServiceCall) -> dict:
        """Đọc (TTS) một câu lên cuộc gọi đang nói."""
        rt, api = _api(hass, call)
        call_id = call.data.get("call_id")
        try:
            if call_id in (None, ""):
                active = (await api.calls() or {}).get("active")
                if not active or active.get("status") != "answered":
                    raise HomeAssistantError("Không có cuộc gọi nào đang nói")
                call_id = active["call_id"]
            await async_say(hass, api, str(call_id), str(call.data["message"]), call.data.get("tts_engine"),
                            call.data.get("language"), wait=bool(call.data.get("wait", True)), restore_mic=True)
        except ZaloCallError as err:
            raise HomeAssistantError(str(err)) from err
        return {"call_id": call_id}

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

    def _explicit_devices(data) -> dict:
        return {k: data[k] for k in ("speaker", "mic", "mic_url", "camera", "volume", "mic_gain", "speaker_gain") if data.get(k) not in (None, "")}

    def _device_source(explicit, rule) -> dict:
        return explicit or {k: rule[k] for k in ("speaker", "mic", "mic_url", "camera", "volume", "mic_gain", "speaker_gain") if rule.get(k)}

    def _call_type(data, plan) -> str:
        """Loại cuộc gọi đi. Nêu `type` thì theo đó; không nêu: tích camera (chắc chắn nối camera) = gọi VIDEO, không thì thoại. AI tự chọn camera
        (connect có «ai») thì không ép video: camera chỉ vào khi AI quyết (thoại được nâng lên video)."""
        if data.get("type"):
            return str(data["type"])
        if plan is not None and (plan.ai or plan.alert) and (("camera" in plan.connect and not plan.connect_ai) or "camera" in plan.connect_now):
            return "video"
        return "user"

    def _connect_for(data, rule, allow_ai: bool = True, alert: bool = False) -> tuple[dict, bool]:
        """(thiết bị, AI chọn lúc chuyển máy). Phần nối (`connect`, chọn nhiều): của lời gọi; không nêu thì các phần ứng với thiết bị lời gọi
        đã nêu (nêu loa → nối loa...); không nêu gì thì của quy tắc threadID; không có thì không nối. Thiết bị: nêu trong lời gọi, không thì của
        quy tắc. "ai" chỉ có nghĩa khi có AI trò chuyện (cuộc gọi cảnh báo không có AI để chọn → voice). Cảnh báo (alert) mà không nêu gì: nối TẤT CẢ
        thiết bị đã cài kể cả camera (báo động thì người nhận phải thấy hiện trường), bất kể quy tắc đang để chế độ nào cho cuộc gọi đến."""
        explicit, rule = _explicit_devices(data), rule or {}
        if data.get("connect") is not None:
            parts = parse_connect(data["connect"])
        elif explicit:
            parts = [p for p, keys in (("mic", ("mic", "mic_url")), ("speaker", ("speaker",)), ("camera", ("camera",))) if any(k in explicit for k in keys)]
        else:
            parts = list(CONNECT_PARTS) if alert else parse_connect(rule.get("connect"))
        if "ai" in parts and not allow_ai:                  # không có AI để chọn: chỉ các phần đã tích, bỏ camera (kín hơn)
            parts = [p for p in parts if p not in ("ai", "camera")]
        devices = devices_for_mode(_device_source(explicit, rule), parts)
        return devices, bool(devices) and "ai" in parts

    def _connect_now_for(data, rule) -> dict:
        """Thiết bị nối NGAY khi nghe máy (ô `connect_now`: của lời gọi, không nêu thì của quy tắc). Mặc định trống: mọi thứ chờ tới lúc người nhà
        nói trực tiếp. Thiết bị lấy như `connect` (nêu trong lời gọi, không thì của quy tắc); chưa cài thì không nối."""
        rule = rule or {}
        parts = parse_connect(data["connect_now"] if data.get("connect_now") is not None else rule.get("connect_now"))
        return devices_for_mode(_device_source(_explicit_devices(data), rule), [p for p in parts if p != "ai"])

    def _build_plan(rt, data):
        """Kế hoạch giọng nói (message/ai/alert) của make_call/answer_call, KIỂM TRA TRƯỚC khi gọi/nghe. ai: true cần pipeline/agent nêu rõ hoặc theo
        quy tắc của threadID đó (không tự rơi về pipeline ưu tiên: nó có quyền thiết bị nhà). Thiết bị nhà (plan.connect) chỉ gồm thứ ĐÃ CÀI:
        trường speaker/mic/camera nêu ngay trong lời gọi, hoặc của quy tắc threadID (theo `connect`); không có thì không nối gì."""
        plan = plan_from_service(data)
        if plan is None:
            return None
        plan.thread_id = str(data.get("thread_id") or "")
        if not plan.ai:
            return plan
        rule = None
        if data.get("thread_id"):
            rule = resolve_rule(get_rules(rt.defaults), data.get("thread_id"), "group" if data.get("type") == "group" else "user", None)
        if rule and not (plan.pipeline_id or plan.agent_id):
            plan.pipeline_id = rule.get("pipeline") or None
            plan.agent_id = rule.get("agent") or ""
            plan.trusted = bool(rule.get("trusted"))
        if not (plan.pipeline_id or plan.agent_id):
            raise ServiceValidationError("ai: true cần chọn pipeline (Assist pipeline) hoặc agent (trợ lý), hoặc đặt quy tắc cho threadID này "
                                         "bằng set_rule — không tự dùng pipeline ưu tiên vì nó có quyền thiết bị nhà")
        plan.connect, plan.connect_ai = _connect_for(data, rule)
        plan.connect_now = _connect_now_for(data, rule)
        if not plan.message and not plan.greeting:           # gọi đi có AI mà không có thông báo: AI chào trước (không để người nghe máy gặp im lặng)
            plan.greeting = (rule or {}).get("greeting") or DEFAULT_GREETING
        return plan

    def _register_voice_plan(rt, call_id, plan) -> None:
        if plan is not None and call_id not in (None, ""):
            rt.voice.plans[str(call_id)] = plan

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
                 ("auto_mic", "auto_video", "video_consent",
                  "auto_video_delay",
                  "echo_guard", "call_volume")
                 if k in call.data}
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
                           vol.Optional("auto_mic"): cv.boolean,
                           vol.Optional("auto_video"): cv.boolean,
                           vol.Optional("video_consent"): cv.boolean,
                           vol.Optional("echo_guard"): vol.In(list(ECHO_MODES)),
                           vol.Optional("call_volume"):
                               vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                           vol.Optional("auto_video_delay"):
                               vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                           }))

    devices = {vol.Optional("connect"): vol.All(cv.ensure_list, [vol.In(list(CONNECT))]),
               vol.Optional("speaker"): cv.string,
               vol.Optional("mic"): cv.string,
               vol.Optional("mic_url"): cv.string,
               vol.Optional("camera"): cv.string,
               vol.Optional("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
               vol.Optional("mic_gain"): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
               vol.Optional("speaker_gain"): vol.All(vol.Coerce(int), vol.Range(min=0, max=300))}
    now = {vol.Optional("connect_now"): vol.All(cv.ensure_list, [vol.In(list(CONNECT))])}     # chỉ make_call/answer_call (cảnh báo nối ngay sau khi đọc)
    voice = {vol.Optional("message"): cv.string,
             vol.Optional("repeat"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
             vol.Optional("ai"): cv.boolean,
             vol.Optional("hangup_after"): cv.boolean,
             vol.Optional("greeting"): cv.string,
             vol.Optional("handover_rule"): cv.string,
             vol.Optional("tts_engine"): cv.entity_id,
             vol.Optional("language"): cv.string,
             vol.Optional("pipeline_id"): cv.string,
             vol.Optional("pipeline"): cv.string,
             vol.Optional("agent"): cv.entity_id}
    rule_schema = {vol.Optional("entry_id"): cv.string,
                   vol.Required("scope"): vol.In(list(SCOPES)),
                   vol.Optional("thread_id"): vol.Any(int, cv.string),
                   vol.Optional("tag"): cv.string,
                   vol.Optional("name"): cv.string,
                   vol.Optional("answer"): cv.boolean,
                   vol.Optional("answer_delay"): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                   vol.Optional("call_types"): vol.All(cv.ensure_list, [vol.In(list(CALL_TYPES))]),
                   vol.Optional("ai"): cv.boolean,
                   vol.Optional("pipeline"): cv.string,
                   vol.Optional("agent"): cv.entity_id,
                   vol.Optional("greeting"): cv.string,
                   vol.Optional("handover_rule"): cv.string,
                   vol.Optional("trusted"): cv.boolean,
                   vol.Optional("reply_ai"): cv.boolean,
                   vol.Optional("voice_text"): cv.boolean,
                   vol.Optional("reply_trigger"): cv.string,
                   vol.Optional("reply_senders"): vol.Any(cv.string, [cv.string]),
                   vol.Optional("reply_quote"): cv.boolean,
                   vol.Optional("reply_prefix"): cv.string,
                   vol.Optional("announce"): cv.boolean,
                   vol.Optional("announce_to"): cv.string,
                   vol.Optional("announce_text"): cv.string,
                   vol.Optional("announce_volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                   vol.Optional("announce_repeat"): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_ANNOUNCE_REPEAT)),
                   vol.Optional("connect"): vol.All(cv.ensure_list, [vol.In(list(CONNECT))]),
                   vol.Optional("connect_now"): vol.All(cv.ensure_list, [vol.In(list(CONNECT))]),
                   vol.Optional("video_request"): vol.In(list(VIDEO_REQUEST)),
                   vol.Optional("speaker"): cv.string,
                   vol.Optional("mic"): cv.string,
                   vol.Optional("mic_url"): cv.string,
                   vol.Optional("camera"): cv.string,
                   vol.Optional("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                   vol.Optional("mic_gain"): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                   vol.Optional("speaker_gain"): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                   vol.Optional("echo_guard"): vol.In(list(RULE_ECHO))}
    hass.services.async_register(DOMAIN, "set_rule", set_rule, schema=vol.Schema(rule_schema), supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "remove_rule", remove_rule,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string, vol.Required("scope"): vol.In(list(SCOPES)),
                           vol.Optional("thread_id"): vol.Any(int, cv.string), vol.Optional("tag"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "set_contact_tags", set_contact_tags,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string, vol.Required("thread_id"): vol.Any(int, cv.string),
                           vol.Optional("tags"): vol.Any(cv.string, [cv.string]), vol.Optional("note"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)
    for _name, _fn in (("list_rules", list_rules), ("list_contacts", list_contacts), ("get_default_devices", get_default_devices)):
        hass.services.async_register(DOMAIN, _name, _fn, schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
                                     supports_response=SupportsResponse.ONLY)
    hass.services.async_register(
        DOMAIN, "accept_video", accept_video,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string, vol.Optional("call_id"): vol.Any(int, cv.string), vol.Optional("camera"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "take_over_call", take_over_call,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string, vol.Optional("call_id"): vol.Any(int, cv.string)}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "say_in_call", say_in_call,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string,
                           vol.Optional("call_id"): vol.Any(int, cv.string),
                           vol.Required("message"): cv.string,
                           vol.Optional("tts_engine"): cv.entity_id,
                           vol.Optional("language"): cv.string,
                           vol.Optional("wait"): cv.boolean}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "make_call", make_call,
        schema=vol.Schema({
            vol.Optional("entry_id"): cv.string,
            vol.Required("thread_id"): cv.string,
            vol.Optional("type"): vol.In(["user", "video", "group"]),
            vol.Optional("peer_name"): cv.string,
            vol.Optional("srtp"): vol.In(["sess", "off", "key"]),
            vol.Optional("extend_profile"): vol.In(["native", "pc", "zca"]),
            **voice, **devices, **now}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "alert_call", alert_call,
        schema=vol.Schema({
            vol.Optional("entry_id"): cv.string,
            vol.Required("thread_id"): cv.string,
            vol.Required("message"): cv.string,
            vol.Optional("type"): vol.In(["user", "video"]),
            vol.Optional("peer_name"): cv.string,
            vol.Optional("after"): vol.In(["hangup", "connect", "wait"]),
            vol.Optional("pipeline"): cv.string,
            vol.Optional("tts_engine"): cv.entity_id,
            vol.Optional("language"): cv.string,
            vol.Optional("repeat"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
            **devices}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "answer_call", answer_call,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string,
                           vol.Optional("call_id"): vol.Any(int, cv.string),
                           **voice, **devices, **now}),
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
