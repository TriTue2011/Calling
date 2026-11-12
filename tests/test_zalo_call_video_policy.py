"""Cong tac tong + quy tac tung nguoi quyet dinh co tu dong y chuyen video khong (video_policy).
Nap file theo duong dan (khong keo homeassistant). Chay: python -m pytest tests/test_zalo_call_video_policy.py"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")


def _load(name):
    spec = importlib.util.spec_from_file_location("zc_" + name, os.path.join(BASE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vp = _load("video_policy")


def test_switch_off_means_everyone_only_gets_reported_even_with_accept_rules():
    for mode in ("ask", "accept", "accept_camera"):
        assert vp.decide({"video_request": mode}, False) == "ask"
        assert vp.decide({"video_request": mode}, None) == "ask"                # chua tung dat = TAT


def test_switch_on_applies_the_per_thread_rule():
    assert vp.decide({"video_request": "accept"}, True) == "accept"
    assert vp.decide({"video_request": "accept_camera"}, True) == "accept_camera"
    assert vp.decide({"video_request": "ask"}, True) == "ask"
    assert vp.decide({}, True) == "ask", "quy tac khong dat video_request = chi bao"


def test_no_rule_is_never_accepted_and_garbage_mode_is_ignored():
    assert vp.decide(None, True) == "ask"
    assert vp.decide({"video_request": "dong_y_het"}, True) == "ask"
    assert vp.decide({"video_request": "accept"}, 1) == "accept", "gia tri bat khac True van tinh la bat"
