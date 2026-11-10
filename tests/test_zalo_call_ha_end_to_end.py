"""Đầu-cuối TRONG Home Assistant thật cho ``zalo_call``: gọi dịch vụ bằng ``hass.services.async_call`` (đúng đường của automation /
Công cụ nhà phát triển), app Zalo là máy chủ giả mô phỏng các tuyến thật. Kiểm: yêu cầu app nhận được, bảng chọn mà HA nhìn thấy
(services.yaml), đường AI tự trả lời (định dạng, màu nhấn mạnh, emoji), lỗi.

Chỉ chạy được khi có HA + pytest-homeassistant-custom-component (ảnh ``r1-test`` trên máy chủ); môi trường khác tự bỏ qua:

    python -m pytest tests/test_zalo_call_ha_end_to_end.py -p pytest_homeassistant_custom_component -o asyncio_mode=auto
"""
import os
import sys
import types

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")
sys.modules.setdefault("turbojpeg", types.SimpleNamespace(TurboJPEG=object))     # camera của HA nạp thư viện này; không cần thật

import custom_components  # noqa: E402

_REPO_CC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components"))
if _REPO_CC not in [os.path.abspath(p) for p in custom_components.__path__]:
    custom_components.__path__.append(_REPO_CC)          # plugin thử của HA đã nạp gói custom_components riêng, che thư mục của kho

from aiohttp import web  # noqa: E402
from homeassistant.core import ServiceCall, SupportsResponse  # noqa: E402
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from homeassistant.helpers.service import async_get_all_descriptions  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

DOMAIN = "zalo_call"
THREAD = "6643404425553198601"


class FakeZaloApp:
    def __init__(self):
        self.requests: list[dict] = []
        self.runner = None
        self.url = ""
        self.fail_next: tuple[int, dict] | None = None

    def last(self, part: str) -> dict:
        return [r for r in self.requests if part in r["path"]][-1]

    async def _any(self, request: web.Request) -> web.Response:
        raw = await request.read()
        body = None
        if raw and request.content_type == "application/json":
            body = await request.json()
        if request.path not in ("/api/status", "/api/calls", "/api/app/login", "/api/settings/devices"):
            self.requests.append({"method": request.method, "path": request.path, "json": body,
                                  "raw": raw if body is None else b"", "ctype": request.content_type})
        if self.fail_next and request.path.startswith("/api/thread"):
            status, payload = self.fail_next
            self.fail_next = None
            return web.json_response(payload, status=status)
        p = request.path
        if p == "/api/app/login":
            return web.json_response({"ok": True})
        if p == "/api/status":
            return web.json_response({"version": "test", "login": True, "sync": "running", "uid": "1"})
        if p == "/api/calls":
            return web.json_response({"calls": []})
        if p == "/api/settings/devices":
            return web.json_response({"devices": {}})
        if p.startswith("/api/thread/"):
            return web.json_response({"ok": True, "data": {"msgId": "8474"}, "message": {"id": "1", "client_id": "1", "text": (body or {}).get("message", "")}})
        if p.startswith("/api/svc/"):
            return web.json_response({"ok": True, "action": p.rsplit("/", 1)[1], "data": {"status": 0}})
        return web.json_response({})

    async def start(self):
        app = web.Application(client_max_size=110 * 1024 * 1024)
        app.router.add_route("*", "/{tail:.*}", self._any)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = "http://127.0.0.1:%d" % site._server.sockets[0].getsockname()[1]

    async def stop(self):
        await self.runner.cleanup()


@pytest.fixture
async def app(socket_enabled):
    a = FakeZaloApp()
    await a.start()
    yield a
    await a.stop()


