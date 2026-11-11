"""Cai dat thiet bi mac dinh cua app: nguon mic, nguon camera, thong so hinh.

Luu o <data_dir>/devices.json (0600: URL luong co the chua mat khau). Giao dien /
API doc ban DA CHE mat khau (user:***@host). Moi cuoc goi co the ghi de bang
truong `mic_url` / `mic_format` / `camera_url` cua /api/call/request, /answer,
/api/call/media. Loa khong nam o day: app chi phat WAV (GET /api/call/audio/out/
<token>) cho bat ky thiet bi nao (loa HA, trinh duyet, may khac).
"""

import json
import os
import re
import threading

DEFAULTS = {
    "mic_url": "",              # "" = khong tu dong phat mic
    "mic_format": "auto",       # auto | s16le16k (PCM tho 16 kHz, vi du mic R1)
    "camera_url": "",           # "" = khong tu dong phat hinh
    "speaker_url": "",          # "" = khong tu dong phat loa truc tiep (URL bo dam http(s) A-law 8 kHz)
    "echo_guard": False,        # tam ngung gui mic khi loa dang phat tieng that (mic va loa cung thiet bi)
    "video": {"width": 640, "height": 360, "fps": 15, "bitrate_kbps": 300},
    "auto_mic": True,           # tu phat mic khi cuoc goi duoc nghe may
    "auto_video_on_request": False,  # dien thoai xin len video: tu dong y + phat camera. MAC DINH TAT (rieng tu): HA quyet dinh theo quy tac `video_request`
    "auto_video_delay": 0,           # giay cho truoc khi tu dong y (0 = ngay)
}
MAX_AUTO_VIDEO_DELAY = 120
MIC_FORMATS = ("auto", "s16le16k")
_URL_OK = re.compile(r"^(rtsps?|https?|rtmps?)://\S+$")
_HTTP_OK = re.compile(r"^https?://\S+$")
_MASK = re.compile(r"(://[^/\s:@]+:)[^@/\s]*@")
# Tham so truy van mang bi mat (khoa mic R1 `?k=`, token...) cung bi che khi hien thi.
_MASK_QUERY = re.compile(r"([?&](?:k|key|token|access_token|auth|pass|password|pwd|secret)=)[^&#\s]*",
                         re.I)
_LIMITS = {"width": (160, 1280), "height": (120, 720), "fps": (5, 30),
           "bitrate_kbps": (50, 1500)}


def mask_url(url):
    """URL voi mat khau (user:***@) va tham so bi mat (?k=***) thay bang *** (hien thi / log)."""
    return _MASK_QUERY.sub(r"\1***", _MASK.sub(r"\1***@", url or ""))


def valid_source(url):
    """Rong, "test", URL luong hop le hoac duong dan tep tuyet doi."""
    return (url == "" or url == "test" or bool(_URL_OK.match(url))
            or (url.startswith("/") and "\n" not in url and ".." not in url))


class DeviceStore:
    def __init__(self, path):
        self._path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return data
        if isinstance(raw, dict):
            self._merge(data, raw, strict=False)
        return data

    @staticmethod
    def _merge(data, patch, strict):
        """Gop `patch` vao `data`. strict: sai gia tri -> ValueError."""
        def bad(msg):
            if strict:
                raise ValueError(msg)

        if "speaker_url" in patch:
            val = str(patch["speaker_url"] or "").strip()
            if "***" in val and re.search(r"=\*\*\*(?:&|$)|\*\*\*@", val):
                pass                          # ban da che: giu nguyen
            elif val == "" or _HTTP_OK.match(val):
                data["speaker_url"] = val
            else:
                bad("speaker_url phai la URL http(s)")
        if "echo_guard" in patch:
            data["echo_guard"] = bool(patch["echo_guard"])
        for key in ("mic_url", "camera_url"):
            if key in patch:
                val = str(patch[key] or "").strip()
                if "***@" in val or re.search(r"=\*\*\*(?:&|$)", val):
                    continue                      # ban da che: giu nguyen
                if valid_source(val):
                    data[key] = val
                else:
                    bad("%s khong hop le" % key)
        if patch.get("mic_format") in MIC_FORMATS:
            data["mic_format"] = patch["mic_format"]
        elif "mic_format" in patch:
            bad("mic_format khong hop le")
        for key in ("auto_mic", "auto_video_on_request"):
            if key in patch:
                data[key] = bool(patch[key])
        if "auto_video_delay" in patch:
            try:
                data["auto_video_delay"] = max(
                    0, min(MAX_AUTO_VIDEO_DELAY, int(patch["auto_video_delay"])))
            except (TypeError, ValueError):
                bad("auto_video_delay khong hop le")
        video = patch.get("video")
        if isinstance(video, dict):
            for key, (lo, hi) in _LIMITS.items():
                if key in video:
                    try:
                        data["video"][key] = max(lo, min(hi, int(video[key])))
                    except (TypeError, ValueError):
                        bad("video.%s khong hop le" % key)

    def get(self):
        """Ban day du (co mat khau) — chi dung trong tien trinh."""
        with self._lock:
            return json.loads(json.dumps(self._data))

    def public(self):
        d = self.get()
        d["mic_url"] = mask_url(d["mic_url"])
        d["camera_url"] = mask_url(d["camera_url"])
        d["speaker_url"] = mask_url(d["speaker_url"])
        return d

    def update(self, patch):
        if not isinstance(patch, dict):
            raise ValueError("thieu noi dung")
        with self._lock:
            new = json.loads(json.dumps(self._data))
            self._merge(new, patch, strict=True)
            self._data = new
            self._save()
            return json.loads(json.dumps(new))

    def _save(self):
        tmp = self._path + ".tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError:
            pass            # khong luu duoc thi van dung ban trong bo nho
