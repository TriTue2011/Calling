"""Nut "Ket thuc" cuoc goi bam khong duoc (2026-11-05 18:06, chay
that): ban 4f40c7e dang chay; cuoc goi 1-1 do chuong toi 00:52 (tu
18:05); bam nut "Ket thuc" KHONG co tac dung — cuoc goi ket o trang
thai dang do chuong, pill topbar van hien, dong ho van chay. Den
18:09 lich su moi ghi "Da ket thuc" — nut khong han hong hoan toan
ma CHAM/tre (bam nhieu lan moi an, hoac UI cap nhat cham sau lan
poll sau, hoac request endcall cham).

Hai cho gay, deu co bang chung code (xem §7m bao-cao.md):

(A) Server — /api/call/end goi sig.endcall() TRUOC, chi goi
record_end() khi endcall thanh cong. Neu request endcall toi Zalo
loi (hoac cham), handler tra 502 va cuoc goi VAN O "sent" trong
log → UI poll /api/calls thay no van active mai. UI lai bo qua
loi tra ve (endCall khong kiem r.error), nen nguoi dung thay nhu
bam khong duoc.

(B) UI — endCall() chi lay muc tieu tu currentCall || detailCall,
la bien cua phien trang. Sau khi load lai trang, ca hai deu null
→ nut Ket thuc o rail KHONG GUI request nao ca (no-op), du server
van giu cuoc goi active. Ngoai ra call_id tu detail view la CHUOI
(record luu str(call_id)) — gui dang chuoi thi server that co the
tra 114 nhu requestcall (§7k), va UI khong co phan hoi ngay trong
luc POST dang bay (dong ho van chay, pill van hien).

Cac test nay PHAI FAIL o code cu va PASS o code moi:
- end khi Zalo tu choi endcall -> van ket thuc cuc bo (A);
- end voi call_id dang chuoi -> server chuan hoa ve so (B);
- end voi id sai/khong co -> ket thuc cuoc dang live (B);
- end cham (Zalo tra loi sau 2 giay) -> log da xoa active truoc
  khi POST tra ve (A, "cham" khong duoc hien nhu "hong");
- end nhom -> di dung group/endcall (12438) thay vi 11306.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from mock_server import MockZalo  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402
from zalo_pc_app import server as app_server  # noqa: E402

# Id rieng cho file nay (chi khac nhau de de doc): server cap
# callId tu counter noi bo (bat dau 1, deep comparison §5.1) va bo
# qua gia tri UI gui len, nen test nao can id that deu lay tu
# response cua /api/call/request (xem _start_call) thay vi dung
# lai hang nay.
CID_SLOW = 1762346001
CID_OK = 1762346002
CID_TWICE = 1762346003
CID_FAIL = 1762346004
CID_STRING = 1762346005
CID_WRONG = 1762346006
CID_GROUP = 1762346007


def _start_app(mock):
    tmp = tempfile.mkdtemp(prefix="zalo-pc-qr-end-")
    os.environ["ZALO_PC_DATA_DIR"] = tmp
    os.environ["ZALO_PC_PORT"] = "0"
    protocol.AUTH_DOMAIN = mock.base
    protocol.VOICECALL_DOMAIN = mock.base
    protocol.PROFILE_DOMAIN = mock.base
    protocol.GROUP_DOMAIN = mock.base
    app_server.PARAM_CIPHER_KEY = "TEST_PARAM_KEY_32_CHARS_LONG_XXX"
    state = app_server.AppState(tmp)
    app_server.STATE = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % port


def _api(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _login(base):
    status, body = _api(base, "POST", "/api/qr/new", {})
    assert body["ok"] is True, body
    deadline = time.time() + 20
    last = {}
    while time.time() < deadline:
        status, last = _api(base, "GET", "/api/qr/status")
        if last["state"] == "done":
            break
        time.sleep(0.5)
    assert last["state"] == "done", last


def _start_call(base, call_id, call_type="user"):
    body = {"callee_id": "20001" if call_type == "user" else "30001",
            "call_id": call_id, "type": call_type}
    if call_type == "group":
        body["partners"] = ["20001", "20002"]
    status, resp = _api(base, "POST", "/api/call/request", body)
    assert resp["ok"] is True, resp
    # Server cap callId tu counter noi bo (bat dau 1, deep comparison
    # §5.1) va bo qua gia tri UI gui len: tra ve id hieu luc de test
    # dung chinh id do cho /api/call/end (nhu UI that lam).
    return resp["call_id"]


def _calls(base):
    status, body = _api(base, "GET", "/api/calls")
    assert status == 200, body
    return body


def _shutdown(httpd, mock):
    # Dung poller sync TRUOC khi tat mock: poller la daemon thread,
    # de no chay tiep sau khi mock tat thi no in loi lien tuc va co
    # the va cham voi stdout luc interpreter tat (abort 134 khong
    # on dinh o cuoi file — 8/8 test pass nhung tien trinh chet luc
    # shutdown). Dung khi mock con song thi poller thoat sach
    # trong ~1 giay (xem them guard sys.is_finalizing() o
    # sync_poll.run).
    try:
        app_server.STATE.stop_sync()
    except Exception:  # noqa: BLE001 - teardown best-effort
        pass
    try:
        httpd.shutdown()
    finally:
        try:
            httpd.server_close()
        except Exception:  # noqa: BLE001
            pass
        mock.stop()


def test_end_clears_log_before_slow_zalo_reply():
    """Tin hieu ket thuc Zalo cham (cancel, mock ngu 2 giay): log
    phai xoa active TRUOC KHI POST /api/call/end tra ve — neu
    khong, UI thay cuoc goi van do chuong trong suot thoi gian cho
    va tuong nut hong (trieu chung 18:06: bam Ket thuc, khong co gi
    thay doi)."""
    mock = MockZalo()
    mock.cancel_mode = "slow"
    mock = mock.start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        eff_id = _start_call(base, CID_SLOW)
        assert _calls(base)["active"] is not None
        result = {}

        def _end():
            result["resp"] = _api(base, "POST", "/api/call/end",
                                  {"uid_to": "20001",
                                   "call_id": eff_id})

        t = threading.Thread(target=_end, daemon=True)
        t.start()
        cleared = False
        deadline = time.time() + 1.5
        while time.time() < deadline:
            if _calls(base)["active"] is None:
                cleared = True
                break
            time.sleep(0.2)
        t.join(timeout=10)
        assert cleared, "active van hien trong luc cancel dang bay"
        status, resp = result["resp"]
        assert resp["ok"] is True, resp
        assert _calls(base)["active"] is None
        httpd.shutdown()
    finally:
        _shutdown(httpd, mock) if httpd else mock.stop()


def test_end_ok_clears_active():
    """Duong hanh phuc: goi roi ket thuc -> het active, lich su
    ghi ended, response tra ended_call_id."""
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        eff_id = _start_call(base, CID_OK)
        status, resp = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id})
        assert resp["ok"] is True, resp
        assert resp["ended_call_id"] == eff_id, resp
        calls = _calls(base)
        assert calls["active"] is None, calls
        by_id = {c["call_id"]: c for c in calls["calls"]}
        assert by_id[str(eff_id)]["status"] == "ended", calls
        httpd.shutdown()
    finally:
        _shutdown(httpd, mock) if httpd else mock.stop()


def test_end_twice_is_safe():
    """Bam Ket thuc 2 lan lien tiep: ca hai deu ok, log van ended,
    khong active tro lai."""
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        eff_id = _start_call(base, CID_TWICE)
        for _ in range(2):
            status, resp = _api(base, "POST", "/api/call/end",
                                {"uid_to": "20001", "call_id": eff_id})
            assert resp["ok"] is True, resp
        calls = _calls(base)
        assert calls["active"] is None, calls
        by_id = {c["call_id"]: c for c in calls["calls"]}
        assert by_id[str(eff_id)]["status"] == "ended", calls
        httpd.shutdown()
    finally:
        _shutdown(httpd, mock) if httpd else mock.stop()


def test_end_when_zalo_cancel_fails_still_ends_locally():
    """Zalo tu choi cancel (mock inner 500): cuoc goi VAN phai
    ket thuc cuc bo — response ok, het active, lich su ended, va
    loi Zalo duoc ghi vao detail cua entry (de chan doan). Code cu
    tra 502 va de cuoc ket o "sent" mai — dung trieu chung that."""
    mock = MockZalo()
    mock.cancel_mode = "error"
    mock = mock.start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        eff_id = _start_call(base, CID_FAIL)
        status, resp = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": eff_id})
        assert resp["ok"] is True, resp
        assert resp["zalo_endcall_ok"] is False, resp
        assert resp["zalo_error"], resp
        calls = _calls(base)
        assert calls["active"] is None, calls
        by_id = {c["call_id"]: c for c in calls["calls"]}
        entry = by_id[str(eff_id)]
        assert entry["status"] == "ended", calls
        assert "mock cancel rejected" in entry["detail"], entry
        httpd.shutdown()
    finally:
        _shutdown(httpd, mock) if httpd else mock.stop()


def test_end_with_string_call_id():
    """call_id dang CHUOI (man hinh chi tiet build tu log record,
    noi call_id duoc luu dang str): server phai chuan hoa ve so
    uint32 truoc khi gui tin hieu ket thuc (cancel) — gui dang
    chuoi thi server that co the tra 114 nhu requestcall (§7k)."""
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        eff_id = _start_call(base, CID_STRING)
        status, resp = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001",
                             "call_id": str(eff_id)})
        assert resp["ok"] is True, resp
        # Mock echo lai body da gui di: callId phai la JSON number.
        assert resp["data"]["body"]["callId"] == eff_id, resp
        assert isinstance(resp["data"]["body"]["callId"], int), resp
        calls = _calls(base)
        assert calls["active"] is None, calls
        by_id = {c["call_id"]: c for c in calls["calls"]}
        assert by_id[str(eff_id)]["status"] == "ended", calls
        httpd.shutdown()
    finally:
        _shutdown(httpd, mock) if httpd else mock.stop()


def test_end_wrong_id_falls_back_to_active():
    """End voi call_id sai/khong khop trong khi co mot cuoc dang
    live: ket thuc cuoc live do (y dinh cua nut Ket thuc la khong
    mo ho — chi co toi da mot cuoc live)."""
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        eff_id = _start_call(base, CID_WRONG)
        status, resp = _api(base, "POST", "/api/call/end",
                            {"uid_to": "20001", "call_id": 999999})
        assert resp["ok"] is True, resp
        assert resp["ended_call_id"] == eff_id, resp
        calls = _calls(base)
        assert calls["active"] is None, calls
        by_id = {c["call_id"]: c for c in calls["calls"]}
        assert by_id[str(eff_id)]["status"] == "ended", calls
        httpd.shutdown()
    finally:
        _shutdown(httpd, mock) if httpd else mock.stop()


def test_group_end_routes_to_group_endcall():
    """Ket thuc cuoc goi NHOM phai di group/endcall (12438) dung
    dang bundle, khong phai endcall 1-1 (11306) voi groupId lam
    uidTo."""
    mock = MockZalo().start()
    httpd = None
    try:
        httpd, base = _start_app(mock)
        _login(base)
        eff_id = _start_call(base, CID_GROUP, call_type="group")
        status, resp = _api(base, "POST", "/api/call/end",
                            {"uid_to": "30001", "call_id": eff_id,
                             "type": "group"})
        assert resp["ok"] is True, resp
        assert resp["ended_call_id"] == eff_id, resp
        paths = [p for p, _, _ in mock.seen]
        assert "/api/voicecall/group/endcall" in paths, paths
        calls = _calls(base)
        assert calls["active"] is None, calls
        by_id = {c["call_id"]: c for c in calls["calls"]}
        assert by_id[str(eff_id)]["status"] == "ended", calls
        httpd.shutdown()
    finally:
        _shutdown(httpd, mock) if httpd else mock.stop()


def test_vc_endcall_group_body_matches_bundle():
    """Body 12438 dung nhu lop wZ gui (static sendEndCallGroup):
    {calleeId, callId, callType, hostCall, data, partners} —
    khong co imei, khong co uidTo. hostCall: nguoi goi la host
    cua cuoc goi di (UNCONFIRMED — bundle chi cho ten field,
    khong cho ngu nghia gia tri)."""
    body = protocol.vc_endcall_group("30001", CID_GROUP, 5, True, None,
                                     ["20001", "20002"])
    assert body == {"calleeId": "30001", "callId": CID_GROUP,
                    "callType": 5, "hostCall": True, "data": None,
                    "partners": ["20001", "20002"]}, body
    assert "imei" not in body and "uidTo" not in body, body


if __name__ == "__main__":
    failed = []
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed.append(fn.__name__)
            print("FAIL", fn.__name__, exc)
    print("%d/%d tests passed" % (len(tests) - len(failed), len(tests)))
    raise SystemExit(1 if failed else 0)
