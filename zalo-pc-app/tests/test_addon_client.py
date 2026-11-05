"""Addon loopback client (zalo_pc_app/addon_client.py) against a
stdlib mock sidecar. No live server, no real account, no secret
value anywhere — the only credential here is a test-only password
that exists solely inside this file's mock.

Covers: login + cookie reuse (one login for two calls), 401 ->
re-login + retry, auth-TTL expiry -> login again, friends/groups/
send mapping (accountSelection, numeric type, NO clientId key),
unreachable -> AddonUnreachable, login failure -> AddonAuthError,
server success=false -> AddonError, account resolution (PC-uid
preference, env override, not-found -> re-resolve + retry),
status()/webhooks round-trip, group_history_full envelope, and the
loopback LocalMediaServer (publish/GET/unknown-token 404).
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import addon_client as ac  # noqa: E402

TEST_USER = "admin"
TEST_PASS = "test-admin-password-only-for-mock"
TEST_COOKIE = "sid-test-1"


class FakeAddonClient:
    """In-memory fake sidecar for delegation tests (used by
    test_contacts.py / test_chat.py / test_services.py): records
    calls, returns canned data, never touches the network. The
    `fail_with` exception (if set) is raised on every call."""

    def __init__(self, fail_with=None):
        self.calls = []
        self.fail_with = fail_with
        self._account = "own-1"
        self.friends_data = [
            {"userId": "20001", "displayName": "Ban A",
             "avatar": "https://example.invalid/a.png"},
            {"userId": "20002", "displayName": "Ban B", "avatar": ""},
        ]
        self.groups_data = {"version": "1",
                            "gridVerMap": {"30001": "1", "30002": "2"}}
        self.group_info_data = {
            "removedsGroup": [], "unchangedsGroup": [],
            "gridInfoMap": {
                "30001": {"groupId": "30001", "name": "Nhom Test",
                          "avt": "", "totalMember": 3,
                          "topMember": [{"id": "20001"},
                                        {"id": "20002"}]},
                "30002": {"groupId": "30002", "name": "Nhom Hai",
                          "avt": "", "totalMember": 2,
                          "topMember": [{"id": "20001"}]},
            }}
        self.history_data = {
            "lastActionId": "a1", "more": 0,
            "groupMsgs": [
                {"type": 1, "threadId": "30001",
                 "data": {"msgId": "m1", "uidFrom": "20001",
                          "content": "Chao ca nhom", "ts": 1762345600,
                          "dName": "Ban A"}},
                {"type": 1, "threadId": "30001",
                 "data": {"msgId": "m2", "uidFrom": "20002",
                          "content": "Chao Ban A", "ts": 1762345601,
                          "dName": "Ban B"}},
            ]}
        self.webhook_config = {}

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.fail_with is not None:
            raise self.fail_with

    def set_pc_uid(self, uid):
        self._record("set_pc_uid", uid)

    def resolve_account(self):
        self._record("resolve_account")
        return self._account

    def health(self):
        self._record("health")
        return {"success": True, "status": "ok", "uptime": 1,
                "accounts": 1}

    def accounts(self):
        self._record("accounts")
        return [{"ownId": "own-1", "phoneNumber": "",
                 "proxy": "Khong co proxy",
                 "displayName": " (own-1)", "isOnline": True}]

    def status(self):
        self._record("status")
        return {"ok": True, "logged_in": True,
                "accounts": [{"ownId": "own-1", "phoneNumber": ""}]}

    def friends(self, count=None, page=None):
        self._record("friends", count=count, page=page)
        return self.friends_data

    def groups(self):
        self._record("groups")
        return self.groups_data

    def group_info(self, group_ids):
        self._record("group_info", group_ids)
        return self.group_info_data

    def find_user(self, phone):
        self._record("find_user", phone)
        return {"userId": "20001"}

    def get_user_info(self, user_id):
        self._record("get_user_info", user_id)
        return {"userId": user_id}

    def send_message(self, thread_id, thread_type, message,
                     quote=None, ttl=None):
        self._record("send_message", thread_id, thread_type, message,
                     quote=quote, ttl=ttl)
        return {"message": {"msgId": 9001}}

    def send_image(self, thread_id, thread_type, image_url,
                   message="", ttl=None):
        self._record("send_image", thread_id, thread_type, image_url,
                     message=message, ttl=ttl)
        return {"message": {"msgId": 9002}}

    def send_images(self, thread_id, thread_type, image_urls,
                    caption="", ttl=None):
        self._record("send_images", thread_id, thread_type,
                     image_urls, caption=caption, ttl=ttl)
        return [{"message": {"msgId": 9003}}]

    def send_file(self, thread_id, thread_type, file_url,
                  message="", ttl=None):
        self._record("send_file", thread_id, thread_type, file_url,
                     message=message, ttl=ttl)
        return {"message": {"msgId": 9004}}

    def send_video(self, thread_id, thread_type, video_url,
                   thumbnail_url=None, duration=None):
        self._record("send_video", thread_id, thread_type, video_url,
                     thumbnail_url=thumbnail_url, duration=duration)
        return {"message": {"msgId": 9005}}

    def send_voice(self, thread_id, thread_type, voice_url, ttl=None):
        self._record("send_voice", thread_id, thread_type, voice_url,
                     ttl=ttl)
        return {"message": {"msgId": 9006}}

    def send_sticker(self, thread_id, thread_type, sticker):
        self._record("send_sticker", thread_id, thread_type, sticker)
        return {"message": {"msgId": 9007}}

    def send_card(self, thread_id, thread_type, options):
        self._record("send_card", thread_id, thread_type, options)
        return {"message": {"msgId": 9008}}

    def send_link(self, thread_id, thread_type, options):
        self._record("send_link", thread_id, thread_type, options)
        return {"message": {"msgId": 9009}}

    def group_history(self, group_id, count=50):
        self._record("group_history", group_id, count)
        return self.history_data

    def group_history_full(self, group_id, count=50):
        self._record("group_history_full", group_id, count)
        return {"data": self.history_data,
                "groupId": str(group_id), "groupName": "Nhom Test",
                "source": "zca-js-2.1.2", "requested": count,
                "returned": len(self.history_data["groupMsgs"]),
                "fromCache": 0}

    def typing(self, thread_id):
        self._record("typing", thread_id)
        return {"status": 0}

    def seen(self, thread_id, thread_type, msg_ids):
        self._record("seen", thread_id, thread_type, msg_ids)
        return {"status": 0}

    def delivered(self, thread_id, thread_type, msg_ids,
                  is_seen=True):
        self._record("delivered", thread_id, thread_type, msg_ids,
                     is_seen=is_seen)
        return {"status": 0}

    def svc(self, op, params):
        self._record("svc", op, params)
        return {"echo_op": op}

    def webhooks_get(self):
        self._record("webhooks_get")
        return {"default": {"messageWebhookUrl": "",
                            "groupEventWebhookUrl": "",
                            "reactionWebhookUrl": ""},
                "accounts": {}}

    def webhooks_get_account(self, own_id):
        self._record("webhooks_get_account", own_id)
        return {"ownId": own_id, "messageWebhookUrl": "",
                "groupEventWebhookUrl": "", "reactionWebhookUrl": ""}

    def webhooks_set(self, own_id, urls):
        self._record("webhooks_set", own_id, urls)
        self.webhook_config[own_id] = dict(urls)
        return {"message": "updated"}

    def webhooks_delete(self, own_id):
        self._record("webhooks_delete", own_id)
        self.webhook_config.pop(own_id, None)
        return {"message": "deleted"}


# ----------------------------------------------------------------------
# Mock sidecar (real HTTP, stdlib only)
# ----------------------------------------------------------------------

class MockSidecar:
    """Tiny HTTP server mimicking the sidecar's auth + envelope:
    POST /api/login sets a session cookie; /api/*ByAccount routes
    require it (401 otherwise); /api/health is public."""

    def __init__(self, accounts=None, fail_once=None):
        self.accounts_list = accounts if accounts is not None else [
            {"ownId": "own-1", "phoneNumber": "",
             "proxy": "Khong co proxy", "displayName": " (own-1)",
             "isOnline": True}]
        self.accounts_calls = 0
        self.fail_once = fail_once or {}  # path -> status to return once
        self.login_count = 0
        self.seen = []  # (method, path, body)
        self.webhooks = {}
        self._httpd = None

    def start(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _json(self, status, obj, cookie=False):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if cookie:
                    self.send_header(
                        "Set-Cookie",
                        "zalo-server.sid=%s; Path=/; HttpOnly"
                        % TEST_COOKIE)
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = 0
                if not length:
                    return {}
                try:
                    return json.loads(
                        self.rfile.read(length).decode())
                except Exception:
                    return {}

            def _authed(self):
                return ("zalo-server.sid=%s" % TEST_COOKIE) in (
                    self.headers.get("Cookie") or "")

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                mock.seen.append(("GET", path, {}))
                if path == "/api/health":
                    return self._json(200, {"success": True,
                                            "status": "ok", "uptime": 7,
                                            "accounts": len(
                                                mock.accounts_list)})
                if path == "/api/accounts":
                    if not self._authed():
                        return self._json(401, {"success": False,
                                                "message": "Chua dang "
                                                "nhap"})
                    mock.accounts_calls += 1
                    return self._json(200, {
                        "success": True, "data": mock.accounts_list,
                        "total": len(mock.accounts_list)})
                if path.startswith("/api/account-webhook/"):
                    if not self._authed():
                        return self._json(401, {"success": False})
                    own = path.rsplit("/", 1)[-1]
                    cfg = mock.webhooks.get(own, {})
                    return self._json(200, {"success": True, "data": {
                        "ownId": own,
                        "messageWebhookUrl": cfg.get(
                            "messageWebhookUrl", ""),
                        "groupEventWebhookUrl": cfg.get(
                            "groupEventWebhookUrl", ""),
                        "reactionWebhookUrl": cfg.get(
                            "reactionWebhookUrl", "")}})
                if path == "/api/account-webhooks":
                    if not self._authed():
                        return self._json(401, {"success": False})
                    return self._json(200, {"success": True, "data": {
                        "default": {"messageWebhookUrl": "",
                                    "groupEventWebhookUrl": "",
                                    "reactionWebhookUrl": ""},
                        "accounts": mock.webhooks}})
                return self._json(404, {"success": False,
                                        "error": "not found"})

            def do_POST(self):
                path = self.path.split("?", 1)[0]
                body = self._body()
                mock.seen.append(("POST", path, body))
                if path in mock.fail_once:
                    status = mock.fail_once.pop(path)
                    return self._json(status, {"success": False,
                                               "message": "injected"})
                if path == "/api/login":
                    mock.login_count += 1
                    if (body.get("username") == TEST_USER
                            and body.get("password") == TEST_PASS):
                        return self._json(200, {
                            "success": True,
                            "user": {"username": TEST_USER,
                                     "role": "admin"}}, cookie=True)
                    return self._json(401, {
                        "success": False,
                        "message": "Tai khoan hoac mat khau khong "
                        "chinh xac"})
                if not self._authed():
                    return self._json(401, {"success": False,
                                            "message": "Chua dang nhap"})
                if path == "/api/account-webhook":
                    own = body.get("ownId")
                    if not own:
                        return self._json(400, {"success": False,
                                                "error": "ownId la bat "
                                                "buoc"})
                    cfg = mock.webhooks.setdefault(own, {})
                    for key in ("messageWebhookUrl",
                                "groupEventWebhookUrl",
                                "reactionWebhookUrl"):
                        if key in body:
                            cfg[key] = body[key]
                    return self._json(200, {"success": True,
                                            "message": "updated"})
                if path == "/api/getAllFriendsByAccount":
                    sel = body.get("accountSelection")
                    if sel == "own-stale":
                        return self._json(500, {
                            "success": False,
                            "error": "Không tìm thấy tài khoản: "
                            "own-stale"})
                    return self._json(200, {
                        "success": True,
                        "data": [{"userId": "20001",
                                  "displayName": "Ban A",
                                  "avatar": ""}],
                        "usedAccount": {"ownId": sel,
                                        "phoneNumber": ""}})
                if path == "/api/getAllGroupsByAccount":
                    return self._json(200, {
                        "success": True,
                        "data": {"version": "1",
                                 "gridVerMap": {"30001": "1"}},
                        "usedAccount": {"ownId": body.get(
                            "accountSelection"), "phoneNumber": ""}})
                if path == "/api/getGroupInfoByAccount":
                    return self._json(200, {
                        "success": True,
                        "data": {"removedsGroup": [],
                                 "unchangedsGroup": [],
                                 "gridInfoMap": {
                                     "30001": {"groupId": "30001",
                                               "name": "Nhom Test",
                                               "avt": "",
                                               "totalMember": 3,
                                               "topMember": [
                                                   {"id": "20001"}]}}},
                        "usedAccount": {"ownId": body.get(
                            "accountSelection"), "phoneNumber": ""}})
                if path == "/api/sendMessageByAccount":
                    return self._json(200, {
                        "success": True,
                        "data": {"message": {"msgId": 123}},
                        "messageTtl": None,
                        "usedAccount": {"ownId": body.get(
                            "accountSelection"), "phoneNumber": ""}})
                if path in ("/api/sendImageByAccount",
                            "/api/sendFileByAccount",
                            "/api/sendVideoByAccount",
                            "/api/sendVoiceByAccount",
                            "/api/sendStickerByAccount",
                            "/api/sendCardByAccount",
                            "/api/sendLinkByAccount"):
                    return self._json(200, {
                        "success": True,
                        "data": {"message": {"msgId": 124}},
                        "usedAccount": {"ownId": body.get(
                            "accountSelection"), "phoneNumber": ""}})
                if path == "/api/getGroupChatHistoryByAccount":
                    return self._json(200, {
                        "success": True,
                        "data": {"groupMsgs": [], "more": 0},
                        "groupId": body.get("groupId"),
                        "groupName": "Nhom Test",
                        "source": "zca-js-2.1.2",
                        "requested": body.get("count", 50),
                        "returned": 0, "fromCache": 0,
                        "usedAccount": {"ownId": body.get(
                            "accountSelection"), "phoneNumber": ""}})
                if path in ("/api/sendTypingEventByAccount",
                            "/api/sendSeenEventByAccount",
                            "/api/sendDeliveredEventByAccount"):
                    return self._json(200, {
                        "success": True, "data": {"status": 0},
                        "usedAccount": {"ownId": body.get(
                            "accountSelection"), "phoneNumber": ""}})
                return self._json(200, {
                    "success": True, "data": {"echo": path},
                    "usedAccount": {"ownId": body.get(
                        "accountSelection"), "phoneNumber": ""}})

            def do_DELETE(self):
                path = self.path.split("?", 1)[0]
                mock.seen.append(("DELETE", path, {}))
                if path.startswith("/api/account-webhook/"):
                    if not self._authed():
                        return self._json(401, {"success": False})
                    mock.webhooks.pop(path.rsplit("/", 1)[-1], None)
                    return self._json(200, {"success": True,
                                            "message": "deleted"})
                return self._json(404, {"success": False,
                                        "error": "not found"})

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        threading.Thread(target=self._httpd.serve_forever,
                         daemon=True).start()
        return self

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()


def _make_client(mock, **kwargs):
    kwargs.setdefault("username", TEST_USER)
    kwargs.setdefault("password", TEST_PASS)
    return ac.AddonClient(base_url=mock.base, **kwargs)


def _bodies(mock, path):
    return [b for m, p, b in mock.seen if p == path]


def test_login_and_cookie_reuse():
    mock = MockSidecar().start()
    try:
        client = _make_client(mock)
        friends = client.friends()
        assert len(friends) == 1 and friends[0]["userId"] == "20001"
        groups = client.groups()
        assert groups["gridVerMap"] == {"30001": "1"}, groups
        # One login for both calls (cookie kept, 6 h client TTL).
        assert mock.login_count == 1, mock.login_count
        # accountSelection was resolved from /api/accounts.
        assert mock.accounts_calls >= 1
        body = _bodies(mock, "/api/getAllFriendsByAccount")[0]
        assert body["accountSelection"] == "own-1", body
    finally:
        mock.stop()


def test_401_relogin_and_retry():
    mock = MockSidecar(
        fail_once={"/api/getAllFriendsByAccount": 401}).start()
    try:
        client = _make_client(mock)
        assert client.friends()[0]["userId"] == "20001"
        # First login + one forced re-login after the 401.
        assert mock.login_count == 2, mock.login_count
        assert len(_bodies(mock, "/api/getAllFriendsByAccount")) == 2
    finally:
        mock.stop()


def test_auth_ttl_expiry_relogs_in():
    mock = MockSidecar().start()
    try:
        client = _make_client(mock)
        client.friends()
        assert mock.login_count == 1
        client._authenticated_at = 0.0  # pretend the 6 h TTL expired
        client.groups()
        assert mock.login_count == 2, mock.login_count
    finally:
        mock.stop()


def test_send_mapping_numeric_type_no_client_id():
    mock = MockSidecar().start()
    try:
        client = _make_client(mock)
        data = client.send_message("20001", "user", "Xin chao")
        assert data["message"]["msgId"] == 123, data
        body = _bodies(mock, "/api/sendMessageByAccount")[0]
        # Numeric type (0/1) — never the string "group" (API-MAP §4.1).
        assert body["type"] == 0 and isinstance(body["type"], int), body
        assert body["threadId"] == "20001", body
        assert "clientId" not in body and "client_id" not in body, body
        data = client.send_message("30001", "group", "Chao nhom")
        body = _bodies(mock, "/api/sendMessageByAccount")[1]
        assert body["type"] == 1, body
        client.send_image("20001", "user",
                          "http://127.0.0.1/x/a.jpg", message="cap")
        body = _bodies(mock, "/api/sendImageByAccount")[0]
        assert body["imagePath"].endswith("/a.jpg"), body
        assert body["type"] == 0, body
        client.send_file("30001", "group",
                         "http://127.0.0.1/x/f.pdf")
        body = _bodies(mock, "/api/sendFileByAccount")[0]
        assert body["fileUrl"].endswith("/f.pdf"), body
        assert body["type"] == 1, body
    finally:
        mock.stop()


def test_unreachable_raises_addon_unreachable():
    client = ac.AddonClient(base_url="http://127.0.0.1:1",
                            username=TEST_USER, password=TEST_PASS,
                            timeout=5)
    try:
        client.health()
        raise AssertionError("expected AddonUnreachable")
    except ac.AddonUnreachable:
        pass
    try:
        client.friends()
        raise AssertionError("expected AddonUnreachable")
    except ac.AddonUnreachable:
        pass


def test_login_failure_and_no_secret_in_error():
    mock = MockSidecar().start()
    try:
        client = _make_client(mock, password="wrong-password")
        try:
            client.friends()
            raise AssertionError("expected AddonAuthError")
        except ac.AddonAuthError as e:
            assert "wrong-password" not in str(e), str(e)
            assert TEST_PASS not in str(e), str(e)
    finally:
        mock.stop()


def test_server_error_surfaced():
    mock = MockSidecar(
        fail_once={"/api/getAllFriendsByAccount": 500}).start()
    try:
        client = _make_client(mock)
        try:
            client.friends()
            raise AssertionError("expected AddonError")
        except ac.AddonError:
            pass
    finally:
        mock.stop()


def test_account_resolution_prefers_pc_uid_and_override():
    accounts = [
        {"ownId": "own-1", "phoneNumber": "", "proxy": "",
         "displayName": " (own-1)", "isOnline": True},
        {"ownId": "own-2", "phoneNumber": "", "proxy": "",
         "displayName": " (own-2)", "isOnline": True},
    ]
    mock = MockSidecar(accounts=accounts).start()
    try:
        client = _make_client(mock, pc_uid="own-2")
        client.friends()
        body = _bodies(mock, "/api/getAllFriendsByAccount")[0]
        assert body["accountSelection"] == "own-2", body
        # Env override wins over the PC uid.
        mock2 = MockSidecar(accounts=accounts).start()
        try:
            client2 = _make_client(mock2, pc_uid="own-2",
                                   account="own-1")
            client2.friends()
            body = _bodies(mock2, "/api/getAllFriendsByAccount")[0]
            assert body["accountSelection"] == "own-1", body
        finally:
            mock2.stop()
    finally:
        mock.stop()


def test_account_not_found_re_resolves_and_retries():
    # First /api/accounts -> [own-stale] (friends fails with the
    # server's "account not found"), second -> [own-1] (succeeds).
    stale = [{"ownId": "own-stale", "phoneNumber": "", "proxy": "",
              "displayName": " (own-stale)", "isOnline": True}]
    good = [{"ownId": "own-1", "phoneNumber": "", "proxy": "",
             "displayName": " (own-1)", "isOnline": True}]
    mock = MockSidecar(accounts=stale).start()
    try:
        client = _make_client(mock)
        # First friends() call: resolves own-stale, server answers
        # "account not found", client re-resolves once. Swap the
        # account list in between so the retry resolves own-1.
        try:
            client.friends()
            raise AssertionError("expected AddonError on first call")
        except ac.AddonError:
            mock.accounts_list = good
        friends = client.friends()
        assert friends and friends[0]["userId"] == "20001", friends
        assert client._account == "own-1", client._account
    finally:
        mock.stop()


def test_status_and_webhooks_round_trip():
    mock = MockSidecar().start()
    try:
        client = _make_client(mock)
        st = client.status()
        assert st["ok"] is True and st["logged_in"] is True, st
        assert [a["ownId"] for a in st["accounts"]] == ["own-1"], st
        got = client.webhooks_get_account("own-1")
        assert got["messageWebhookUrl"] == "", got
        client.webhooks_set("own-1", {
            "messageWebhookUrl": "http://127.0.0.1:9/hook-msg",
            "groupEventWebhookUrl": "",
            "reactionWebhookUrl": ""})
        got = client.webhooks_get_account("own-1")
        assert got["messageWebhookUrl"] == \
            "http://127.0.0.1:9/hook-msg", got
        all_cfg = client.webhooks_get()
        assert "own-1" in all_cfg["accounts"], all_cfg
        client.webhooks_delete("own-1")
        got = client.webhooks_get_account("own-1")
        assert got["messageWebhookUrl"] == "", got
    finally:
        mock.stop()


def test_group_history_full_envelope():
    mock = MockSidecar().start()
    try:
        client = _make_client(mock)
        env = client.group_history_full("30001", 50)
        assert env["source"] == "zca-js-2.1.2", env
        assert env["groupName"] == "Nhom Test", env
        assert env["requested"] == 50 and env["returned"] == 0, env
        assert isinstance(env["data"], dict), env
    finally:
        mock.stop()


def test_svc_generic_op():
    mock = MockSidecar().start()
    try:
        client = _make_client(mock)
        data = client.svc("getGroupInfo", {"groupId": ["30001"]})
        assert "gridInfoMap" in data, data
        assert data["gridInfoMap"]["30001"]["name"] == "Nhom Test", data
        body = [b for m, p, b in mock.seen
                if p == "/api/getGroupInfoByAccount"][0]
        assert body["accountSelection"] == "own-1", body
        assert body["groupId"] == ["30001"], body
    finally:
        mock.stop()


def test_local_media_server_loopback_only():
    tmp = tempfile.mkdtemp(prefix="zalo-pc-media-test-")
    try:
        path = os.path.join(tmp, "hello.txt")
        with open(path, "wb") as f:
            f.write(b"hello media")
        server = ac.LocalMediaServer(tmp)
        url, token = server.publish(path)
        assert url.startswith("http://127.0.0.1:"), url
        assert len(token) == 32, token
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.read() == b"hello media"
        # Unknown token -> 404; traversal -> 404.
        bad = url.rsplit("/", 2)[0] + "/badtoken/hello.txt"
        try:
            urllib.request.urlopen(bad, timeout=5)
            raise AssertionError("expected 404 for bad token")
        except urllib.error.HTTPError as e:
            assert e.code == 404, e.code
        server.unpublish(token)
        try:
            urllib.request.urlopen(url, timeout=5)
            raise AssertionError("expected 404 after unpublish")
        except urllib.error.HTTPError as e:
            assert e.code == 404, e.code
        server.stop()
    finally:
        pass


def test_make_client_none_without_password():
    old = os.environ.pop("ZALO_SERVER_ADMIN_PASSWORD", None)
    try:
        assert ac.make_client() is None
    finally:
        if old is not None:
            os.environ["ZALO_SERVER_ADMIN_PASSWORD"] = old


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL ADDON CLIENT TESTS PASSED")
