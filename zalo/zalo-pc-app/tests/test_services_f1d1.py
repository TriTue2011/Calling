"""Tests for F1 vote_poll + D1 reject_friend_request
(zalo_pc_app/services.py) — ops ngoai 96.

Nguon endpoint + ma lenh + body (khong bia):
  - F1 vote_poll: GET group-wpa /api/poll/vote (12084)
    {poll_id, option_ids, imei} — SERVICE-MAP.md §2.4 (bundle PC)
    + zca-js votePoll(pollId, optionId) (GET, cung path/body).
  - D1 reject_friend_request: POST friend-wpa /api/friend/reject
    (11428) {fid} (KHONG imei, KHONG language) — SERVICE-MAP.md
    §2.1 (bundle PC) + zca-js rejectFriendRequest(friendId)
    (POST, cung path/body).

Mock/offline: moi thu qua MockZalo, khong gui that.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from test_services import (  # noqa: E402
    _api, _login_via_qr, _start_app_server, make_svc, patch_domains,
    seen_paths, seen_post_paths)
from zalo_pc_app import services as svc_mod  # noqa: E402


def test_f1d1_catalog_extras():
    """2 op moi la ngoai 96 (addon_no None), deu supported —
    khong lam tang total_96; extras 5 -> 8 (gom ca keepAlive
    cua H5, cung la op ngoai 96)."""
    cat = svc_mod.build_catalog()
    assert cat["counts"]["total_96"] == 96, cat["counts"]
    extras = [e for e in cat["services"] if e["addon_no"] is None]
    assert len(extras) == 9, extras      # 8 cu + get_settings (12/11/2026)
    assert all(e["status"] == "supported" for e in extras), extras
    by_action = {e["action"]: e for e in cat["services"]
                 if e["action"]}
    assert by_action["vote_poll"]["status"] == "supported"
    assert by_action["reject_friend_request"]["status"] == "supported"
    assert by_action["vote_poll"]["body_unverified"] is False
    assert by_action["reject_friend_request"]["body_unverified"] \
        is False
    # pc label phai ghi dung path + ma lenh bundle.
    assert by_action["vote_poll"]["pc"] == "/api/poll/vote (12084)", \
        by_action["vote_poll"]["pc"]
    assert by_action["reject_friend_request"]["pc"] == \
        "/api/friend/reject (11428)", \
        by_action["reject_friend_request"]["pc"]
    # OPS spec: domain/path/code/method/thread dung nhu bundle.
    vote = svc_mod.OPS["vote_poll"]
    assert (vote["domain"], vote["path"], vote["code"],
            vote["method"], vote["thread"]) == \
        ("group", "/api/poll/vote", 12084, "GET", "group"), vote
    reject = svc_mod.OPS["reject_friend_request"]
    assert (reject["domain"], reject["path"], reject["code"],
            reject["method"], reject["thread"]) == \
        ("friend", "/api/friend/reject", 11428, "POST", "none"), \
        reject


def test_dispatch_vote_poll():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        g = {"thread_id": "30001", "type": "group"}
        # Bo 1 phieu: GET /api/poll/vote, body dung 3 truong.
        d = svc.dispatch("vote_poll", dict(
            g, poll_id="p1", option_ids="o2"))
        assert d["path"] == "/api/poll/vote", d
        assert d["body"] == {"poll_id": "p1", "option_ids": ["o2"],
                             "imei": "dev-1"}, d
        assert "/api/poll/vote" in seen_paths(mock, "/api/poll/")
        assert "/api/poll/vote" not in seen_post_paths(mock), \
            "vote_poll must be GET"
        # Nhieu lua chon: CSV -> list; alias option_id don.
        d = svc.dispatch("vote_poll", dict(
            g, poll_id="p1", option_ids="o1,o3"))
        assert d["body"]["option_ids"] == ["o1", "o3"], d
        d = svc.dispatch("vote_poll", dict(
            g, poll_id="p1", option_id="o2"))
        assert d["body"]["option_ids"] == ["o2"], d
        # Chi nhom: thread 1-1 bi tu choi.
        try:
            svc.dispatch("vote_poll", {
                "thread_id": "20001", "type": "user",
                "poll_id": "p1", "option_ids": "o2"})
            raise AssertionError("vote_poll on user must refuse")
        except svc_mod.UnsupportedService as e:
            assert "nhóm" in e.reason, e.reason
        # Thieu param -> ValueError (HTTP 400), khong goi Zalo.
        before = len(mock.seen)
        for params in (dict(g, option_ids="o2"),
                       dict(g, poll_id="p1"),
                       dict(g, poll_id="p1", option_ids=""),
                       dict(g, poll_id="p1", option_ids=" , ")):
            try:
                svc.dispatch("vote_poll", params)
                raise AssertionError(
                    "vote_poll %s must raise" % (params,))
            except ValueError as e:
                assert ("poll_id" in str(e)
                        or "option_ids" in str(e)), e
        assert len(mock.seen) == before, mock.seen[before:]
    finally:
        mock.stop()


def test_dispatch_reject_friend_request():
    mock = MockZalo().start()
    try:
        patch_domains(mock)
        svc = make_svc(mock)
        # POST /api/friend/reject, body CHI {fid} — khong imei,
        # khong language (khac accept: {fid, language}).
        d = svc.dispatch("reject_friend_request", {"user_id": "20009"})
        assert d["path"] == "/api/friend/reject", d
        assert d["body"] == {"fid": "20009"}, d
        assert "/api/friend/reject" in seen_post_paths(mock), \
            "reject_friend_request must be POST"
        # Thieu user_id -> ValueError, khong goi Zalo.
        before = len(mock.seen)
        try:
            svc.dispatch("reject_friend_request", {})
            raise AssertionError("missing user_id must raise")
        except ValueError as e:
            assert "user_id" in str(e), e
        assert len(mock.seen) == before, mock.seen[before:]
    finally:
        mock.stop()


def test_f1d1_http_api():
    """HTTP API: chua login -> 401 ca hai op; sau login -> 200;
    thieu param -> 400 (giong cac op khac)."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-f1d1-test-")
    mock = MockZalo().start()
    httpd = None
    try:
        patch_domains(mock)
        httpd, base = _start_app_server(mock, tmp)
        status, body = _api(base, "POST", "/api/svc/vote_poll",
                            {"thread_id": "30001", "type": "group",
                             "poll_id": "p1", "option_ids": "o2"})
        assert status == 401, body
        assert body["error"] == "chua_dang_nhap", body
        status, body = _api(base, "POST",
                            "/api/svc/reject_friend_request",
                            {"user_id": "20009"})
        assert status == 401, body
        assert body["error"] == "chua_dang_nhap", body
        _login_via_qr(base)
        status, body = _api(base, "POST", "/api/svc/vote_poll",
                            {"thread_id": "30001", "type": "group",
                             "poll_id": "p1", "option_ids": "o2"})
        assert status == 200, body
        assert body["ok"] is True, body
        assert body["data"]["path"] == "/api/poll/vote", body
        assert body["data"]["body"] == {
            "poll_id": "p1", "option_ids": ["o2"],
            "imei": body["data"]["body"]["imei"]}, body
        status, body = _api(base, "POST",
                            "/api/svc/reject_friend_request",
                            {"user_id": "20009"})
        assert status == 200, body
        assert body["data"]["path"] == "/api/friend/reject", body
        assert body["data"]["body"] == {"fid": "20009"}, body
        status, body = _api(base, "POST", "/api/svc/vote_poll",
                            {"thread_id": "30001", "type": "group",
                             "poll_id": "p1"})
        assert status == 400, body
        assert "option_ids" in body["error"], body
        status, body = _api(base, "POST",
                            "/api/svc/reject_friend_request", {})
        assert status == 400, body
        assert "user_id" in body["error"], body
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
    print("ALL F1D1 TESTS PASSED")
