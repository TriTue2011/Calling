"""Contacts cache + 429 backoff tests (sửa lỗi 429, 2026-11-05).

Nguyên nhân gốc (log thật 17:37 +07 ngày 05/11): /api/contacts gọi
lại Zalo tươi MỖI lần load, không cache — 7 khối [contacts-shape]
giống hệt nhau liên tiếp (friends len=60 + groups v4 len=6 +
getmg-v2 len=6) dội vào Zalo tới 7 lần, tới khi friends trả 429.
Các test này pin hành vi sửa:
  - load thường trong TTL trả cache, không gọi Zalo lần 2;
  - ?force=1 (nút "Tải lại") bỏ qua TTL nhưng không bỏ qua backoff;
  - hết TTL thì gọi tươi lại;
  - 429 có cache -> trả cache + retry_after_seconds, không báo lỗi khô;
  - 429 không cache -> 429 + retry_after_seconds;
  - trong backoff không gọi Zalo thêm dù bấm tải lại (kể cả force);
  - 429 liên tiếp thì backoff gấp đôi (60 -> 120), tối đa 300;
  - lỗi không phải 429 (602) vẫn báo đúng endpoint và không làm
    bẩn cache; logout xóa cache.
Chạy qua HTTP API thật (/api/contacts) với MockZalo ở chế độ
"rate429" (HTTP 429 thật, đúng dạng log live). Không đăng nhập
thật, không gọi thật bằng tài khoản nào.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def _api(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _login_via_qr(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            return
        time.sleep(0.5)
    raise AssertionError("qr did not reach done: %s" % last)


def _setup():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-429-test-")
    mock = MockZalo().start()
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port
    _login_via_qr(base)
    return mock, httpd, base, state


def _teardown(mock, httpd):
    httpd.shutdown()
    mock.stop()


def _count(mock, path):
    return len([1 for p, _, _ in mock.seen if p == path])


def _friends_calls(mock):
    return _count(mock, "/api/social/friend/getfriends")


def _groups_v4_calls(mock):
    return _count(mock, "/api/group/getlg/v4")


def _group_info_calls(mock):
    return _count(mock, "/api/group/getmg-v2")


def test_cache_hit_no_second_zalo_call():
    """Hai lần load thường liên tiếp: chỉ lần đầu gọi Zalo tươi
    (1 friends + 1 v4 + 1 getmg-v2); lần 2 trả cache, mock không
    thấy thêm cuộc gọi nào. Đây chính là sửa cho 7 lần dội."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert body["cached"] is False and body["source"] == "fresh", body
        assert body["rate_limited"] is False, body
        assert body["retry_after_seconds"] == 0, body
        assert isinstance(body["fetched_at"], int), body
        assert [r["name"] for r in body["friends"]["rows"]] == \
            ["Ban A", "Ban B", "Ban C"], body
        assert _friends_calls(mock) == 1, mock.seen
        assert _groups_v4_calls(mock) == 1, mock.seen
        assert _group_info_calls(mock) == 1, mock.seen
        status, body2 = _api(base, "GET", "/api/contacts")
        assert status == 200, body2
        assert body2["cached"] is True and body2["source"] == "cache", body2
        assert body2["fetched_at"] == body["fetched_at"], body2
        assert body2["friends"]["rows"] == body["friends"]["rows"], body2
        assert body2["groups"]["rows"] == body["groups"]["rows"], body2
        assert _friends_calls(mock) == 1, mock.seen
        assert _groups_v4_calls(mock) == 1, mock.seen
        assert _group_info_calls(mock) == 1, mock.seen
    finally:
        _teardown(mock, httpd)


def test_force_refresh_bypasses_ttl():
    """?force=1 (nút "Tải lại") bỏ qua TTL: gọi tươi lại ngay cả
    khi cache còn mới, và response lại là fresh."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 200, body
        assert body["cached"] is False and body["source"] == "fresh", body
        assert _friends_calls(mock) == 2, mock.seen
        assert _groups_v4_calls(mock) == 2, mock.seen
        assert _group_info_calls(mock) == 2, mock.seen
        # Load thường sau đó lại trả cache (của lần force vừa rồi).
        status, body = _api(base, "GET", "/api/contacts")
        assert body["cached"] is True and body["source"] == "cache", body
        assert _friends_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


def test_ttl_expiry_refetches():
    """Hết TTL (120 giây) thì load thường KHÔNG chờ gọi tươi nữa
    (stale-while-revalidate, sửa lỗi load chậm 2026-11-05): trả
    cache cũ ngay (source "stale", stale=true) và làm mới nền;
    lần load sau đó thấy dữ liệu mới (cache của lần làm mới nền).
    Giả lập thời gian trôi bằng cách lùi fetched_at của cache
    (không ngủ 120 giây thật)."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert _friends_calls(mock) == 1, mock.seen
        state._contacts_cache["fetched_at"] -= (
            app_server.CONTACTS_TTL_SECONDS + 1)
        old_fetched_at = state._contacts_cache["fetched_at"]
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert body["cached"] is True and body["source"] == "stale", body
        assert body["stale"] is True, body
        assert body["fetched_at"] == int(old_fetched_at), body
        # Trả ngay: lần làm mới nền chưa kịp chạy xong lúc này
        # (mock chưa thấy thêm cuộc gọi nào cũng được chấp nhận —
        # chỉ cần lần load SAU thấy dữ liệu mới).
        deadline = time.time() + 10
        while time.time() < deadline:
            status, body = _api(base, "GET", "/api/contacts")
            assert status == 200, body
            if body["source"] in ("fresh", "cache") \
                    and _friends_calls(mock) == 2:
                break
            time.sleep(0.2)
        else:
            raise AssertionError(
                "background refresh did not finish: %s" % body)
        assert _friends_calls(mock) == 2, mock.seen
        assert _groups_v4_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


