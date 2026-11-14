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



# ---- _auto_credentials: Docker thường (không add-on) — không đặt tài khoản thì tự sinh, biến rỗng = chưa đặt ----
def test_auto_khong_dat_gi_thi_tu_sinh_va_giu_lai_khi_khoi_dong_lai():
    with tempfile.TemporaryDirectory() as d:
        env = {}
        pw = ep._auto_credentials(env, d)
        assert pw and env["ZALO_PC_APP_USER"] == "admin" and env["ZALO_PC_APP_PASSWORD"] == pw
        info = os.path.join(d, ep.LOGIN_INFO_NAME)
        assert stat.S_IMODE(os.stat(info).st_mode) == 0o600                         # chỉ chủ đọc được
        assert "Mat khau: " + pw in open(info, encoding="utf-8").read()
        env2 = {}
        assert ep._auto_credentials(env2, d) is None                                # khởi động lại: dùng lại, KHÔNG sinh mới và KHÔNG in lại
        assert env2["ZALO_PC_APP_USER"] == "admin" and env2["ZALO_PC_APP_PASSWORD"] == pw


def test_auto_bien_rong_cua_compose_la_chua_dat_va_phai_duoc_thay():
    with tempfile.TemporaryDirectory() as d:
        env = {"ZALO_PC_APP_USER": "", "ZALO_PC_APP_PASSWORD": "", "ZALO_PC_APP_PASSWORD_HASH": ""}      # compose ${BIEN:-} cho ra chuỗi rỗng
        pw = ep._auto_credentials(env, d)
        assert pw and env["ZALO_PC_APP_USER"] == "admin" and env["ZALO_PC_APP_PASSWORD"] == pw, env     # trước đây setdefault KHÔNG thay được chuỗi rỗng
        env = {"ZALO_PC_APP_USER": "  ", "ZALO_PC_APP_PASSWORD": "  "}
        assert ep._auto_credentials(env, d) is None                                 # mật khẩu đã đặt (dù là khoảng trắng) là giá trị người dùng đặt: giữ nguyên; user khoảng trắng = chưa đặt
        assert env["ZALO_PC_APP_USER"] == "admin"


def test_auto_gia_tri_nguoi_dung_dat_luon_thang_va_khong_tao_tep():
    with tempfile.TemporaryDirectory() as d:
        env = {"ZALO_PC_APP_USER": "tritue", "ZALO_PC_APP_PASSWORD": "mk-that"}
        assert ep._auto_credentials(env, d) is None and env == {"ZALO_PC_APP_USER": "tritue", "ZALO_PC_APP_PASSWORD": "mk-that"}
        env = {"ZALO_PC_APP_PASSWORD_HASH": "$pbkdf2-sha256$1$a$b"}
        assert ep._auto_credentials(env, d) is None and "ZALO_PC_APP_USER" not in env      # có hash: không đụng gì (app tự báo nếu thiếu user)
        assert not os.path.exists(os.path.join(d, ep.LOGIN_INFO_NAME))


def test_auto_chi_dat_user_thi_sinh_mat_khau_cho_dung_user_do():
    with tempfile.TemporaryDirectory() as d:
        env = {"ZALO_PC_APP_USER": "chu-nha"}
        pw = ep._auto_credentials(env, d)
        assert pw and env["ZALO_PC_APP_USER"] == "chu-nha" and env["ZALO_PC_APP_PASSWORD"] == pw
        assert "Ten dang nhap: chu-nha" in open(os.path.join(d, ep.LOGIN_INFO_NAME), encoding="utf-8").read()
        env = {"ZALO_PC_APP_PASSWORD": "chi-co-mat-khau"}                           # chỉ đặt mật khẩu: user mặc định admin, giữ mật khẩu đã đặt
        assert ep._auto_credentials(env, d) is None and env["ZALO_PC_APP_USER"] == "admin" and env["ZALO_PC_APP_PASSWORD"] == "chi-co-mat-khau"


def test_auto_khong_ghi_duoc_thu_muc_du_lieu_van_chay_va_bao_loi():
    env = {}
    pw = ep._auto_credentials(env, "/proc/khong-ghi-duoc/x")
    assert pw and env["ZALO_PC_APP_PASSWORD"] == pw                                 # vẫn có mật khẩu cho lần chạy này (cảnh báo không lưu được ra stderr)


def test_addon_extras_bat_ingress_va_doi_webhook_url():
    with tempfile.TemporaryDirectory() as d:
        env = {}
        ep._apply_addon_extras(env, os.path.join(d, "khong-co.json"))          # Docker thuong (khong options.json): khong dong vao gi
        assert env == {}
        ep._apply_addon_extras(env, _opts(d, ["list"]))
        assert env == {}
        env = {}
        ep._apply_addon_extras(env, _opts(d, {"username": "a", "password": "b", "webhook_url": " http://ha:8123/api/webhook/x "}))
        assert env == {"ZALO_PC_INGRESS": "1", "ZALO_PC_WEBHOOK_URL": "http://ha:8123/api/webhook/x"}
        env = {}
        ep._apply_addon_extras(env, _opts(d, {"webhook_url": ""}))             # tuy chon trong: khong dat bien webhook
        assert env == {"ZALO_PC_INGRESS": "1"}


def test_addon_extras_bien_dat_san_thang_tuy_chon():
    with tempfile.TemporaryDirectory() as d:
        env = {"ZALO_PC_INGRESS": "0", "ZALO_PC_WEBHOOK_URL": "http://tu-env/"}
        ep._apply_addon_extras(env, _opts(d, {"webhook_url": "http://tu-tuy-chon/"}))
        assert env == {"ZALO_PC_INGRESS": "0", "ZALO_PC_WEBHOOK_URL": "http://tu-env/"}
        env = {"ZALO_PC_INGRESS": "", "ZALO_PC_WEBHOOK_URL": ""}                # rong (compose) = chua dat: duoc thay
        ep._apply_addon_extras(env, _opts(d, {"webhook_url": "http://tu-tuy-chon/"}))
        assert env == {"ZALO_PC_INGRESS": "1", "ZALO_PC_WEBHOOK_URL": "http://tu-tuy-chon/"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL ENTRYPOINT TESTS PASSED")
