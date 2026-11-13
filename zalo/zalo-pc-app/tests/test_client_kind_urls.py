"""Mọi yêu cầu Zalo phải khai zpw_type/zpw_ver ĐÚNG kiểu đăng nhập đang dùng (web 30/695, pc 24/693), kể cả sau khi đổi kiểu lúc chạy.

Hai lớp kiểm: (1) quét mã nguồn: không có hằng bị đóng băng lúc nạp mô-đun, không số cứng 693/694/695; (2) gọi thật các hàm dựng URL
của từng nhóm dịch vụ (báo hiệu cuộc gọi, dịch vụ chung, chat, danh bạ, phong bì đăng nhập, WebSocket) ở cả hai kiểu."""
import ast
import base64
import glob
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from zalo_pc_app import chat, contacts, protocol, qr_login, services, signaling, ws_listener  # noqa: E402

EXPECT = {"web": (30, 695), "pc": (24, 693)}
ENK = base64.b64encode(b"0123456789abcdef").decode()
PKG = os.path.join(HERE, "..", "zalo_pc_app")


def _q(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


def _check(client, url, what):
    q = _q(url)
    t, v = EXPECT[client]
    assert q.get("zpw_type") == str(t) and q.get("zpw_ver") == str(v), "%s (%s): %s" % (what, client, {k: q.get(k) for k in ("zpw_type", "zpw_ver")})


def test_static_nothing_frozen_at_import_and_no_hardcoded_versions():
    bad = []
    for path in sorted(glob.glob(os.path.join(PKG, "*.py"))):
        name = os.path.basename(path)
        tree = ast.parse(open(path, encoding="utf-8").read())
        if name != "protocol.py":
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and n.value in (693, 694, 695) and isinstance(n.value, int):
                    bad.append("%s:%d số cứng %s" % (name, n.lineno, n.value))
                if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("protocol") and any(a.name in ("API_TYPE", "API_VERSION") for a in n.names):
                    bad.append("%s:%d import thẳng hằng API_*" % (name, n.lineno))
        for n in tree.body:   # cấp mô-đun gọi common_params/đọc API_* -> đóng băng
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
                d = ast.dump(n)
                if name != "protocol.py" and ("common_params" in d or "API_TYPE" in d or "API_VERSION" in d):
                    bad.append("%s:%d dùng lúc nạp mô-đun" % (name, n.lineno))
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in list(n.args.defaults) + [x for x in n.args.kw_defaults if x]:
                    ds = ast.dump(d)
                    if "common_params" in ds or "API_TYPE" in ds or "API_VERSION" in ds:
                        bad.append("%s:%d %s: tham số mặc định đóng băng" % (name, n.lineno, n.name))
    assert not bad, bad


def test_every_url_builder_follows_the_client():
    seen = []
    for client in ("web", "pc", "web"):                 # web -> pc -> web: đổi lúc chạy phải có hiệu lực ngay
        protocol.set_client(client)
        urls = []

        def rec_get(url, timeout=0):
            urls.append(("signaling", url))
            return 200, {"error_code": 0, "data": "x"}
        sig = signaling.Signaling(rec_get, "dev", ENK)
        try:
            sig.endcall("123", 456)
        except Exception:                                # giải mã trả lời giả sẽ lỗi; URL đã ghi
            pass
        assert urls, "Signaling không gọi http_get"
        _check(client, urls[0][1], "Signaling.endcall")

        post_urls = []
        svc = services.Services(lambda u, timeout=0: (200, {"error_code": 0, "data": "x"}),
                                lambda u, f, timeout=0: (post_urls.append(u) or (200, {"error_code": 0, "data": "x"})), "dev", ENK, service_map={})
        _check(client, svc._url("https://h", "/api/x", {"a": 1}), "Services._url")
        _check(client, svc._url("https://h", "/api/x", {}, no_params=True), "Services._url no_params")
        try:
            svc._post("https://h", "/api/x", {"a": 1})
        except Exception:
            pass
        assert post_urls, "Services._post không gửi"
        _check(client, post_urls[0], "Services._post")

        _check(client, chat._url_with_params("https://h", "/api/x", {"a": 1}, ENK), "chat._url_with_params")
        _check(client, chat._multipart_url("https://h", "/api/x", {"a": 1}, ENK, 2), "chat._multipart_url")
        _check(client, contacts._url_with_params("https://h", "/api/x", {"a": 1}, ENK), "contacts._url_with_params")
        _check(client, ws_listener.build_url("wss://h/p", protocol.API_VERSION, protocol.API_TYPE), "ws_listener.build_url")
        _check(client, protocol.build_url("https://h", "/p", protocol.common_params()), "protocol.common_params")

        t, v = EXPECT[client]
        for key in (None, "TEST_PARAM_KEY_32_CHARS_LONG_XXX"):                 # phong bì đăng nhập (có/không mã hoá tham số)
            env, _enk = qr_login._envelope({"imei": "d"}, "reqqr", key, "dev")
            assert env["type"] == t and env["client_version"] == v, (client, key, env.get("type"), env.get("client_version"))
        seen.append(client)
    assert seen == ["web", "pc", "web"]
    protocol.set_client("web")


def test_user_agent_follows_the_client_like_real_zalo_pc():
    protocol.set_client("pc")
    assert protocol.user_agent() == "ZaloPC-win32-24v693"           # y hệt Zalo PC 26.11.10 thật (nhật ký mạng)
    protocol.set_client("web")
    assert protocol.user_agent() == "zalo-pc-qr/1.0"
    src = open(os.path.join(PKG, "server.py"), encoding="utf-8").read()
    # chỉ còn đúng 1 chỗ cố định: phép thử proxy tới wpa.zalo.me (không phải yêu cầu dịch vụ)
    assert src.count('"zalo-pc-qr/1.0"') == 1, src.count('"zalo-pc-qr/1.0"')


def test_web_mode_calls_and_rejected_services_use_pc_identity():
    """Kiểu web: dịch vụ nào không dùng được với zpw_type/zpw_ver của web thì dùng của PC."""
    protocol._PC_HOSTS.clear()
    try:
        protocol.set_client("web")
        call = "https://voicecall-wpa.chat.zalo.me/api/voicecall/answer?zpw_ver=695&zpw_type=30&params=abc"
        chat = "https://tt-chat1-wpa.chat.zalo.me/api/message/sms?zpw_ver=695&zpw_type=30&params=abc"
        nop = "https://tt-chat1-wpa.chat.zalo.me/api/x?params=abc"
        assert _q(protocol.adapt_url(call))["zpw_type"] == "24" and _q(protocol.adapt_url(call))["zpw_ver"] == "693"
        assert _q(protocol.adapt_url(call))["params"] == "abc"
        assert protocol.adapt_url(chat) == chat and protocol.adapt_url(nop) == nop
        assert protocol.user_agent_for(call) == "ZaloPC-win32-24v693" and protocol.user_agent_for(chat) == "zalo-pc-qr/1.0"
        # máy chủ bị từ chối vì kiểu -> học -> các yêu cầu sau của máy chủ đó đi bằng PC
        assert protocol.type_rejected({"error_code": 602, "error_message": "zpw_type bị thiếu hoặc không đúng"})
        assert protocol.type_rejected({"error_code": 1, "error_message": "ZPW_VER sai"})
        assert not protocol.type_rejected({"error_code": 0, "error_message": "zpw_type"})
        assert not protocol.type_rejected({"error_code": 600, "error_message": "zpw_sek bị thiếu hoặc không đúng"})
        assert not protocol.type_rejected("x") and not protocol.type_rejected({})
        assert protocol.learn_pc(chat) is True and protocol.learn_pc(chat) is False
        assert _q(protocol.adapt_url(chat))["zpw_type"] == "24" and protocol.user_agent_for(chat) == "ZaloPC-win32-24v693"
        assert protocol.adapt_url(nop) == nop                    # không có tham số kiểu thì giữ nguyên
        # kiểu pc: không đổi gì
        protocol.set_client("pc")
        assert protocol.adapt_url(call) == call and protocol.adapt_url(chat) == chat
    finally:
        protocol._PC_HOSTS.clear()
        protocol.set_client("web")


def test_transport_retries_once_with_pc_when_zalo_rejects_the_web_type():
    import contextlib
    import io
    import json as _json
    from zalo_pc_app import server as app_server
    protocol._PC_HOSTS.clear()
    protocol.set_client("web")
    sent = []

    class Resp:
        def __init__(self, body):
            self.status, self._b = 200, _json.dumps(body).encode()

        def read(self):
            return self._b

    orig = app_server._zalo_urlopen

    def fake(req, timeout):
        q = _q(req.full_url)
        sent.append((q.get("zpw_type"), q.get("zpw_ver"), req.get_header("User-agent")))
        if q.get("zpw_type") == "30" and "group-wpa" in req.full_url:       # chỉ máy chủ nhóm từ chối kiểu web
            return contextlib.nullcontext(Resp({"error_code": 602, "error_message": "zpw_type bị thiếu hoặc không đúng"}))
        return contextlib.nullcontext(Resp({"error_code": 0, "data": "ok"}))
    app_server._zalo_urlopen = fake
    try:
        tr = app_server.make_transport("sek")
        url = "https://group-wpa.chat.zalo.me/api/group/getlg/v4?zpw_ver=695&zpw_type=30&params=a"
        st, body = tr.http_get(url)
        assert body["error_code"] == 0, body
        assert sent == [("30", "695", "zalo-pc-qr/1.0"), ("24", "693", "ZaloPC-win32-24v693")], sent
        sent.clear()
        tr.http_get(url)                                        # máy chủ đã học: đi thẳng bằng PC, không thử 2 lần
        assert sent == [("24", "693", "ZaloPC-win32-24v693")], sent
        sent.clear()
        tr.http_get("https://voicecall-wpa.chat.zalo.me/api/voicecall/ringring?zpw_ver=695&zpw_type=30&params=a")
        assert sent == [("24", "693", "ZaloPC-win32-24v693")], sent      # gọi điện luôn PC
        sent.clear()
        tr.http_get("https://profile-wpa.chat.zalo.me/api/x?zpw_ver=695&zpw_type=30&params=a")
        assert sent[0][:2] == ("30", "695") and len(sent) == 1, sent       # dịch vụ khác vẫn web
    finally:
        app_server._zalo_urlopen = orig
        protocol._PC_HOSTS.clear()
        protocol.set_client("web")


def test_transport_does_not_learn_pc_when_pc_is_rejected_too():
    import contextlib
    import json as _json
    from zalo_pc_app import server as app_server
    protocol._PC_HOSTS.clear()
    protocol.set_client("web")
    sent = []

    class Resp:
        status = 200

        def read(self):
            return _json.dumps({"error_code": 602, "error_message": "zpw_type bị thiếu hoặc không đúng"}).encode()
    orig = app_server._zalo_urlopen
    app_server._zalo_urlopen = lambda req, timeout: (sent.append(_q(req.full_url)["zpw_type"]) or contextlib.nullcontext(Resp()))
    try:
        tr = app_server.make_transport("sek")
        url = "https://group-wpa.chat.zalo.me/api/group/getlg/v4?zpw_ver=695&zpw_type=30"
        st, body = tr.http_get(url)
        assert body["error_code"] == 602 and sent == ["30", "24"], sent        # thử PC 1 lần, vẫn bị từ chối
        assert not protocol._PC_HOSTS, "PC cũng bị từ chối thì KHÔNG học (lỗi không do kiểu)"
        sent.clear()
        tr.http_get(url)
        assert sent == ["30", "24"], sent                                      # vẫn bắt đầu bằng web
    finally:
        app_server._zalo_urlopen = orig
        protocol._PC_HOSTS.clear()
        protocol.set_client("web")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CLIENT KIND URL TESTS PASSED")
