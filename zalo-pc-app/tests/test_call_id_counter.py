"""callId counter nho tang dan (deep comparison §5.1 — nghi ngo cao
nhat cho vu goi khong do chuong).

Engine PC that dung counter tang dan nho (1, 2, 3, ... qua `lock
xadd`) lam callId; app cu dung epoch seconds (~1,7 ti). Server chap
nhan ca hai (status=0) nhung callId la identity cua cuoc goi — server
dung no de tuong quan 11300<->11301 va bao cho peer — nen peer co the
xu ly khac nhau. Server phai cap callId tu counter noi bo cua process
(bat dau 1, tang moi cuoc goi, don dieu, thread-safe) va BO QUA gia
tri UI gui len — giong nhu type_request khong duoc tin (xem
_type_request_for). Cac test nay PHAI FAIL o code cu (epoch seconds)
va PASS o code moi.
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

from mock_server import MockZalo  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402


def _reset():
    # Counter la module-global, song suot process test: reset truoc
    # moi test de ket qua khong phu thuoc thu tu chay.
    app_server._CALL_ID_COUNTER = 0


def test_counter_starts_at_one():
    """Cuoc goi dau tien cua process co callId = 1 (nhu engine)."""
    _reset()
    assert app_server._normalize_call_id(None) == 1
    assert app_server._normalize_call_id(1762345678) == 2
    assert app_server._normalize_call_id("c9") == 3


def test_counter_increments_monotonically():
    """Moi cuoc goi nhan id lon hon cuoc truoc mot don vi, don dieu."""
    _reset()
    ids = [app_server._normalize_call_id(None) for _ in range(5)]
    assert ids == [1, 2, 3, 4, 5], ids


def test_counter_ignores_ui_values():
    """Gia tri UI gui len (epoch seconds, chuoi mili-giay, rac,
    thieu, vuot uint32) deu bi bo qua — server luon cap counter.
    Day la diem khac co ban voi code cu (giu nguyen gia tri hop le
    cua UI, fallback epoch seconds khi khong hop le)."""
    _reset()
    assert app_server._normalize_call_id(1762345678) == 1
    assert app_server._normalize_call_id("1762345678000") == 2
    assert app_server._normalize_call_id("c9") == 3
    assert app_server._normalize_call_id("") == 4
    assert app_server._normalize_call_id(None) == 5
    assert app_server._normalize_call_id(2 ** 32) == 6
    assert app_server._normalize_call_id(0) == 7
    assert app_server._normalize_call_id(-5) == 8


def test_counter_is_small_uint32():
    """Id cap ra la JSON number uint32 hop le, va NHO nhu engine
    (khong phai epoch seconds ~1,7 ti)."""
    _reset()
    for _ in range(10):
        value = app_server._normalize_call_id(None)
        assert isinstance(value, int), value
        assert 1 <= value <= 2 ** 32 - 1, value
        assert value < 1000000, value


def test_counter_thread_safe():
    """8 thread cap dong thoi: khong trung, khong sot — dung tap
    1..200 day du (khoa bao ve counter)."""
    _reset()
    got = []
    lock = threading.Lock()

    def _mint_many():
        local = [app_server._normalize_call_id(None) for _ in range(25)]
        with lock:
            got.extend(local)

    threads = [threading.Thread(target=_mint_many) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(got) == 200, len(got)
    assert sorted(got) == list(range(1, 201)), sorted(got)[:10]


# ------------------------------------------------------------------ e2e
# Drive the real app HTTP API (same harness shape as
# test_call_11301.py): QR login against the mock, then POST
# /api/call/request with an epoch-seconds call_id and check the
# server mints a SMALL counter id, used consistently for the call.

def _start_app(mock):
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-callid-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    os.environ["ZALO_PC_PORT"] = "0"
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    app_server.PARAM_CIPHER_KEY = "TEST_PARAM_KEY_32_CHARS_LONG_XXX"
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % port


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


def _login(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def test_request_mints_small_call_id_e2e():
    """POST /api/call/request voi call_id epoch seconds -> response
    tra call_id NHO (counter), va mock thay requestcall dung id do:
    mot cuoc goi giu mot id xuyen suot 11300 (va 11301 khi co)."""
    _reset()
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        status, body = _api(base, "POST", "/api/call/request",
                            {"callee_id": "20001",
                             "call_id": 1762345678})
        assert body["ok"] is True, body
        eff_id = body["call_id"]
        assert isinstance(eff_id, int), body
        assert 1 <= eff_id < 1000000, body
        assert eff_id != 1762345678, body
        state = mock.voice_call_state(eff_id)
        assert state["requested"] is True, state
        # Cuoc goi thu hai nhan id lon hon cuoc truoc mot don vi.
        status, body2 = _api(base, "POST", "/api/call/request",
                             {"callee_id": "20002",
                              "call_id": 1762345679})
        assert body2["ok"] is True, body2
        assert body2["call_id"] == eff_id + 1, body2
        httpd.shutdown()
    finally:
        try:
            app_server.STATE.stop_sync()
        except Exception:  # noqa: BLE001 - teardown best-effort
            pass
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001 - teardown best-effort
                pass
        mock.stop()


if __name__ == "__main__":
    failed = []
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed.append(fn.__name__)
            print("FAIL", fn.__name__, exc)
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("ALL PASSED")