def test_429_with_cache_returns_cache_and_backoff():
    """429 khi đã có cache: trả 200 với danh bạ cũ + báo chờ 60 giây
    (source cache-after-429, rate_limited), KHÔNG báo lỗi khô.
    Trong backoff, bấm tải lại (kể cả force) cũng không gọi Zalo
    thêm lần nào nữa."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert _friends_calls(mock) == 1, mock.seen
        mock.friends_mode = "rate429"
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 200, body
        assert body["cached"] is True, body
        assert body["source"] == "cache-after-429", body
        assert body["rate_limited"] is True, body
        assert body["retry_after_seconds"] == 60, body
        assert [r["name"] for r in body["friends"]["rows"]] == \
            ["Ban A", "Ban B", "Ban C"], body
        # Lần force này đã thử Zalo 1 lần và dính 429.
        assert _friends_calls(mock) == 2, mock.seen
        # Bấm tải lại nữa trong backoff: không gọi Zalo thêm.
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 200 and body["source"] == "cache-after-429", body
        assert body["retry_after_seconds"] > 0, body
        assert _friends_calls(mock) == 2, mock.seen
        # Load thường trong backoff cũng vậy.
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["cached"] is True, body
        assert _friends_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


def test_429_groups_returns_cache():
    """429 ở phía groups (sau khi friends tươi đã thành công): vẫn
    trả toàn bộ cache cũ, không trộn nửa tươi nửa cũ, và vẫn báo chờ."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        mock.groups_mode = "rate429"
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 200, body
        assert body["source"] == "cache-after-429", body
        assert body["rate_limited"] is True, body
        assert body["retry_after_seconds"] == 60, body
        assert [r["name"] for r in body["groups"]["rows"]] == \
            ["Nhom X", "Nhom Y"], body
        # Friends tươi đã chạy 1 lần rồi mới dính 429 ở groups.
        assert _friends_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


def test_429_without_cache_returns_429_with_retry_after():
    """429 khi CHƯA có cache: không có gì để trả, nên trả 429 kèm
    retry_after_seconds=60 (không phải lỗi khô không thời gian chờ).
    Trong backoff không gọi Zalo thêm; hết backoff thì gọi lại được."""
    mock, httpd, base, state = _setup()
    try:
        mock.friends_mode = "rate429"
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 429, body
        assert body["rate_limited"] is True, body
        assert body["retry_after_seconds"] == 60, body
        assert "429" in body["error"], body
        assert _friends_calls(mock) == 1, mock.seen
        # Zalo hết 429 nhưng vẫn trong backoff: vẫn 429, không gọi.
        mock.friends_mode = "ok"
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 429, body
        assert _friends_calls(mock) == 1, mock.seen
        # Hết backoff (giả lập thời gian trôi): gọi tươi thành công.
        state._contacts_backoff_until = 0
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert body["source"] == "fresh", body
        assert body["friends"]["rows"], body
        assert _friends_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


def test_backoff_doubles_on_consecutive_429():
    """429 liên tiếp: lần chờ thứ hai là 120 giây (60 gấp đôi),
    không phải 60 mãi — ngăn việc bấm tải lại kéo dài cơn 429."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        mock.friends_mode = "rate429"
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 200 and body["retry_after_seconds"] == 60, body
        # Hết backoff lần 1, vẫn 429: lần chờ thứ hai gấp đôi.
        state._contacts_backoff_until = 0
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 200, body
        assert body["source"] == "cache-after-429", body
        assert body["retry_after_seconds"] == 120, body
    finally:
        _teardown(mock, httpd)


def test_non429_error_not_cached_and_still_attributed():
    """Lỗi 602 (không phải 429) vẫn báo đúng endpoint với 502 và
    KHÔNG làm bẩn cache: lần sau gọi lại vẫn tươi bình thường."""
    mock, httpd, base, state = _setup()
    try:
        mock.friends_mode = "error602"
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 502 and "friends:" in body["error"], body
        assert "602" in body["error"], body
        assert state._contacts_cache is None, state._contacts_cache
        mock.friends_mode = "ok"
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["source"] == "fresh", body
        assert body["friends"]["rows"], body
        mock.groups_mode = "error602"
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 502 and "groups:" in body["error"], body
        # Cache cũ vẫn còn nguyên sau lỗi groups (không bị ghi đè
        # bằng dữ liệu nửa vời).
        assert state._contacts_cache is not None, state._contacts_cache
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["source"] == "cache", body
    finally:
        _teardown(mock, httpd)


def test_logout_clears_cache_and_backoff():
    """Đăng xuất xóa cache + backoff của phiên cũ; sau đó
    /api/contacts đòi đăng nhập (401), không trả cache của phiên cũ."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert state._contacts_cache is not None
        mock.friends_mode = "rate429"
        _api(base, "GET", "/api/contacts?force=1")
        assert state._contacts_backoff_until > 0
        status, body = _api(base, "POST", "/api/logout", {})
        assert status == 200 and body["ok"] is True, body
        assert state._contacts_cache is None, state._contacts_cache
        assert state._contacts_backoff_until == 0
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 401, body
    finally:
        _teardown(mock, httpd)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CONTACTS CACHE/429 TESTS PASSED")
