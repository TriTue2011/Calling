"""Kenh dieu khien long-poll (99101 getControllFromPolling) — event
async cho upload file/ghi am.

BANG CHUNG BUNDLE (compact-app-pc.5c0110a3a8749b3aacde.js,
Zalo PC 26.11.10):
  static getControllFromPolling(e,t):
    GET q[$] + "/?" + commonParams + "&params=" + e + "&ts=" + unix
    timeout 1e3 * Q   (Q = lp_ctl_timeout, mac dinh 30 giay)
  q = config.zpw_ctrs_new (danh sach URL long-poll dieu khien, server
  tra ve o getLoginInfo — app luu nguyen tu config, khong hard-code);
  e = idPoll.getLastActionIds() — CUNG dinh dang params nhu kenh tin
  nhan 99100 (xem sync_poll.PollCursor).
  Kenh nay RIENG BIET voi kenh tin nhan 99100 (getChatFromPolling,
  zpw_chts_new): event async cua upload KHONG ve qua 99100.

  `_processCtrlMessages(e,t)`: `e.controls` la list cac
  {content: {act_type, ...}, controlId}; content.data la CHUOI JSON
  (parse neu bat dau bang "{" hoac "["); gom theo act_type roi
  dispatch: "file_done" / "video_done" / "photo_success" /
  "voice_aac_success" / ...
  `_processVoiceAsyncDoneEvent(e)`: moi event co fileId + data;
  `t = {amr: n.data[L.VOICE_TYPE.AMR], aac: n.data[L.VOICE_TYPE.AAC]}`
  voi `VOICE_TYPE={AMR:5, AAC:6}` — tuc la data co key SO "5"/"6";
  roi `handleEventFromCtrl({fileId, data: t}, "VOICE")` — day event
  toi handler ma upload-manager dang ky theo fileId
  (`waitAsyncFileInfo` / `__waitAsyncFileInfo`); handler dien
  `fileUrl = amr||aac` (+ `aacUrl` khi co amr, + `secureKey` chi khi
  async data co no) vao fileAsync truoc khi gui buoc 2
  (asyncfile/msg 11777/13001). Event voice CHI co amr/aac — khong
  co secureKey (secureKey chi xuat hien o mapVoiceResponse, tuc la
  passthrough tu chunk-response, va chi dung cho E2EE/pcloud).

  `__waitAsyncFileInfo` cung doc cache truoc (`getFileIdData`):
  event den TRUOC khi wait dang ky van duoc nhan ngay. Registry o
  day giu dung hanh vi do: deliver() luu lai, wait() tra ngay neu
  da co.

QUYET DINH THIET KE (ghi ro, chua chung minh bang live):
  - Moi poller (tin nhan 99100, ctrl 99101) giu PollCursor RIENG.
    Bundle dung CHUNG mot idPoll cho ca hai poller (ca hai deu goi
    getLastActionIds()); tach rieng tranh race giua hai thread
    long-poll cung cap nhat mot con tro, vi moi kenh co queueStatus
    rieng trong response cua no. Hanh vi nay can live kiem chung
    cung voi viec event voice_aac_success co ve that khong.
  - Poller nay CHI xu ly event voice_aac_success (phuc vu
    send_voice); cac act_type khac duoc bo qua im lang — group_event
    / reaction van cho kenh ctrl day du (xem ghi chu o sync_poll).
  - Khong replay chunk cuoi khi het gio nhu bundle (replay last
    chunk sau 30 s doi voi file nho): o day het timeout thi loi ro
    rang, khong gui buoc 2 (xem chat.send_voice). Replay la viec
    can lam them neu live cho thay event hay bi mat.
"""

import json
import sys
import threading
import time
import urllib.parse

from . import protocol
from .crypto import decode_postlogin_data
from .sync_poll import (ERR_STOP_RETRY, KickOut, PollCursor,
                        RETRY_BASE_SECONDS, RETRY_MAX_SECONDS)

# act_type cua event voice trong payload ctrl (bundle
# _processCtrlMessages: case "voice_aac_success").
CTRL_VOICE_ACT = "voice_aac_success"

# Key SO cua URL trong data cua event voice (bundle
# VOICE_TYPE={AMR:5, AAC:6}).
VOICE_TYPE_AMR = "5"
VOICE_TYPE_AAC = "6"


