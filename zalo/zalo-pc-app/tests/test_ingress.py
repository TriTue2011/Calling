"""Home Assistant Ingress (add-on): tin cậy đúng nguồn, viết lại đường dẫn, thân POST chunked (14/11/2026).
Run: python3 tests/test_ingress.py"""
import http.client
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-ingress-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_PORT"] = "0"
os.environ["ZALO_PC_APP_USER"] = "nguoi-dung-test"
os.environ["ZALO_PC_APP_PASSWORD"] = "mat-khau-test-123"
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)
from zalo_pc_app import ingress  # noqa: E402
from zalo_pc_app import server as sv  # noqa: E402

PFX = "/api/hassio_ingress/abcDEF123_-xyz0987654321"
ON = {"ZALO_PC_INGRESS": "1"}
HDR = {"X-Ingress-Path": PFX}


def test_trust_rules():
    assert ingress.prefix_for(ingress.SUPERVISOR_IP, HDR, ON) == PFX
    assert ingress.prefix_for(ingress.SUPERVISOR_IP, {"X-Ingress-Path": PFX + "/"}, ON) == PFX      # dấu / cuối bị bỏ
    assert ingress.prefix_for(ingress.SUPERVISOR_IP, HDR, {}) == ""                                 # chưa bật ZALO_PC_INGRESS (Docker thường)
    assert ingress.prefix_for(ingress.SUPERVISOR_IP, HDR, {"ZALO_PC_INGRESS": "0"}) == ""
    assert ingress.prefix_for("192.168.1.50", HDR, ON) == ""                                        # từ LAN giả header: KHÔNG tin
    assert ingress.prefix_for("127.0.0.1", HDR, ON) == ""
    assert ingress.prefix_for(ingress.SUPERVISOR_IP, {}, ON) == ""                                  # Supervisor nhưng thiếu header
    for bad in ("/", "/x", "//evil.com", "/api/hassio_ingress/", "/api/hassio_ingress/a", "/api/hassio_ingress/abc/../x",
                "/api/hassio_ingress/abcdefgh'+alert(1)+'", "https://evil.com/api/hassio_ingress/abcdefgh12"):
        assert ingress.prefix_for(ingress.SUPERVISOR_IP, {"X-Ingress-Path": bad}, ON) == "", bad      # tiền tố chèn được vào JS/HTML phải khớp khuôn
    assert ingress.enabled({"ZALO_PC_INGRESS": " TRUE "}) and not ingress.enabled({"ZALO_PC_INGRESS": ""})


def test_read_chunked():
    body = b"5\r\nhello\r\n6;ext=1\r\n world\r\n0\r\nTrailer: x\r\n\r\n"
    assert ingress.read_chunked(io.BytesIO(body)) == b"hello world"
    assert ingress.read_chunked(io.BytesIO(b"0\r\n\r\n")) == b""
    assert ingress.read_chunked(io.BytesIO(b"zz\r\nabc\r\n")) is None                                # kích thước hỏng
    assert ingress.read_chunked(io.BytesIO(b"5\r\nhel")) is None                                     # cụt giữa chừng
    assert ingress.read_chunked(io.BytesIO(b"")) is None
    assert ingress.read_chunked(io.BytesIO(b"a\r\n0123456789\r\n0\r\n\r\n"), maximum=5) is None      # quá giới hạn


def test_rewrite_html_css():
    html = ('<html><head><link rel="stylesheet" href="/style.css"></head><body>'
            '<form action="/api/app/login"><img src="/fonts/a.png"><a href="//cdn.x/y">'
            '<a href="https://x/y"><a href="rel/path"><script src="/app.js"></script></body></html>')
    out = ingress.rewrite_html(html, PFX)
    assert out.index("<script>(function(){") < out.index('<link rel="stylesheet"'), "shim phải đứng trước mọi script/link"
    for want in ('href="%s/style.css"' % PFX, 'action="%s/api/app/login"' % PFX, 'src="%s/fonts/a.png"' % PFX, 'src="%s/app.js"' % PFX):
        assert want in out, want
    for keep in ('href="//cdn.x/y"', 'href="https://x/y"', 'href="rel/path"'):
        assert keep in out, keep                                                                     # // (cùng giao thức), tuyệt đối đầy đủ, tương đối: giữ nguyên
    assert ingress.rewrite_html("<p>x</p>", PFX).startswith("<script>")                             # không có <head>: shim đặt đầu
    css = "a{background:url(/fonts/x.woff2)}b{src:url('/fonts/y.woff2')}c{src:url(\"/f/z\")}d{background:url(//h/x)}e{background:url(data:x)}"
    out = ingress.rewrite_css(css, PFX)
    assert "url(%s/fonts/x.woff2)" % PFX in out and "url('%s/fonts/y.woff2')" % PFX in out and 'url("%s/f/z")' % PFX in out
    assert "url(//h/x)" in out and "url(data:x)" in out


