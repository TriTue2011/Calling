"""Tên người gọi đọc ra loa: không bao giờ là dãy số; ưu tiên quy tắc, rồi danh bạ đã lưu, rồi tên Zalo. Nạp file theo đường dẫn (không kéo homeassistant).
Chạy: python -m pytest tests/test_zalo_call_caller_name.py"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")
spec = importlib.util.spec_from_file_location("zc_caller_name", os.path.join(BASE, "caller_name.py"))
cn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cn)

CONTACTS = {"friends": {"rows": [{"id": "6643404425553198601", "name": "Đại ca"}, {"id": "1", "name": ""}]},
            "groups": {"rows": [{"id": "77", "name": "Gia đình"}]}}


def test_find_contact_name_by_thread_id_in_friends_and_groups():
    assert cn.find_contact_name(CONTACTS, "6643404425553198601") == "Đại ca"
    assert cn.find_contact_name(CONTACTS, 77) == "Gia đình"
    for bad_id in ("1", "999", "", None):                      # tên rỗng / không có / thiếu id
        assert cn.find_contact_name(CONTACTS, bad_id) == "", bad_id
    for bad in (None, {}, [], "x", {"friends": None}, {"friends": {"rows": None}}, {"friends": {"rows": ["x", None]}}):
        assert cn.find_contact_name(bad, "1") == "", bad


def test_spoken_name_priority_rule_then_contact_then_zalo_name():
    assert cn.spoken_name({"name": "Bố"}, {"contact_name": "Đại ca", "peer": "Việt"}) == "Bố"
    assert cn.spoken_name({}, {"contact_name": "Đại ca", "peer": "6643404425553198601"}) == "Đại ca"
    assert cn.spoken_name({}, {"peer": "Nguyễn Việt"}) == "Nguyễn Việt"


def test_spoken_name_never_reads_a_bare_number():
    assert cn.spoken_name({}, {"peer": "6643404425553198601"}) == "một người"                       # ca thật 12/11: caller_name rỗng, peer là mã
    assert cn.spoken_name({"name": "6643404425553198601"}, {"peer": "6643404425553198601", "contact_status": "stranger"}) == "người lạ"
    assert cn.spoken_name({}, {"contact_status": "stranger"}) == "người lạ"
    assert cn.spoken_name({}, {}) == "một người"
    assert cn.spoken_name({"name": "  "}, {"contact_name": " Mẹ "}) == "Mẹ"
