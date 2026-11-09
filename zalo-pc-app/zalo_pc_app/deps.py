"""Kiem tra thu vien he thong ma app can khi chay (image Docker phai co du).

- ffmpeg co encoder libx264: phat hinh camera len cuoc goi, doi tin thoai;
- libopus: ma hoa/giai ma tieng cuoc goi (Opus 16 kHz);
- libcrypto (OpenSSL): AES-CTR cho SRTP nhanh (ban thuan Python cham ~25 ms/goi 1 KB,
  du lam nghen am thanh khi co hinh).

`check()` tra ket qua tung muc; `require()` dung khi build image (Dockerfile) va khi
khoi dong de loi hien ra som, ro rang, thay vi cuoc goi cham/khong tieng.
"""

import ctypes
import ctypes.util
import shutil
import subprocess

_CACHE = None


def _ffmpeg():
    path = shutil.which("ffmpeg")
    if not path:
        return {"ok": False, "detail": "khong co ffmpeg"}
    try:
        out = subprocess.run([path, "-hide_banner", "-encoders"], capture_output=True,
                             text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "detail": "ffmpeg loi: %s" % str(exc)[:60]}
    has_x264 = "libx264" in out
    return {"ok": has_x264, "path": path,
            "detail": "ok" if has_x264 else "ffmpeg khong co encoder libx264"}


def _lib(name, fallback):
    found = ctypes.util.find_library(name) or fallback
    try:
        ctypes.CDLL(found)
    except OSError as exc:
        return {"ok": False, "detail": "khong nap duoc %s: %s" % (found, str(exc)[:60])}
    return {"ok": True, "detail": found}


def check(refresh=False):
    """{"ffmpeg": {ok, detail}, "opus": {...}, "openssl": {...}, "ok": bool}."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE
    res = {"ffmpeg": _ffmpeg(), "opus": _lib("opus", "libopus.so.0"),
           "openssl": _lib("crypto", "libcrypto.so.3")}
    res["ok"] = all(v["ok"] for v in res.values())
    _CACHE = res
    return res


def require():
    """Nem SystemExit neu thieu thu vien bat buoc (dung trong build / khoi dong)."""
    res = check(refresh=True)
    missing = ["%s: %s" % (k, v["detail"]) for k, v in res.items()
               if isinstance(v, dict) and not v["ok"]]
    if missing:
        raise SystemExit("THIEU THU VIEN: " + "; ".join(missing))
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(require(), ensure_ascii=False))
