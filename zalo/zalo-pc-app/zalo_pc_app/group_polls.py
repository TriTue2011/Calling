"""Bình chọn nhóm: ai CHƯA bình chọn, và (có xác nhận) xoá họ khỏi nhóm.

Dữ liệu lấy từ các dịch vụ có sẵn của app (không thêm đường gọi Zalo mới):
  * ``get_list_board`` (phải kèm board_type/page/count/last_id/last_type, thiếu là Zalo trả 114): danh sách bảng tin của nhóm; phần tử
    ``boardType == 3`` là bình chọn, có ``poll_id``, ``question``, ``closed``, ``is_anonymous`` và ``options[].voters`` (ID người đã chọn).
  * ``get_group_info``: thành viên (``memberIds``, ``currentMems`` kèm tên), ``creatorId``, ``adminIds``, ``totalMember``, ``hasMoreMember``.
  * ``remove_user_from_group``: xoá thành viên (không hoàn tác được).

An toàn: trưởng nhóm, phó nhóm và chính tài khoản này KHÔNG BAO GIỜ nằm trong danh sách «chưa bình chọn»; danh sách thành viên chưa đủ
(``hasMoreMember``) thì không cho xoá; xoá chỉ nhận ID nằm trong danh sách vừa tính lại phía server (không tin danh sách từ trình duyệt),
cần ``confirm`` rõ ràng, mỗi lần tối đa MAX_REMOVE người và cách nhau REMOVE_DELAY_S giây để Zalo không chặn.
"""
from __future__ import annotations

import time

BOARD_POLL = 3
BOARD_PAGE = 20
BOARD_MAX_PAGES = 5
MAX_REMOVE = 10
REMOVE_DELAY_S = 1.5
MODES = ("none", "any", "min")


class PollError(ValueError):
    """Lỗi do dữ liệu/tham số: trả cho người dùng thành thông báo rõ ràng (HTTP 400/502)."""


def _unwrap(res):
    """handle_svc trả (status, {"ok", "data"}); lỗi thì PollError với lời của Zalo."""
    status, obj = res
    if status != 200:
        raise PollError(str((obj or {}).get("error") or "lỗi %s" % status))
    return (obj or {}).get("data")


def normalize_poll(item: dict):
    """Phần tử bảng tin -> bình chọn gọn, hoặc None nếu không phải bình chọn."""
    if not isinstance(item, dict) or item.get("boardType") != BOARD_POLL:
        return None
    d = item.get("data") or {}
    if d.get("poll_id") in (None, ""):
        return None
    opts = []
    for o in d.get("options") or []:
        opts.append({"option_id": o.get("option_id"), "content": str(o.get("content") or ""), "votes": int(o.get("votes") or 0),
                     "voters": [str(v) for v in (o.get("voters") or [])]})
    return {"poll_id": str(d["poll_id"]), "question": str(d.get("question") or ""), "closed": bool(d.get("closed")),
            "anonymous": bool(d.get("is_anonymous")), "multi": bool(d.get("allow_multi_choices")), "creator": str(d.get("creator") or ""),
            "created_time": d.get("created_time"), "expired_time": d.get("expired_time"), "num_vote": int(d.get("num_vote") or 0), "options": opts}


def poll_voters(poll: dict) -> set:
    return {v for o in poll["options"] for v in o["voters"]}


def load_polls(svc, group_id: str) -> list:
    """Mọi bình chọn của nhóm (tối đa BOARD_MAX_PAGES trang), mới trước. ``svc(action, body)`` -> data."""
    out, seen = [], set()
    for page in range(1, BOARD_MAX_PAGES + 1):
        data = svc("get_list_board", {"thread_id": group_id, "type": "group", "board_type": 0, "page": page, "count": BOARD_PAGE,
                                      "last_id": 0, "last_type": 0})
        items = (data or {}).get("items") or []
        fresh = 0
        for it in items:
            p = normalize_poll(it)
            if p and p["poll_id"] not in seen:
                seen.add(p["poll_id"])
                out.append(p)
                fresh += 1
        if len(items) < BOARD_PAGE or not fresh:
            break
    return out


def load_group(svc, group_id: str) -> dict:
    """Thông tin nhóm gọn: tên, thành viên (id + tên), trưởng nhóm, phó nhóm, danh sách đã đủ chưa."""
    data = svc("get_group_info", {"thread_id": group_id, "type": "group"})
    g = data.get(group_id) if isinstance(data, dict) and group_id in data else data
    if not isinstance(g, dict):
        raise PollError("Không đọc được thông tin nhóm")
    names = {str(m.get("id")): str(m.get("dName") or m.get("zaloName") or m.get("id")) for m in (g.get("currentMems") or []) if isinstance(m, dict)}
    ids = [str(i) for i in (g.get("memberIds") or [])] or list(names)
    total = int(g.get("totalMember") or len(ids))
    return {"name": str(g.get("name") or ""), "members": [{"id": i, "name": names.get(i, i)} for i in ids], "total": total,
            "creator": str(g.get("creatorId") or ""), "admins": {str(a) for a in (g.get("adminIds") or [])},
            "complete": not g.get("hasMoreMember") and len(ids) >= total}


