"""Bình chọn nhóm: lọc người chưa bình chọn và xoá khỏi nhóm (có xác nhận), ở mức logic và ở mức tuyến server.

Chạy: python3 tests/test_group_polls.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mock_server import MockZalo  # noqa: E402
from zalo_pc_app import group_polls as gp  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402
import test_voice_112 as v  # noqa: E402  (khuôn dựng server + đăng nhập giả)

G = "30001"
OWN = "9000"


def board_item(pid, question, options, closed=False, anonymous=False, multi=False):
    return {"boardType": 3, "data": {"poll_id": pid, "question": question, "closed": closed, "is_anonymous": anonymous,
                                     "allow_multi_choices": multi, "creator": "c0", "created_time": 1, "expired_time": 0, "num_vote": 3,
                                     "options": [{"option_id": i, "content": c, "votes": len(vs), "voters": vs} for i, (c, vs) in enumerate(options)]}}


ITEMS = [
    board_item(101, "Đi ăn tối?", [("Có", ["m1", "m2"]), ("Không", ["m3"])], multi=True),
    board_item(102, "Đặt món gì?", [("Phở", ["m1"]), ("Bún", [])]),
    board_item(103, "Ẩn danh", [("A", [])], anonymous=True),
    board_item(104, "Cuộc cũ", [("A", ["m4"])], closed=True),
    {"boardType": 1, "data": {"id": "n1"}},                       # ghi chú: bỏ qua
]
MEMBERS = ["c0", "a1", OWN, "m1", "m2", "m3", "m4", "m5"]


def group_info(has_more=False, total=None):
    return {G: {"name": "Nhóm thử", "memberIds": MEMBERS, "creatorId": "c0", "adminIds": ["a1"], "totalMember": total or len(MEMBERS),
                "hasMoreMember": has_more, "currentMems": [{"id": m, "dName": "Tên " + m} for m in MEMBERS]}}


class FakeSvc:
    def __init__(self, items=ITEMS, has_more=False, total=None):
        self.items, self.has_more, self.total, self.kicked, self.calls = items, has_more, total, [], []

    def __call__(self, action, body):
        self.calls.append((action, body))
        if action == "get_group_info":
            return group_info(self.has_more, self.total)
        if action == "get_list_board":
            assert {"board_type", "page", "count", "last_id", "last_type"} <= set(body), "thiếu tham số phân trang: Zalo trả 114"
            return {"items": self.items if body["page"] == 1 else [], "count": len(self.items)}
        if action == "remove_user_from_group":
            self.kicked.append(body["member_id"])
            return {}
        raise AssertionError(action)


def ids(lst):
    return sorted(x["id"] for x in lst)


def test_none_mode_lists_members_who_voted_in_no_poll_and_protects_leaders():
    svc = FakeSvc()
    group, polls = gp.load_group(svc, G), gp.load_polls(svc, G)
    assert [p["poll_id"] for p in polls] == ["101", "102", "103", "104"]
    chosen = gp.select_polls(polls, None)                                    # mặc định: mọi bình chọn đang MỞ
    assert [p["poll_id"] for p in chosen] == ["101", "102", "103"]
    r = gp.compute_non_voters(group, chosen, OWN, "none")
    assert r["polls_used"] == ["101", "102"] and [s["poll_id"] for s in r["skipped"]] == ["103"], r
    assert ids(r["non_voters"]) == ["m4", "m5"], "m4 chỉ bình chọn ở cuộc ĐÃ ĐÓNG nên không tính"
    assert {p["id"]: p["why"] for p in r["protected"]} == {"c0": "trưởng nhóm", "a1": "phó nhóm", OWN: "chính tài khoản này"}
    assert r["members_complete"] is True


def test_any_and_min_modes_with_multiple_polls_and_multi_choice():
    svc = FakeSvc()
    group, polls = gp.load_group(svc, G), gp.load_polls(svc, G)
    chosen = gp.select_polls(polls, ["101", "102"])
    assert ids(gp.compute_non_voters(group, chosen, OWN, "any")["non_voters"]) == ["m2", "m3", "m4", "m5"]   # m1 là người duy nhất có mặt ở cả hai
    assert ids(gp.compute_non_voters(group, chosen, OWN, "min", 2)["non_voters"]) == ["m2", "m3", "m4", "m5"]
    assert ids(gp.compute_non_voters(group, chosen, OWN, "min", 1)["non_voters"]) == ["m4", "m5"]
    big = gp.compute_non_voters(group, chosen, OWN, "min", 99)                # trần: không quá số bình chọn dùng được
    assert big["min_votes"] == 2


def test_anonymous_only_and_bad_arguments_are_refused():
    svc = FakeSvc()
    group, polls = gp.load_group(svc, G), gp.load_polls(svc, G)
    for bad in (lambda: gp.compute_non_voters(group, gp.select_polls(polls, ["103"]), OWN),
                lambda: gp.compute_non_voters(group, polls, OWN, "xyz"),
                lambda: gp.select_polls(polls, ["999"])):
        try:
            bad()
            raise AssertionError("phải lỗi")
        except gp.PollError:
            pass
    assert gp.select_polls(polls, ["104"])[0]["closed"] is True               # chọn rõ bình chọn đã đóng thì được


def test_remove_requires_confirm_complete_members_and_only_fresh_non_voters():
    svc = FakeSvc()
    group, polls = gp.load_group(svc, G), gp.load_polls(svc, G)
    fresh = gp.compute_non_voters(group, gp.select_polls(polls, ["101", "102"]), OWN)
    slept = []
    for kw, why in ((dict(confirm=None), "confirm"), (dict(confirm="true"), "confirm"), (dict(confirm=True, member_ids=[]), "Chưa chọn"),
                    (dict(confirm=True, member_ids=["m1"]), "không được xoá"),            # đã bình chọn
                    (dict(confirm=True, member_ids=["c0"]), "không được xoá"),            # trưởng nhóm
                    (dict(confirm=True, member_ids=["a1"]), "không được xoá"),            # phó nhóm
                    (dict(confirm=True, member_ids=[OWN]), "không được xoá"),             # chính mình
                    (dict(confirm=True, member_ids=["m%d" % i for i in range(11)]), "tối đa")):
        kw.setdefault("member_ids", ["m4"])
        try:
            gp.remove_members(svc, G, group, fresh, kw["member_ids"], kw["confirm"], sleep=slept.append)
            raise AssertionError("phải từ chối: %s" % why)
        except gp.PollError as e:
            assert why.lower() in str(e).lower(), (why, str(e))
    assert svc.kicked == [], "từ chối thì không xoá ai"
    out = gp.remove_members(svc, G, group, fresh, ["m4", "m5"], True, sleep=slept.append)
    assert [r["ok"] for r in out["results"]] == [True, True] and svc.kicked == ["m4", "m5"] and slept == [gp.REMOVE_DELAY_S], (out, slept)
    assert out["remaining"] == 0
    incomplete = FakeSvc(has_more=True, total=50)
    g2 = gp.load_group(incomplete, G)
    assert g2["complete"] is False
    try:
        gp.remove_members(incomplete, G, g2, fresh, ["m4"], True, sleep=slept.append)
        raise AssertionError("nhóm chưa đủ danh sách: không xoá")
    except gp.PollError as e:
        assert "chưa đủ" in str(e)


def test_one_failed_removal_is_reported_and_does_not_stop_the_rest():
    svc = FakeSvc()
    group, polls = gp.load_group(svc, G), gp.load_polls(svc, G)
    fresh = gp.compute_non_voters(group, gp.select_polls(polls, ["101", "102"]), OWN)
    orig = svc.__call__

    def flaky(action, body):
        if action == "remove_user_from_group" and body["member_id"] == "m4":
            raise gp.PollError("Zalo từ chối")
        return orig(action, body)
    out = gp.remove_members(flaky, G, group, fresh, ["m4", "m5"], True, sleep=lambda s: None)
    assert out["results"] == [{"id": "m4", "ok": False, "error": "Zalo từ chối"}, {"id": "m5", "ok": True}], out
    assert out["remaining"] == 1, "m4 chưa xoá được nên vẫn còn lại"


def test_remove_all_takes_batches_of_ten_recomputed_each_time_until_none_remain():
    members = ["c0", "a1", OWN] + ["v%d" % i for i in range(3)] + ["x%d" % i for i in range(23)]     # 23 người chưa bình chọn
    state = {"gone": set()}

    def svc(action, body):
        if action == "get_group_info":
            left = [m for m in members if m not in state["gone"]]
            return {G: {"name": "N", "memberIds": left, "creatorId": "c0", "adminIds": ["a1"], "totalMember": len(left), "hasMoreMember": False,
                        "currentMems": [{"id": m, "dName": m} for m in left]}}
        if action == "get_list_board":
            return {"items": [board_item(1, "q", [("A", ["v0", "v1", "v2"])])]} if body["page"] == 1 else {"items": []}
        if action == "remove_user_from_group":
            state["gone"].add(body["member_id"])
            return {}
    rounds = []
    for _ in range(10):
        group, polls = gp.load_group(svc, G), gp.load_polls(svc, G)
        fresh = gp.compute_non_voters(group, gp.select_polls(polls, ["1"]), OWN)
        out = gp.remove_members(svc, G, group, fresh, None, True, sleep=lambda s: None, take_all=True)
        rounds.append((len(out["results"]), out["remaining"]))
        if out["remaining"] == 0:
            break
    assert rounds == [(10, 13), (10, 3), (3, 0)], rounds
    assert not (state["gone"] & {"c0", "a1", OWN, "v0", "v1", "v2"}), "không bao giờ xoá trưởng/phó nhóm, chính mình hay người đã bình chọn"
    assert len(state["gone"]) == 23
    group, polls = gp.load_group(svc, G), gp.load_polls(svc, G)
    fresh = gp.compute_non_voters(group, gp.select_polls(polls, ["1"]), OWN)
    assert gp.remove_members(svc, G, group, fresh, None, True, take_all=True) == {"results": [], "remaining": 0}
    try:
        gp.remove_members(svc, G, group, fresh, None, None, take_all=True)
        raise AssertionError("xoá hết cũng phải có confirm")
    except gp.PollError:
        pass


# -- qua tuyến server ----------------------------------------------------------------------------------
def _patched_server(svc):
    mock = MockZalo().start()
    httpd = v._run_server(mock)
    real = app_server.services_mod.handle_svc

    def fake(state, action, body, files=None):
        try:
            return 200, {"ok": True, "action": action, "data": svc(action, body)}
        except gp.PollError as e:
            return 502, {"error": str(e)}
    app_server.services_mod.handle_svc = fake
    return mock, httpd, real


def test_server_routes_list_filter_and_remove_with_confirmation():
    svc = FakeSvc()
    mock, httpd, real = _patched_server(svc)
    try:
        # uid thật của phiên (mock) cũng là thành viên: phải được bảo vệ
        own = str((app_server.STATE.session or {}).get("uid") or OWN)
        global MEMBERS
        old = list(MEMBERS)
        MEMBERS[:] = ["c0", "a1", own, "m1", "m2", "m3", "m4", "m5"]
        status, body = v.api_json("GET", "/api/group/%s/polls" % G)
        assert status == 200 and [p["poll_id"] for p in body["polls"]] == ["101", "102", "103", "104"], body
        assert body["group"]["complete"] is True and body["polls"][0]["voted"] == 3, body
        status, r = v.api_json("POST", "/api/group/%s/poll_non_voters" % G, {"poll_ids": ["101", "102"], "mode": "none"})
        assert status == 200 and ids(r["non_voters"]) == ["m4", "m5"] and own in ids(r["protected"]), r
        status, r = v.api_json("POST", "/api/group/%s/poll_non_voters" % G, {"mode": "bậy"})
        assert status == 400, r
        n = len(svc.kicked)
        status, r = v.api_json("POST", "/api/group/%s/remove_members" % G, {"poll_ids": ["101", "102"], "member_ids": ["m4"]})
        assert status == 400 and "confirm" in r["error"] and len(svc.kicked) == n, "không confirm thì không xoá"
        status, r = v.api_json("POST", "/api/group/%s/remove_members" % G, {"poll_ids": ["101", "102"], "member_ids": ["m1"], "confirm": True})
        assert status == 400 and svc.kicked == [], "người đã bình chọn không xoá được"
        app_server.REMOVE_SLEEP = None
        status, r = v.api_json("POST", "/api/group/%s/remove_members" % G, {"poll_ids": ["101", "102"], "member_ids": ["m4"], "confirm": True})
        assert status == 200 and r["removed"] == 1 and svc.kicked == ["m4"] and r["remaining"] == 1, r
        status, r = v.api_json("POST", "/api/group/%s/remove_members" % G, {"poll_ids": ["101", "102"], "all": True, "confirm": True})
        assert status == 200 and svc.kicked == ["m4", "m4", "m5"], (status, r, svc.kicked)    # giả lập không xoá thật nên m4 vẫn còn trong danh sách
        MEMBERS[:] = old
    finally:
        app_server.services_mod.handle_svc = real
        httpd.shutdown()
        mock.stop()
        app_server.STATE.stop_sync()


def test_server_routes_need_the_zalo_session():
    mock = MockZalo().start()
    try:
        httpd = v._run_server(mock)
        try:
            app_server.STATE.session = None
            status, body = v.api_json("GET", "/api/group/%s/polls" % G)
            assert status == 401, (status, body)
            status, body = v.api_json("POST", "/api/group/%s/remove_members" % G, {"confirm": True, "member_ids": ["m4"]})
            assert status == 401, (status, body)
        finally:
            httpd.shutdown()
    finally:
        mock.stop()
        app_server.STATE.stop_sync()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL GROUP POLL TESTS PASSED")
