"""Doi mat khau app tu WebUI: ham loi, giu qua khoi dong lai, va qua HTTP that.

Mat khau trong file nay chi la du lieu gia cho test.
"""

import json
import os
import stat
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
USER, PW1, PW2, PW3 = "nguoi-dung-test", "mat-khau-cu-111", "mat-khau-moi-222", "mat-khau-moi-333"

tmp = tempfile.mkdtemp(prefix="zalo-pc-app-pwchange-")
os.environ["ZALO_PC_DATA_DIR"] = tmp
os.environ["ZALO_PC_APP_USER"] = USER
os.environ["ZALO_PC_APP_PASSWORD"] = PW1
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)

from zalo_pc_app import app_auth  # noqa: E402
from zalo_pc_app import server as sv  # noqa: E402


def _env(**kw):
    e = {"ZALO_PC_APP_USER": USER}
    e.update(kw)
    return e


def test_change_validates_and_revokes_other_sessions():
    d = tempfile.mkdtemp()
    a = app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=PW1))
    keep, _ = a.create_session(USER)
    other, _ = a.create_session(USER)
    for old, new, code in ((PW1 + "x", PW2, "sai_mat_khau_cu"), (PW1, "ngan", "mat_khau_qua_ngan"),
                           (PW1, "x" * 300, "mat_khau_qua_dai"), (PW1, PW1, "mat_khau_trung"),
                           (None, PW2, "sai_mat_khau_cu"), (PW1, None, "mat_khau_qua_ngan")):
        try:
            a.change_password(old, new, keep_token=keep)
        except app_auth.PasswordChangeError as exc:
            assert exc.code == code, (old, new, exc.code)
        else:
            raise AssertionError((old, new))
    assert a.verify(USER, PW1) and not a.verify(USER, PW2)          # that bai khong doi gi
    assert a.change_password(PW1, PW2, keep_token=keep) == 1         # thu hoi dung 1 phien khac
    assert a.validate_token(keep) == USER and a.validate_token(other) is None
    assert a.verify(USER, PW2) and not a.verify(USER, PW1)
    mode = stat.S_IMODE(os.stat(os.path.join(d, "app_auth.json")).st_mode)
    assert mode == 0o600, oct(mode)
    assert PW2 not in open(os.path.join(d, "app_auth.json")).read()  # khong luu ban ro


def test_ui_password_survives_restart_until_env_changes():
    d = tempfile.mkdtemp()
    a = app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=PW1))
    a.change_password(PW1, PW2)
    # Khoi dong lai voi CUNG env (mat khau cu trong .env): giu mat khau doi qua WebUI.
    b = app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=PW1))
    assert b.verify(USER, PW2) and not b.verify(USER, PW1)
    # Doi tiep qua WebUI roi khoi dong lai: van giu ban moi nhat.
    b.change_password(PW2, PW3)
    c = app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=PW1))
    assert c.verify(USER, PW3)
    # Chu may doi env sang mat khau KHAC: env thang (dat lai co chu dich).
    env2 = "mat-khau-env-moi-444"
    e = app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=env2))
    assert e.verify(USER, env2) and not e.verify(USER, PW3)
    # Va tu do giu env moi qua khoi dong.
    assert app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=env2)).verify(USER, env2)


def test_env_hash_mode_cannot_be_changed_in_ui():
    d = tempfile.mkdtemp()
    h = app_auth.hash_password(PW1)
    a = app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD_HASH=h))
    assert a.managed_by_env_hash is True
    try:
        a.change_password(PW1, PW2)
    except app_auth.PasswordChangeError as exc:
        assert exc.code == "managed_by_env"
    else:
        raise AssertionError("phai tu choi")
    assert a.verify(USER, PW1)


def test_legacy_verifier_file_still_loads():
    d = tempfile.mkdtemp()
    h = app_auth.hash_password(PW1)
    with open(os.path.join(d, "app_auth.json"), "w") as fh:
        json.dump({"password_hash": h}, fh)               # dinh dang cu (khong source/env_hash)
    a = app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=PW1))
    assert a.verify(USER, PW1)
    a.change_password(PW1, PW2)
    assert app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=PW1)).verify(USER, PW2)


class _Client:
    def __init__(self, base):
        self.base, self.cookie = base, ""

    def req(self, method, path, body=None):
        r = urllib.request.Request(self.base + path, method=method,
                                   data=json.dumps(body).encode() if body is not None else None)
        r.add_header("Content-Type", "application/json")
        if self.cookie:
            r.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                sc = resp.headers.get("Set-Cookie") or ""
                if sc.startswith("zalo_pc_app="):
                    self.cookie = sc.split(";", 1)[0]
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())


def test_http_endpoint_end_to_end():
    d = tempfile.mkdtemp()
    sv.STATE = sv.AppState(d, auth=app_auth.AppAuth.from_env(d, _env(ZALO_PC_APP_PASSWORD=PW1)))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sv.Handler)
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        a, b = _Client(base), _Client(base)
        assert a.req("POST", "/api/app/password", {})[0] == 401            # chua dang nhap
        assert a.req("POST", "/api/app/login", {"username": USER, "password": PW1})[0] == 200
        assert b.req("POST", "/api/app/login", {"username": USER, "password": PW1})[0] == 200
        assert a.req("GET", "/api/app/status")[1]["can_change_password"] is True
        st, r = a.req("POST", "/api/app/password", {"old_password": "sai-sai-sai", "new_password": PW2})
        assert st == 403 and r["error"] == "sai_mat_khau_cu"
        st, r = a.req("POST", "/api/app/password", {"old_password": PW1, "new_password": "ngan"})
        assert st == 400 and r["error"] == "mat_khau_qua_ngan"
        st, r = a.req("POST", "/api/app/password", {"old_password": PW1, "new_password": PW2})
        assert st == 200 and r == {"ok": True, "other_sessions_revoked": 1}, (st, r)
        assert a.req("GET", "/api/app/status")[1]["logged_in"] is True       # phien hien tai con
        assert b.req("GET", "/api/app/status")[1]["logged_in"] is False      # phien khac bi dang xuat
        fresh = _Client(base)
        assert fresh.req("POST", "/api/app/login", {"username": USER, "password": PW1})[0] == 401
        assert fresh.req("POST", "/api/app/login", {"username": USER, "password": PW2})[0] == 200
        # Che do HASH cua env: status bao khong doi duoc, endpoint tra 409.
        sv.STATE.auth.managed_by_env_hash = True
        assert a.req("GET", "/api/app/status")[1]["can_change_password"] is False
        st, r = a.req("POST", "/api/app/password", {"old_password": PW2, "new_password": PW3})
        assert st == 409 and r["error"] == "managed_by_env"
    finally:
        httpd.shutdown()


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s: %r" % (t.__name__, exc))
        else:
            print("PASS %s" % t.__name__)
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
