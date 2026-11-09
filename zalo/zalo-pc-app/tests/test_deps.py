"""Kiem tra thu vien he thong (deps) — logic phan loai, khong phu thuoc may chay test."""

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import deps  # noqa: E402


def test_check_shape_and_require_reports_missing():
    real_which, real_lib, real_run = deps.shutil.which, deps._lib, deps.subprocess.run
    try:
        deps.shutil.which = lambda n: None
        deps._lib = lambda name, fb: {"ok": True, "detail": fb}
        res = deps.check(refresh=True)
        assert res["ffmpeg"]["ok"] is False and res["ok"] is False
        try:
            deps.require()
        except SystemExit as exc:
            assert "ffmpeg" in str(exc) and "THIEU" in str(exc)
        else:
            raise AssertionError("phai bao thieu ffmpeg")
        # ffmpeg co nhung khong co libx264 -> van thieu.
        deps.shutil.which = lambda n: "/usr/bin/ffmpeg"
        deps.subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout=" V..... mpeg4")
        assert deps.check(refresh=True)["ffmpeg"]["ok"] is False
        # Du: ffmpeg + libx264 + thu vien.
        deps.subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout=" V....D libx264 H.264")
        ok = deps.check(refresh=True)
        assert ok["ok"] is True and deps.require()["ffmpeg"]["path"] == "/usr/bin/ffmpeg"
        # Thieu libopus -> require() noi ro.
        deps._lib = lambda name, fb: ({"ok": False, "detail": "khong nap duoc " + fb}
                                      if name == "opus" else {"ok": True, "detail": fb})
        try:
            deps.require()
        except SystemExit as exc:
            assert "opus" in str(exc)
        else:
            raise AssertionError("phai bao thieu libopus")
    finally:
        deps.shutil.which, deps._lib, deps.subprocess.run = real_which, real_lib, real_run
        deps._CACHE = None


if __name__ == "__main__":
    test_check_shape_and_require_reports_missing()
    print("ALL DEPS TESTS PASSED")
