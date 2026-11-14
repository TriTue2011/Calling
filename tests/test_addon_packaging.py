"""Hai add-on (có / không giao diện) phải khớp mã nguồn: phiên bản, image, tuỳ chọn, ingress (14/11/2026).

Hỏng ở đây nghĩa là: Supervisor kéo một thẻ image không tồn tại (add-on không cài được), hoặc một tuỳ chọn người
dùng điền mà entrypoint không đọc (điền rồi không có tác dụng), hoặc quên bản dịch. Chạy: python3 tests/test_addon_packaging.py
"""
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
APP = os.path.join(ROOT, "zalo", "zalo-pc-app")


def _yaml(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


MANIFEST = json.loads(_text("custom_components", "zalo_call", "manifest.json"))["version"]
UI = _yaml("zalo_calling", "config.yaml")
NOUI = _yaml("zalo_calling_noui", "config.yaml")


def test_repository_yaml_points_at_this_repo():
    r = _yaml("repository.yaml")
    assert r["url"] == "https://github.com/TriTue2011/Zalo-calling" and r["name"] and r["maintainer"]


def test_versions_follow_manifest_and_image_tags():
    assert UI["version"] == MANIFEST, "add-on có giao diện phải cùng phiên bản với manifest (thẻ image :%s)" % MANIFEST
    assert NOUI["version"] == MANIFEST + "-noui", "add-on không giao diện dùng thẻ :<version>-noui"
    assert UI["image"] == NOUI["image"] == "ghcr.io/tritue2011/zalo-calling"
    wf = _text(".github", "workflows", "image.yml")
    assert "zalo-calling:${{ needs.test.outputs.version }}\n" in wf, "image.yml phải đẩy thẻ :<version> (Supervisor kéo thẻ này)"
    assert "zalo-calling:${{ needs.test.outputs.version }}-noui" in wf, "image.yml phải đẩy thẻ :<version>-noui"
    assert "target: noui" in wf


def test_slugs_and_platforms():
    assert UI["slug"] == "zalo_calling" and NOUI["slug"] == "zalo_calling_noui" and UI["slug"] != NOUI["slug"]
    for c in (UI, NOUI):
        assert c["arch"] == ["amd64", "aarch64"], "image CI dựng linux/amd64 + linux/arm64"
        assert c["init"] is False, "entrypoint của image tự hạ quyền; init:true của HA sẽ chen vào"
        assert c["ports"] == {"8080/tcp": 8080} and "8080/tcp" in c["ports_description"]
        assert "/api/app/status" in c["watchdog"], "watchdog phải trỏ đường công khai, không cần đăng nhập"


def test_ingress_only_on_ui_addon():
    assert UI["ingress"] is True and UI["ingress_port"] == 8080 and UI["ingress_stream"] is True, \
        "ingress_stream bắt buộc: video cuộc gọi là luồng MJPEG dài"
    assert UI["panel_title"] and UI["panel_icon"].startswith("mdi:")
    for k in ("ingress", "ingress_port", "panel_title", "panel_icon"):
        assert k not in NOUI, "bản không giao diện không có bảng bên (%s)" % k


def test_options_schema_translations_agree():
    for name, c in (("zalo_calling", UI), ("zalo_calling_noui", NOUI)):
        assert set(c["options"]) == set(c["schema"]) == {"username", "password", "webhook_url"}, name
        for lang in ("vi", "en"):
            tr = _yaml(name, "translations", lang + ".yaml")
            assert set(tr["configuration"]) == set(c["options"]), (name, lang)
            for o, v in tr["configuration"].items():
                assert v["name"] and v["description"], (name, lang, o)
            assert "8080/tcp" in tr["network"]
        for f in ("icon.png", "logo.png", "DOCS.md", "README.md"):
            assert os.path.getsize(os.path.join(ROOT, name, f)) > 100, (name, f)


def test_required_vs_optional_options():
    # có giao diện: không điền gì vẫn chạy (app tự sinh); điền thì dùng
    assert UI["schema"]["username"] == "str?"
    assert UI["schema"]["password"] == "password?"
    # không giao diện: tên + mật khẩu BẮT BUỘC (không dấu ?, có độ dài tối thiểu) vì không có WebUI để đặt sau
    assert not NOUI["schema"]["username"].endswith("?") and not NOUI["schema"]["password"].endswith("?")
    assert re.fullmatch(r"password\((\d+),\d+\)", NOUI["schema"]["password"]) and int(re.findall(r"\d+", NOUI["schema"]["password"])[0]) >= 8
    assert NOUI["options"]["password"] == "", "mặc định rỗng để Supervisor đòi người dùng điền, không phát mật khẩu chung"
    assert UI["schema"]["webhook_url"] == NOUI["schema"]["webhook_url"] == "url?"


def test_every_option_is_read_by_the_entrypoint():
    src = _text("zalo", "zalo-pc-app", "docker-entrypoint.py")
    for opt in set(UI["options"]) | set(NOUI["options"]):
        assert 'opts.get("%s")' % opt in src, "entrypoint không đọc tuỳ chọn %s: điền rồi không có tác dụng" % opt


def test_release_checks_addon_versions():
    wf = _text(".github", "workflows", "release.yml")
    assert "zalo_calling/config.yaml" in wf and "zalo_calling_noui/config.yaml" in wf, "release.yml phải kiểm version add-on == tag"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("ALL ADDON PACKAGING TESTS PASSED")