@pytest.fixture
async def setup(hass, app, enable_custom_integrations, tmp_path):
    hass.config.allowlist_external_dirs.add(str(tmp_path))
    assert await async_setup_component(hass, "homeassistant", {})          # zalo_call phụ thuộc conversation, cần lõi homeassistant trước
    entry = MockConfigEntry(domain=DOMAIN, title="Zalo Call", data={"url": app.url, "username": "u", "password": "p", "webhook_id": "wh-test"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def call(hass, service, data):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=True)


def uid(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, "%s_%s" % (entry.entry_id, key))


async def test_send_message_plain_sends_only_type_and_message(hass, setup, app):
    await call(hass, "send_message", {"thread_id": THREAD, "type": "user", "message": "Xin chào"})
    r = app.last("/send")
    assert r["path"] == "/api/thread/%s/send" % THREAD and r["json"] == {"type": "user", "message": "Xin chào"}, "tin thường không kèm trường định dạng"


async def test_send_message_with_format_emphasis_and_emoji_reaches_the_app(hass, setup, app):
    await call(hass, "send_message", {"thread_id": THREAD, "type": "group", "message": "**Nhiệt độ** 29°C", "format": "markdown",
                                      "auto_emphasis": "orange", "emoji": "ok", "auto_emoji": True})
    assert app.last("/send")["json"] == {"type": "group", "message": "**Nhiệt độ** 29°C", "format": "markdown",
                                         "auto_emphasis": "orange", "emoji": "ok", "auto_emoji": True}


async def test_send_file_and_link_and_reaction_and_undo_reach_the_app(hass, setup, app, tmp_path):
    f = tmp_path / "bao-cao.txt"
    f.write_bytes(b"NOI-DUNG")
    await call(hass, "send_file", {"thread_id": THREAD, "type": "user", "file": str(f)})
    r = app.last("/sendfile")
    assert r["path"] == "/api/thread/%s/sendfile" % THREAD and r["ctype"] == "multipart/form-data" and b"NOI-DUNG" in r["raw"] and b"bao-cao.txt" in r["raw"]
    await call(hass, "send_link", {"thread_id": THREAD, "type": "user", "link": "https://example.com", "message": "xem"})
    assert app.last("/sendlink")["json"] == {"type": "user", "link": "https://example.com", "message": "xem"}
    await call(hass, "add_reaction", {"thread_id": THREAD, "type": "user", "icon": "heart", "msg_id": "8474", "cli_msg_id": "1794325228249"})
    assert app.last("/api/svc/add_reaction")["json"]["icon"] == "heart"
    await call(hass, "undo_message", {"thread_id": THREAD, "type": "user", "msg_id": "8474", "cli_msg_id": "1794325228249"})
    assert app.last("/api/svc/undo_message")["json"]["msg_id"] == "8474"


async def test_path_outside_allowlist_is_refused_before_reaching_the_app(hass, setup, app):
    n = len(app.requests)
    with pytest.raises(ServiceValidationError):
        await call(hass, "send_file", {"thread_id": THREAD, "type": "user", "file": "/etc/passwd"})
    assert len(app.requests) == n


async def test_app_error_becomes_a_home_assistant_error(hass, setup, app):
    app.fail_next = (502, {"error": "response inner error_code=114 Tham số không hợp lệ"})
    with pytest.raises(HomeAssistantError, match="114"):
        await call(hass, "send_message", {"thread_id": THREAD, "type": "user", "message": "x"})


async def test_home_assistant_sees_the_pickers_in_the_service_descriptions(hass, setup):
    d = (await async_get_all_descriptions(hass))[DOMAIN]
    f = d["send_message"]["fields"]
    emoji_opts = f["emoji"]["selector"]["select"]["options"]
    assert len(emoji_opts) >= 30 and {"value": "ok", "label": "✅  ok"} in emoji_opts and f["emoji"]["selector"]["select"]["custom_value"] is True
    assert f["format"]["selector"]["select"]["options"] == ["plain", "markdown"]
    assert f["auto_emphasis"]["selector"]["select"]["options"] == ["red", "orange", "yellow", "green"]
    assert "boolean" in f["auto_emoji"]["selector"]
    icons = [o["value"] for o in d["add_reaction"]["fields"]["icon"]["selector"]["select"]["options"]]
    assert len(icons) >= 50 and {"like", "heart", "haha", "wow", "cry", "angry"} <= set(icons)


@pytest.fixture
def fake_agent(hass):
    """Trợ lý hội thoại giả: trả về markdown như các mô hình AI thường làm."""
    calls = []

    async def process(call: ServiceCall):
        calls.append(call.data)
        return {"response": {"speech": {"plain": {"speech": "**Nhiệt độ** 29°C\n- Cửa mở lúc 15:30"}}}}
    hass.services.async_register("conversation", "process", process, supports_response=SupportsResponse.ONLY)
    return calls


async def test_ai_reply_is_formatted_as_markdown_by_default_and_follows_the_new_switches(hass, setup, app, fake_agent):
    from custom_components.zalo_call.ai import async_ai_reply
    from custom_components.zalo_call import ai as ai_mod
    ai_mod.MIN_INTERVAL = 0
    rt = hass.data[DOMAIN][setup.entry_id]
    await rt.defaults.async_set(ai_enabled=True)
    event = {"content": "trời nay sao", "thread_id": THREAD, "thread_type": "user", "is_self": False}
    await async_ai_reply(hass, setup, event)
    assert fake_agent and app.last("/send")["json"] == {"type": "user", "message": "**Nhiệt độ** 29°C\n- Cửa mở lúc 15:30", "format": "markdown"}, \
        "mặc định: markdown (hết dấu ** thô), không tự đổi màu/emoji"
    # bật qua đúng các thực thể trên thiết bị (như người dùng bấm trong giao diện)
    sel = uid(hass, setup, "select", "ai_emphasis")
    sw = uid(hass, setup, "switch", "ai_emoji")
    fmt = uid(hass, setup, "select", "ai_format")
    assert sel and sw and fmt, "thiếu thực thể điều khiển AI: %s %s %s" % (sel, sw, fmt)
    await hass.services.async_call("select", "select_option", {"entity_id": sel, "option": "orange"}, blocking=True)
    await hass.services.async_call("switch", "turn_on", {"entity_id": sw}, blocking=True)
    await async_ai_reply(hass, setup, event)
    assert app.last("/send")["json"] == {"type": "user", "message": "**Nhiệt độ** 29°C\n- Cửa mở lúc 15:30", "format": "markdown",
                                         "auto_emphasis": "orange", "auto_emoji": True}
    await hass.services.async_call("select", "select_option", {"entity_id": fmt, "option": "plain"}, blocking=True)
    await hass.services.async_call("select", "select_option", {"entity_id": sel, "option": "off"}, blocking=True)
    await hass.services.async_call("switch", "turn_off", {"entity_id": sw}, blocking=True)
    await async_ai_reply(hass, setup, event)
    assert app.last("/send")["json"] == {"type": "user", "message": "**Nhiệt độ** 29°C\n- Cửa mở lúc 15:30", "format": "plain"}


async def test_ai_does_not_reply_to_groups_or_own_messages(hass, setup, app, fake_agent):
    from custom_components.zalo_call.ai import async_ai_reply
    rt = hass.data[DOMAIN][setup.entry_id]
    await rt.defaults.async_set(ai_enabled=True)
    n = len(app.requests)
    await async_ai_reply(hass, setup, {"content": "x", "thread_id": "9", "thread_type": "group", "is_self": False})
    await async_ai_reply(hass, setup, {"content": "x", "thread_id": THREAD, "thread_type": "user", "is_self": True})
    assert not fake_agent and len(app.requests) == n
