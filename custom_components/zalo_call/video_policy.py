"""Quyết định xử lý lời xin chuyển sang video (thuần Python, không phụ thuộc Home Assistant để test riêng).

Hai lớp, cả hai phải cho phép thì mới tự đồng ý:
  1. CÔNG TẮC TỔNG trên thiết bị «Cho phép đồng ý chuyển sang video» (mặc định TẮT).
  2. QUY TẮC của chính người/nhóm đó: ``video_request`` = accept | accept_camera (không có quy tắc hoặc ask = chỉ báo).
Áp cho cả cuộc gọi đến lẫn cuộc gọi đi (quy tắc tìm theo mã Zalo của người kia).
"""
from __future__ import annotations

from typing import Any

ASK, ACCEPT, ACCEPT_CAMERA = "ask", "accept", "accept_camera"


def decide(rule: dict | None, consent_on: Any) -> str:
    """ask (chỉ báo sự kiện, KHÔNG đồng ý) | accept | accept_camera."""
    if not rule or not consent_on:
        return ASK
    mode = str(rule.get("video_request") or ASK)
    return mode if mode in (ACCEPT, ACCEPT_CAMERA) else ASK
