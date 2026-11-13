"""ZALO_PC_PLATFORM: giá trị `platform` khai trong extendData (mặc định 2; thử 1 để điện thoại coi là máy di động)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import media_endpoints as me  # noqa: E402


def _platform_with(env):
    old = os.environ.pop("ZALO_PC_PLATFORM", None)
    try:
        if env is not None:
            os.environ["ZALO_PC_PLATFORM"] = env
        return me.native_extend_data("1.2.3.4:4200", "1.2.3.4:4200", False)["platform"]
    finally:
        os.environ.pop("ZALO_PC_PLATFORM", None)
        if old is not None:
            os.environ["ZALO_PC_PLATFORM"] = old


def test_default_is_2_and_flag_switches_to_1():
    assert _platform_with(None) == 2
    assert _platform_with("1") == 1


def test_garbage_value_falls_back_to_2():
    assert _platform_with("abc") == 2
    assert _platform_with("9") == 2
    assert _platform_with("") == 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL PLATFORM FLAG TESTS PASSED")
