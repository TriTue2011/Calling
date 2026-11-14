"""README phải đổi CÙNG LÚC với mã: biến môi trường, tuỳ chọn add-on, tệp compose, dịch vụ, liên kết (14/11/2026).

Chủ máy chốt: tài liệu cài đặt luôn đúng với hiện tại. Test này làm CI đỏ khi thêm biến/tuỳ chọn/dịch vụ mà quên README,
hoặc README trỏ tới tệp/mục không còn. (Các khối dịch vụ sinh tự động do test_zalo_call_docs.py giữ.)
Chạy: python3 tests/test_readme_matches_code.py
"""
import glob
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
APP = os.path.join(ROOT, "zalo", "zalo-pc-app")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


ROOT_README = text("README.md")
ZALO_README = text("zalo", "README.md")
APP_README = text("zalo", "zalo-pc-app", "README.md")
DOCS = [("README.md", ROOT_README), ("zalo/README.md", ZALO_README), ("zalo/zalo-pc-app/README.md", APP_README)]
SERVICES = yaml.safe_load(text("custom_components", "zalo_call", "services.yaml"))


def test_every_env_var_users_can_set_is_in_the_app_readme():
    """Mọi ZALO_PC_* xuất hiện ở nơi người dùng đặt (compose, .env.example, entrypoint, Dockerfile) phải có trong bảng biến của README app."""
    files = [os.path.join(APP, n) for n in ("docker-compose.yml", "docker-compose.noui.yml", ".env.example", "docker-entrypoint.py", "Dockerfile")]
    names = set()
    for f in files:
        names |= {n for n in re.findall(r"ZALO_PC_[A-Z0-9_]*[A-Z0-9]", open(f, encoding="utf-8").read())}
    assert names, "không tìm thấy biến nào: regex hỏng?"
    thieu = sorted(n for n in names if n not in APP_README)
    assert not thieu, "README app thiếu biến môi trường: %s" % thieu


def test_addon_section_points_at_has_addons_and_documents_options():
    """Add-on nằm ở kho has-addons (không ở kho này): README gốc phải nêu kho đó, hai bản, và các tuỳ chọn add-on app đọc (username/password/webhook_url)."""
    assert "https://github.com/TriTue2011/has-addons" in ROOT_README and "zalo_calling_noui" in ROOT_README
    for opt in ("username", "password", "webhook_url"):
        assert "`%s`" % opt in ROOT_README, "README gốc không giải thích tuỳ chọn `%s`" % opt
    src = open(os.path.join(APP, "docker-entrypoint.py"), encoding="utf-8").read()
    for opt in ("username", "password", "webhook_url"):
        assert 'opts.get("%s")' % opt in src, "entrypoint không đọc tuỳ chọn add-on %s" % opt
    assert not os.path.exists(os.path.join(ROOT, "zalo_calling")) and not os.path.exists(os.path.join(ROOT, "repository.yaml")), \
        "add-on chỉ ở has-addons: không để bản trùng slug trong kho này"


def test_install_section_names_real_files_images_and_services():
    for f in ("docker-compose.yml", "docker-compose.noui.yml", ".env.example"):
        assert os.path.exists(os.path.join(APP, f)), f
        assert f in ROOT_README + APP_README, "README không nhắc %s" % f
    dockerfile = open(os.path.join(APP, "Dockerfile"), encoding="utf-8").read()
    assert re.search(r"^FROM base AS noui", dockerfile, re.M) and re.search(r"^FROM base AS ui", dockerfile, re.M)
    for tag in (":latest", ":noui"):
        assert tag in ROOT_README and tag in APP_README, "README thiếu thẻ image %s" % tag
    assert "ghcr.io/tritue2011/zalo-calling" in ROOT_README
    for sid in ("login_qr", "logout", "get_app_settings", "set_app_settings", "set_app_password", "test_webhook"):
        assert sid in SERVICES, "dịch vụ %s không còn trong services.yaml" % sid
        assert "zalo_call.%s" % sid in ROOT_README, "mục Cài đặt (README gốc) phải nhắc zalo_call.%s" % sid
    sec = SERVICES["set_app_settings"]["fields"]["section"]["selector"]["select"]["options"]
    for v in [o["value"] if isinstance(o, dict) else o for o in sec]:
        assert v in ROOT_README, "README gốc không nhắc mục cài đặt `%s` của set_app_settings" % v


