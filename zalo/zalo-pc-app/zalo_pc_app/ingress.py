"""Home Assistant Ingress: cho giao dien app hien ngay trong bang ben HA (add-on).

Supervisor chuyen tiep /api/hassio_ingress/<token>/... toi app (cat tien to di) va them
header X-Ingress-Path. Trinh duyet thi van dung tien to do, nen moi duong dan tuyet doi
trong giao dien ("/api/...", "/ui/app.js") se lac ra goc cua HA. Module nay lo ba viec:

1. TIN CAY: chi tin yeu cau den tu Supervisor (172.30.32.2) mang header X-Ingress-Path hop le,
   va chi khi ZALO_PC_INGRESS bat. Nguoi dung da dang nhap HA nen khong hoi mat khau lan nua.
   Yeu cau tu LAN (cong 8080 mo ra ngoai) van phai dang nhap nhu thuong.
2. VIET LAI: HTML (href/src/action) va CSS (url(/...)) duoc gan tien to; mot doan shim chen vao
   dau trang va bao pho fetch / XHR / thuoc tinh src, href, action / window.open de cac duong
   dan do bang JS tu gan tien to. Khong co danh sach tu khoa: moi duong dan tuyet doi dang
   "/x" (khong phai "//x") deu duoc gan.
3. THAN POST CHUNKED: Ingress gui lai thân POST bang Transfer-Encoding: chunked, khong co
   Content-Length. do_POST doc theo Content-Length nen se mat than; read_chunked gom lai.
"""

import os
import re

SUPERVISOR_IP = "172.30.32.2"
PREFIX_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]{8,128}$")
MAX_BODY = 64 * 1024 * 1024  # tep gui qua Zalo toi da cung cap nay


def enabled(env=None):
    """Bat bang ZALO_PC_INGRESS=1 (add-on tu dat). Mac dinh TAT: Docker thuong khong co Supervisor."""
    v = (os.environ if env is None else env).get("ZALO_PC_INGRESS", "")
    return v.strip().lower() in ("1", "true", "yes", "on")


def prefix_for(client_ip, headers, env=None):
    """Tien to ingress cua yeu cau nay, hoac "" neu khong phai yeu cau ingress DANG TIN.

    Dieu kien: bat ZALO_PC_INGRESS, nguon la Supervisor, header co dang /api/hassio_ingress/<token>.
    Thieu mot dieu kien la "" (giu nguyen hanh vi cu, buoc dang nhap)."""
    if not enabled(env) or client_ip != SUPERVISOR_IP:
        return ""
    p = (headers.get("X-Ingress-Path") or "").strip().rstrip("/")
    return p if PREFIX_RE.match(p) else ""


def read_chunked(rfile, maximum=MAX_BODY):
    """Gom than POST gui bang Transfer-Encoding: chunked thanh bytes.

    Quá `maximum` thi dung doc va tra None (nguoi goi dong ket noi); than hong cung None."""
    body = bytearray()
    while True:
        line = rfile.readline(72)
        if not line:
            return None
        try:
            size = int(line.split(b";", 1)[0].strip(), 16)
        except ValueError:
            return None
        if size == 0:
            while rfile.readline(72).strip():  # bo phan trailer
                pass
            return bytes(body)
        if len(body) + size > maximum:
            return None
        chunk = rfile.read(size)
        if len(chunk) != size:
            return None
        body.extend(chunk)
        rfile.read(2)  # CRLF sau moi khoi


_ATTR_RE = re.compile(r'(\b(?:href|src|action)\s*=\s*)(["\'])/(?!/)')
_CSS_URL_RE = re.compile(r"(url\(\s*)([\"']?)/(?!/)")


def rewrite_html(text, prefix):
    """Gan tien to cho moi href/src/action tuyet doi, roi chen shim ngay sau <head>."""
    out = _ATTR_RE.sub(lambda m: "%s%s%s/" % (m.group(1), m.group(2), prefix), text)
    shim = "<script>%s</script>" % shim_js(prefix)
    i = out.lower().find("<head>")
    if i >= 0:
        return out[:i + 6] + shim + out[i + 6:]
    return shim + out


def rewrite_css(text, prefix):
    return _CSS_URL_RE.sub(lambda m: "%s%s%s/" % (m.group(1), m.group(2), prefix), text)


def shim_js(prefix):
    """Doan JS chay truoc moi script khac. `prefix` da qua PREFIX_RE nen chi gom [A-Za-z0-9_/-]."""
    return ("(function(){var P=%r;window.__zIng=P;"
            "function fix(u){return(typeof u==='string'&&u.charAt(0)==='/'&&u.charAt(1)!=='/'"
            "&&u.indexOf(P+'/')!==0)?P+u:u}"
            "var F=window.fetch;if(F)window.fetch=function(i,o){return F.call(this,fix(i),o)};"
            "var X=XMLHttpRequest.prototype.open;"
            "XMLHttpRequest.prototype.open=function(m,u){arguments[1]=fix(u);return X.apply(this,arguments)};"
            "function prop(C,n){var d=Object.getOwnPropertyDescriptor(C.prototype,n);"
            "if(d&&d.set)Object.defineProperty(C.prototype,n,{configurable:true,enumerable:d.enumerable,"
            "get:d.get,set:function(v){d.set.call(this,fix(v))}})}"
            "[[HTMLImageElement,'src'],[HTMLMediaElement,'src'],[HTMLSourceElement,'src'],"
            "[HTMLScriptElement,'src'],[HTMLAnchorElement,'href'],[HTMLLinkElement,'href'],"
            "[HTMLFormElement,'action'],[HTMLIFrameElement,'src']].forEach(function(a){prop(a[0],a[1])});"
            "var S=Element.prototype.setAttribute;"
            "Element.prototype.setAttribute=function(n,v){"
            "if(/^(src|href|action)$/i.test(n))v=fix(v);return S.call(this,n,v)};"
            "var E=window.EventSource;if(E){var NE=function(u,o){return new E(fix(u),o)};NE.prototype=E.prototype;"
            "NE.CONNECTING=0;NE.OPEN=1;NE.CLOSED=2;window.EventSource=NE}"
            "var O=window.open;window.open=function(u){arguments[0]=fix(u);return O.apply(window,arguments)};"
            "})();") % prefix
