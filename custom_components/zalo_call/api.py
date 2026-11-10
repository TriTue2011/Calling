"""Lop goi API cua app Zalo PC (container zalo-pc-app, cong 8080).

App bat dang nhap (user/mat khau) va giu phien bang cookie; lop nay tu
dang nhap lai mot lan khi gap 401.
"""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=60)


class ZaloCallError(Exception):
    """Loi goi app hoac Zalo (kem ma HTTP khi co)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ZaloCallAuthError(ZaloCallError):
    """Sai tai khoan/mat khau cua app."""


class ZaloCallApi:
    def __init__(self, session: aiohttp.ClientSession, url: str,
                 username: str, password: str) -> None:
        self._s = session
        self.url = url.rstrip("/")
        self._user = username
        self._pw = password
        self._lock = asyncio.Lock()

    async def login(self) -> None:
        try:
            async with self._s.post(
                    self.url + "/api/app/login",
                    json={"username": self._user, "password": self._pw},
                    timeout=TIMEOUT) as r:
                if r.status in (401, 403):
                    raise ZaloCallAuthError("Sai tài khoản hoặc mật khẩu app",
                                            r.status)
                if r.status == 429:
                    raise ZaloCallError("App khoá tạm vì đăng nhập sai nhiều lần",
                                        r.status)
                if r.status != 200:
                    raise ZaloCallError("Đăng nhập app lỗi HTTP %s" % r.status,
                                        r.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ZaloCallError("Không gọi được tới app: %s" % err) from err

    async def _request(self, method: str, path: str, *, retry: bool = True,
                       **kw: Any) -> Any:
        try:
            async with self._s.request(method, self.url + path,
                                       timeout=TIMEOUT, **kw) as r:
                if r.status == 401 and retry:
                    async with self._lock:
                        await self.login()
                    return await self._request(method, path, retry=False, **kw)
                try:
                    data = await r.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    data = {}
                if r.status >= 400:
                    msg = (data.get("error") if isinstance(data, dict) else None) \
                        or "HTTP %s" % r.status
                    raise ZaloCallError(str(msg), r.status)
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ZaloCallError("Không gọi được tới app: %s" % err) from err

    # -- trang thai ---------------------------------------------------------
    async def status(self) -> dict:
        return await self._request("GET", "/api/status")

    async def calls(self) -> dict:
        return await self._request("GET", "/api/calls")

    async def contacts(self) -> dict:
        return await self._request("GET", "/api/contacts")

    # -- 96 service ---------------------------------------------------------
    async def svc(self, action: str, body: dict) -> Any:
        res = await self._request("POST", "/api/svc/" + action, json=body)
        return res.get("data", res) if isinstance(res, dict) else res

    # -- tin nhan -----------------------------------------------------------
    async def thread_send(self, ttype: str, thread_id: str, message: str,
                          fmt: str | None = None,
                          auto_emphasis: Any = None,
                          emoji: str | None = None,
                          auto_emoji: Any = None,
                          zalo_emoji: str | None = None) -> Any:
        body: dict[str, Any] = {"type": ttype, "message": message}
        if fmt:
            body["format"] = str(fmt)
        for key, val in (("auto_emphasis", auto_emphasis), ("emoji", emoji),
                         ("auto_emoji", auto_emoji), ("zalo_emoji", zalo_emoji)):
            if val not in (None, "", False):
                body[key] = val
        return await self._request(
            "POST", "/api/thread/%s/send" % thread_id, json=body)

    async def thread_sendlink(self, ttype: str, thread_id: str, link: str,
                              message: str = "") -> Any:
        return await self._request(
            "POST", "/api/thread/%s/sendlink" % thread_id,
            json={"type": ttype, "link": link, "message": message})

    async def _multipart(self, action: str, ttype: str, thread_id: str,
                         filename: str, data: bytes, mime: str,
                         kind: str | None) -> Any:
        form = aiohttp.FormData()
        form.add_field("type", ttype)
        if kind:
            form.add_field("kind", kind)
        form.add_field("file", data, filename=filename, content_type=mime)
        return await self._request(
            "POST", "/api/thread/%s/%s" % (thread_id, action), data=form)

    async def thread_sendfile(self, ttype, thread_id, filename, data, mime,
                              kind="file") -> Any:
        return await self._multipart("sendfile", ttype, thread_id, filename,
                                     data, mime, kind)

    async def thread_sendvoice(self, ttype, thread_id, filename, data,
                               mime) -> Any:
        return await self._multipart("sendvoice", ttype, thread_id, filename,
                                     data, mime, None)

    # -- cuoc goi -----------------------------------------------------------
    async def call_request(self, thread_id: str, call_type: str,
                           peer_name: str = "", srtp: str | None = None,
                           extend_profile: str | None = None,
                           devices: dict | None = None) -> dict:
        body = {"callee_id": thread_id, "type": call_type,
                "peer_name": peer_name or thread_id}
        if srtp in ("sess", "off", "key"):      # bo trong = app tu chon (auto)
            body["srtp"] = srtp
        if extend_profile in ("native", "pc", "zca"):
            body["extend_profile"] = extend_profile
        body.update(devices or {})              # mic_url / mic_format / camera_url
        return await self._request("POST", "/api/call/request", json=body)

    async def call_answer(self, call_id: str | int | None = None,
                          devices: dict | None = None) -> dict:
        body = {"call_id": call_id if call_id is not None else ""}
        body.update(devices or {})
        return await self._request("POST", "/api/call/answer", json=body)

    async def call_reject(self, call_id: str | int | None = None) -> dict:
        return await self._request(
            "POST", "/api/call/reject",
            json={"call_id": call_id if call_id is not None else ""})

    async def call_media_status(self, call_id: str | int) -> dict | None:
        """Trang thai media (kem audio_token) cua mot cuoc goi dang song."""
        data = await self.calls()
        for c in (data or {}).get("calls", []):
            if str(c.get("call_id")) == str(call_id):
                return c.get("media")
        return None

    async def devices_get(self) -> dict:
        return (await self._request("GET", "/api/settings/devices")).get("devices", {})

    async def devices_set(self, patch: dict) -> dict:
        """Dat thiet bi mac dinh cua app (mic_url, mic_format, camera_url, video, auto_*)."""
        return await self._request("POST", "/api/settings/devices", json=patch)

    async def media_control(self, body: dict) -> dict:
        """Bat/tat mic hoac hinh cua cuoc goi: {call_id?, action, target, mic_url, camera_url...}."""
        return await self._request("POST", "/api/call/media", json=body)

    async def upgrade_video(self, body: dict) -> dict:
        """Chuyen cuoc goi THOAI dang dien ra sang VIDEO: {call_id?, camera_url?}."""
        return await self._request("POST", "/api/call/upgrade_video", json=body)

    async def call_end(self, call_id: str | int | None = None) -> dict:
        return await self._request(
            "POST", "/api/call/end",
            json={"call_id": call_id if call_id is not None else ""})

    async def voice_to_text(self, url: str, wait: float = 25) -> dict:
        """Zalo AI chuyen TIN NHAN THOAI (URL tep tren may chu Zalo) thanh van ban.
        wait > 0: app cho toi ngan ay giay roi tra {done, text}."""
        return await self._request(
            "POST", "/api/voice2text", json={"url": url, "wait": wait})

    # -- webhook va dang nhap Zalo -----------------------------------------
    async def get_webhooks(self) -> dict:
        return await self._request("GET", "/api/webhooks")

    async def set_webhooks(self, cfg: dict) -> dict:
        return await self._request("POST", "/api/webhooks", json=cfg)

    async def qr_new(self) -> dict:
        return await self._request("POST", "/api/qr/new", json={})
