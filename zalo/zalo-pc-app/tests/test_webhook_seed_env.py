"""Bản không WebUI: webhook ban đầu từ biến môi trường, KHÔNG BAO GIỜ đè cấu hình đã có (14/11/2026).
Run: python3 tests/test_webhook_seed_env.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import webhooks as wh  # noqa: E402


def store(d):
    return wh.WebhookStore(os.path.join(d, wh.FILENAME))


def test_one_url_seeds_all_four_kinds_with_private_file():
    with tempfile.TemporaryDirectory() as d:
        s = store(d)
        assert s.seed_from_env({"ZALO_PC_WEBHOOK_URL": "http://ha:8123/api/webhook/abc"}) is True
        cfg = s.load()
        assert all(cfg[u] == "http://ha:8123/api/webhook/abc" for u in wh.URL_FIELDS) and all(cfg[e] is True for e in wh.ENABLED_FIELDS), cfg
        assert oct(os.stat(s.path).st_mode & 0o777) == "0o600"                      # chứa mã bí mật: chỉ chủ đọc được


def test_per_kind_url_wins_over_common_and_partial_is_allowed():
    with tempfile.TemporaryDirectory() as d:
        s = store(d)
        s.seed_from_env({"ZALO_PC_WEBHOOK_URL": "http://a/x", "ZALO_PC_WEBHOOK_CALL_URL": "http://b/y", "ZALO_PC_WEBHOOK_MESSAGE_URL": "http://c/z"})
        cfg = s.load()
        assert cfg["call_webhook_url"] == "http://b/y" and cfg["message_webhook_url"] == "http://c/z" and cfg["reaction_webhook_url"] == "http://a/x"
    with tempfile.TemporaryDirectory() as d:
        s = store(d)
        s.seed_from_env({"ZALO_PC_WEBHOOK_CALL_URL": "http://only/call"})
        cfg = s.load()
        assert cfg["call_webhook_url"] == "http://only/call" and cfg["message_webhook_url"] == ""       # chỉ loại được đặt mới có địa chỉ


def test_never_overwrites_existing_config_and_empty_means_unset():
    with tempfile.TemporaryDirectory() as d:
        s = store(d)
        s.save({"message_webhook_url": "http://da-dat-trong-webui/x", "message_enabled": False})
        before = open(s.path, encoding="utf-8").read()
        assert s.seed_from_env({"ZALO_PC_WEBHOOK_URL": "http://env/y"}) is False                       # đã có tệp: KHÔNG đè (WebUI/HA/dịch vụ đã đặt)
        assert open(s.path, encoding="utf-8").read() == before and s.load()["message_enabled"] is False
    with tempfile.TemporaryDirectory() as d:
        s = store(d)
        assert s.seed_from_env({}) is False and s.seed_from_env({"ZALO_PC_WEBHOOK_URL": "", "ZALO_PC_WEBHOOK_CALL_URL": "  "}) is False   # compose ${BIEN:-} = rỗng = chưa đặt
        assert not s.exists()                                                       # không tạo tệp rỗng (để tích hợp HA còn tự điền được)


def test_bad_url_is_skipped_not_fatal():
    with tempfile.TemporaryDirectory() as d:
        s = store(d)
        assert s.seed_from_env({"ZALO_PC_WEBHOOK_URL": "ftp://khong-hop-le", "ZALO_PC_WEBHOOK_CALL_URL": "http://ok/c"}) is True
        cfg = s.load()
        assert cfg["call_webhook_url"] == "http://ok/c" and cfg["message_webhook_url"] == ""         # địa chỉ sai bị bỏ qua, các loại khác vẫn nạp
        s2 = store(tempfile.mkdtemp())
        assert s2.seed_from_env({"ZALO_PC_WEBHOOK_URL": "javascript:alert(1)"}) is False and not s2.exists()


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
    print("ALL WEBHOOK SEED TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