def test_shim_is_valid_js_and_patches():
    shim = ingress.shim_js(PFX)
    assert PFX in shim and "\n" not in shim
    node = subprocess.run(["node", "-e", "new Function(process.argv[1])", shim], capture_output=True, text=True)
    assert node.returncode == 0, node.stderr
    js = r"""
    const shim = process.argv[1], P = process.argv[2];
    const calls = [];
    global.window = global; global.fetch = (u) => { calls.push(['fetch', u]); return Promise.resolve(); };
    global.XMLHttpRequest = function () {}; XMLHttpRequest.prototype.open = function (m, u) { calls.push(['xhr', u]); };
    const mk = (n) => { function C() {} Object.defineProperty(C.prototype, n, { configurable: true, get() { return this['_' + n]; }, set(v) { this['_' + n] = v; } }); return C; };
    global.HTMLImageElement = mk('src'); global.HTMLMediaElement = mk('src'); global.HTMLSourceElement = mk('src'); global.HTMLScriptElement = mk('src');
    global.HTMLAnchorElement = mk('href'); global.HTMLLinkElement = mk('href'); global.HTMLFormElement = mk('action'); global.HTMLIFrameElement = mk('src');
    global.Element = function () {}; Element.prototype.setAttribute = function (n, v) { this[n] = v; };
    global.open = (u) => { calls.push(['open', u]); };
    global.EventSource = function (u, o) { calls.push(['sse', u]); this.u = u; }; EventSource.prototype.close = function () {};
    eval(shim);
    fetch('/api/x'); fetch('//h/x'); fetch('https://h/x'); fetch('rel'); fetch(P + '/api/da-co');
    const x = new XMLHttpRequest(); x.open('GET', '/api/y');
    const img = new HTMLImageElement(); img.src = '/api/call/video/view?id=1';
    const a = new HTMLAnchorElement(); a.href = '/call';
    const el = new Element(); el.setAttribute('src', '/ui/a.js'); el.setAttribute('data-x', '/khong-doi');
    window.open('/call', 'w');
    const es = new EventSource('/api/events'); es.close(); const es2 = new EventSource('//h/e');
    console.log(JSON.stringify({ calls, img: img.src, a: a.href, el: el.src, dx: el['data-x'], ing: window.__zIng }));
    """
    out = subprocess.run(["node", "-e", js, shim, PFX], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["calls"] == [["fetch", PFX + "/api/x"], ["fetch", "//h/x"], ["fetch", "https://h/x"], ["fetch", "rel"], ["fetch", PFX + "/api/da-co"],
                          ["xhr", PFX + "/api/y"], ["open", PFX + "/call"], ["sse", PFX + "/api/events"], ["sse", "//h/e"]], r["calls"]
    assert r["img"] == PFX + "/api/call/video/view?id=1" and r["a"] == PFX + "/call" and r["el"] == PFX + "/ui/a.js" and r["dx"] == "/khong-doi"
    assert r["ing"] == PFX


def raw(base_port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", base_port, timeout=10)
    c.request(method, path, body=body, headers=headers or {}, encode_chunked=False)
    r = c.getresponse()
    data = r.read().decode("utf-8", "replace")
    out = (r.status, dict(r.getheaders()), data)
    c.close()
    return out


def test_server_end_to_end():
    st = sv.AppState(tmp)
    sv.STATE = st
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    saved_ip, saved_env = ingress.SUPERVISOR_IP, os.environ.get("ZALO_PC_INGRESS")
    try:
        ingress.SUPERVISOR_IP = "127.0.0.1"                                                          # thử trên máy này: coi 127.0.0.1 là Supervisor
        os.environ["ZALO_PC_INGRESS"] = "1"
        # 1) Qua ingress: vào thẳng giao diện, không cần mật khẩu, HTML/CSS đã gắn tiền tố, JS vẫn nguyên.
        s, h, body = raw(port, "GET", "/", HDR)
        assert s == 200 and "text/html" in h["Content-Type"], (s, h)
        assert "window.__zIng=" in body and ('src="%s/ui/app.js"' % PFX) in body and ('href="%s/ui/app.css"' % PFX) in body, body[:600]
        assert not re.search(r'(?:href|src|action)="/(?!/|api/hassio_ingress/)', body), "còn đường dẫn tuyệt đối chưa gắn tiền tố"
        s, h, body = raw(port, "GET", "/ui/app.js", HDR)
        assert s == 200 and "text/javascript" in h["Content-Type"] and "__zIng" in body and body.count("window.__zIng=") == 0   # JS không bị chèn shim
        s, h, body = raw(port, "GET", "/style.css", HDR)
        assert s == 200 and ("url(%s/fonts/" % PFX in body or "url('%s/fonts/" % PFX in body or "url(\"%s/fonts/" % PFX in body or "url(" not in body), body[:300]
        s, h, body = raw(port, "GET", "/call", HDR)
        assert s == 200 and ('src="%s/ui/call.js"' % PFX) in body
        s, h, body = raw(port, "GET", "/api/app/status", HDR)
        assert json.loads(body)["logged_in"] is True
        s, h, body = raw(port, "GET", "/login", HDR)                                                 # đã vào rồi → quay lại app, Location có tiền tố
        assert s == 302 and h["Location"] == PFX + "/", (s, h)
        # 2) Không qua ingress (LAN / Docker thường): vẫn bắt đăng nhập và KHÔNG viết lại.
        s, h, body = raw(port, "GET", "/")
        assert s == 302 and h["Location"] == "/login", (s, h)
        s, _, body = raw(port, "GET", "/api/app/status")
        assert json.loads(body)["logged_in"] is False
        s, h, body = raw(port, "GET", "/login")
        assert s == 200 and "__zIng=" not in body and 'href="/style.css"' in body
        os.environ["ZALO_PC_INGRESS"] = "0"                                                          # header giả khi chưa bật ingress: bỏ qua
        s, _, body = raw(port, "GET", "/api/app/status", HDR)
        assert json.loads(body)["logged_in"] is False
        os.environ["ZALO_PC_INGRESS"] = "1"
        ingress.SUPERVISOR_IP = "10.9.9.9"                                                           # nguồn khác Supervisor giả header: bỏ qua
        s, _, body = raw(port, "GET", "/api/app/status", HDR)
        assert json.loads(body)["logged_in"] is False
        ingress.SUPERVISOR_IP = "127.0.0.1"
        # 3) POST chunked (Ingress không gửi Content-Length) vẫn tới được hàm xử lý và kết nối giữ sống cho yêu cầu kế.
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        payload = json.dumps({"username": "nguoi-dung-test", "password": "mat-khau-test-123"}).encode()

        def gen():
            yield payload[:10]
            yield payload[10:]
        c.request("POST", "/api/app/login", body=gen(), headers=dict(HDR, **{"Content-Type": "application/json"}), encode_chunked=True)
        r = c.getresponse()
        data = json.loads(r.read())
        assert r.status == 200 and data.get("ok") is True, (r.status, data)                          # thân JSON không mất
        c.request("GET", "/api/app/status", headers=HDR)                                              # cùng kết nối: rfile đã được trả lại
        r = c.getresponse()
        assert r.status == 200 and json.loads(r.read())["logged_in"] is True
        c.close()
        # 4) Thân chunked hỏng → 400 chứ không treo.
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.putrequest("POST", "/api/app/login")
        c.putheader("Transfer-Encoding", "chunked")
        c.putheader("Content-Type", "application/json")
        c.endheaders(b"zz\r\nabc\r\n")
        r = c.getresponse()
        assert r.status == 400, r.status
        c.close()
    finally:
        ingress.SUPERVISOR_IP = saved_ip
        if saved_env is None:
            os.environ.pop("ZALO_PC_INGRESS", None)
        else:
            os.environ["ZALO_PC_INGRESS"] = saved_env
        httpd.shutdown()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("ALL INGRESS TESTS PASSED")