def test_no_removed_default_device_fields_in_docs():
    """set_default_devices không còn speaker/mic/mic_url/camera (chọn theo quy tắc / từng cuộc gọi): tài liệu không được dạy dùng."""
    fields = set(SERVICES["set_default_devices"]["fields"])
    assert not ({"speaker", "mic", "mic_url", "camera"} & fields)
    for name, doc in DOCS:
        for m in re.finditer(r"set_default_devices[^\n]{0,200}", doc):
            seg = m.group(0)
            assert "`speaker`" not in seg and "`camera`" not in seg, "%s dạy đặt speaker/camera bằng set_default_devices: %s" % (name, seg[:120])


def _slug(h):
    h = re.sub(r"[`*_~]", "", h.strip().lower())
    h = re.sub(r"[^\w\- ]", "", h, flags=re.UNICODE)
    return h.replace(" ", "-")


def test_relative_links_and_anchors_resolve():
    bad = []
    for name, doc in DOCS:
        base = os.path.dirname(os.path.join(ROOT, name))
        body = re.sub(r"```.*?```", "", doc, flags=re.S)
        for m in re.finditer(r"\]\(([^)\s]+)\)", body):
            link = m.group(1)
            if re.match(r"^(https?:|mailto:)", link):
                continue
            path, _, anchor = link.partition("#")
            target = os.path.normpath(os.path.join(base, path)) if path else os.path.join(ROOT, name)
            if not os.path.exists(target):
                bad.append("%s -> %s (không có tệp)" % (name, link))
                continue
            if anchor and target.endswith(".md"):
                with open(target, encoding="utf-8") as f:
                    t = re.sub(r"```.*?```", "", f.read(), flags=re.S)
                slugs = {_slug(h) for h in re.findall(r"^#{1,6}\s+(.+)$", t, re.M)} | set(re.findall(r'<a id="([^"]+)"', t))
                if anchor not in slugs:
                    bad.append("%s -> %s (không có mục)" % (name, link))
    assert not bad, "liên kết hỏng:\n  " + "\n  ".join(bad)


def test_every_service_named_in_docs_exists():
    """Mọi `zalo_call.<tên>` được nhắc trong README / DOCS phải là dịch vụ có thật (đổi tên hay xoá dịch vụ mà quên tài liệu → đỏ)."""
    bad = []
    for name, doc in DOCS:
        for sid in set(re.findall(r"zalo_call\.([a-z][a-z0-9_]+)", doc)):
            if sid not in SERVICES and sid not in ("zip", "call_voice"):      # zalo_call.zip = gói phát hành; call_voice = tên module Python, không phải dịch vụ
                bad.append("%s: zalo_call.%s" % (name, sid))
    assert not bad, "dịch vụ không tồn tại: %s" % sorted(bad)


def test_readme_follows_the_install_to_automation_order():
    """README gốc: Docker → Compose → Portainer → tích hợp → kết nối → dịch vụ → automation."""
    heads = re.findall(r"^## (.+)$", ROOT_README, re.M)
    want = ["Cài đặt app bằng Docker", "Thêm tích hợp Home Assistant", "Kết nối tích hợp", "Dịch vụ cuộc gọi", "Danh mục MỌI dịch vụ", "Nhận cuộc gọi, sự kiện", "Blueprint mẫu"]
    pos = [next(i for i, h in enumerate(heads) if k in h) for k in want]
    assert pos == sorted(pos), pos
    for sub in ("### 1.1. Docker", "### 1.2. Docker Compose", "### 1.3. Portainer"):
        assert sub in ROOT_README, sub


def test_dockerfile_default_target_is_the_ui_image():
    """:latest phải là bản CÓ giao diện: đích `ui` đứng CUỐI Dockerfile (docker build không --target lấy giai đoạn cuối)."""
    stages = re.findall(r"^FROM .+ AS (\w+)", open(os.path.join(APP, "Dockerfile"), encoding="utf-8").read(), re.M)
    assert stages[-1] == "ui" and "noui" in stages, stages


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("ALL README SYNC TESTS PASSED")
