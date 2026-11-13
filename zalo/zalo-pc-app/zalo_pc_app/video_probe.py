"""Đo video (độ rộng, độ cao, thời lượng) bằng ffprobe trước khi gửi video thật vào Zalo (13/11/2026).

Zalo dựng khung video từ `width`/`height`/`duration` trong tin; thiếu thì khung mặc định 1280x720 và không có thời lượng. ffprobe đọc thẳng
từ địa chỉ http(s) (chỉ cho giao thức http/https/tls để địa chỉ lạ không mở được tệp cục bộ). Lỗi bất kỳ -> {} và caller dùng mặc định:
đo hỏng không được chặn việc gửi.
"""

import json
import subprocess


def probe_video(url, timeout=15, run=subprocess.run):
    """-> {"width": int, "height": int, "duration_ms": int}; khoá nào không đọc được thì vắng. Không bao giờ ném lỗi."""
    if not str(url or "").lower().startswith(("http://", "https://")):
        return {}
    cmd = ["ffprobe", "-v", "error", "-protocol_whitelist", "http,https,tcp,tls,crypto", "-select_streams", "v:0",
           "-show_streams", "-show_format", "-of", "json", str(url)]
    try:
        p = run(cmd, capture_output=True, timeout=timeout, text=True)
        if p.returncode != 0:
            return {}
        d = json.loads(p.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    out = {}
    st = (d.get("streams") or [{}])[0] or {}
    try:
        w, h = int(st.get("width") or 0), int(st.get("height") or 0)
    except (TypeError, ValueError):
        w = h = 0
    rot = 0
    try:
        rot = int(float((st.get("tags") or {}).get("rotate") or 0))
        for sd in st.get("side_data_list") or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
    except (TypeError, ValueError):
        rot = 0
    if abs(rot) % 180 == 90:          # điện thoại quay dọc: khung hiển thị đã xoay
        w, h = h, w
    if w > 0 and h > 0:
        out["width"], out["height"] = w, h
    try:
        sec = float((d.get("format") or {}).get("duration") or st.get("duration") or 0)
        if sec > 0:
            out["duration_ms"] = int(round(sec * 1000))
    except (TypeError, ValueError):
        pass
    return out
