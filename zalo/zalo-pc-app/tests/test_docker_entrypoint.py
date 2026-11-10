"""Entrypoint: doc tuy chon add-on HA (options.json) thanh tai khoan dang nhap cua app."""

import importlib.util
import json
import os
import stat
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "docker_entrypoint", os.path.join(HERE, "..", "docker-entrypoint.py"))
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)


def _opts(d, data):
    p = os.path.join(d, "options.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return p


def test_khong_co_options_thi_khong_dong_vao_gi():
    with tempfile.TemporaryDirectory() as d:
        env = {}
        assert ep._apply_addon_options(env, os.path.join(d, "khong-co.json"), d) is None
        assert env == {}
        open(os.path.join(d, "hong.json"), "w").write("{ khong phai json")
        assert ep._apply_addon_options(env, os.path.join(d, "hong.json"), d) is None
        assert ep._apply_addon_options(env, _opts(d, ["list"]), d) is None
        assert env == {}


def test_tuy_chon_co_mat_khau_thanh_bien_moi_truong():
    with tempfile.TemporaryDirectory() as d:
        env = {}
        shown = ep._apply_addon_options(env, _opts(d, {"username": " tritue ", "password": "mk-that"}), d)
        assert shown is None                                   # mat khau do nguoi dung dat: khong in ra log
        assert env == {"ZALO_PC_APP_USER": "tritue", "ZALO_PC_APP_PASSWORD": "mk-that"}
        assert not os.path.exists(os.path.join(d, ep.LOGIN_INFO_NAME))


def test_bo_trong_mat_khau_thi_tu_sinh_giu_lai_va_khong_doi_khi_khoi_dong_lai():
    with tempfile.TemporaryDirectory() as d:
        opts = _opts(d, {"username": "", "password": ""})
        env1 = {}
        pw1 = ep._apply_addon_options(env1, opts, d)
        assert pw1 and len(pw1) >= 12
        assert env1["ZALO_PC_APP_USER"] == "admin" and env1["ZALO_PC_APP_PASSWORD"] == pw1
        info = os.path.join(d, ep.LOGIN_INFO_NAME)
        assert stat.S_IMODE(os.stat(info).st_mode) == 0o600     # tep chua mat khau chi chu so huu doc
        env2 = {}
        assert ep._apply_addon_options(env2, opts, d) == pw1     # khoi dong lai: cung mat khau
        assert env2["ZALO_PC_APP_PASSWORD"] == pw1


def test_bien_moi_truong_dat_san_thang_tuy_chon():
    with tempfile.TemporaryDirectory() as d:
        env = {"ZALO_PC_APP_USER": "tu-env", "ZALO_PC_APP_PASSWORD": "mk-env"}
        ep._apply_addon_options(env, _opts(d, {"username": "khac", "password": "khac"}), d)
        assert env == {"ZALO_PC_APP_USER": "tu-env", "ZALO_PC_APP_PASSWORD": "mk-env"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL ENTRYPOINT TESTS PASSED")
