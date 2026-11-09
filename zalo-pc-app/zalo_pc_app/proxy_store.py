"""Danh sách proxy HTTP/HTTPS cho đường gọi ra Zalo của app.

Lưu ở <data>/proxy.json (chế độ 0600, vì URL có thể chứa user:mật khẩu).
Chỉ áp cho các cuộc gọi HTTPS tới Zalo (báo hiệu, tin nhắn, danh bạ);
media UDP của cuộc gọi không đi qua proxy HTTP được. Không bao giờ trả
mật khẩu proxy ra ngoài: danh sách công khai chỉ có scheme://host:port.
"""
import json
import os
import secrets
import threading
import urllib.parse

FILENAME = "proxy.json"
MAX_ITEMS = 20
MAX_URL_LEN = 300


def validate_proxy_url(value):
    """Trả URL đã chuẩn hóa, hoặc ném ValueError nêu rõ lỗi."""
    if not isinstance(value, str):
        raise ValueError("URL proxy phải là chuỗi")
    value = value.strip()
    if not value or len(value) > MAX_URL_LEN or any(c.isspace() for c in value):
        raise ValueError("URL proxy rỗng, quá dài hoặc có khoảng trắng")
    if "://" not in value:
        value = "http://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Chỉ hỗ trợ proxy http:// hoặc https:// (không có socks)")
    if not parsed.hostname:
        raise ValueError("URL proxy thiếu địa chỉ máy")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Cổng proxy không hợp lệ")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Cổng proxy phải từ 1 đến 65535")
    return value


def display_of(url):
    """scheme://host:port — không có user:mật khẩu."""
    p = urllib.parse.urlparse(url)
    host = p.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    return "%s://%s%s" % (p.scheme, host, (":%d" % p.port) if p.port else "")


class ProxyStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        items = [i for i in (data.get("items") or [])
                 if isinstance(i, dict) and i.get("id") and i.get("url")]
        active = data.get("active") or ""
        if active not in {i["id"] for i in items}:
            active = ""
        return {"items": items, "active": active}

    def _save(self, data):
        tmp = self.path + ".tmp"
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def public(self):
        with self._lock:
            data = self._load()
        return {"active": data["active"], "items": [
            {"id": i["id"], "name": i.get("name") or "", "display": display_of(i["url"]),
             "has_auth": "@" in urllib.parse.urlparse(i["url"]).netloc}
            for i in data["items"]]}

    def add(self, url, name=""):
        url = validate_proxy_url(url)
        with self._lock:
            data = self._load()
            if len(data["items"]) >= MAX_ITEMS:
                raise ValueError("Tối đa %d proxy" % MAX_ITEMS)
            if any(i["url"] == url for i in data["items"]):
                raise ValueError("Proxy này đã có trong danh sách")
            pid = secrets.token_hex(4)
            data["items"].append({"id": pid, "name": str(name or "")[:60], "url": url})
            self._save(data)
            return pid

    def remove(self, pid):
        with self._lock:
            data = self._load()
            data["items"] = [i for i in data["items"] if i["id"] != pid]
            if data["active"] == pid:
                data["active"] = ""
            self._save(data)

    def set_active(self, pid):
        with self._lock:
            data = self._load()
            if pid and pid not in {i["id"] for i in data["items"]}:
                raise ValueError("Không có proxy này")
            data["active"] = pid or ""
            self._save(data)

    def url_of(self, pid):
        with self._lock:
            for i in self._load()["items"]:
                if i["id"] == pid:
                    return i["url"]
        return ""

    def active_url(self):
        with self._lock:
            data = self._load()
        for i in data["items"]:
            if i["id"] == data["active"]:
                return i["url"]
        return ""
