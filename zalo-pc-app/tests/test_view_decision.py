"""View-decision tests (sửa lỗi nháy trang QR 2026-11-05).

Lỗi: sau khi làm mới trang, giao diện hiện trang "Đăng nhập bằng
mã QR" trong khi sidebar vẫn ghi "Đã đăng nhập" — vì view-login
hiện sẵn trong HTML rồi app.js mới await /api/status để đổi view.
Hành vi mới pin ở đây:
  - HTML lúc tải: CHỈ view-loading (trung tính) hiện; view-login
    ẩn sẵn (static assert trên app.html).
  - app.js thật chạy với DOM giả lập (node, không cần trình duyệt):
    đã đăng nhập -> view đầu tiên là view-loading, view quyết định
    là view-main, KHÔNG BAO GIỜ qua view-login;
    chưa đăng nhập -> view-loading rồi view-login, không qua
    view-main, không gọi /api/contacts;
    đã đăng nhập + contacts trả stale -> view-main ngay, rồi tự
    tải lại lần nữa sau 3 giây để lấy bản mới (SWR follow-up).
    đã đăng nhập + lần tải lại sau stale gặp lỗi 429 khô -> danh
    sách cũ vẫn hiện (count-all giữ nguyên, không về 0/0/0) và
    banner lỗi hiện rõ mã 429.
Không đăng nhập thật, không gọi thật bằng tài khoản nào.
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
APP_HTML = os.path.join(ROOT, "zalo_pc_app", "static", "app.html")
APP_JS = os.path.join(ROOT, "zalo_pc_app", "static", "app.js")
HARNESS = os.path.join(HERE, "view_decision_harness.js")


def test_html_loading_view_is_the_only_default_view():
    """app.html: view-loading hiện sẵn, view-login ẩn sẵn, sidebar
    không khẳng định "Chưa đăng nhập" trước khi biết phiên."""
    html = open(APP_HTML, encoding="utf-8").read()
    m = re.search(r'<section id="view-loading"[^>]*>', html)
    assert m, "view-loading section missing"
    assert "display:none" not in m.group(0), \
        "view-loading must be visible by default: %s" % m.group(0)
    m = re.search(r'<section id="view-login"[^>]*>', html)
    assert m, "view-login section missing"
    assert "display:none" in m.group(0), \
        "view-login must be hidden by default: %s" % m.group(0)
    m = re.search(r'<section id="view-main"[^>]*>', html)
    assert m and "display:none" in m.group(0), \
        "view-main must be hidden by default"
    assert "Chưa đăng nhập" not in html, \
        "sidebar must not claim logged-out before /api/status"
    assert "loading-text" in html, "loading view needs #loading-text"


def test_js_boot_shows_loading_before_deciding():
    """app.js: boot hiện view-loading rồi mới loadMain(); view-login
    chỉ được show() từ nhánh !st.login trong loadMain."""
    js = open(APP_JS, encoding="utf-8").read()
    assert 'show("view-loading");\nloadMain();' in js, \
        "boot must show view-loading then loadMain()"
    assert 'if (!st.login) { show("view-login");' in js, \
        "QR view must only appear on a proven logged-out status"
    assert '"view-loading"' in js.split("const VIEWS")[1].split(";")[0], \
        "view-loading must be in VIEWS"


def _run_harness(scenario):
    p = subprocess.run(["node", HARNESS, scenario],
                       cwd=ROOT, capture_output=True, text=True,
                       timeout=60)
    out = (p.stdout + p.stderr).strip()
    assert p.returncode == 0, out
    assert ("PASS %s" % scenario) in out, out
    return out


def test_logged_in_first_view_is_main_never_qr():
    """Đã đăng nhập: view đầu tiên là loading, view quyết định là
    danh bạ, không qua trang QR."""
    out = _run_harness("logged-in")
    print(out)


def test_logged_out_shows_qr():
    """Chưa đăng nhập: loading rồi trang QR, không hiện danh bạ,
    không gọi /api/contacts."""
    out = _run_harness("logged-out")
    print(out)


def test_logged_in_stale_follows_up():
    """Đã đăng nhập + contacts stale: danh bạ hiện ngay (không qua
    QR), rồi app tự tải lại lần nữa để lấy bản mới."""
    out = _run_harness("logged-in-stale")
    print(out)


def test_logged_in_reload_error_keeps_old_list():
    """Đã đăng nhập + lần tải lại sau stale gặp lỗi 429 khô: danh
    sách cũ vẫn hiện (không về 0/0/0 như ảnh 18:06 ngày 2026-11-05),
    banner lỗi hiện rõ mã 429."""
    out = _run_harness("logged-in-reload-error")
    print(out)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL VIEW DECISION TESTS PASSED")
