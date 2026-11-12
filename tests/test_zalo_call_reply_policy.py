"""Quy tac tra loi AI trong nhom (reply_policy + rules): tu khoa goi, nguoi gui duoc phep, trich dan, tien to.
Nap file theo duong dan (goi custom_components.zalo_call se keo ca homeassistant). Chay: python -m pytest tests/test_zalo_call_reply_policy.py"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "custom_components", "zalo_call")


def _load(name):
    spec = importlib.util.spec_from_file_location("zc_" + name, os.path.join(BASE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rp = _load("reply_policy")
rules = _load("rules")

GROUP = {"thread_type": 1, "thread_id": "8845", "sender_id": "6643404425553198601", "uid_from": "207908325", "content": "@Bot bật đèn phòng khách",
         "kind": "text", "message_id": "8474470959615", "cli_msg_id": "1794325284060", "msg_ts": "1794325284060"}


def test_group_without_trigger_answers_everything_as_before():
    ok, text = rp.evaluate({}, GROUP)
    assert ok and text == "@Bot bật đèn phòng khách"


def test_group_trigger_required_case_insensitive_and_stripped():
    rule = {"reply_trigger": "@bot"}
    ok, text = rp.evaluate(rule, GROUP)
    assert ok and text == "bật đèn phòng khách", text                     # bo ca '@bot' khoi cau hoi
    ok, text = rp.evaluate(rule, dict(GROUP, content="hey @BOT, bật đèn"))
    assert ok and "bật đèn" in text and "bot" not in text.lower(), text
    assert rp.evaluate(rule, dict(GROUP, content="xin chao ca nha"))[0] is False
    assert rp.evaluate(rule, dict(GROUP, content="Bot oi bat den"))[0] is False, "tu khoa phai go dung (co @), khong khop 'bot' bua bai"
    assert rp.evaluate(rule, dict(GROUP, content="@Bot"))[1] == "@Bot", "bo tu khoa xong rong thi giu nguyen"
    assert rp.evaluate({"reply_trigger": "robot"}, dict(GROUP, content="Robot dau roi"))[1] == "dau roi", "tu khoa khong co @ van dung duoc"


def test_group_senders_limit_matches_either_id_form_and_ignores_private():
    rule = {"reply_senders": "207908325, 111"}
    assert rp.evaluate(rule, GROUP)[0] is True                                         # ma so ngan (uid_from)
    assert rp.evaluate({"reply_senders": "6643404425553198601"}, GROUP)[0] is True        # ma dai (sender_id)
    assert rp.evaluate({"reply_senders": "999"}, GROUP)[0] is False
    assert rp.evaluate({"reply_senders": ["207908325"]}, GROUP)[0] is True
    private = dict(GROUP, thread_type=0)
    assert rp.evaluate({"reply_senders": "999", "reply_trigger": "xyz"}, private)[0] is True, "tin 1-1 khong bi tu khoa/nguoi gui chan"
    assert rp.evaluate({}, dict(GROUP, content="  "))[0] is False


def test_parse_ids():
    assert rp.parse_ids("1, 2;3\n4  2") == ["1", "2", "3", "4"] and rp.parse_ids(None) == [] and rp.parse_ids(["5", 6, ""]) == ["5", "6"]


def test_prefix_and_quote_payload():
    assert rp.apply_prefix({"reply_prefix": "Bot-Hass: "}, "Xong") == "Bot-Hass: Xong" and rp.apply_prefix({"reply_prefix": "Bot-Hass:"}, "Xong") == "Bot-Hass: Xong"
    assert rp.apply_prefix({}, "Xong") == "Xong" and rp.apply_prefix({"reply_prefix": "  "}, "Xong") == "Xong"
    assert rp.quote_payload({}, GROUP, "group", "8845", "x") is None, "tat thi khong trich dan"
    q = rp.quote_payload({"reply_quote": True}, dict(GROUP, original_content="@Bot bật đèn"), "group", "8845", "Đã bật")
    assert q == {"thread_id": "8845", "type": "group", "text": "Đã bật", "msg_id": "8474470959615", "qmsg_owner": "207908325",
                 "qmsg_cli_id": "1794325284060", "qmsg_type": 1, "qmsg_ts": 1794325284060, "qmsg": "@Bot bật đèn"}, q
    assert rp.quote_payload({"reply_quote": True}, dict(GROUP, cli_msg_id=""), "group", "8845", "x") is None, "thieu ma tin goc"
    assert rp.quote_payload({"reply_quote": True}, dict(GROUP, kind="photo"), "group", "8845", "x") is None, "chi tin chu"
    assert rp.quote_payload({"reply_quote": True}, dict(GROUP, msg_ts="abc"), "user", "9", "x")["qmsg_ts"] == 0


def test_rules_accept_and_normalize_new_fields():
    r = rules.normalize({"reply_ai": True, "agent": "conversation.x", "reply_trigger": " @Bot ", "reply_senders": ["207908325", 111, ""],
                         "reply_quote": 1, "reply_prefix": "Bot: "})
    assert r["reply_trigger"] == "@Bot" and r["reply_senders"] == "207908325, 111" and r["reply_quote"] is True and r["reply_prefix"] == "Bot:", r
    old = rules.normalize({"reply_trigger": "@a"})
    assert rules.normalize({"reply_quote": True}, old)["reply_trigger"] == "@a", "truong khong neu thi giu nhu cu"
    d = rules.DEFAULT_RULE
    assert d["reply_trigger"] == "" and d["reply_senders"] == "" and d["reply_quote"] is False and d["reply_prefix"] == ""
