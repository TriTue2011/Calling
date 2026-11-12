"""Chế độ chống vọng: quy tắc riêng thắng, auto thì theo mặc định thiết bị (echo_policy).
Nạp file theo đường dẫn (không kéo homeassistant). Chạy: python -m pytest tests/test_zalo_call_echo_policy.py"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")
spec = importlib.util.spec_from_file_location("zc_echo_policy", os.path.join(BASE, "echo_policy.py"))
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)


def test_rule_mode_wins_over_device_default():
    for mode in ("on", "duplex", "off"):
        for dev in ("auto", "on", "duplex", "off", None, "xx"):
            assert ep.effective(mode, dev) == mode, (mode, dev)


def test_auto_or_missing_rule_mode_follows_device_default():
    for rule in ("auto", "", None, "bay"):
        assert ep.effective(rule, "duplex") == "duplex" and ep.effective(rule, "on") == "on" and ep.effective(rule, "off") == "off", rule
        assert ep.effective(rule, "auto") == "auto"


def test_bad_device_default_falls_back_to_auto():
    assert ep.effective(None, None) == "auto" and ep.effective("auto", "xx") == "auto" and ep.effective("", 5) == "auto"