def compute_non_voters(group: dict, polls: list, own_id: str, mode: str = "none", min_votes: int = 1) -> dict:
    """Người chưa bình chọn trong các ``polls`` đã chọn.

    mode: ``none`` = không bình chọn ở bình chọn nào; ``any`` = bỏ sót ít nhất một; ``min`` = bình chọn ít hơn ``min_votes`` cuộc.
    Bình chọn ẩn danh không có người chọn nên bị bỏ qua (kèm lý do). Trưởng/phó nhóm và chính tài khoản này luôn được loại khỏi danh sách."""
    if mode not in MODES:
        raise PollError("mode phải là một trong: " + ", ".join(MODES))
    usable = [p for p in polls if not p["anonymous"]]
    skipped = [{"poll_id": p["poll_id"], "question": p["question"], "why": "bình chọn ẩn danh: không có danh sách người chọn"}
               for p in polls if p["anonymous"]]
    if not usable:
        raise PollError("Chưa có bình chọn nào dùng được (không có bình chọn, hoặc tất cả đều ẩn danh)")
    try:
        min_votes = max(1, int(min_votes))
    except (TypeError, ValueError):
        raise PollError("min_votes phải là số nguyên")
    min_votes = min(min_votes, len(usable))
    voted_sets = [poll_voters(p) for p in usable]
    protected_ids = {group["creator"], own_id, *group["admins"]} - {""}
    non, prot = [], []
    for m in group["members"]:
        count = sum(1 for s in voted_sets if m["id"] in s)
        missing = (count == 0) if mode == "none" else (count < len(usable)) if mode == "any" else (count < min_votes)
        if not missing:
            continue
        if m["id"] in protected_ids:
            why = "trưởng nhóm" if m["id"] == group["creator"] else "chính tài khoản này" if m["id"] == own_id else "phó nhóm"
            prot.append({"id": m["id"], "name": m["name"], "voted": count, "why": why})
        else:
            non.append({"id": m["id"], "name": m["name"], "voted": count})
    return {"mode": mode, "min_votes": min_votes, "polls_used": [p["poll_id"] for p in usable], "skipped": skipped, "non_voters": non,
            "protected": prot, "members_total": len(group["members"]), "members_complete": group["complete"],
            "polls_count": len(usable)}


def select_polls(polls: list, poll_ids) -> list:
    """Danh sách bình chọn theo ``poll_ids``; bỏ trống = mọi bình chọn ĐANG MỞ."""
    if poll_ids:
        want = [str(i) for i in poll_ids]
        have = {p["poll_id"]: p for p in polls}
        missing = [i for i in want if i not in have]
        if missing:
            raise PollError("Không thấy bình chọn: " + ", ".join(missing))
        return [have[i] for i in want]
    return [p for p in polls if not p["closed"]]


def remove_members(svc, group_id: str, group: dict, fresh_non_voters: dict, member_ids, confirm, sleep=time.sleep, take_all: bool = False) -> dict:
    """Xoá thành viên khỏi nhóm. Trả {"results": [...], "remaining": số người chưa bình chọn còn lại}.

    Chỉ nhận ID nằm trong danh sách «chưa bình chọn» VỪA tính lại (không tin danh sách từ trình duyệt); cần confirm; có trần MAX_REMOVE mỗi lần
    và độ trễ giữa các lần xoá. ``take_all``: lấy tối đa MAX_REMOVE người đầu của danh sách vừa tính (để xoá toàn bộ thì gọi lặp lại tới khi
    remaining = 0; mỗi lượt đều tính lại từ dữ liệu mới nhất)."""
    if confirm is not True:
        raise PollError("Cần confirm: true để xoá thành viên (không hoàn tác được)")
    if not group["complete"]:
        raise PollError("Danh sách thành viên của nhóm chưa đủ (nhóm lớn): không xoá theo danh sách thiếu")
    pool = [m["id"] for m in fresh_non_voters["non_voters"]]
    if take_all:
        ids = pool[:MAX_REMOVE]
        if not ids:
            return {"results": [], "remaining": 0}
    else:
        ids = [str(i) for i in (member_ids or [])]
        if not ids:
            raise PollError("Chưa chọn thành viên nào")
        if len(ids) > MAX_REMOVE:
            raise PollError("Mỗi lần xoá tối đa %d người (đã chọn %d); xoá từng đợt" % (MAX_REMOVE, len(ids)))
        bad = [i for i in ids if i not in set(pool)]
        if bad:
            raise PollError("Không được xoá (không nằm trong danh sách chưa bình chọn hiện tại, hoặc là trưởng/phó nhóm): " + ", ".join(bad))
    results = []
    for n, mid in enumerate(ids):
        if n:
            sleep(REMOVE_DELAY_S)
        try:
            svc("remove_user_from_group", {"thread_id": group_id, "type": "group", "member_id": mid})
            results.append({"id": mid, "ok": True})
        except PollError as exc:
            results.append({"id": mid, "ok": False, "error": str(exc)})
    removed = sum(1 for r in results if r["ok"])
    return {"results": results, "remaining": max(0, len(pool) - removed)}
