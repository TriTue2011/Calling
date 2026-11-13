"""Sức khoẻ tài khoản Zalo từ /api/status của app (hàm thuần, không phụ thuộc Home Assistant).

online      đã đăng nhập và cả hai kênh nhận (tin nhắn, điều khiển/cuộc gọi) đang chạy
degraded    đã đăng nhập nhưng một kênh dừng / chưa có / đang thử lại (có thể lỡ tin hoặc cuộc gọi đến)
logged_out  chưa đăng nhập hoặc phiên đã kết thúc (xem thuộc tính reason: local_logout / remote_revoked / session_rejected)
"""
from __future__ import annotations

from typing import Any

STATES = ("online", "degraded", "logged_out")
SESSION_END_TEXT = {
    "local_logout": "Bạn đã đăng xuất",
    "remote_revoked": "Bị thu hồi từ xa (đăng nhập ở nơi khác)",
    "session_rejected": "Zalo từ chối phiên (hết hạn)",
}


def account_state(status: dict[str, Any] | None) -> str:
    if not isinstance(status, dict) or not status.get("login"):
        return "logged_out"
    if status.get("sync") == "running" and status.get("ctrl") == "running":
        return "online"
    return "degraded"


def attributes(status: dict[str, Any] | None) -> dict[str, Any]:
    status = status if isinstance(status, dict) else {}
    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    end = health.get("last_session_end") if isinstance(health.get("last_session_end"), dict) else None
    out: dict[str, Any] = {"sync": status.get("sync"), "ctrl": status.get("ctrl"),
                           "keepalive": (status.get("keepalive") or {}).get("state") if isinstance(status.get("keepalive"), dict) else None}
    ws = status.get("ws") if isinstance(status.get("ws"), dict) else {}
    out["ws"] = ws.get("state") or "off"                      # kênh WebSocket (poll luôn chạy song song làm dự phòng)
    out["ws_active"] = bool(ws.get("active"))
    if end:
        out["last_session_end"] = SESSION_END_TEXT.get(str(end.get("detail")), str(end.get("detail")))
        out["last_session_end_at"] = end.get("t")
    events = health.get("events") if isinstance(health.get("events"), list) else []
    out["recent_events"] = [{"t": e.get("t"), "kind": e.get("kind"), "detail": e.get("detail")} for e in events[-5:] if isinstance(e, dict)]
    return out
