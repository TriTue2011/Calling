"""ZALO_PC_API_TYPE / ZALO_PC_API_VERSION: mặc định 30/695, đặt 24/693 để khai như Zalo PC thật."""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _read(env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("ZALO_PC_API_")}
    e.update(env)
    out = subprocess.run([sys.executable, "-I", "-c",
                          "import sys; sys.path.insert(0, %r); from zalo_pc_app import protocol as p; "
                          "print(p.API_TYPE, p.API_VERSION, p.common_params()['zpw_type'], p.common_params()['zpw_ver'])" % ROOT],
                         capture_output=True, text=True, env=e, check=True).stdout.split()
    return tuple(int(x) for x in out)


def test_default_is_30_695():
    assert _read({}) == (30, 695, 30, 695)


def test_flag_switches_everything_to_pc_values():
    assert _read({"ZALO_PC_API_TYPE": "24", "ZALO_PC_API_VERSION": "693"}) == (24, 693, 24, 693)


def test_garbage_falls_back_to_default():
    assert _read({"ZALO_PC_API_TYPE": "abc", "ZALO_PC_API_VERSION": ""}) == (30, 695, 30, 695)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL API TYPE FLAG TESTS PASSED")
