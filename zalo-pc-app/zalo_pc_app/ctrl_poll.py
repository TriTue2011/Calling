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
  `_processFileAsyncDoneEvent(e)` (file thuong): moi event co
  fileId + data.url -> `handleEventFromCtrl({fileId, url}, "FILE")`;
  handler dien `fileUrl = url` (chuoi) vao fileAsync truoc buoc 2
  — cung gate nhu voice, chi khac dang event (url thang thay vi
  amr/aac). FileAsyncRegistry o day la ban sao cua
  VoiceAsyncRegistry cho dang do ({"url"} thay vi {"amr", "aac"}).

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
  - Poller nay xu ly event voice_aac_success (phuc vu send_voice)
    VA file_done (phuc vu send_file) — xem extract_voice_async /
    extract_file_async; cac act_type khac co y nghia cho webhook:
    "group" -> group_event, "reactions"/"reacts"/"reactGroups" ->
    reaction (xem extract_group_events / extract_reactions).
    Cac act_type khong biet van bo qua im lang.
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
from .sync_poll import (ERR_STOP_RETRY, KickOut,
                        MAX_CONSEC_ERRORS, NonJsonResponse,
                        PollCursor, RETRY_BASE_SECONDS,
                        RETRY_MAX_SECONDS)

# act_type cua event voice trong payload ctrl (bundle
# _processCtrlMessages: case "voice_aac_success").
CTRL_VOICE_ACT = "voice_aac_success"

# act_type cua event file trong payload ctrl (bundle
# _processCtrlMessages: case "file_done").
CTRL_FILE_ACT = "file_done"

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


