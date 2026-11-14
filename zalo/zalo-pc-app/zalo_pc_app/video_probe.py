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


VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".3gp")


def is_video_name(name):
    return str(name or "").lower().endswith(VIDEO_EXTS)


def probe_video_bytes(data, filename="video.mp4", timeout=30, run=subprocess.run):
    """Đo video đã có byte trong bộ nhớ (WebUI tải lên): {"width","height","duration_ms","thumb": <JPEG bytes>}. Ghi tạm ra tệp rồi gọi ffprobe/ffmpeg; khoá nào không đo được thì vắng.
    Không bao giờ ném lỗi (thiếu ffmpeg → {}): gửi video vẫn tiếp tục, chỉ không có ảnh bìa."""
    import os
    import tempfile
    out = {}
    d = tempfile.mkdtemp(prefix="zalo-vprobe-")
    path = os.path.join(d, "in" + (os.path.splitext(str(filename))[1] if is_video_name(filename) else ".mp4"))
    try:
        with open(path, "wb") as fh:
            fh.write(bytes(data))
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format", "-of", "json", path]
        try:
            p = run(cmd, capture_output=True, timeout=timeout, text=True)
            if p.returncode == 0:
                dd = json.loads(p.stdout or "{}")
                st = (dd.get("streams") or [{}])[0] or {}
                w, h = int(st.get("width") or 0), int(st.get("height") or 0)
                rot = 0
                try:
                    rot = int(float((st.get("tags") or {}).get("rotate") or 0))
                    for sd in st.get("side_data_list") or []:
                        if "rotation" in sd:
                            rot = int(float(sd["rotation"]))
                except (TypeError, ValueError):
                    rot = 0
                if abs(rot) % 180 == 90:
                    w, h = h, w
                if w > 0 and h > 0:
                    out["width"], out["height"] = w, h
                sec = float((dd.get("format") or {}).get("duration") or st.get("duration") or 0)
                if sec > 0:
                    out["duration_ms"] = int(round(sec * 1000))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        jpg = os.path.join(d, "thumb.jpg")
        seek = "0.5" if out.get("duration_ms", 0) > 1500 else "0"
        try:
            p = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", seek, "-i", path, "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", "-q:v", "4", jpg],
                    capture_output=True, timeout=timeout)
            if p.returncode == 0 and os.path.isfile(jpg) and os.path.getsize(jpg) > 100:
                with open(jpg, "rb") as fh:
                    out["thumb"] = fh.read()
        except (OSError, subprocess.SubprocessError):
            pass
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    return out
