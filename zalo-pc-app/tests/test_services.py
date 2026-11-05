"""Tests for the addon-services panel (zalo_pc_app/services.py).

Pins, against the strict mock (two-layer envelope, common params
zpw_ver=695/zpw_type=30, fully percent-encoded params):
  - the catalog covers all 96 addon services exactly once, with
    honest statuses (supported / view / chat / zalobot /
    unsupported) and no fake "supported" for a service without a
    PC path in the 231-command table;
  - every supported op hits the right PC endpoint for its thread
    type (1-1 toid vs group grid) and decodes the envelope;
  - unsupported / chat / zalobot / unknown actions fail loudly
    with their status + reason (409 on the HTTP API), never with
    a fake success;
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
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo, TEST_PARAM_KEY, TEST_SESSION_KEY  # noqa: E402
from test_addon_client import FakeAddonClient  # noqa: E402
from zalo_pc_app import addon_client as addon_client_mod  # noqa: E402
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


def make_svc():
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


def seen_paths(mock, prefix):
    return [p for p, _, _ in mock.seen if p.startswith(prefix)]


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
    # PIVOT addon-embedded (2026-11-05): trong 96 co 79 supported
    # (48 PC + 25 no-PC-path + 6 zalobot-web-only) + 2 view + 11 chat
    # + 4 zalobot-only (proxies x3 + get_login_qr) = 96; khong con
    # "unsupported" nao. counts["supported"]=84 cong them 5 extra
    # (addon_no None, deu supported) ngoai bang 96.
    supported_96 = [e for e in by_no.values()
                    if e["status"] == "supported"]
    assert len(supported_96) == 79, len(supported_96)
    assert cat["counts"]["supported"] == 84, cat["counts"]
    assert cat["counts"]["view"] == 2, cat["counts"]
    assert cat["counts"]["chat"] == 11, cat["counts"]
    assert cat["counts"]["zalobot"] == 4, cat["counts"]
    assert cat["counts"].get("unsupported", 0) == 0, cat["counts"]
    # The 5 ops outside the 96 (quote, seen, fetchImportant, group
    # link detail, label update) carry addon_no None and are all
    # supported — they must not inflate the 96 count.
    extras = [e for e in cat["services"] if e["addon_no"] is None]
    assert len(extras) == 5, extras
    assert all(e["status"] == "supported" for e in extras), extras
    # Every OPS action appears in the catalog exactly once; the
    # catalog also carries addon-only actions (in ADDON_OPS) that the
    # PC dispatch table never had — those are the newly-supported
    # ops from the pivot.
    actions = [e["action"] for e in cat["services"] if e["action"]]
    assert len(actions) == len(set(actions)), "duplicate action"
    assert set(svc_mod.OPS) <= set(actions), set(svc_mod.OPS) - set(actions)
    assert set(actions) <= set(svc_mod.OPS) | set(svc_mod.ADDON_OPS), \
        set(actions) - set(svc_mod.OPS) - set(svc_mod.ADDON_OPS)
    # Unsupported entries carry a reason and no action (no button).
    for e in cat["services"]:
        if e["status"] in ("unsupported", "zalobot", "chat"):
            assert e["action"] is None, e
            assert e["reason"], e
    # Spot-check: cac op tung "no PC path" nay chay qua addon.
    by_addon = {e["addon"]: e for e in cat["services"]}
    for addon in ("add_reaction", "set_pinned_conversation",
                  "create_poll", "set_account_webhook"):
        assert by_addon[addon]["status"] == "supported", by_addon[addon]
        assert by_addon[addon]["action"] == addon, by_addon[addon]
    # 4 op zalobot con lai: proxies x3 + get_login_qr.
    assert sorted(e["addon"] for e in cat["services"]
                  if e["status"] == "zalobot") == \
        ["add_proxy", "get_login_qr", "get_proxies", "remove_proxy"]
    assert "khung chat" in by_addon["send_message"]["reason"]


def test_catalog_body_unverified_flagged():
    """Ops whose body the audit did NOT fully trace are flagged, so
    the UI warns and the integrator knows what to verify live.
    The handful with a known body (typing, seen, sticker, history,
    fetchImportant) are flagged False."""
    known = {"send_typing_event", "mark_seen", "send_sticker",
             "get_group_chat_history", "fetch_important"}
    for action, spec in svc_mod.OPS.items():
        if action in known:
            assert spec["body_unverified"] is False, action
        else:
            assert spec["body_unverified"] is True, action


# ---------------------------------------------------------------- dispatch
def test_dispatch_message_ops_both_threads():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc()
        # undo 1-1 -> /api/message/undo (11281 path), group ->
        # /api/group/undomsg; body carries toid vs grid + imei.
        d = svc.dispatch("undo_message", {
            "thread_id": "20001", "type": "user", "msg_id": "m1",
            "cli_msg_id": "c1"})
        assert d["path"] == "/api/message/undo", d
        assert d["body"]["toid"] == "20001"
        assert d["body"]["msgId"] == "m1"
        assert d["body"]["imei"] == "dev-1", d
        d = svc.dispatch("undo_message", {
            "thread_id": "30001", "type": "group", "msg_id": "m2"})
        assert d["path"] == "/api/group/undomsg", d
        assert d["body"]["grid"] == "30001", d
        # delete / forward / quote / seen / typing / sticker, both.
        d = svc.dispatch("delete_message", {
            "thread_id": "30001", "type": "group", "msg_id": "m3"})
        assert d["path"] == "/api/group/deletemsg", d
        d = svc.dispatch("forward_message", {
            "thread_id": "20001", "type": "user", "msg_id": "m4",
            "dest_thread_ids": "20002, 30001"})
        assert d["path"] == "/api/message/forward", d
        assert d["body"]["threadIds"] == ["20002", "30001"], d
        d = svc.dispatch("quote_message", {
            "thread_id": "20001", "type": "user", "msg_id": "m5",
            "text": "trich dan"})
        assert d["path"] == "/api/message/quote", d
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
        assert d["body"]["clientId"], d
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
        # fetchImportant: user only.
        d = svc.dispatch("fetch_important", {
            "thread_id": "20001", "type": "user"})
        assert d["path"] == "/api/message/fetchImportant", d
        assert d["body"]["uid"] == "20001"
        assert d["body"]["limit"] == 50, d
    finally:
        mock.stop()


def test_dispatch_group_ops():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc()
        g = {"thread_id": "30001", "type": "group"}
        d = svc.dispatch("create_group", {
            "name": "Nhom Moi", "member_ids": "20001,20002"})
        assert d["path"] == "/api/group/create", d
        assert d["body"]["members"] == ["20001", "20002"], d
        d = svc.dispatch("get_group_info", g)
        assert d["path"] == "/api/group/getgi/v2", d
        d = svc.dispatch("add_user_to_group",
                         dict(g, member_id="20003"))
        assert d["path"] == "/api/group/invite", d
        d = svc.dispatch("remove_user_from_group",
                         dict(g, member_id="20003"))
        assert d["path"] == "/api/group/kickout", d
        d = svc.dispatch("change_group_name", dict(g, name="Ten Moi"))
        assert d["path"] == "/api/group/updateinfo", d
        assert d["body"]["name"] == "Ten Moi", d
        d = svc.dispatch("change_group_avatar",
                         dict(g, avatar_url="https://x.invalid/a.png"))
        assert d["path"] == "/api/group/upavatar", d
        d = svc.dispatch("add_group_deputy", dict(g, member_id="20002"))
        assert d["path"] == "/api/group/admins/add", d
        d = svc.dispatch("remove_group_deputy",
                         dict(g, member_id="20002"))
        assert d["path"] == "/api/group/admins/remove", d
        d = svc.dispatch("change_group_owner",
                         dict(g, member_id="20002"))
        assert d["path"] == "/api/group/change-owner", d
        d = svc.dispatch("disperse_group", g)
        assert d["path"] == "/api/group/disperse", d
        d = svc.dispatch("enable_group_link", g)
        assert d["path"] == "/api/group/link/new", d
        d = svc.dispatch("disable_group_link", g)
        assert d["path"] == "/api/group/link/disable", d
        d = svc.dispatch("get_group_link", g)
        assert d["path"] == "/api/group/link/detail", d
        d = svc.dispatch("join_group", {"link": "https://zalo.me/g/abc"})
        assert d["path"] == "/api/group/link/join", d
        d = svc.dispatch("leave_group", dict(g, silent="true"))
        assert d["path"] == "/api/group/leave", d
        assert d["body"]["silent"] is True, d
        d = svc.dispatch("create_note_group", dict(g, title="Ghi chu"))
        assert d["path"] == "/api/board/topic/create", d
        d = svc.dispatch("edit_note_group",
                         dict(g, topic_id="t1", title="Sua"))
        assert d["path"] == "/api/board/topic/update", d
        d = svc.dispatch("get_list_board", g)
        assert d["path"] == "/api/board/list", d
        # Group-only ops refuse a user thread (no fake 1-1 call).
        try:
            svc.dispatch("change_group_name", {
                "thread_id": "20001", "type": "user", "name": "X"})
            raise AssertionError("group op on user thread must refuse")
        except svc_mod.UnsupportedService as e:
            assert "nhóm" in e.reason, e.reason
    finally:
        mock.stop()


def test_dispatch_conversation_profile_sticker():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc()
        u = {"thread_id": "20001", "type": "user"}
        d = svc.dispatch("get_unread_mark", {})
        assert d["path"] == "/api/conv/getUnreadMark", d
        d = svc.dispatch("add_unread_mark", u)
        assert d["path"] == "/api/conv/addUnreadMark", d
        d = svc.dispatch("remove_unread_mark", u)
        assert d["path"] == "/api/conv/removeUnreadMark", d
        d = svc.dispatch("delete_chat", u)
        assert d["path"] == "/api/message/deleteconver", d
        d = svc.dispatch("delete_chat",
                         {"thread_id": "30001", "type": "group"})
        assert d["path"] == "/api/group/deleteconver", d
        d = svc.dispatch("get_auto_delete_chat", {})
        assert d["path"] == "/api/conv/autodelete/getConvers", d
        d = svc.dispatch("update_auto_delete_chat",
                         dict(u, ttl="86400000"))
        assert d["path"] == "/api/conv/autodelete/updateConvers", d
        assert d["body"]["ttl"] == 86400000, d
        d = svc.dispatch("get_mute", {})
        assert d["path"] == "/api/social/profile/getmute", d
        d = svc.dispatch("set_mute", dict(u, duration="3600"))
        assert d["path"] == "/api/social/profile/setmute", d
        assert d["body"]["duration"] == 3600, d
        d = svc.dispatch("find_user", {"phone": "0900000000"})
        assert d["path"] == "/api/social/friend/phonebook/v2", d
        d = svc.dispatch("get_user_info", {"user_id": "20002"})
        assert d["path"] == "/api/social/friend/getprofiles/v2", d
        d = svc.dispatch("last_online", {"user_id": "20002"})
        assert d["path"] == "/api/social/profile/lastOnline", d
        d = svc.dispatch("update_profile", {"name": "Ten Moi"})
        assert d["path"] == "/api/social/profile/update", d
        assert d["body"]["name"] == "Ten Moi", d
        d = svc.dispatch("update_settings", {
            "setting_type": "seen_status", "status": "0"})
        assert d["path"] == "/api/setting/update", d
        assert d["body"]["status"] == 0, d
        d = svc.dispatch("change_account_avatar",
                         {"avatar_url": "https://x.invalid/b.png"})
        assert d["path"] == "/api/social/profile/avatar-url", d
        d = svc.dispatch("get_avatar_list", {"count": "5", "page": "2"})
        assert d["path"] == "/api/social/avatar-list", d
        assert d["body"] == {"count": 5, "page": 2,
                             "imei": "dev-1"}, d
        d = svc.dispatch("get_stickers", {})
        assert d["path"] == "/api/message/sticker/category/list", d
        d = svc.dispatch("get_stickers_detail",
                         {"sticker_album": "a1"})
        assert d["body"]["cateId"] == "a1", d
        d = svc.dispatch("parse_link", {"link": "https://example.invalid"})
        assert d["path"] == "/api/message/parselink", d
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
        svc = make_svc()
        u = {"thread_id": "20001", "type": "user"}
        g = {"thread_id": "30001", "type": "group"}
        d = svc.dispatch("create_reminder", dict(
            u, title="Hop", content="Nho hop", remind_time="2026-11-06"))
        assert d["path"] == "/api/board/oneone/create", d
        assert d["body"]["toid"] == "20001", d
        d = svc.dispatch("remove_reminder", dict(u, reminder_id="r1"))
        assert d["path"] == "/api/board/oneone/remove", d
        d = svc.dispatch("edit_reminder",
                         dict(u, topic_id="r1", title="Hop moi"))
        assert d["path"] == "/api/board/oneone/update", d
        d = svc.dispatch("edit_reminder",
                         dict(g, topic_id="r1", title="Hop moi"))
        assert d["path"] == "/api/board/topic/updateEventResponse", d
        d = svc.dispatch("get_list_reminder", u)
        assert d["path"] == "/api/board/oneone/list", d
        d = svc.dispatch("get_list_reminder", g)
        assert d["path"] == "/api/board/listReminder", d
        d = svc.dispatch("get_reminder", dict(g, reminder_id="r1"))
        assert d["path"] == "/api/board/topic/getReminder", d
        d = svc.dispatch("get_reminder_responses",
                         dict(g, reminder_id="r1"))
        assert d["path"] == "/api/board/topic/listResponseEvent", d
        # Group create/remove: no endpoint in the table — refuse
        # with the reason, never invent a path.
        for action, extra in (("create_reminder", {
                "title": "Hop", "remind_time": "2026-11-06"}),
                              ("remove_reminder", {"reminder_id": "r1"})):
            try:
                svc.dispatch(action, dict(g, **extra))
                raise AssertionError("%s on group must refuse" % action)
            except svc_mod.UnsupportedService as e:
                assert "chưa có endpoint" in e.reason, e.reason
    finally:
        mock.stop()


def test_dispatch_refusals_and_validation():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc()
        # PIVOT: cac op tung "unsupported"/"zalobot" nay gio la
        # "supported" (chi qua addon) — PC dispatch van tu choi
        # (khong co duong PC), nhung status phan anh dung catalog.
        # Chi get_proxies (khong co route JSON) con "zalobot".
        cases = [
            ("add_reaction", "supported"),
            ("set_pinned_conversation", "supported"),
            ("create_poll", "supported"),
            ("add_quick_message", "supported"),
            ("send_friend_request", "supported"),
            ("block_user", "supported"),
            ("set_account_webhook", "supported"),
            ("get_proxies", "zalobot"),
            ("get_logged_accounts", "supported"),
            ("send_message", "chat"),
            ("send_file", "chat"),
            ("send_video", "chat"),
        ]
        for action, want_status in cases:
            try:
                svc.dispatch(action, {"thread_id": "20001",
                                      "type": "user"})
                raise AssertionError("%s must refuse" % action)
            except svc_mod.UnsupportedService as e:
                assert e.status == want_status, (action, e.status)
                assert e.reason, action
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
def _start_app_server(mock, tmp, addon=None):
    app_server.PARAM_CIPHER_KEY = TEST_PARAM_KEY
    state = app_server.AppState(tmp)
    if addon is not None:
        state.addon = addon
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

        # Op chi chay qua addon, ma khong co sidecar: 502
        # addon_unavailable (khong phai 409 "khong ho tro").
        status, body = _api(base, "POST", "/api/svc/add_reaction",
                            {"thread_id": "20001", "type": "user",
                             "msg_id": "m1", "icon": "like"})
        assert status == 502, body
        assert "addon_unavailable" in body["error"], body
        status, body = _api(base, "POST", "/api/svc/set_account_webhook",
                            {"own_id": "10001"})
        assert status == 502, body
        assert "addon_unavailable" in body["error"], body
        # Op khong co route JSON nao (proxies): van 409 zalobot.
        status, body = _api(base, "POST", "/api/svc/get_proxies", {})
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

        # A group-only reminder create refuses honestly (409).
        status, body = _api(base, "POST", "/api/svc/create_reminder",
                            {"thread_id": "30001", "type": "group",
                             "title": "Hop",
                             "remind_time": "2026-11-06"})
        assert status == 409, body
        assert "chưa có endpoint" in body["error"], body
        httpd.shutdown()
    finally:
        if httpd:
            try:
                httpd.shutdown()
            except Exception:
                pass
        mock.stop()


def test_svc_http_api_via_addon():
    """Uy quyen /api/svc/* qua sidecar (FakeAddonClient): cac op tung
    "Chua ho tro" nay tra 200; op khong co -> 404; sidecar chet ->
    502; catalog qua HTTP bao 84 supported / 4 zalobot."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-svc-addon-")
    mock = MockZalo().start()
    httpd = None
    try:
        patch_domains(mock)
        fake = FakeAddonClient()
        httpd, base = _start_app_server(mock, tmp, addon=fake)
        status, body = _api(base, "GET", "/api/svc/catalog")
        assert status == 200, body
        assert body["counts"]["supported"] == 84, body["counts"]
        assert body["counts"]["zalobot"] == 4, body["counts"]

        _login_via_qr(base)

        # add_reaction: truoc day 409 "unsupported", nay qua addon.
        status, body = _api(base, "POST", "/api/svc/add_reaction",
                            {"thread_id": "20001", "type": "user",
                             "msg_id": "m1", "icon": "like"})
        assert status == 200 and body["ok"] is True, body
        svc_calls = [c for c in fake.calls if c[0] == "svc"]
        assert len(svc_calls) == 1, svc_calls
        assert svc_calls[0][1][0] == "addReaction", svc_calls
        params = svc_calls[0][1][1]
        assert params["icon"] == "like", params
        assert params["dest"]["threadId"] == "20001", params
        assert params["dest"]["type"] == 0, params

        # block_user (op chi co tren addon) + get_logged_accounts.
        status, body = _api(base, "POST", "/api/svc/block_user",
                            {"thread_id": "20001", "type": "user"})
        assert status == 200 and body["ok"] is True, body
        status, body = _api(base, "POST",
                            "/api/svc/get_logged_accounts", {})
        assert status == 200 and body["ok"] is True, body

        # Webhook account qua addon (special, khong phai svc generic).
        status, body = _api(base, "POST", "/api/svc/set_account_webhook",
                            {"own_id": "own-1",
                             "message_webhook_url":
                             "http://127.0.0.1:9/hook"})
        assert status == 200 and body["ok"] is True, body
        assert fake.webhook_config["own-1"]["messageWebhookUrl"] == \
            "http://127.0.0.1:9/hook", fake.webhook_config

        # Unknown action -> 404 (khong doi khi co addon).
        status, body = _api(base, "POST", "/api/svc/khong_co",
                            {"thread_id": "20001"})
        assert status == 404, body

        # Chat-frame op van 409 (khong qua addon).
        status, body = _api(base, "POST", "/api/svc/send_message",
                            {"thread_id": "20001", "type": "user",
                             "message": "xin chao"})
        assert status == 409 and body["status"] == "chat", body

        # Sidecar chet: op addon tra 502, khong roi ve PC.
        app_server.STATE.addon = FakeAddonClient(
            fail_with=addon_client_mod.AddonUnreachable("down"))
        status, body = _api(base, "POST", "/api/svc/add_reaction",
                            {"thread_id": "20001", "type": "user",
                             "msg_id": "m1", "icon": "like"})
        assert status == 502, body
        assert str(body.get("error", "")).startswith(
            "addon_unavailable"), body
        httpd.shutdown()
    finally:
        if httpd:
            try:
                httpd.shutdown()
            except Exception:
                pass
        mock.stop()


def test_dispatch_via_addon_unit():
    """dispatch_via_addon (unit, khong HTTP): body map dung cho undo/
    delete/reaction + thread type so; op ngoai ADDON_OPS -> 409."""
    fake = FakeAddonClient()
    data = svc_mod.dispatch_via_addon(
        fake, "undo_message",
        {"thread_id": "20001", "type": "user", "msg_id": "m1",
         "cli_msg_id": "c1"})
    assert data == {"echo_op": "undo"}, data
    op, params = fake.calls[-1][1]
    assert op == "undo", fake.calls
    assert params["payload"] == {"msgId": "m1", "cliMsgId": "c1"}, params
    assert params["threadId"] == "20001" and params["type"] == 0, params
    data = svc_mod.dispatch_via_addon(
        fake, "add_reaction",
        {"thread_id": "30001", "type": "group", "msg_id": "m2",
         "cli_msg_id": "c2", "icon": "like"})
    assert data == {"echo_op": "addReaction"}, data
    op, params = fake.calls[-1][1]
    assert op == "addReaction", fake.calls
    assert params["dest"]["type"] == 1, params
    assert params["icon"] == "like", params
    # Op khong co trong ADDON_OPS (forward can body tin) -> khong
    # co thao tac addon (UnknownAction o tang dispatch; HTTP tra 404).
    try:
        svc_mod.dispatch_via_addon(
            fake, "forward_message",
            {"thread_id": "20001", "type": "user"})
        raise AssertionError("expected UnknownAction")
    except svc_mod.UnknownAction:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL SERVICES TESTS PASSED")
