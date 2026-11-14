"""Đóng gói hai image (có UI / không UI) từ cùng mã nguồn; compose KHÔNG báo lỗi khi thiếu biến môi trường (14/11/2026).
Run: python3 tests/test_docker_packaging.py"""
import os
import re
import sys

try:
    import yaml
except ImportError:                     # PyYAML chỉ là công cụ dev
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..")
REPO = os.path.join(APP, "..", "..")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as fh:
        return fh.read()


def test_dockerfile_has_noui_and_ui_targets_with_ui_last_and_static_removed_only_in_noui():
    df = read(APP, "Dockerfile")
    stages = re.findall(r"^FROM\s+\S+\s+AS\s+(\w+)\s*$", df, re.M)
    assert stages == ["base", "noui", "ui"], stages                                # ui đứng CUỐI: `docker build` không chỉ định đích = bản có giao diện như trước
    noui = df[df.index("FROM base AS noui"):df.index("FROM base AS ui")]
    assert "rm -rf /app/zalo_pc_app/static" in noui                               # chỉ bản không UI xóa tệp WebUI
    assert df.count("rm -rf /app/zalo_pc_app/static") == 1
    assert "/api/app/status" in df and "/login" not in re.search(r"HEALTHCHECK.*", df, re.S).group(0).split("ENTRYPOINT")[0]     # healthcheck dùng đường có ở cả hai image


def test_compose_files_never_fail_on_missing_env_vars():
    for name in ("docker-compose.yml", "docker-compose.noui.yml"):
        text = read(APP, name)
        bad = re.findall(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", text)                   # ${BIEN} trơn → compose báo lỗi/cảnh báo khi thiếu biến
        assert not bad, (name, bad)
        required = re.findall(r"\$\{[A-Za-z_][A-Za-z0-9_]*:\?", text)             # ${BIEN:?lỗi} = BẮT BUỘC
        assert not required, (name, required)
        for var in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", text):
            assert re.search(r"\$\{%s:-" % var, text), (name, var)               # mọi biến đều có mặc định rỗng/giá trị
    if yaml is None:
        return
    ui, noui = yaml.safe_load(read(APP, "docker-compose.yml")), yaml.safe_load(read(APP, "docker-compose.noui.yml"))
    assert ui["services"]["zalo-pc"]["image"].endswith("zalo-calling:latest") and noui["services"]["zalo-pc"]["image"].endswith("zalo-calling:noui")
    assert ui["services"]["zalo-pc"]["container_name"] != noui["services"]["zalo-pc"]["container_name"]      # chạy song song/đổi qua lại không đụng tên
    for svc in (ui["services"]["zalo-pc"], noui["services"]["zalo-pc"]):
        assert svc["environment"]["ZALO_PC_APP_USER"] == "${ZALO_PC_APP_USER:-}" and svc["environment"]["ZALO_PC_APP_PASSWORD"] == "${ZALO_PC_APP_PASSWORD:-}"
        assert "ZALO_PC_UI" not in svc["environment"]                              # KHÔNG đặt ZALO_PC_UI trong compose (chuỗi rỗng sẽ đè mặc định của image)
        assert svc["labels"]["com.centurylinklabs.watchtower.enable"] == "true"


def test_env_example_lists_every_variable_as_optional():
    text = read(APP, ".env.example")
    for var in ("ZALO_PC_APP_USER", "ZALO_PC_APP_PASSWORD", "ZALO_PC_APP_PASSWORD_HASH", "ZALO_PC_WEBHOOK_URL", "ZALO_PC_UI"):
        assert var in text, var
    assert "KHÔNG bắt buộc" in text and re.search(r"^ZALO_PC_APP_USER=$", text, re.M) and re.search(r"^ZALO_PC_APP_PASSWORD=$", text, re.M)   # mẫu để trống, copy ra không gây lỗi


def test_ci_builds_both_images_from_same_dockerfile():
    if yaml is None:
        return
    wf = yaml.safe_load(read(REPO, ".github", "workflows", "image.yml"))
    steps = [s for s in wf["jobs"]["image"]["steps"] if str(s.get("uses", "")).startswith("docker/build-push-action")]
    assert len(steps) == 2, len(steps)
    plain, noui = steps
    assert "target" not in plain["with"] and noui["with"]["target"] == "noui"
    assert plain["with"]["file"] == noui["with"]["file"] == "./zalo/zalo-pc-app/Dockerfile"
    tags_plain, tags_noui = plain["with"]["tags"], noui["with"]["tags"]
    assert ":latest" in tags_plain and "-noui" not in tags_plain                    # thẻ cũ không đổi
    assert tags_noui.count("-noui") == 2 and tags_noui.strip().endswith("zalo-calling:noui")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ALL DOCKER PACKAGING TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
