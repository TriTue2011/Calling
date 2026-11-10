"""Tests for the addon-services panel (zalo_pc_app/services.py).

Pins, against the strict mock (two-layer envelope, common params
zpw_ver=695/zpw_type=30, fully percent-encoded params):
  - the catalog covers all 96 addon services exactly once, with
    honest statuses (73 supported + 2 already viewable + 11 chat +
    10 zalobot-only + 0 unsupported — the old "25 with no PC path"
    claim was wrong: all 25 have PC endpoints, SERVICE-MAP.md §2);
  - every supported op hits the right PC endpoint for its thread
    type (1-1 toid vs group grid) with the bundle-verified body
    (field names, GET vs POST, imei present/absent exactly as the
    real client sends it) and decodes the envelope;
  - the 9 genuine gaps + QR web stay refused (409), never with a
    fake success;
  - the HTTP API requires a Zalo login (401) and validates params
    (400).

No real login, no real call, no real message is sent: everything
goes to MockZalo.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY, TEST_SESSION_KEY  # noqa: E402
from zalo_pc_app import chat as chat_mod  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import services as svc_mod  # noqa: E402


def http_get(url, cookie="", timeout=15):
    req = urllib.request.Request(url, method="GET")
    if cookie:
        req.add_header("Cookie", "zpw_sek=" + cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def http_post(url, form, cookie="", timeout=15):
    req = urllib.request.Request(url, method="POST",
                                 data=form.encode("utf-8"))
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if cookie:
        req.add_header("Cookie", "zpw_sek=" + cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def http_post_multipart(url, body_bytes, content_type, cookie="",
                        timeout=15):
    req = urllib.request.Request(url, method="POST", data=body_bytes)
    req.add_header("Content-Type", content_type)
    if cookie:
        req.add_header("Cookie", "zpw_sek=" + cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def make_svc(mock):
    return svc_mod.Services(
        partial(http_get, cookie="sek-test"),
        partial(http_post, cookie="sek-test"),
        "dev-1", TEST_SESSION_KEY,
        service_map={"reaction": mock.base,
                     "quick_message": mock.base},
        http_post_multipart=partial(http_post_multipart,
                                    cookie="sek-test"))


def make_svc_no_map():
    """Services khong co services map — REACTION / QUICK_MESSAGE
    phai tu choi thay vi doan domain."""
    return svc_mod.Services(
        partial(http_get, cookie="sek-test"),
        partial(http_post, cookie="sek-test"),
        "dev-1", TEST_SESSION_KEY)


def patch_domains(mock):
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    protocol.CHAT_DOMAIN = mock.base
    protocol.CONVERS_DOMAIN = mock.base
    protocol.FRIEND_DOMAIN = mock.base
    protocol.ALIAS_DOMAIN = mock.base
    protocol.LABEL_DOMAIN = mock.base
    protocol.BOARD_DOMAIN = mock.base
    protocol.STICKER_DOMAIN = mock.base
    protocol.FILE_DOMAIN = mock.base


def seen_paths(mock, prefix):
    return [p for p, _, _ in mock.seen if p.startswith(prefix)]


def seen_post_paths(mock):
    return [p for p, _ in mock.seen_post]


# ---------------------------------------------------------------- catalog
def test_catalog_covers_all_96():
    cat = svc_mod.build_catalog()
    by_no = {}
    for e in cat["services"]:
        if e["addon_no"] is not None:
            assert e["addon_no"] not in by_no, \
                "duplicate addon_no %s" % e["addon_no"]
            by_no[e["addon_no"]] = e
    assert sorted(by_no) == list(range(1, 97)), sorted(by_no)
    assert cat["counts"]["total_96"] == 96, cat["counts"]
    # Honest split (SERVICE-MAP.md): 73 supported + 2 already
    # viewable + 11 chat + 10 zalobot-only + 0 unsupported = 96.
    # The old "25 with no PC path" claim was wrong — all 25 have
    # PC endpoints (SERVICE-MAP.md §2).
    supported_96 = [e for e in by_no.values()
                    if e["status"] == "supported"]
    assert len(supported_96) == 73, len(supported_96)
    assert cat["counts"]["view"] == 2, cat["counts"]
    assert cat["counts"]["chat"] == 11, cat["counts"]
    assert cat["counts"]["zalobot"] == 10, cat["counts"]
    assert cat["counts"].get("unsupported", 0) == 0, cat["counts"]
    # The 8 ops outside the 96 (quote, seen, fetchImportant, group
    # link detail, label update, keepAlive, vote_poll,
    # reject_friend_request) carry addon_no None and
    # are all supported — they must not inflate the 96 count.
    extras = [e for e in cat["services"] if e["addon_no"] is None]
    assert len(extras) == 8, extras
    assert all(e["status"] == "supported" for e in extras), extras
    # Every OPS action appears in the catalog exactly once.
    actions = [e["action"] for e in cat["services"] if e["action"]]
    assert sorted(actions) == sorted(svc_mod.OPS), actions
    # Unsupported entries carry a reason and no action (no button).
    for e in cat["services"]:
        if e["status"] in ("unsupported", "zalobot", "chat"):
            assert e["action"] is None, e
            assert e["reason"], e
    # Spot-check the headline cases.
    by_addon = {e["addon"]: e for e in cat["services"]}
    assert by_addon["add_reaction"]["status"] == "supported"
    assert "REACTION" in by_addon["add_reaction"]["desc"]
    assert by_addon["set_pinned_conversation"]["status"] == "supported"
    assert by_addon["create_poll"]["status"] == "supported"
    assert "webhook" in by_addon["set_account_webhook"]["reason"].lower()
    assert "khung chat" in by_addon["send_message"]["reason"]
    assert "QR" in by_addon["get_login_qr"]["reason"]


def test_catalog_body_unverified_flagged():
    """Ops whose body the audit did NOT fully trace are flagged, so
    the UI warns and the integrator knows what to verify live.
    The rest carry fully bundle-verified bodies (SERVICE-MAP.md
    §4 + bundle greps 2026-11-05)."""
    unverified = {
        "add_quick_message", "add_reaction",
        "change_account_avatar", "change_group_avatar",
        "create_group", "create_note_group", "create_poll",
        "create_reminder", "delete_chat", "edit_note_group",
        "edit_reminder", "forward_message", "get_avatar_list",
        "get_group_link", "get_list_board", "get_list_reminder",
        "get_user_info", "last_online", "mark_seen",
        "remove_unread_mark", "update_label", "update_profile",
        "update_quick_message", "update_settings",
    }
    assert len(unverified) == 24, unverified
    for action, spec in svc_mod.OPS.items():
        if action in unverified:
            assert spec["body_unverified"] is True, action
        else:
            assert spec["body_unverified"] is False, action


# ---------------------------------------------------------------- dispatch
def test_dispatch_message_ops_both_threads():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        # undo 1-1 -> /api/message/undo (11281); body {msgId, toid,
        # clientId NUMBER, cliMsgIdUndo} — KHONG imei.
        d = svc.dispatch("undo_message", {
            "thread_id": "20001", "type": "user", "msg_id": "m1",
            "cli_msg_id": "1234567890123"})
        assert d["path"] == "/api/message/undo", d
        assert d["body"]["toid"] == "20001"
        assert d["body"]["msgId"] == "m1"
        assert d["body"]["cliMsgIdUndo"] == 1234567890123, d
        assert isinstance(d["body"]["clientId"], int), d
        assert "imei" not in d["body"], d
        # undo nhom -> /api/group/undomsg; {grid, clientId,
        # visibility:0, imei}; clientId tang don dieu.
        d2 = svc.dispatch("undo_message", {
            "thread_id": "30001", "type": "group", "msg_id": "m2"})
        assert d2["path"] == "/api/group/undomsg", d2
        assert d2["body"]["grid"] == "30001", d2
        assert d2["body"]["visibility"] == 0, d2
        assert d2["body"]["imei"] == "dev-1", d2
        assert d2["body"]["clientId"] > d["body"]["clientId"], d
        assert "cliMsgIdUndo" not in d2["body"], d2
        # delete: {toid|grid, msgs:[], onlyMe, imei}.
        d = svc.dispatch("delete_message", {
            "thread_id": "30001", "type": "group", "msg_id": "m3",
            "cli_msg_id": "1234567890124"})
        assert d["path"] == "/api/group/deletemsg", d
        assert d["body"] == {"grid": "30001", "msgs": ["m3"],
                             "onlyMe": 1, "cliMsgId": 1234567890124,
                             "imei": "dev-1"}, d
        # forward: khung {toId|grid, imei} — lap theo tung dich.
        d = svc.dispatch("forward_message", {
            "msg_id": "m4", "message": "xin chao",
            "dest_thread_ids": "20002, 20003", "type": "user"})
        assert d["results"][0]["path"] == "/api/message/forward", d
        assert d["results"][0]["body"] == {"toId": "20002",
                                           "imei": "dev-1"}, d
        assert d["results"][1]["body"]["toId"] == "20003", d
        d = svc.dispatch("forward_message", {
            "msg_id": "m4", "dest_thread_ids": "30002",
            "type": "group"})
        assert d["results"][0]["path"] == "/api/group/forward", d
        assert d["results"][0]["body"] == {"grid": "30002",
                                           "imei": "dev-1"}, d
        # quote 1-1: qmsg* fields; nhom: language + visibility,
        # KHONG imei.
        d = svc.dispatch("quote_message", {
            "thread_id": "20001", "type": "user", "msg_id": "m5",
            "text": "trich dan", "qmsg_owner": "20002",
            "qmsg_cli_id": "1234567890125", "qmsg": "tin goc"})
        assert d["path"] == "/api/message/quote", d
        assert d["body"]["qmsgOwner"] == "20002", d
        assert d["body"]["qmsgId"] == "m5", d
        assert d["body"]["qmsgCliId"] == 1234567890125, d
        assert d["body"]["qmsgType"] == 1, d
        assert d["body"]["qmsg"] == "tin goc", d
        assert isinstance(d["body"]["clientId"], int), d
        d = svc.dispatch("quote_message", {
            "thread_id": "30001", "type": "group", "msg_id": "m5",
            "text": "trich dan", "qmsg_owner": "20002",
            "qmsg": "tin goc"})
        assert d["path"] == "/api/group/quote", d
        assert d["body"]["language"] == "vi", d
        assert d["body"]["visibility"] == 0, d
        assert "imei" not in d["body"], d
        # seen / typing / sticker, both.
        d = svc.dispatch("mark_seen", {
            "thread_id": "30001", "type": "group",
            "msg_ids": "m6,m7"})
        assert d["path"] == "/api/group/seen", d
        assert d["body"]["msg_ids"] == ["m6", "m7"], d
        assert d["body"]["seen"] is True, d
        d = svc.dispatch("send_typing_event", {
            "thread_id": "20001", "type": "user"})
        assert d["path"] == "/api/message/typing", d
        assert d["body"]["destType"] == "USER", d
        d = svc.dispatch("send_typing_event", {
            "thread_id": "30001", "type": "group"})
        assert d["path"] == "/api/group/typing", d
        assert d["body"]["grid"] == "30001", d
        d = svc.dispatch("send_sticker", {
            "thread_id": "20001", "type": "user", "sticker_id": "s9",
            "cate_id": "c2"})
        assert d["path"] == "/api/message/sticker", d
        assert d["body"]["stickerId"] == "s9", d
        assert isinstance(d["body"]["clientId"], int), d
        assert d["body"]["ttl"] == 0, d
        d = svc.dispatch("send_sticker", {
            "thread_id": "30001", "type": "group", "sticker_id": "s9"})
        assert d["path"] == "/api/group/sticker", d
        # Group history: only groups; 1-1 must refuse honestly.
        d = svc.dispatch("get_group_chat_history", {
            "thread_id": "30001", "type": "group", "count": "10"})
        assert d["path"] == "/api/group/history", d
        assert d["body"] == {"grid": "30001", "count": 10}, d
        try:
            svc.dispatch("get_group_chat_history", {
                "thread_id": "20001", "type": "user"})
            raise AssertionError("1-1 history must refuse")
        except svc_mod.UnsupportedService as e:
            assert "nhóm" in e.reason, e.reason
        # fetchImportant: user only, body {limit, uid} (no imei).
        d = svc.dispatch("fetch_important", {
            "thread_id": "20001", "type": "user"})
        assert d["path"] == "/api/message/fetchImportant", d
        assert d["body"] == {"limit": 50, "uid": "20001"}, d
    finally:
        mock.stop()


def test_dispatch_friends():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        d = svc.dispatch("send_friend_request", {
            "user_id": "20009", "message": "Chao ban"})
        assert d["path"] == "/api/friend/sendreq", d
        assert d["body"] == {"toid": "20009", "msg": "Chao ban",
                             "reqsrc": -1, "imei": "dev-1",
                             "language": "vi"}, d
        d = svc.dispatch("accept_friend_request", {"user_id": "20009"})
        assert d["path"] == "/api/friend/accept", d
        assert d["body"] == {"fid": "20009", "language": "vi"}, d
        d = svc.dispatch("block_user", {"user_id": "20009"})
        assert d["path"] == "/api/friend/block", d
        assert d["body"] == {"fid": "20009", "imei": "dev-1"}, d
        d = svc.dispatch("unblock_user", {"user_id": "20009"})
        assert d["path"] == "/api/friend/unblock", d
        assert d["body"] == {"fid": "20009", "imei": "dev-1"}, d
        d = svc.dispatch("get_sent_friend_requests", {})
        assert d["path"] == "/api/friend/requested/list", d
        assert d["body"] == {"imei": "dev-1"}, d
        d = svc.dispatch("undo_friend_request", {"friend_id": "20009"})
        assert d["path"] == "/api/friend/undo", d
        assert d["body"] == {"fid": "20009"}, d
        d = svc.dispatch("remove_friend", {"friend_id": "20009"})
        assert d["path"] == "/api/friend/remove", d
        assert d["body"] == {"fid": "20009", "imei": "dev-1"}, d
        # Alias: GET; update co imei, remove KHONG imei.
        d = svc.dispatch("change_friend_alias", {
            "friend_id": "20002", "alias": "Ban B"})
        assert d["path"] == "/api/alias/update", d
        assert d["body"] == {"friendId": "20002", "alias": "Ban B",
                             "imei": "dev-1"}, d
        assert "/api/alias/update" in seen_paths(mock, "/api/alias/")
        assert "/api/alias/update" not in seen_post_paths(mock), \
            "alias update must be GET"
        d = svc.dispatch("remove_friend_alias", {"friend_id": "20002"})
        assert d["path"] == "/api/alias/remove", d
        assert d["body"] == {"friendId": "20002"}, d
        d = svc.dispatch("block_view_feed", {
            "user_id": "20009", "is_block_feed": "1"})
        assert d["path"] == "/api/friend/feed/block", d
        assert d["body"] == {"fid": "20009", "isBlockFeed": 1,
                             "imei": "dev-1"}, d
        d = svc.dispatch("block_view_feed", {
            "user_id": "20009", "is_block_feed": "false"})
        assert d["body"]["isBlockFeed"] == 0, d
    finally:
        mock.stop()


def test_dispatch_group_ops():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        g = {"thread_id": "30001", "type": "group"}
        # create_group la GET (khong phai POST) — body gname.
        d = svc.dispatch("create_group", {
            "name": "Nhom Moi", "member_ids": "20001,20002"})
        assert d["path"] == "/api/group/create", d
        assert d["body"]["gname"] == "Nhom Moi", d
        assert d["body"]["members"] == ["20001", "20002"], d
        assert d["body"]["nameChanged"] == 1, d
        assert isinstance(d["body"]["clientId"], int), d
        assert "imei" not in d["body"], d
        assert "/api/group/create" in seen_paths(mock, "/api/group/")
        assert "/api/group/create" not in seen_post_paths(mock), \
            "create_group must be GET"
        # get_group_info qua getmg (12604) da lan het.
        d = svc.dispatch("get_group_info", g)
        assert d["path"] == "/api/group/getmg", d
        assert d["body"] == {"grids": ["30001"], "avatar_size": 160,
                             "member_avatar_size": 160, "mpage": 1,
                             "mcount": 50, "imei": "dev-1"}, d
        assert "/api/group/getmg" in seen_post_paths(mock)
        d = svc.dispatch("add_user_to_group",
                         dict(g, member_id="20003"))
        assert d["path"] == "/api/group/invite", d
        assert d["body"] == {"grid": "30001",
                             "members": ["20003"]}, d
        d = svc.dispatch("remove_user_from_group",
                         dict(g, member_id="20003"))
        assert d["path"] == "/api/group/kickout", d
        assert d["body"] == {"grid": "30001", "members": ["20003"],
                             "imei": "dev-1"}, d
        d = svc.dispatch("change_group_name", dict(g, name="Ten Moi"))
        assert d["path"] == "/api/group/updateinfo", d
        assert d["body"] == {"grid": "30001", "gname": "Ten Moi",
                             "imei": "dev-1"}, d
        # change_group_avatar: upload file, khong phai URL.
        try:
            svc.dispatch("change_group_avatar", dict(g))
            raise AssertionError("avatar without file must raise")
        except ValueError as e:
            assert "file" in str(e), e
        d = svc.dispatch(
            "change_group_avatar", dict(g, width="800", height="600"),
            files={"file": ("avt.png", "image/png", b"FAKEPNG")})
        assert d["path"] == "/api/group/upavatar", d
        assert d["body"]["grid"] == "30001", d
        assert isinstance(d["body"]["clientId"], int), d
        assert d["body"]["originWidth"] == 800, d
        assert d["body"]["originHeight"] == 600, d
        # Deputy: GET, members ARRAY.
        d = svc.dispatch("add_group_deputy", dict(g, member_id="20002"))
        assert d["path"] == "/api/group/admins/add", d
        assert d["body"] == {"grid": "30001", "members": ["20002"],
                             "imei": "dev-1"}, d
        assert "/api/group/admins/add" not in seen_post_paths(mock), \
            "add_group_deputy must be GET"
        d = svc.dispatch("remove_group_deputy",
                         dict(g, member_id="20002"))
        assert d["path"] == "/api/group/admins/remove", d
        assert d["body"]["members"] == ["20002"], d
        # change owner: newAdminId.
        d = svc.dispatch("change_group_owner",
                         dict(g, member_id="20002"))
        assert d["path"] == "/api/group/change-owner", d
        assert d["body"] == {"grid": "30001", "newAdminId": "20002",
                             "imei": "dev-1", "language": "vi"}, d
        d = svc.dispatch("disperse_group", g)
        assert d["path"] == "/api/group/disperse", d
        assert d["body"] == {"grid": "30001", "imei": "dev-1"}, d
        # Group link ops: GET, khong phai POST.
        d = svc.dispatch("enable_group_link", g)
        assert d["path"] == "/api/group/link/new", d
        assert "/api/group/link/new" not in seen_post_paths(mock)
        d = svc.dispatch("disable_group_link", g)
        assert d["path"] == "/api/group/link/disable", d
        assert "/api/group/link/disable" not in seen_post_paths(mock)
        d = svc.dispatch("get_group_link", g)
        assert d["path"] == "/api/group/link/detail", d
        d = svc.dispatch("join_group", {"link": "https://zalo.me/g/abc"})
        assert d["path"] == "/api/group/link/join", d
        assert d["body"] == {"link": "https://zalo.me/g/abc",
                             "clientLang": "vi"}, d
        assert "/api/group/link/join" not in seen_post_paths(mock)
        # leave: grids ARRAY + silent 0/1.
        d = svc.dispatch("leave_group", dict(g, silent="true"))
        assert d["path"] == "/api/group/leave", d
        assert d["body"] == {"grids": ["30001"], "imei": "dev-1",
                             "silent": 1, "language": "vi"}, d
        d = svc.dispatch("leave_group", dict(g, silent="false"))
        assert d["body"]["silent"] == 0, d
        # Note group (board domain).
        d = svc.dispatch("create_note_group", dict(g, title="Ghi chu"))
        assert d["path"] == "/api/board/topic/create", d
        assert d["body"]["grid"] == "30001", d
        assert d["body"]["type"] == 0, d
        assert d["body"]["color"] == -16777216, d
        assert json.loads(d["body"]["params"]) == \
            {"title": "Ghi chu"}, d
        assert d["body"]["needPin"] is False, d
        assert "src" not in d["body"], d
        d = svc.dispatch("edit_note_group",
                         dict(g, topic_id="t1", title="Sua"))
        assert d["path"] == "/api/board/topic/update", d
        assert d["body"]["topicId"] == "t1", d
        assert json.loads(d["body"]["params"]) == {"title": "Sua"}, d
        assert "needPin" not in d["body"], d
        d = svc.dispatch("get_list_board", g)
        assert d["path"] == "/api/board/list", d
        assert d["body"] == {"group_id": "30001",
                             "imei": "dev-1"}, d
        # Group-only ops refuse a user thread (no fake 1-1 call).
        try:
            svc.dispatch("change_group_name", {
                "thread_id": "20001", "type": "user", "name": "X"})
            raise AssertionError("group op on user thread must refuse")
        except svc_mod.UnsupportedService as e:
            assert "nhóm" in e.reason, e.reason
    finally:
        mock.stop()


def test_dispatch_pin_hidden_archived():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        # get_pin_conversations: shape that {version, conversations}.
        d = svc.dispatch("get_pin_conversations", {})
        assert d == {"version": 3, "conversations": ["u20001"]}, d
        # set_pinned: GET list truoc (version 3) roi POST update.
        d = svc.dispatch("set_pinned_conversation", {
            "thread_id": "20002", "type": "user", "pinned": "true"})
        assert d["path"] == "/api/pinconvers/update", d
        assert d["body"] == {"version": 3, "conversations": [
            "u20001", "u20002"]}, d
        d = svc.dispatch("set_pinned_conversation", {
            "thread_id": "20001", "type": "user", "pinned": "false"})
        assert d["body"] == {"version": 3, "conversations": []}, d
        d = svc.dispatch("set_pinned_conversation", {
            "thread_id": "30001", "type": "group", "pinned": "true"})
        assert d["body"] == {"version": 3, "conversations": [
            "u20001", "g30001"]}, d
        # Loi 212 (server chua co danh sach ghim) -> version 0,
        # danh sach rong.
        mock.pin_list_mode = "error212"
        d = svc.dispatch("set_pinned_conversation", {
            "thread_id": "20002", "type": "user", "pinned": "true"})
        assert d["body"] == {"version": 0, "conversations": [
            "u20002"]}, d
        mock.pin_list_mode = "ok"
        # Archived / hidden.
        d = svc.dispatch("get_archived_chat_list", {})
        assert d["path"] == "/api/archivedchat/list", d
        assert d["body"] == {"version": 0, "imei": "dev-1"}, d
        d = svc.dispatch("get_hidden_conversations", {})
        assert d["path"] == "/api/hiddenconvers/get-all", d
        assert d["body"] == {"imei": "dev-1"}, d
        d = svc.dispatch("set_hidden_conversations", {
            "thread_id": "20001", "type": "user", "hidden": "true"})
        assert d["path"] == "/api/hiddenconvers/add-remove", d
        assert json.loads(d["body"]["add_threads"]) == ["20001"], d
        assert json.loads(d["body"]["del_threads"]) == [], d
        d = svc.dispatch("set_hidden_conversations", {
            "thread_id": "20001", "type": "user", "hidden": "false"})
        assert json.loads(d["body"]["del_threads"]) == ["20001"], d
        assert json.loads(d["body"]["add_threads"]) == [], d
        d = svc.dispatch("update_hidden_convers_pin", {"pin": "1234"})
        assert d["path"] == "/api/hiddenconvers/update-pin", d
        assert d["body"] == {"new_pin": "1234", "imei": "dev-1"}, d
        # reset PIN: GET KHONG co params.
        d = svc.dispatch("reset_hidden_convers_pin", {})
        assert d["path"] == "/api/hiddenconvers/reset", d
        assert d["body"] == {}, d
        seen_reset = [qs for p, qs, _ in mock.seen
                      if p == "/api/hiddenconvers/reset"]
        assert seen_reset and "params" not in seen_reset[0], seen_reset
    finally:
        mock.stop()


def test_dispatch_reaction():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        # like: map da xac minh (rType 3, rIcon "/-strong").
        d = svc.dispatch("add_reaction", {
            "thread_id": "20001", "type": "user", "icon": "like",
            "msg_id": "m1", "cli_msg_id": "1234567890123"})
        assert d["path"] == "/api/message/reaction", d
        assert d["body"]["toid"] == "20001", d
        assert "imei" not in d["body"], d
        item = d["body"]["react_list"][0]
        assert item["clientId"] == 1234567890123, item
        msg = json.loads(item["message"])
        assert msg["rMsg"] == [{"gMsgID": "m1",
                                "cMsgID": 1234567890123,
                                "msgType": 1}], msg
        assert msg["rIcon"] == "/-strong" and msg["rType"] == 3, msg
        assert msg["source"] == 6, msg
        # Nhom: grid + imei.
        d = svc.dispatch("add_reaction", {
            "thread_id": "30001", "type": "group", "icon": "like",
            "msg_id": "m2", "cli_msg_id": "1234567890124"})
        assert d["path"] == "/api/group/reaction", d
        assert d["body"]["grid"] == "30001", d
        assert d["body"]["imei"] == "dev-1", d
        # Bang day du (zca-js): icon co ten trong bang -> tu suy (rIcon, rType), khong can truyen tay.
        d = svc.dispatch("add_reaction", {
            "thread_id": "20001", "type": "user", "icon": "heart",
            "msg_id": "m1", "cli_msg_id": "1234567890123"})
        msg = json.loads(d["body"]["react_list"][0]["message"])
        assert msg["rIcon"] == "/-heart" and msg["rType"] == 5, msg
        assert len(svc_mod.REACTION_ICONS) >= 50, "bang bieu tuong phai day du"
        # Icon ngoai bang: phai truyen r_icon/r_type truc tiep (co thi dung), khong co thi bao loi ro rang kem danh sach ten.
        d = svc.dispatch("add_reaction", {
            "thread_id": "20001", "type": "user", "icon": "tu-dat",
            "msg_id": "m1", "cli_msg_id": "1234567890123",
            "r_icon": "/-heart", "r_type": "5"})
        msg = json.loads(d["body"]["react_list"][0]["message"])
        assert msg["rIcon"] == "/-heart" and msg["rType"] == 5, msg
        try:
            svc.dispatch("add_reaction", {
                "thread_id": "20001", "type": "user", "icon": "tu-dat",
                "msg_id": "m1", "cli_msg_id": "1234567890123"})
            raise AssertionError("icon ngoai bang phai bao loi")
        except ValueError as e:
            assert "không có trong bảng" in str(e) and "heart" in str(e), e
        # Khong co services map -> tu choi, khong doan domain.
        svc2 = make_svc_no_map()
        try:
            svc2.dispatch("add_reaction", {
                "thread_id": "20001", "type": "user", "icon": "like",
                "msg_id": "m1", "cli_msg_id": "1234567890123"})
            raise AssertionError("no service map must refuse")
        except svc_mod.UnsupportedService as e:
            assert "services map" in e.reason, e.reason
    finally:
        mock.stop()


def test_dispatch_poll():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        g = {"thread_id": "30001", "type": "group"}
        d = svc.dispatch("create_poll", dict(
            g, question="Chon mon?", options="A,B,C",
            allow_multi_choices="true"))
        assert d["path"] == "/api/poll/create", d
        assert d["body"] == {
            "group_id": "30001", "question": "Chon mon?",
            "options": ["A", "B", "C"], "allow_multi_choices": True,
            "allow_add_new_option": True, "is_anonymous": False,
            "poll_type": 0, "expired_time": 0, "pinAct": 0,
            "imei": "dev-1"}, d
        d = svc.dispatch("get_poll_detail", dict(g, poll_id="p1"))
        assert d["path"] == "/api/poll/detail", d
        assert d["body"] == {"poll_id": "p1", "imei": "dev-1"}, d
        assert "/api/poll/detail" not in seen_post_paths(mock), \
            "get_poll_detail must be GET"
        d = svc.dispatch("lock_poll", dict(g, poll_id="p1"))
        assert d["path"] == "/api/poll/end", d
        assert d["body"] == {"poll_id": "p1", "imei": "dev-1"}, d
    finally:
        mock.stop()


def test_dispatch_quick_message():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        d = svc.dispatch("add_quick_message", {
            "keyword": "chao", "title": "Chao ban!"})
        assert d["path"] == "/api/quickmessage/create", d
        assert d["body"] == {"keyword": "chao", "message": "Chao ban!",
                             "imei": "dev-1"}, d
        assert "media" not in d["body"] and "type" not in d["body"], d
        assert "/api/quickmessage/create" not in seen_post_paths(mock)
        d = svc.dispatch("get_quick_message", {})
        assert d["path"] == "/api/quickmessage/list", d
        assert d["body"] == {"version": 0, "lang": 0,
                             "imei": "dev-1"}, d
        d = svc.dispatch("remove_quick_message",
                         {"item_ids": "i1,i2"})
        assert d["path"] == "/api/quickmessage/delete", d
        assert d["body"] == {"itemIds": ["i1", "i2"]}, d
        d = svc.dispatch("update_quick_message", {
            "item_id": "i1", "keyword": "chao2",
            "title": "Chao ban nhe!"})
        assert d["path"] == "/api/quickmessage/update", d
        assert d["body"] == {"itemId": "i1", "keyword": "chao2",
                             "message": "Chao ban nhe!"}, d
        # Khong co services map -> tu choi.
        svc2 = make_svc_no_map()
        try:
            svc2.dispatch("get_quick_message", {})
            raise AssertionError("no service map must refuse")
        except svc_mod.UnsupportedService as e:
            assert "services map" in e.reason, e.reason
    finally:
        mock.stop()


def test_dispatch_conversation_profile_sticker():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        u = {"thread_id": "20001", "type": "user"}
        # get_unread_mark / get_auto_delete_chat: params rong {}.
        d = svc.dispatch("get_unread_mark", {})
        assert d["path"] == "/api/conv/getUnreadMark", d
        assert d["body"] == {}, d
        d = svc.dispatch("add_unread_mark", u)
        assert d["path"] == "/api/conv/addUnreadMark", d
        inner = json.loads(d["body"]["param"])
        assert inner == {"convsGroup": [], "convsUser": ["20001"],
                         "imei": "dev-1"}, inner
        d = svc.dispatch("add_unread_mark",
                         {"thread_id": "30001", "type": "group"})
        inner = json.loads(d["body"]["param"])
        assert inner["convsGroup"] == ["30001"], inner
        assert inner["convsUser"] == [], inner
        d = svc.dispatch("remove_unread_mark", u)
        assert d["path"] == "/api/conv/removeUnreadMark", d
        inner = json.loads(d["body"]["param"])
        assert inner == {"convsGroup": [], "convsUser": ["20001"]}, inner
        d = svc.dispatch("delete_chat", u)
        assert d["path"] == "/api/message/deleteconver", d
        assert d["body"] == {"toid": "20001", "onlyMe": 1,
                             "imei": "dev-1"}, d
        d = svc.dispatch("delete_chat",
                         {"thread_id": "30001", "type": "group",
                          "cli_msg_id": "1234567890123"})
        assert d["path"] == "/api/group/deleteconver", d
        assert d["body"]["cliMsgId"] == 1234567890123, d
        d = svc.dispatch("get_auto_delete_chat", {})
        assert d["path"] == "/api/conv/autodelete/getConvers", d
        assert d["body"] == {}, d
        # update_auto_delete: POST nhung params trong QUERY URL.
        d = svc.dispatch("update_auto_delete_chat",
                         dict(u, ttl="86400000"))
        assert d["path"] == "/api/conv/autodelete/updateConvers", d
        assert d["body"] == {"threadId": "20001", "isGroup": False,
                             "ttl": 86400000, "clientLang": "vi"}, d
        assert "/api/conv/autodelete/updateConvers" in \
            seen_post_paths(mock), "auto-delete update must be POST"
        seen_q = [qs for p, qs, _ in mock.seen
                  if p == "/api/conv/autodelete/updateConvers"]
        assert seen_q and "params" in seen_q[0], seen_q
        d = svc.dispatch("update_auto_delete_chat", {
            "thread_id": "30001", "type": "group", "ttl": "0"})
        assert d["body"]["isGroup"] is True, d
        assert d["body"]["ttl"] == 0, d
        d = svc.dispatch("get_mute", {})
        assert d["path"] == "/api/social/profile/getmute", d
        # set_mute: action 1/3, muteType 1/2, startTime hien tai.
        before = int(time.time())
        d = svc.dispatch("set_mute", dict(u, duration="3600"))
        assert d["path"] == "/api/social/profile/setmute", d
        assert d["body"]["toid"] == "20001", d
        assert d["body"]["duration"] == 3600, d
        assert d["body"]["action"] == 1, d
        assert d["body"]["muteType"] == 1, d
        assert before <= d["body"]["startTime"] <= int(time.time()), d
        assert d["body"]["imei"] == "dev-1", d
        d = svc.dispatch("set_mute", dict(u, duration="0"))
        assert d["body"]["action"] == 3, d
        d = svc.dispatch("set_mute", {
            "thread_id": "30001", "type": "group", "duration": "-1"})
        assert d["body"]["muteType"] == 2, d
        assert d["body"]["duration"] == -1, d
        d = svc.dispatch("find_user", {"phone": "0900000000"})
        assert d["path"] == "/api/friend/profile/get", d
        assert d["body"] == {"phone": "0900000000",
                             "avatar_size": 240, "language": "vi",
                             "imei": "dev-1"}, d
        d = svc.dispatch("get_user_info", {"user_id": "20002"})
        assert d["path"] == "/api/social/friend/getprofiles/v2", d
        d = svc.dispatch("last_online", {"user_id": "20002"})
        assert d["path"] == "/api/social/profile/lastOnline", d
        assert d["body"] == {"uid": "20002", "imei": "dev-1"}, d
        d = svc.dispatch("update_profile", {"name": "Ten Moi"})
        assert d["path"] == "/api/social/profile/update", d
        assert d["body"]["name"] == "Ten Moi", d
        # update_settings la GET tren wpa.zalo.me (auth domain).
        d = svc.dispatch("update_settings", {
            "setting_type": "seen_status", "status": "0"})
        assert d["path"] == "/api/setting/update", d
        assert d["body"]["status"] == 0, d
        assert "/api/setting/update" not in seen_post_paths(mock), \
            "update_settings must be GET"
        # change_account_avatar: upload file.
        try:
            svc.dispatch("change_account_avatar", {})
            raise AssertionError("avatar without file must raise")
        except ValueError as e:
            assert "file" in str(e), e
        d = svc.dispatch(
            "change_account_avatar", {},
            files={"file": ("b.png", "image/png", b"FAKEPNG")})
        assert d["path"] == "/api/profile/upavatar", d
        assert d["body"]["language"] == "vi", d
        assert isinstance(d["body"]["clientId"], int), d
        d = svc.dispatch("get_avatar_list", {"count": "5", "page": "2"})
        assert d["path"] == "/api/social/avatar-list", d
        assert d["body"] == {"count": 5, "page": 2,
                             "imei": "dev-1"}, d
        # get_stickers: params AES cua chuoi rong "".
        d = svc.dispatch("get_stickers", {})
        assert d["path"] == "/api/message/sticker/category/list", d
        assert d["body"] == "", d
        d = svc.dispatch("get_stickers_detail",
                         {"sticker_album": "a1"})
        assert d["path"] == \
            "/api/message/sticker/category/detail", d
        assert d["body"] == {"cid": "a1"}, d
        d = svc.dispatch("parse_link", {"link": "https://example.invalid"})
        assert d["path"] == "/api/message/parselink", d
        assert d["body"] == {"link": "https://example.invalid",
                             "version": 1, "imei": "dev-1"}, d
        d = svc.dispatch("get_labels", {})
        assert d["path"] == "/api/convlabel/get", d
        d = svc.dispatch("update_label", dict(u, label_ids="l1,l2"))
        assert d["path"] == "/api/convlabel/update", d
        assert d["body"]["labelIds"] == ["l1", "l2"], d
    finally:
        mock.stop()


def test_dispatch_reminders_user_vs_group():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        u = {"thread_id": "20001", "type": "user"}
        g = {"thread_id": "30001", "type": "group"}
        # create 1-1: objectData JSON-str.
        d = svc.dispatch("create_reminder", dict(
            u, title="Hop", content="Nho hop",
            remind_time="2026-11-06T10:00:00+07:00"))
        assert d["path"] == "/api/board/oneone/create", d
        assert d["body"]["imei"] == "dev-1", d
        obj = json.loads(d["body"]["objectData"])
        assert obj["toUid"] == "20001", obj
        assert obj["type"] == 0, obj
        assert obj["color"] == -16777216, obj
        assert obj["emoji"] == "⏰", obj
        assert obj["duration"] == -1, obj
        assert obj["params"] == {"title": "Hop",
                                 "content": "Nho hop"}, obj
        assert obj["needPin"] is False, obj
        assert obj["repeat"] == 0, obj
        expect_ms = int(datetime(2026, 11, 6, 3, 0, 0,
                                 tzinfo=timezone.utc).timestamp() * 1000)
        assert obj["startTime"] == expect_ms, obj
        assert "src" not in obj, obj
        # create nhom: qua topic/create (da lan) — khong con 409.
        d = svc.dispatch("create_reminder", dict(
            g, title="Hop", remind_time="2026-11-06T10:00:00+07:00"))
        assert d["path"] == "/api/board/topic/create", d
        assert d["body"]["grid"] == "30001", d
        assert d["body"]["type"] == 0, d
        assert json.loads(d["body"]["params"]) == {"title": "Hop"}, d
        assert d["body"]["startTime"] == expect_ms, d
        # remove: 1-1 {uid, reminderId} (KHONG imei); nhom qua
        # topic/remove.
        d = svc.dispatch("remove_reminder", dict(u, reminder_id="r1"))
        assert d["path"] == "/api/board/oneone/remove", d
        assert d["body"] == {"uid": "20001", "reminderId": "r1"}, d
        d = svc.dispatch("remove_reminder", dict(g, reminder_id="r1"))
        assert d["path"] == "/api/board/topic/remove", d
        assert d["body"] == {"grid": "30001", "topicId": "r1",
                             "imei": "dev-1"}, d
        # edit: 1-1 objectData (KHONG imei); nhom eventId.
        d = svc.dispatch("edit_reminder",
                         dict(u, topic_id="r1", title="Hop moi"))
        assert d["path"] == "/api/board/oneone/update", d
        assert "imei" not in d["body"], d
        obj = json.loads(d["body"]["objectData"])
        assert obj["reminderId"] == "r1", obj
        assert obj["params"] == {"title": "Hop moi"}, obj
        assert obj["startTime"] == -1, obj
        d = svc.dispatch("edit_reminder",
                         dict(g, topic_id="r1", title="Hop moi"))
        assert d["path"] == "/api/board/topic/updateEventResponse", d
        assert d["body"] == {"grid": "30001", "eventId": "r1",
                             "imei": "dev-1"}, d
        # list: objectData JSON-str({uid|group_id}).
        d = svc.dispatch("get_list_reminder", u)
        assert d["path"] == "/api/board/oneone/list", d
        assert json.loads(d["body"]["objectData"]) == \
            {"uid": "20001"}, d
        assert "imei" not in d["body"], d
        d = svc.dispatch("get_list_reminder", g)
        assert d["path"] == "/api/board/listReminder", d
        assert json.loads(d["body"]["objectData"]) == \
            {"group_id": "30001"}, d
        assert d["body"]["imei"] == "dev-1", d
        # get / responses: chi eventId (+ imei cho get).
        d = svc.dispatch("get_reminder", {"reminder_id": "r1"})
        assert d["path"] == "/api/board/topic/getReminder", d
        assert d["body"] == {"eventId": "r1", "imei": "dev-1"}, d
        d = svc.dispatch("get_reminder_responses",
                         {"reminder_id": "r1"})
        assert d["path"] == "/api/board/topic/listResponseEvent", d
        assert d["body"] == {"eventId": "r1"}, d
    finally:
        mock.stop()


def test_dispatch_refusals_and_validation():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        cases = [
            ("get_logged_accounts", "zalobot"),
            ("get_account_details", "zalobot"),
            ("get_account_webhooks", "zalobot"),
            ("set_account_webhook", "zalobot"),
            ("delete_account_webhook", "zalobot"),
            ("get_proxies", "zalobot"),
            ("add_proxy", "zalobot"),
            ("remove_proxy", "zalobot"),
            ("get_login_qr", "zalobot"),
            ("send_message", "chat"),
            ("send_file", "chat"),
            ("send_video", "chat"),
            ("send_card", "chat"),
        ]
        for action, want_status in cases:
            try:
                svc.dispatch(action, {"thread_id": "20001",
                                      "type": "user"})
                raise AssertionError("%s must refuse" % action)
            except svc_mod.UnsupportedService as e:
                assert e.status == want_status, (action, e.status)
                assert e.reason, action
        # The old 25 "unsupported" now all work — spot-check one of
        # each family refuses NOTHING.
        for action, params in (
                ("send_friend_request", {"user_id": "20009"}),
                ("set_pinned_conversation", {
                    "thread_id": "20001", "type": "user",
                    "pinned": "true"}),
                ("create_poll", {"thread_id": "30001", "type": "group",
                                 "question": "Q?", "options": "A,B"}),
                ("add_quick_message", {"keyword": "k",
                                       "title": "t"}),
                ("add_reaction", {"thread_id": "20001", "type": "user",
                                  "icon": "like", "msg_id": "m1",
                                  "cli_msg_id": "1234567890123"})):
            d = svc.dispatch(action, params)
            assert d.get("path") or d.get("results"), (action, d)
        try:
            svc.dispatch("khong_co_thao_tac_nay", {})
            raise AssertionError("unknown action must raise")
        except svc_mod.UnknownAction:
            pass
        # Missing required param -> ValueError (HTTP 400), not a
        # call to Zalo with an empty body.
        before = len(mock.seen)
        try:
            svc.dispatch("undo_message",
                         {"thread_id": "20001", "type": "user"})
            raise AssertionError("missing msg_id must raise")
        except ValueError as e:
            assert "msg_id" in str(e), e
        assert len(mock.seen) == before, mock.seen[before:]
        try:
            svc.dispatch("undo_message", {"type": "user",
                                          "msg_id": "m1"})
            raise AssertionError("missing thread_id must raise")
        except ValueError as e:
            assert "thread_id" in str(e), e
    finally:
        mock.stop()


# ---------------------------------------------------------------- HTTP API
def _start_app_server(mock, tmp):
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % port


def _api(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _api_raw(base, method, path, data, content_type):
    req = urllib.request.Request(base + path, method=method, data=data)
    req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _login_via_qr(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            return
        time.sleep(0.5)
    raise AssertionError("qr did not reach done: %s" % last)


def test_svc_http_api():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-test-")
    mock = MockZalo().start()
    httpd = None
    try:
        patch_domains(mock)
        httpd, base = _start_app_server(mock, tmp)

        # Catalog: static description, no account data. (In this
        # test server app auth is not configured, so no app session
        # is needed here; in production the route sits behind the
        # same app-login gate as every /api/* route — see
        # test_app_auth.py, which pins 401 for it unauthenticated.)
        status, body = _api(base, "GET", "/api/svc/catalog")
        assert status == 200, body
        assert body["counts"]["total_96"] == 96, body["counts"]
        assert body["counts"]["supported"] == 81, body["counts"]

        # Before login: every op is 401 (Zalo session required).
        status, body = _api(base, "POST", "/api/svc/send_typing_event",
                            {"thread_id": "20001", "type": "user"})
        assert status == 401, body
        assert body["error"] == "chua_dang_nhap", body

        _login_via_qr(base)

        # A supported op works end to end and decodes the envelope.
        status, body = _api(base, "POST", "/api/svc/send_typing_event",
                            {"thread_id": "20001", "type": "user"})
        assert status == 200, body
        assert body["ok"] is True, body
        assert body["data"]["path"] == "/api/message/typing", body
        assert body["data"]["body"]["toid"] == "20001", body

        # A group op goes to the group endpoint.
        status, body = _api(base, "POST", "/api/svc/change_group_name",
                            {"thread_id": "30001", "type": "group",
                             "name": "Ten Moi"})
        assert status == 200, body
        assert body["data"]["path"] == "/api/group/updateinfo", body

        # Reaction works end to end: mock login tra services map
        # (reaction/quick_message -> mock base).
        status, body = _api(base, "POST", "/api/svc/add_reaction",
                            {"thread_id": "20001", "type": "user",
                             "icon": "like", "msg_id": "m1",
                             "cli_msg_id": "1234567890123"})
        assert status == 200, body
        assert body["data"]["path"] == "/api/message/reaction", body
        item = body["data"]["body"]["react_list"][0]
        assert item["clientId"] == 1234567890123, item
        assert json.loads(item["message"])["rType"] == 3, item

        # Group reminder create/remove now work (topic/create,
        # topic/remove) — no longer 409.
        status, body = _api(base, "POST", "/api/svc/create_reminder",
                            {"thread_id": "30001", "type": "group",
                             "title": "Hop",
                             "remind_time": "2026-11-06T10:00:00+07:00"})
        assert status == 200, body
        assert body["data"]["path"] == "/api/board/topic/create", body
        status, body = _api(base, "POST", "/api/svc/remove_reminder",
                            {"thread_id": "30001", "type": "group",
                             "reminder_id": "r1"})
        assert status == 200, body
        assert body["data"]["path"] == "/api/board/topic/remove", body

        # Group avatar upload (multipart field "file").
        mbody, mctype = chat_mod.build_multipart(
            {"thread_id": "30001", "type": "group"},
            [("file", "avt.png", "image/png", b"FAKEPNG")])
        status, body = _api_raw(base, "POST",
                                "/api/svc/change_group_avatar",
                                mbody, mctype)
        assert status == 200, body
        assert body["data"]["path"] == "/api/group/upavatar", body

        # A zalobot-only service answers 409 with its status + a
        # clear reason — never a fake success.
        status, body = _api(base, "POST", "/api/svc/get_login_qr", {})
        assert status == 409 and body["status"] == "zalobot", body
        status, body = _api(base, "POST", "/api/svc/set_account_webhook",
                            {"own_id": "10001"})
        assert status == 409 and body["status"] == "zalobot", body
        status, body = _api(base, "POST", "/api/svc/send_message",
                            {"thread_id": "20001", "type": "user",
                             "message": "xin chao"})
        assert status == 409 and body["status"] == "chat", body

        # Unknown action -> 404; missing param -> 400.
        status, body = _api(base, "POST", "/api/svc/khong_co",
                            {"thread_id": "20001"})
        assert status == 404, body
        status, body = _api(base, "POST", "/api/svc/undo_message",
                            {"thread_id": "20001", "type": "user"})
        assert status == 400, body
        assert "msg_id" in body["error"], body
        httpd.shutdown()
    finally:
        if httpd:
            try:
                httpd.shutdown()
            except Exception:
                pass
        mock.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL SERVICES TESTS PASSED")
