"""WebUI không được gửi Referer: kho video của Zalo (dlfl.vn) trả 403 khi có Referer nên thẻ <video> không phát được (14/11/2026).
Run: python3 tests/test_webui_referrer.py"""
import os
import re
import sys

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "zalo_pc_app", "static", "zalo", "index.html")


def test_index_declares_no_referrer_before_any_resource():
    s = open(HTML, encoding="utf-8").read()
    head = s[s.index("<head>"):s.index("</head>")]
    m = re.search(r'<meta\s+name="referrer"\s+content="no-referrer"\s*>', head)
    assert m, "thiếu <meta name=referrer content=no-referrer> trong <head>"
    link = head.find("<link")
    assert link == -1 or m.start() < link, "meta referrer phải đứng trước mọi tài nguyên tải từ trang"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, str(e)[:200])
    print("ALL WEBUI REFERRER TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
