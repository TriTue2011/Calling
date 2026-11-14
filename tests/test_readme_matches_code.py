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
for _a in ("zalo_calling", "zalo_calling_noui"):
    DOCS += [(_a + "/DOCS.md", text(_a, "DOCS.md")), (_a + "/README.md", text(_a, "README.md"))]
UI = yaml.safe_load(text("zalo_calling", "config.yaml"))
NOUI = yaml.safe_load(text("zalo_calling_noui", "config.yaml"))
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


def test_addon_options_and_names_are_documented():
    for c in (UI, NOUI):
        assert c["name"] in ROOT_README, "README gốc không nhắc add-on «%s»" % c["name"]
        for opt in c["options"]:
            assert "`%s`" % opt in ROOT_README, "README gốc không giải thích tuỳ chọn `%s`" % opt
    for name, doc in (("zalo_calling", text("zalo_calling", "DOCS.md")), ("zalo_calling_noui", text("zalo_calling_noui", "DOCS.md"))):
        for opt in yaml.safe_load(text(name, "config.yaml"))["options"]:
            assert "`%s`" % opt in doc, "%s/DOCS.md không giải thích tuỳ chọn `%s`" % (name, opt)
    repo = yaml.safe_load(text("repository.yaml"))["url"]
    assert repo in ROOT_README and repo in text("zalo_calling", "DOCS.md"), "địa chỉ kho add-on trong README phải là %s" % repo


def test_install_section_names_real_files_images_and_services():
    for f in ("docker-compose.yml", "docker-compose.noui.yml", ".env.example"):
        assert os.path.exists(os.path.join(APP, f)), f
        assert f in ROOT_README + APP_README, "README không nhắc %s" % f
    dockerfile = open(os.path.join(APP, "Dockerfile"), encoding="utf-8").read()
    assert re.search(r"^FROM base AS noui", dockerfile, re.M) and re.search(r"^FROM base AS ui", dockerfile, re.M)
    for tag in (":latest", ":noui"):
        assert tag in ROOT_README and tag in APP_README, "README thiếu thẻ image %s" % tag
    assert UI["image"] in ROOT_README
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
