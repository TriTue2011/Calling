"""Stale-while-revalidate tests (sửa lỗi load lại chậm 2026-11-05).

Lỗi: sau khi làm mới trang, danh bạ hiện ra rất chậm — vì
/api/contacts gọi tươi lên Zalo và BẮT TRÌNH DUYỆT CHỜ (Zalo chậm
hoặc đang 429 thì trang treo lâu). Hành vi mới pin ở đây:
  - hết TTL nhưng CÓ cache -> trả cache cũ NGAY (source "stale",
    stale=true), làm mới nền trong thread riêng; lần load sau thấy
    dữ liệu mới. Kể cả khi Zalo chậm (mock slow_seconds) thì lần
    trả stale vẫn nhanh.
  - hoàn toàn CHƯA có cache -> vẫn chờ gọi tươi (không có gì để
    trả ngay).
  - ?force=1 (nút "Tải lại" có chủ đích) -> vẫn gọi tươi đồng bộ
    như cũ (người dùng đã chủ đích chờ), nhưng vẫn tôn trọng
    backoff 429.
  - đang backoff 429 -> trả cache-after-429 như cũ, KHÔNG làm mới
    nền thêm (không gọi Zalo thêm trong backoff).
  - làm mới nền dính 429 -> cache cũ vẫn còn, backoff được đặt,
    lần load sau trả cache-after-429.
  - đăng xuất trong lúc làm mới nền đang chạy -> kết quả nền bị
    bỏ, không hồi sinh cache của phiên cũ.
  - nhiều load cùng lúc khi cache đã hết TTL -> chỉ MỘT lần làm
    mới nền (không dội Zalo).
Chạy qua HTTP API thật (/api/contacts) với MockZalo. Không đăng
nhập thật, không gọi thật bằng tài khoản nào.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
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
        with urllib.request.urlopen(req, timeout=20) as resp:
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
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-swr-test-")
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


def _age_cache_past_ttl(state):
    state._contacts_cache["fetched_at"] -= (
        app_server.CONTACTS_TTL_SECONDS + 1)


def _wait_until(fn, deadline_seconds=15, what="condition"):
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(0.2)
    raise AssertionError("timed out waiting for: %s" % what)


def test_stale_returns_immediately_while_zalo_slow():
    """Hết TTL + Zalo chậm 2 giây/endpoint: load trả cache cũ NGAY
    (dưới 1,5 giây — không chờ 3 lần gọi tươi ~6 giây), rồi làm
    mới nền xong thì lần load sau thấy dữ liệu mới."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["source"] == "fresh", body
        assert _friends_calls(mock) == 1, mock.seen
        mock.slow_seconds = 2
        _age_cache_past_ttl(state)
        t0 = time.time()
        status, body = _api(base, "GET", "/api/contacts")
        elapsed = time.time() - t0
        assert status == 200, body
        assert body["source"] == "stale" and body["stale"] is True, body
        assert [r["name"] for r in body["friends"]["rows"]] == \
            ["Ban A", "Ban B", "Ban C"], body
        assert elapsed < 1.5, "stale load waited for Zalo: %.2fs" % elapsed
        # Làm mới nền chạy xong (3 endpoint x 2 giây) thì lần load
        # sau trả cache mới, không còn stale. Chờ cả 3 endpoint
        # đều gọi lần 2 — friends==2 một mình chỉ chứng tỏ lần làm
        # mới đã BẮT ĐẦU, chưa xong (friends là cuộc gọi đầu tiên).
        _wait_until(lambda: _friends_calls(mock) == 2
                    and _groups_v4_calls(mock) == 2
                    and _group_info_calls(mock) == 2,
                    15, "background refresh to finish all 3 calls")
        _wait_until(lambda: _api(base, "GET", "/api/contacts")[1]
                    .get("source") == "cache",
                    10, "next load to serve the refreshed cache")
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert body["source"] == "cache" and body["stale"] is False, body
        assert body["friends"]["rows"], body
    finally:
        _teardown(mock, httpd)


def test_no_cache_waits_for_fresh():
    """Chưa có cache thì KHÔNG có gì để trả ngay: load phải chờ
    gọi tươi (Zalo chậm 2 giây -> load mất ít nhất ~1,5 giây)
    và trả dữ liệu tươi."""
    mock, httpd, base, state = _setup()
    try:
        mock.slow_seconds = 2
        t0 = time.time()
        status, body = _api(base, "GET", "/api/contacts")
        elapsed = time.time() - t0
        assert status == 200, body
        assert body["source"] == "fresh" and body["stale"] is False, body
        assert body["friends"]["rows"], body
        assert elapsed >= 1.5, \
            "no-cache load returned too fast: %.2fs" % elapsed
        assert _friends_calls(mock) == 1, mock.seen
    finally:
        _teardown(mock, httpd)


