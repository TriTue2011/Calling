"""Thẻ và ghi chú danh bạ + quy tắc theo thẻ (rules.py). Nạp file theo đường dẫn (không kéo homeassistant).
Chạy: python -m pytest tests/test_zalo_call_tags.py"""
import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")
spec = importlib.util.spec_from_file_location("zc_rules_tags", os.path.join(BASE, "rules.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def _rules(**kw):
    r = R.empty_rules()
    r.update(kw)
    return r


def test_norm_tag_and_parse_tags_are_case_space_and_comma_insensitive():
    assert R.norm_tag("  Gia   Đình ") == "gia đình"
    assert R.norm_tag("a,b") == "a b"                                   # dấu phẩy không lọt vào tên thẻ
    assert R.norm_tag(None) == "" and R.norm_tag("   ") == ""
    assert len(R.norm_tag("x" * 100)) == R.MAX_TAG_LEN
    assert R.parse_tags("Gia đình, người lớn tuổi,, GIA ĐÌNH") == ["gia đình", "người lớn tuổi"]      # bỏ rỗng, bỏ trùng không phân biệt hoa thường
    assert R.parse_tags(["A", " a ", "B"]) == ["a", "b"]
    assert R.parse_tags(None) == [] and R.parse_tags(5) == [] and R.parse_tags({"a": 1}) == []
    assert len(R.parse_tags(",".join("t%d" % i for i in range(30)))) == R.MAX_TAGS_PER_CONTACT


def test_validate_scope_tag_needs_a_name_and_other_scopes_still_work():
    assert R.validate_scope("tag", None, "  Gia Đình ") == "gia đình"
    for bad in ("", "   ", None, ","):
        with pytest.raises(R.RuleError):
            R.validate_scope("tag", None, bad)
    assert R.validate_scope("thread", "123") == "123"
    assert R.validate_scope("contacts", None) == "" and R.validate_scope("groups", None, "bo qua") == ""
    with pytest.raises(R.RuleError):
        R.validate_scope("thread", "abc")
    with pytest.raises(R.RuleError):
        R.validate_scope("khac", "1")


def test_resolve_order_thread_then_tag_then_general_rule():
    thread_rule, tag_rule, contacts_rule, strangers_rule = {"name": "thread"}, {"name": "tag"}, {"name": "contacts"}, {"name": "strangers"}
    rules = _rules(threads={"111": thread_rule}, tags={"gia đình": tag_rule}, contacts=contacts_rule, strangers=strangers_rule,
                   contact_meta={"111": {"tags": ["gia đình"]}, "222": {"tags": ["gia đình"]}, "333": {"tags": ["ban be"]}})
    assert R.resolve(rules, "111", "user", "friend") is thread_rule             # quy tắc theo người đè mọi thứ
    assert R.resolve(rules, "222", "user", "friend") is tag_rule                # thẻ thắng quy tắc chung của danh bạ
    assert R.resolve(rules, "222", "user", "stranger") is tag_rule              # thẻ do chủ nhà gắn tay: áp cả khi app báo là người lạ
    assert R.resolve(rules, "222", "user", None) is tag_rule                    # và cả khi chưa biết quen hay lạ
    assert R.resolve(rules, "333", "user", "friend") is contacts_rule           # thẻ không có quy tắc: rơi về quy tắc chung
    assert R.resolve(rules, "444", "user", "friend") is contacts_rule
    assert R.resolve(rules, "444", "user", "unknown") is None                   # hành vi cũ giữ nguyên: không đoán


def test_first_tag_with_a_rule_wins_in_the_order_they_were_attached():
    a, b = {"name": "a"}, {"name": "b"}
    rules = _rules(tags={"a": a, "b": b}, contact_meta={"1": {"tags": ["b", "a"]}, "2": {"tags": ["khong co", "a"]}})
    assert R.resolve(rules, "1", "user", "friend") is b
    assert R.resolve(rules, "2", "user", "friend") is a                         # thẻ đầu không có quy tắc thì xét thẻ sau


def test_group_with_tag_rule_and_old_rule_dicts_without_new_keys_still_resolve():
    g = {"name": "nhom"}
    rules = _rules(tags={"to": g}, contact_meta={"G1": {"tags": ["to"]}}, groups={"name": "mọi nhóm"})
    assert R.resolve(rules, "G1", "group", "group") is g                       # nhóm cũng gắn thẻ được
    old_style = {"threads": {}, "groups": {"name": "g"}, "contacts": {"name": "c"}, "strangers": {}}   # kho cũ chưa có tags / contact_meta
    assert R.resolve(old_style, "9", "user", "friend") == {"name": "c"}
    assert R.resolve(old_style, "9", "group", "group") == {"name": "g"}


def test_empty_rules_and_get_rules_keep_tag_stores_and_never_share_state():
    e1, e2 = R.empty_rules(), R.empty_rules()
    assert set(e1) == {"threads", "tags", "contact_meta", "groups", "contacts", "strangers"}
    e1["tags"]["x"] = {"name": "x"}
    assert e2["tags"] == {}                                                      # mỗi lần gọi một bản riêng

    class Defaults:
        def get(self, key):
            return {"rules": {"tags": {"a": {"name": "a"}}, "contact_meta": {"1": {"tags": ["a"], "note": "n"}}, "bi_la": {"x": 1}}}.get(key)
    got = R.get_rules(Defaults())
    assert got["tags"]["a"]["name"] == "a" and got["contact_meta"]["1"]["note"] == "n" and "bi_la" not in got