def _event_data(raw):
    """data cua mot ctrl content: dict, hoac CHUOI JSON (bundle
    parse neu bat dau bang "{" hoac "["); dang khac -> None."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text[:1] in ("{", "["):
            try:
                parsed = json.loads(text)
            except ValueError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def _url(value):
    """URL hop le: chuoi khong rong; dang khac -> None."""
    return value if isinstance(value, str) and value else None


def extract_voice_async(data):
    """Tach cac event voice_aac_success tu payload ctrl da giai ma
    -> [{"fileId", "amr", "aac"}] (amr/aac co the None neu event
    chi co mot dang). Event thieu fileId, thieu ca hai URL, hoac
    sai dinh dang thi bo qua — kenh ctrl con nhieu loai event
    khac, khong duoc do vi mot event la.

    data: dict da giai ma cua mot lan poll ctrl, co key
    "controls" la list cac {content: {act_type, fileId, data}}."""
    out = []
    if not isinstance(data, dict):
        return out
    controls = data.get("controls")
    if not isinstance(controls, list):
        return out
    for ctrl in controls:
        if not isinstance(ctrl, dict):
            continue
        content = ctrl.get("content")
        if not isinstance(content, dict):
            continue
        if content.get("act_type") != CTRL_VOICE_ACT:
            continue
        file_id = content.get("fileId")
        if not file_id:
            continue
        urls = _event_data(content.get("data"))
        if not urls:
            continue
        amr = _url(urls.get(VOICE_TYPE_AMR) or urls.get(5)
                   or urls.get("amr"))
        aac = _url(urls.get(VOICE_TYPE_AAC) or urls.get(6)
                   or urls.get("aac"))
        if not amr and not aac:
            continue
        out.append({"fileId": str(file_id), "amr": amr, "aac": aac})
    return out


class VoiceAsyncRegistry:
    """Kho ket qua event async voice theo fileId (giong local map
    fileId->data cua bundle: setFileIdData/getFileIdData).

    - deliver() luu lai ngay ca khi chua co ai doi (event co the
      den truoc khi send_voice bat dau doi — bundle cache-hit).
    - wait() tra ngay neu da co, khong thi cho toi timeout roi tra
      None (khong nem loi — caller quyet dinh loi ro rang).
    - feeder_running: True khi CtrlPoller dang chay va nap
      registry; False thi khong co event nao se den nua — caller
      loi nhanh thay vi doi het timeout (xem chat.send_voice).
    Chi luu URL (khong luu noi dung file, khong log URL)."""

    def __init__(self, max_entries=200):
        self._lock = threading.Lock()
        self._results = {}  # fileId -> {"amr", "aac"}
        self._events = {}   # fileId -> threading.Event
        self.feeder_running = False
        self._max = max(1, int(max_entries or 200))

    def deliver(self, file_id, amr=None, aac=None):
        """Ghi nhan event cho fileId; tra True neu co it nhat mot
        URL hop le (False thi bo qua — khong danh thuc waiter)."""
        amr = _url(amr)
        aac = _url(aac)
        if not amr and not aac:
            return False
        fid = str(file_id)
        with self._lock:
            self._results[fid] = {"amr": amr, "aac": aac}
            event = self._events.get(fid)
            if event is None:
                event = self._events[fid] = threading.Event()
            # Cat muc cu nhat khi tran (fileId la duy nhat moi lan
            # gui nen kho nay chi phong tran RAM neu server day
            # event cho file khong ai doi).
            while len(self._results) > self._max:
                oldest = next(iter(self._results))
                self._results.pop(oldest, None)
                self._events.pop(oldest, None)
            event.set()
        return True

    def wait(self, file_id, timeout_s=120.0):
        """Doi event cho fileId toi da timeout_s giay. Tra dict
        {"amr", "aac"} (mot trong hai co the None) neu co, None neu
        het gio. Tra NGAY neu event da den truoc."""
        fid = str(file_id)
        with self._lock:
            cached = self._results.get(fid)
            if cached is not None:
                return dict(cached)
            event = self._events.get(fid)
            if event is None:
                event = self._events[fid] = threading.Event()
        try:
            timeout = float(timeout_s)
        except (TypeError, ValueError):
            timeout = 120.0
        if timeout <= 0:
            return None
        if not event.wait(timeout):
            return None
        with self._lock:
            got = self._results.get(fid)
        return dict(got) if got is not None else None

    def discard(self, file_id):
        """Xoa muc cua fileId (sau khi da dung xong)."""
        with self._lock:
            self._results.pop(str(file_id), None)
            self._events.pop(str(file_id), None)


class CtrlPoller:
    """Long-poll kenh dieu khien 99101 chay nen: GET lien tuc toi
    zpw_ctrs_new, giai ma payload, tach event voice_aac_success
    giao cho VoiceAsyncRegistry.

    http_get(url, timeout) -> (status, json) — giong transport
    cua Chat/Signaling (mang cookie zpw_sek). Loi mang -> backoff
    roi poll lai; KickOut (-69) -> dung han (giong SyncPoller)."""

    def __init__(self, http_get, poll_urls, zpw_enk, own_id,
                 registry, ctl_timeout=30):
        urls = [u for u in (poll_urls or []) if u]
        if not urls:
            raise ValueError("ctrl_poll: can it nhat 1 poll URL "
                             "(zpw_ctrs_new tu getLoginInfo)")
        if registry is None:
            raise ValueError("ctrl_poll: can VoiceAsyncRegistry")
        self.http_get = http_get
        self.urls = urls
        self.zpw_enk = zpw_enk
        self.own_id = str(own_id or "")
        self.registry = registry
        try:
            self.ctl_timeout = int(ctl_timeout or 30)
        except (TypeError, ValueError):
            self.ctl_timeout = 30
        if self.ctl_timeout <= 0:
            self.ctl_timeout = 30
        self.cursor = PollCursor()
        self._idx = 0
        self._stop = threading.Event()
        self._thread = None
        self.kicked_out = False
        self.last_error = ""
        self.polls = 0  # dem so lan poll (chan doan, khong log nd)

    def _poll_url(self):
        base = self.urls[self._idx % len(self.urls)].rstrip("/")
        qs = urllib.parse.urlencode(protocol.common_params())
        return "%s/?%s&params=%s&ts=%d" % (
            base, qs, self.cursor.param(), int(time.time()))

    def poll_once(self):
        """Mot lan long-poll ctrl. Tra ve "ok" | "empty" |
        "rotated". Timeout cuc bo -> xoay endpoint, tra "rotated".
        Loi HTTP / loi giai ma -> RuntimeError (caller backoff).
        Server bao dung -> KickOut."""
        url = self._poll_url()
        try:
            status, payload = self.http_get(
                url, timeout=self.ctl_timeout + 5)
        except TimeoutError:
            self._idx = (self._idx + 1) % len(self.urls)
            return "rotated"
        except Exception as e:  # noqa: BLE001 - mang loi -> backoff
            raise RuntimeError("ctrl_poll: poll loi mang: %s"
                               % type(e).__name__)
        self.polls += 1
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("ctrl_poll: network status=%s" % status)
        if payload.get("data") == "":
            return "empty"
        code = payload.get("error_code")
        if code == ERR_STOP_RETRY:
            self.kicked_out = True
            raise KickOut("ctrl_poll: server tra -69, dung retry")
        if code not in (0, None):
            raise RuntimeError("ctrl_poll: error_code=%s" % code)
        data = decode_postlogin_data(payload, self.zpw_enk)
        if data is None:
            return "empty"
        for event in extract_voice_async(data):
            self.registry.deliver(event["fileId"], event["amr"],
                                  event["aac"])
        self.cursor.update_from(data)
        return "ok"

    def run(self):
        """Vong poll lien tuc cho toi stop() — giong SyncPoller.run
        (backoff 3s, nhan doi, tran 60s; san 1 giay moi vong)."""
        backoff = RETRY_BASE_SECONDS
        try:
            while not self._stop.is_set():
                started = time.time()
                try:
                    self.poll_once()
                    backoff = RETRY_BASE_SECONDS
                except KickOut:
                    return
                except Exception as e:  # noqa: BLE001
                    self.last_error = str(e)
                    if not sys.is_finalizing():
                        print("[ctrl-poll] %s; retry sau %.0fs"
                              % (self.last_error, backoff), flush=True)
                    if self._stop.wait(backoff):
                        return
                    backoff = min(backoff * 2, RETRY_MAX_SECONDS)
                    continue
                elapsed = time.time() - started
                if elapsed < 1.0 and self._stop.wait(1.0 - elapsed):
                    return
        finally:
            self.registry.feeder_running = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self.registry.feeder_running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.registry.feeder_running = False
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2)
