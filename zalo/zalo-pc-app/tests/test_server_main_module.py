"""Lỗi 14/11/2026: container chạy `python3 -m zalo_pc_app.server` (mô-đun `__main__`), còn mã tách ở calls/ gọi `srv()` -> `from .. import server` nạp BẢN SAO THỨ HAI của
server.py (STATE, bộ đếm call_id riêng): «Kết thúc» báo no_live_call, call_id cuộc gọi đi về 1,2,3 (Zalo từ chối -101). Test chạy đúng kiểu `-m` trong tiến trình con.
Run: python3 tests/test_server_main_module.py"""
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..")
sys.path.insert(0, APP)


def test_srv_prefers_running_main_module():
    from zalo_pc_app.calls import _srv
    fake = types.ModuleType("__main__")
    fake.__spec__ = types.SimpleNamespace(name="zalo_pc_app.server")
    fake.STATE = object()
    old = sys.modules["__main__"]
    sys.modules["__main__"] = fake
    try:
        assert _srv.srv() is fake
    finally:
        sys.modules["__main__"] = old


def test_python_dash_m_runs_one_copy_only():
    """Chạy server như container (`-m`, không có thông tin đăng nhập app nên main() thoát mã 2 ngay sau khi nạp xong): sau đó `import zalo_pc_app.server`
    và srv() phải cùng MỘT mô-đun, không có bản sao thứ hai."""
    script = (
        "import runpy, sys\n"
        "try:\n"
        "    runpy.run_module('zalo_pc_app.server', run_name='__main__', alter_sys=True)\n"
        "except SystemExit:\n"
        "    pass\n"
        "import zalo_pc_app.server as s\n"
        "from zalo_pc_app.calls._srv import srv\n"
        "assert srv() is s, 'srv() tra ve ban sao thu hai'\n"
        "assert s is sys.modules['zalo_pc_app.server']\n"
        "assert s.__name__ == '__main__', s.__name__\n"
        "print('MOT BAN DUY NHAT')\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZALO_PC_APP_")}
    env["ZALO_PC_DATA_DIR"] = os.path.join(os.environ.get("TMPDIR", "/tmp"), "zalo-main-module-test")
    os.makedirs(env["ZALO_PC_DATA_DIR"], exist_ok=True)
    p = subprocess.run([sys.executable, "-c", script], cwd=APP, env=env, capture_output=True, text=True, timeout=60)
    assert "MOT BAN DUY NHAT" in p.stdout, (p.stdout[-300:], p.stderr[-600:])


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("ALL SERVER MAIN MODULE TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