def test_force_refresh_is_synchronous_despite_stale():
    """?force=1 khi cache đã hết TTL: vẫn gọi tươi ĐỒNG BỘ (trả
    fresh, chờ Zalo chậm) — nút "Tải lại" là chủ đích lấy mới
    ngay, không ăn cache cũ."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["source"] == "fresh", body
        mock.slow_seconds = 2
        _age_cache_past_ttl(state)
        t0 = time.time()
        status, body = _api(base, "GET", "/api/contacts?force=1")
        elapsed = time.time() - t0
        assert status == 200, body
        assert body["source"] == "fresh" and body["stale"] is False, body
        assert elapsed >= 1.5, \
            "force load returned too fast: %.2fs" % elapsed
        assert _friends_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


def test_stale_in_backoff_no_background_refresh():
    """Hết TTL nhưng đang backoff 429: trả cache-after-429 như cũ
    và KHÔNG làm mới nền (không gọi Zalo thêm trong backoff)."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        mock.friends_mode = "rate429"
        status, body = _api(base, "GET", "/api/contacts?force=1")
        assert status == 200 and body["source"] == "cache-after-429", body
        assert _friends_calls(mock) == 2, mock.seen
        _age_cache_past_ttl(state)
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert body["source"] == "cache-after-429", body
        assert body["retry_after_seconds"] > 0, body
        assert _friends_calls(mock) == 2, mock.seen
        time.sleep(1.5)
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["source"] == "cache-after-429", body
        assert _friends_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


def test_background_refresh_429_keeps_cache_and_sets_backoff():
    """Làm mới nền dính 429: lần trả stale ban đầu vẫn có dữ liệu
    cũ; sau khi nền thất bại, cache cũ vẫn còn và backoff được
    đặt — lần load sau trả cache-after-429 kèm thời gian chờ."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        _age_cache_past_ttl(state)
        mock.friends_mode = "rate429"
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert body["source"] == "stale" and body["stale"] is True, body
        assert [r["name"] for r in body["friends"]["rows"]] == \
            ["Ban A", "Ban B", "Ban C"], body
        _wait_until(
            lambda: state._contacts_backoff_until > time.time(),
            10, "background refresh to set the 429 backoff")
        assert _friends_calls(mock) == 2, mock.seen
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        assert body["source"] == "cache-after-429", body
        assert body["rate_limited"] is True, body
        assert body["retry_after_seconds"] > 0, body
        assert [r["name"] for r in body["friends"]["rows"]] == \
            ["Ban A", "Ban B", "Ban C"], body
    finally:
        _teardown(mock, httpd)


def test_logout_discards_background_refresh():
    """Đăng xuất trong lúc làm mới nền đang chạy (Zalo chậm):
    kết quả nền bị bỏ, cache không hồi sinh cho phiên đã đăng
    xuất; /api/contacts sau đó đòi đăng nhập (401)."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        mock.slow_seconds = 2
        _age_cache_past_ttl(state)
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200 and body["source"] == "stale", body
        assert state._contacts_refreshing is True
        status, body = _api(base, "POST", "/api/logout", {})
        assert status == 200 and body["ok"] is True, body
        assert state._contacts_cache is None, state._contacts_cache
        _wait_until(lambda: state._contacts_refreshing is False,
                    15, "background refresh thread to finish")
        assert state._contacts_cache is None, state._contacts_cache
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 401, body
    finally:
        _teardown(mock, httpd)


def test_concurrent_stale_loads_share_one_refresh():
    """Ba load cùng lúc khi cache đã hết TTL: cả ba đều trả stale
    ngay, nhưng chỉ MỘT lần làm mới nền chạy (friends chỉ gọi
    thêm đúng 1 lần, không dội 3 lần)."""
    mock, httpd, base, state = _setup()
    try:
        status, body = _api(base, "GET", "/api/contacts")
        assert status == 200, body
        mock.slow_seconds = 1
        _age_cache_past_ttl(state)
        results = []

        def _load():
            results.append(_api(base, "GET", "/api/contacts"))

        threads = [threading.Thread(target=_load) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        assert len(results) == 3, results
        for status, body in results:
            assert status == 200, body
            assert body["source"] == "stale", body
        _wait_until(lambda: _friends_calls(mock) == 2,
                    15, "the single shared background refresh")
        time.sleep(0.5)
        assert _friends_calls(mock) == 2, mock.seen
    finally:
        _teardown(mock, httpd)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL CONTACTS STALE-WHILE-REVALIDATE TESTS PASSED")