def extract_file_async(data):
    """Tach cac event file_done tu payload ctrl da giai ma
    -> [{"fileId", "url"}]. Event thieu fileId, thieu url, hoac
    sai dinh dang thi bo qua — kenh ctrl con nhieu loai event
    khac, khong duoc do vi mot event la.

    Bang chung bundle (compact-app-pc, _processCtrlMessages):
    `case "file_done"` -> `_processFileAsyncDoneEvent(e)`: moi
    event co fileId + data.url (data la CHUOI JSON hoac dict) ->
    `handleEventFromCtrl({fileId, url}, "FILE")`.

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
        if content.get("act_type") != CTRL_FILE_ACT:
            continue
        file_id = content.get("fileId")
        if not file_id:
            continue
        urls = _event_data(content.get("data"))
        if not urls:
            continue
        url = _url(urls.get("url"))
        if not url:
            continue
        out.append({"fileId": str(file_id), "url": url})
    return out


def extract_group_events(data):
    """Tach cac event nhom tu payload ctrl da giai ma
    -> [{"threadId", "group_id", "type", "act", "data"}].

    Bang chung bundle (compact-app-pc, _processCtrlMessages):
    controls co content.act_type == "group" duoc gom ve
    `_processGroupCtrlEvents_old` — moi item co data la dict
    (hoac chuoi JSON) voi groupId + act (vd "group_type") +
    time + sourceId. act/groupId co the nam trong data hoac
    o muc content — ham nay doc ca hai cho. Event thieu
    groupId hoac thieu act thi bo qua; trung trong mot batch
    thi chi lay mot.
    """
    out = []
    seen = set()
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
        if content.get("act_type") != "group":
            continue
        parsed = _event_data(content.get("data"))
        group_id = ""
        act = ""
        if isinstance(parsed, dict):
            group_id = (parsed.get("groupId")
                        or parsed.get("group_id")
                        or parsed.get("idTo") or "")
            act = parsed.get("act") or parsed.get("type") or ""
        if not group_id:
            group_id = (content.get("groupId")
                        or content.get("group_id")
                        or content.get("idTo") or "")
        if not act:
            act = content.get("act") or content.get("type") or ""
        if not group_id or not act:
            continue
        detail = parsed if isinstance(parsed, dict) else content
        try:
            detail_key = json.dumps(detail, ensure_ascii=False,
                                    sort_keys=True, default=str)
        except (TypeError, ValueError):
            detail_key = str(detail)
        key = (str(group_id), str(act), detail_key)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "threadId": str(group_id),
            "group_id": str(group_id),
            "type": str(act),
            "act": str(act),
            "data": detail,
        })
    return out


def _reaction_icon(entry):
    """Icon cua mot reaction: rIcon (chuoi) hoac icon; dang khac
    -> None."""
    if not isinstance(entry, dict):
        return None
    for field in ("rIcon", "icon"):
        value = entry.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _reaction_thread(item):
    """Thread cua mot reaction: idTo, tru "0" (exe chuan hoa
    "0"==idTo thanh uidFrom — phia nhan, uidFrom la doi phuong
    1-1)."""
    if not isinstance(item, dict):
        return ""
    thread = str(item.get("idTo") or "")
    if thread in ("", "0"):
        thread = str(item.get("uidFrom") or "")
    if not thread:
        thread = str(item.get("threadId")
                     or item.get("groupId") or "")
    return thread


def extract_reactions(data):
    """Tach cac reaction tu payload ctrl da giai ma
    -> [{"threadId", "msgId", "uidFrom", "icon", "type"}].

    Bang chung bundle (compact-app-pc, _processCtrlMessages):
    payload ctrl co key "reactions" / "reacts" / "reactGroups";
    moi muc co idTo, msgId, cliMsgId, content (chuoi JSON voi
    danh sach rMsg), uidFrom; muc rMsg co rMsgId, rIcon (chuoi),
    rType (so). Ham chuan hoa cua exe (processReactionMessages)
    tra ve {idTo, lastReceiveReactId, rClientMsgId, rMsgId,
    reactions}. Exe cung chuan hoa "0"==idTo thanh uidFrom.

    Ham nay chap nhan ca dang muc phang (msgId/rMsgId + rIcon
    o muc goc) lan dang long nhau (content.rMsg, reactions) va
    bo qua muc thieu thread/msg — khong doan truong. Icon co the
    rong (vd event go reaction, chua co bang chung hinh dang
    cu the) — van dispatch khi du thread/msg/nguoi tha.
    Trung trong mot batch thi chi lay mot. "type" la loai thread
    (0 = 1-1, 1 = nhom) theo ten key — "reactGroups" la nhom,
    "reactions"/"reacts" la 1-1; thread_id moi la can cu dinh
    tuyen chinh xac.
    """
    out = []
    seen = set()
    if not isinstance(data, dict):
        return out
    for key in ("reactions", "reacts", "reactGroups"):
        items = data.get(key)
        if not isinstance(items, list):
            continue
        thread_kind = 1 if key == "reactGroups" else 0
        for item in items:
            if not isinstance(item, dict):
                continue
            thread = _reaction_thread(item)
            if not thread:
                continue
            nested = _event_data(item.get("content"))
            entries = []
            if isinstance(nested, dict) \
                    and isinstance(nested.get("rMsg"), list):
                entries = [e for e in nested["rMsg"]
                           if isinstance(e, dict)]
            elif isinstance(item.get("reactions"), list):
                entries = [e for e in item["reactions"]
                           if isinstance(e, dict)]
            if entries:
                for entry in entries:
                    msg_id = (entry.get("rMsgId")
                              or entry.get("msgId")
                              or item.get("msgId") or "")
                    sender = (entry.get("uidFrom")
                              or item.get("uidFrom") or "")
                    icon = _reaction_icon(entry) \
                        or _reaction_icon(item)
                    if not msg_id or not sender:
                        continue
                    dedup = (thread, str(msg_id), str(sender),
                             icon or "")
                    if dedup in seen:
                        continue
                    seen.add(dedup)
                    out.append({"threadId": thread,
                                "msgId": str(msg_id),
                                "uidFrom": str(sender),
                                "icon": icon or "",
                                "type": thread_kind})
                continue
            msg_id = item.get("rMsgId") or item.get("msgId") or ""
            sender = item.get("uidFrom") or ""
            icon = _reaction_icon(item)
            if not msg_id or not sender:
                continue
            dedup = (thread, str(msg_id), str(sender), icon or "")
            if dedup in seen:
                continue
            seen.add(dedup)
            out.append({"threadId": thread,
                        "msgId": str(msg_id),
                        "uidFrom": str(sender),
                        "icon": icon or "",
                        "type": thread_kind})
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


class FileAsyncRegistry:
    """Kho ket qua event async file theo fileId — BAN SAO cua
    VoiceAsyncRegistry cho dang event file_done (xem
    extract_file_async): deliver() luu {"url"}, wait() tra ngay
    neu da co (cache-hit cua bundle: getFileIdData), khong thi
    cho toi timeout roi tra None. feeder_running: True khi
    CtrlPoller dang chay va nap registry. Chi luu URL (khong luu
    noi dung file, khong log URL)."""

    def __init__(self, max_entries=200):
        self._lock = threading.Lock()
        self._results = {}  # fileId -> {"url"}
        self._events = {}   # fileId -> threading.Event
        self.feeder_running = False
        self._max = max(1, int(max_entries or 200))

    def deliver(self, file_id, url=None):
        """Ghi nhan event cho fileId; tra True neu co URL hop le
        (False thi bo qua — khong danh thuc waiter)."""
        url = _url(url)
        if not url:
            return False
        fid = str(file_id)
        with self._lock:
            self._results[fid] = {"url": url}
            event = self._events.get(fid)
            if event is None:
                event = self._events[fid] = threading.Event()
            while len(self._results) > self._max:
                oldest = next(iter(self._results))
                self._results.pop(oldest, None)
                self._events.pop(oldest, None)
            event.set()
        return True

    def wait(self, file_id, timeout_s=120.0):
        """Doi event cho fileId toi da timeout_s giay. Tra dict
        {"url"} neu co, None neu het gio. Tra NGAY neu event da
        den truoc."""
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
    giao cho VoiceAsyncRegistry va file_done giao cho
    FileAsyncRegistry (None thi bo qua event file — send_file loi
    ro thay vi doi mai).

    http_get(url, timeout) -> (status, json) — giong transport
    cua Chat/Signaling (mang cookie zpw_sek). Loi mang -> backoff
    roi poll lai; KickOut (-69) -> dung han (giong SyncPoller)."""

    def __init__(self, http_get, poll_urls, zpw_enk, own_id,
                 registry, ctl_timeout=30, cursor=None,
                 on_cursor=None, on_group_event=None,
                 on_reaction=None, file_registry=None):
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
        # Registry file (co the None): nap khi event file_done ve;
        # feeder_running cua no duoc bat/tat cung poller nhu voice.
        self.file_registry = file_registry
        try:
            self.ctl_timeout = int(ctl_timeout or 30)
        except (TypeError, ValueError):
            self.ctl_timeout = 30
        if self.ctl_timeout <= 0:
            self.ctl_timeout = 30
        # Con tro khoi tao tu dia (SyncCursorStore) — nhu
        # SyncPoller; rieng kenh ctrl, luu qua on_cursor.
        if isinstance(cursor, PollCursor):
            self.cursor = cursor
        elif isinstance(cursor, dict):
            self.cursor = PollCursor.from_dict(cursor)
        else:
            self.cursor = PollCursor()
        self.on_cursor = on_cursor
        # on_group_event(event) / on_reaction(event): goi cho moi
        # event nhom / reaction tach duoc (xem extract_*); loi o
        # callback khong lam chet poller.
        self.on_group_event = on_group_event
        self.on_reaction = on_reaction
        # Chan doan batch vua xu ly (khong log noi dung).
        self.last_batch = {"group_events": 0, "reactions": 0,
                           "at": 0}
        self._idx = 0
        self._stop = threading.Event()
        self._thread = None
        self.kicked_out = False
        self.last_error = ""
        self.polls = 0  # dem so lan poll (chan doan, khong log nd)
        # Nhu SyncPoller (loi live 08/11): dem loi lien tiep,
        # auth_failed khi 401/403, stopped_reason khi run() tu
        # dung sau loi keo dai.
        self.consec_errors = 0
        self.auth_failed = False
        self.stopped_reason = ""

    def _poll_url(self):
        base = self.urls[self._idx % len(self.urls)].rstrip("/")
        qs = urllib.parse.urlencode(protocol.common_params())
        return "%s/?%s&params=%s&ts=%d" % (
            base, qs, self.cursor.param(), int(time.time()))

    def poll_once(self):
        """Mot lan long-poll ctrl. Tra ve "ok" | "empty" |
        "rotated". Timeout cuc bo -> xoay endpoint, tra "rotated".
        Loi HTTP / loi giai ma -> RuntimeError (caller backoff).
        Server bao dung -> KickOut.

        Phan loai loi giong SyncPoller.poll_once (loi live 08/11):
        NonJsonResponse rong -> "empty" (khong dem loi); co body
        -> RuntimeError ro co status + preview; 401/403 -> "phien
        het han" + auth_failed=True. Moi loi RuntimeError ghi
        last_error + dem consec_errors; run() tu dung poller
        khi dem dat MAX_CONSEC_ERRORS."""
        try:
            result = self._poll_once()
        except KickOut:
            raise
        except RuntimeError as e:
            self.last_error = str(e)
            self.consec_errors += 1
            raise
        except Exception as e:  # noqa: BLE001 - mang loi -> backoff
            self.last_error = ("ctrl_poll: poll loi mang: %s"
                               % type(e).__name__)
            self.consec_errors += 1
            raise RuntimeError(self.last_error)
        # Poll thanh cong: xoa co auth_failed cua mot lan 401
        # thoang qua (xem SyncPoller.poll_once).
        self.auth_failed = False
        return result

    def _poll_once(self):
        """Than poll_once — xem SyncPoller._poll_once."""
        url = self._poll_url()
        try:
            status, payload = self.http_get(
                url, timeout=self.ctl_timeout + 5)
        except TimeoutError:
            self._idx = (self._idx + 1) % len(self.urls)
            self.consec_errors = 0
            self.last_error = ""
            return "rotated"
        except NonJsonResponse as e:
            if e.empty:
                self.consec_errors = 0
                self.last_error = ""
                return "empty"
            self._idx = (self._idx + 1) % len(self.urls)
            raise RuntimeError(
                "ctrl_poll: poll tra ve khong phai JSON "
                "(status=%s, body='%s')" % (e.status, e.preview))
        self.polls += 1
        if status in (401, 403):
            self.auth_failed = True
            raise RuntimeError(
                "ctrl_poll: poll: phien het han (HTTP %s) "
                "- quet QR lai" % status)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError("ctrl_poll: network status=%s" % status)
        if payload.get("data") == "":
            self.consec_errors = 0
            self.last_error = ""
            return "empty"
        code = payload.get("error_code")
        if code == ERR_STOP_RETRY:
            self.kicked_out = True
            raise KickOut("ctrl_poll: server tra -69, dung retry")
        if code not in (0, None):
            raise RuntimeError("ctrl_poll: error_code=%s" % code)
        data = decode_postlogin_data(payload, self.zpw_enk)
        if data is None:
            self.consec_errors = 0
            self.last_error = ""
            return "empty"
        for event in extract_voice_async(data):
            self.registry.deliver(event["fileId"], event["amr"],
                                  event["aac"])
        if self.file_registry is not None:
            for event in extract_file_async(data):
                self.file_registry.deliver(event["fileId"],
                                           event["url"])
        group_events = extract_group_events(data)
        reactions = extract_reactions(data)
        before = self.cursor.to_dict()
        self.cursor.update_from(data)
        for event in group_events:
            if self.on_group_event is not None:
                try:
                    self.on_group_event(event)
                except Exception:  # noqa: BLE001 - callback loi
                    pass
        for event in reactions:
            if self.on_reaction is not None:
                try:
                    self.on_reaction(event)
                except Exception:  # noqa: BLE001 - callback loi
                    pass
        self.last_batch = {"group_events": len(group_events),
                           "reactions": len(reactions),
                           "at": time.time()}
        if self.on_cursor is not None \
                and self.cursor.to_dict() != before:
            try:
                self.on_cursor(self.cursor)
            except Exception:  # noqa: BLE001 - luu con tro loi
                pass
        self.consec_errors = 0
        self.last_error = ""
        return "ok"

    def run(self):
        """Vong poll lien tuc cho toi stop() — giong SyncPoller.run
        (backoff 3s, nhan doi, tran 60s; san 1 giay moi vong).
        Loi keo dai (consec_errors >= MAX_CONSEC_ERRORS): tu
        dung de AppState mo lai (xem SyncPoller.run)."""
        backoff = RETRY_BASE_SECONDS
        try:
            while not self._stop.is_set():
                started = time.time()
                try:
                    result = self.poll_once()
                    backoff = RETRY_BASE_SECONDS
                except KickOut:
                    return
                except Exception as e:  # noqa: BLE001
                    self.last_error = str(e)
                    if not sys.is_finalizing():
                        print("[ctrl-poll] %s; retry sau %.0fs"
                              % (self.last_error, backoff), flush=True)
                    if self.consec_errors >= MAX_CONSEC_ERRORS:
                        self.stopped_reason = "persistent_errors"
                        if not sys.is_finalizing():
                            print("[ctrl-poll] dung poller sau %d "
                                  "loi lien tiep: %s; se tu mo lai "
                                  "qua vong retry"
                                  % (self.consec_errors,
                                     self.last_error), flush=True)
                        return
                    if self._stop.wait(backoff):
                        return
                    backoff = min(backoff * 2, RETRY_MAX_SECONDS)
                    continue
                elapsed = time.time() - started
                if result != "ok" and elapsed < 1.0 \
                        and self._stop.wait(1.0 - elapsed):
                    return
        finally:
            self.registry.feeder_running = False
            if self.file_registry is not None:
                self.file_registry.feeder_running = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self.registry.feeder_running = True
        if self.file_registry is not None:
            self.file_registry.feeder_running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        return True

    def is_alive(self):
        """True khi poller dang chay (thread song + chua bi da).
        Dung de server.py quyet dinh co can mo lai kenh ctrl
        khong khi sync van chay (KickOut -69 chi dung ctrl;
        run() thoat thi _thread chet, is_alive False)."""
        if self.kicked_out:
            return False
        thread = self._thread
        return thread is not None and thread.is_alive()

    def stop(self):
        self.registry.feeder_running = False
        if self.file_registry is not None:
            self.file_registry.feeder_running = False
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2)
