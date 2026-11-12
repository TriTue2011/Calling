"""Dong bo lich su tu dien thoai (history_sync): mat ma, khung ZDB4.0, may trang thai, tai ve.

Tep ZDB gia duoc DUNG bang openssl CLI, ma hoa AES-256-CBC tung khoi 64 KB DOC LAP (IV 0) nhu dien thoai — doc lap voi cach giai ma cua app
(app dung ECB toan bo + XOR) nen lech thi test do. Mock/offline hoan toan: khong goi Zalo that.
Run: python3 tests/test_history_sync.py
"""

import base64
import json
import lzma
import os
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from zalo_pc_app import history_sync as hs  # noqa: E402

CHUNK = 0x10000


def sh(args, data=None):
    p = subprocess.run(["openssl"] + args, input=data, capture_output=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def make_db(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE msgs (id INTEGER PRIMARY KEY, sender TEXT, body TEXT, ts INTEGER)")
    con.execute("CREATE TABLE meta (k TEXT, v TEXT)")
    for i in range(rows):
        con.execute("INSERT INTO msgs (sender, body, ts) VALUES (?,?,?)", ("u%d" % (i % 3), "tin so %d " % i + os.urandom(40).hex(), 1700000000 + i))
    con.commit()
    con.close()


def build_zdb(files, aes_key, prefix=b""):
    """files: [(name, bytes)] -> ban ma hoa ZDB4.0 giong dien thoai."""
    header = b"ZDB4.0" + bytes(8) + struct.pack(">I", len(files))   # magic(6) + 8 byte + count o byte 14
    for name, data in files:
        nb = name.encode()
        header += struct.pack(">I", len(nb)) + nb + struct.pack(">I", len(data))
    xz = lzma.compress(b"".join(d for _, d in files))
    plain = header + xz
    plain += bytes((-len(plain)) % 16)
    out = bytearray(prefix)
    for off in range(0, len(plain), CHUNK):
        out += sh(["enc", "-aes-256-cbc", "-K", aes_key.hex(), "-iv", "00" * 16, "-nopad"], plain[off:off + CHUNK])
    return bytes(out)


def new_key(tmp):
    kp = os.path.join(tmp, "key.pem")
    pub_b64 = hs.generate_keypair(kp)
    assert base64.b64decode(pub_b64)[:2] == b"\x30\x82"          # SPKI DER (SEQUENCE)
    assert oct(os.stat(kp).st_mode & 0o777) == "0o600", oct(os.stat(kp).st_mode)
    return kp


def wrap_key(kp, raw):
    pub_pem = sh(["rsa", "-in", kp, "-pubout"])
    pf = os.path.join(os.path.dirname(kp), "pub.pem")
    open(pf, "wb").write(pub_pem)
    return base64.b64encode(sh(["pkeyutl", "-encrypt", "-pubin", "-inkey", pf, "-pkeyopt", "rsa_padding_mode:pkcs1"], raw)).decode()


def test_rsa_and_zdb_roundtrip_multi_chunk():
    tmp = tempfile.mkdtemp(prefix="hs-")
    kp = new_key(tmp)
    raw = os.urandom(16)
    assert hs.rsa_decrypt_pkcs1(kp, base64.b64decode(wrap_key(kp, raw))) == raw
    key = hs.derive_zdb_aes_key(raw)
    assert key == raw.hex().upper().encode() and len(key) == 32
    d1, d2 = os.path.join(tmp, "a.db"), os.path.join(tmp, "g.db")
    make_db(d1, 1500)
    make_db(d2, 300)
    files = [("123456.db", open(d1, "rb").read()), ("group_789.db", open(d2, "rb").read())]
    assert sum(len(d) for _, d in files) > 3 * CHUNK                       # chac chan nhieu khoi
    for prefix in (b"", b"\x01\x02\x03\x04"):                              # lech dau 0 va 4 (zca-js thu ca hai)
        enc = build_zdb(files, key, prefix)
        out = hs.unpack_zdb(hs.decrypt_zdb(enc, key), os.path.join(tmp, "out%d" % len(prefix)))
        assert [f["name"] for f in out] == ["123456.db", "group_789.db"], out
        for f, (_, data) in zip(out, files):
            assert open(f["path"], "rb").read() == data, f["name"]
        schema = hs.inspect_sqlite(out[0]["path"])
        assert schema["msgs"]["columns"] == ["id", "sender", "body", "ts"] and schema["msgs"]["rows"] == 1500 and schema["meta"]["rows"] == 0, schema


def test_wrong_key_and_unsafe_inputs():
    tmp = tempfile.mkdtemp(prefix="hs-")
    key = hs.derive_zdb_aes_key(os.urandom(16))
    enc = build_zdb([("1.db", b"x" * 100)], key)
    for bad in (hs.derive_zdb_aes_key(os.urandom(16)),):
        try:
            hs.decrypt_zdb(enc, bad)
            raise AssertionError("sai khoa phai that bai")
        except hs.SyncError as e:
            assert "ZDB4.0" in str(e), e
    kp = new_key(tmp)
    try:
        hs.rsa_decrypt_pkcs1(kp, os.urandom(256))
        raise AssertionError("encrypted_key rac phai that bai")
    except hs.SyncError:
        pass
    try:
        hs.rsa_decrypt_pkcs1(kp, b"short")
        raise AssertionError("sai do dai phai that bai")
    except hs.SyncError as e:
        assert "do dai" in str(e), e
    # ten co duong dan -> chi lay ten tep, ghi TRONG thu muc dich (khong thoat ra ngoai)
    out_dir = os.path.join(tmp, "o")
    res = hs.unpack_zdb(hs.decrypt_zdb(build_zdb([("../x.db", b"x")], key), key), out_dir)
    assert res[0]["name"] == "x.db" and os.path.dirname(os.path.abspath(res[0]["path"])) == os.path.abspath(out_dir), res
    assert not os.path.exists(os.path.join(tmp, "x.db")), "tep khong duoc thoat khoi thu muc dich"
    for evil_name in ("..", "a b.db", "x;rm.db"):
        try:
            hs.unpack_zdb(hs.decrypt_zdb(build_zdb([(evil_name, b"x")], key), key), os.path.join(tmp, "o2"))
            raise AssertionError("ten khong an toan phai bi tu choi: %r" % evil_name)
        except hs.SyncError as e:
            assert "khong an toan" in str(e), e
    for url in ("file:///etc/passwd", "http://127.0.0.1/x", "http://169.254.169.254/x", "https://localhost/x", "http://10.0.0.5/x", "ftp://a/b"):
        try:
            hs.check_download_url(url)
            raise AssertionError("phai chan " + url)
        except hs.SyncError:
            pass
    hs.check_download_url("https://transfersync.zaloapp.com/api/x")


def test_extract_sync_events_and_scalars():
    payload = {"controls": [
        {"content": {"act_type": "syncmsgmb", "act": "syncmsg_info", "data": json.dumps({"url": "https://x/y", "encrypted_key": "SECRET", "file_size": 5})}},
        {"content": {"act_type": "transfer_msg", "act": "user_confirm", "data": {"status": 1}}},
        {"content": {"act_type": "group", "act": "x", "data": "{}"}},
        {"content": {"act_type": "syncmsgmb", "act": "transfer_error", "data": "khong-phai-json"}}]}
    ev = hs.extract_sync_events(payload)
    assert [e["act"] for e in ev] == ["syncmsg_info", "user_confirm", "transfer_error"], ev
    assert ev[0]["data"]["file_size"] == 5 and ev[2]["data"] == {}, ev
    sc = hs._scalars({"url": "u", "encrypted_key": "k", "n": 3, "ok": True, "nested": {"a": 1}, "long": "x" * 200, "s": "abc"})
    assert sc == {"n": 3, "ok": True, "s": "abc"}, sc


class _Handler(BaseHTTPRequestHandler):
    blob = b""
    need_cookie = False
    need_browser = False
    always_400 = False

    def do_GET(self):
        if self.always_400 or (self.need_browser and "Mozilla" not in (self.headers.get("User-Agent") or "")):
            body = b'{"error_code":400,"error_message":"Bad request"}'
            self.send_response(400)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.need_cookie and "zpw_sek=SEK" not in (self.headers.get("Cookie") or ""):
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.blob)))
        self.end_headers()
        self.wfile.write(self.blob)

    def log_message(self, *a):
        pass


class FakeServices:
    def __init__(self):
        self.calls = []

    def _get(self, domain, path, body, no_params=False):
        self.calls.append((path, dict(body)))
        return None


def _wait(fn, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.1)
    raise AssertionError("timeout")


def _serve(blob, need_cookie=False, need_browser=False, always_400=False):
    handler = type("H", (_Handler,), {"blob": blob, "need_cookie": need_cookie, "need_browser": need_browser, "always_400": always_400})
    handler.cls = handler
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_state_machine_end_to_end():
    tmp = tempfile.mkdtemp(prefix="hs-")
    svc = FakeServices()
    logs = []
    sync = hs.HistorySync(tmp, lambda: svc, cookie_provider=lambda: "SEK", imei_provider=lambda: "imei-1", allow_local=True, log=logs.append)
    assert sync.status()["stage"] == "idle" and sync.status()["busy"] is False
    # khong co yeu cau nao dang cho: su kien den tu nhien bi bo qua
    sync.on_event({"act": "syncmsg_info", "act_type": "syncmsgmb", "data": {"url": "http://127.0.0.1:1/x", "encrypted_key": "AAAA"}})
    assert sync.status()["stage"] == "idle" and any("bo qua syncmsg_info" in m for m in logs), logs
    sync.start()
    st = sync.status()
    assert st["stage"] == "waiting_phone" and st["busy"] is True, st
    path, body = svc.calls[0]
    assert path == "/api/message/pull_mobile_msg" and body["pc_name"] == hs.PC_NAME and body["imei"] == "imei-1", svc.calls
    assert base64.b64decode(body["public_key"])[:2] == b"\x30\x82" and body["from_seq_id"] == 0 and body["temp_key"] == "", body
    try:
        sync.start()
        raise AssertionError("dang chay thi khong duoc bat dau lai")
    except hs.SyncError as e:
        assert "đang có" in str(e), e
    sync.on_event({"act": "user_confirm", "act_type": "syncmsgmb", "data": {"status": 1}})
    assert "phản hồi" in sync.status()["detail"] and sync.status()["events"][-1]["act"] == "user_confirm"
    # dien thoai tra syncmsg_info: tai (lan dau 403 -> thu kem cookie) -> giai ma
    kp = os.path.join(tmp, "history_sync", "key.pem")
    raw = os.urandom(16)
    key = hs.derive_zdb_aes_key(raw)
    dbp = os.path.join(tmp, "x.db")
    make_db(dbp, 200)
    enc = build_zdb([("555.db", open(dbp, "rb").read())], key)
    srv = _serve(enc, need_cookie=True)
    try:
        info = {"url": "http://127.0.0.1:%d/snap" % srv.server_address[1], "encrypted_key": wrap_key(kp, raw), "file_name": "a.db.crypt",
                "file_size": len(enc), "checksum_code": "abc", "from_seq_id": 0, "is_full_transfer": 1}
        sync.on_event({"act": "syncmsg_info", "act_type": "syncmsgmb", "data": info})
        _wait(lambda: sync.status()["stage"] in ("done", "error"))
    finally:
        srv.shutdown()
    st = sync.status()
    assert st["stage"] == "done", st
    assert st["files"] == [{"name": "555.db", "size": len(open(dbp, "rb").read())}], st["files"]
    assert st["schema"]["555.db"]["msgs"]["rows"] == 200, st["schema"]
    assert os.path.exists(os.path.join(st["run_dir"], "555.db")) and os.path.exists(os.path.join(st["run_dir"], "snapshot.db.crypt"))
    assert svc.calls[-1][0] == "/api/message/delete_snapshot_mobile_msg", svc.calls          # don ban chup tren may chu nhu PC
    blob = json.dumps(st)
    assert "SECRET" not in blob and info["encrypted_key"] not in blob and "127.0.0.1" not in blob, "khong duoc lo khoa/URL trong trang thai"
    assert not any(info["encrypted_key"] in m for m in logs), "khong ghi khoa vao nhat ky"
    assert any("msgs(id,sender,body,ts)=200 dong" in m for m in logs), logs                    # chi cau truc, khong noi dung


def test_error_paths_and_cancel():
    tmp = tempfile.mkdtemp(prefix="hs-")

    class Boom(FakeServices):
        def _get(self, *a, **k):
            raise RuntimeError("svc GET /api/message/pull_mobile_msg: network status=500")
    s1 = hs.HistorySync(tmp, lambda: Boom(), allow_local=True, log=lambda m: None)
    try:
        s1.start()
        raise AssertionError("phai nem loi")
    except RuntimeError:
        pass
    assert s1.status()["stage"] == "error" and "500" in s1.status()["detail"], s1.status()
    # transfer_error tu dien thoai
    svc = FakeServices()
    s2 = hs.HistorySync(tmp, lambda: svc, allow_local=True, log=lambda m: None)
    s2.start()
    s2.on_event({"act": "transfer_error", "act_type": "transfer_msg", "data": {"code": 7}})
    assert s2.status()["stage"] == "error" and "Điện thoại báo lỗi" in s2.status()["detail"], s2.status()
    # syncmsg_info hong (khoa rac): trang thai error ro, khong treo
    s3 = hs.HistorySync(tmp, lambda: svc, allow_local=True, log=lambda m: None)
    s3.start()
    srv = _serve(b"not a zdb file" * 50)
    try:
        s3.on_event({"act": "syncmsg_info", "act_type": "syncmsgmb", "data": {"url": "http://127.0.0.1:%d/x" % srv.server_address[1],
                                                                                "encrypted_key": base64.b64encode(os.urandom(256)).decode()}})
        _wait(lambda: s3.status()["stage"] == "error")
    finally:
        srv.shutdown()
    assert "Không xử lý được" in s3.status()["detail"], s3.status()
    # huy
    s4 = hs.HistorySync(tmp, lambda: svc, allow_local=True, log=lambda m: None)
    s4.start()
    s4.cancel()
    assert s4.status()["stage"] == "cancelled" and svc.calls[-1][0] == "/api/message/cancel_pull_mobile_msg", (s4.status(), svc.calls[-1])
    # treo qua lau
    s4.start()
    s4.state["started_at"] = int(time.time()) - hs.WAIT_PHONE_SECONDS - 5
    assert s4.status().get("stale") is True and "Huỷ" in s4.status()["detail"], s4.status()


def _prepare(tmp, svc, blob_files=None):
    """start() + khoa that + ZDB hop le; tra ve (sync, info_builder, raw)."""
    sync = hs.HistorySync(tmp, lambda: svc, cookie_provider=lambda: "SEK", imei_provider=lambda: "imei-1", allow_local=True, log=lambda m: None)
    sync.start()
    raw = os.urandom(16)
    key = hs.derive_zdb_aes_key(raw)
    dbp = os.path.join(tmp, "x.db")
    make_db(dbp, 50)
    enc = build_zdb([("777.db", open(dbp, "rb").read())], key)
    return sync, enc, wrap_key(os.path.join(tmp, "history_sync", "key.pem"), raw)


def test_browser_style_headers_are_tried_when_plain_get_gets_400():
    tmp = tempfile.mkdtemp(prefix="hs-")
    svc = FakeServices()
    sync, enc, wrapped = _prepare(tmp, svc)
    srv = _serve(enc, need_browser=True)
    try:
        info = {"url": "http://127.0.0.1:%d/snap?key=K&exp=1&sig=S" % srv.server_address[1], "encrypted_key": wrapped, "file_size": len(enc)}
        sync.on_event({"act": "syncmsg_info", "act_type": "syncmsgmb", "data": info})
        _wait(lambda: sync.status()["stage"] in ("done", "error"))
    finally:
        srv.shutdown()
    assert sync.status()["stage"] == "done", sync.status()


def test_failed_download_keeps_event_and_retry_needs_no_new_phone_confirmation():
    tmp = tempfile.mkdtemp(prefix="hs-")
    svc = FakeServices()
    sync, enc, wrapped = _prepare(tmp, svc)
    pulls = lambda: len([c for c in svc.calls if c[0] == "/api/message/pull_mobile_msg"])
    assert pulls() == 1
    srv = _serve(enc, always_400=True)
    info = {"url": "http://127.0.0.1:%d/snap?key=K&sig=SECRETSIG" % srv.server_address[1], "encrypted_key": wrapped, "file_size": len(enc)}
    try:
        sync.on_event({"act": "syncmsg_info", "act_type": "syncmsgmb", "data": info})
        _wait(lambda: sync.status()["stage"] == "error")
        st = sync.status()
        assert "HTTP 400" in st["detail"] and "Bad request" in st["detail"] and st["can_retry"] is True, st          # ma + than phan hoi that, thay vi mu
        assert "SECRETSIG" not in json.dumps(st), "khong lo chu ky URL trong trang thai"
        saved = sync._last_saved()
        assert saved and saved[0]["url"] == info["url"], saved
        assert oct(os.stat(os.path.join(saved[1], "event.json")).st_mode & 0o777) == "0o600"
        assert os.path.exists(os.path.join(saved[1], "key.pem"))
    finally:
        srv.shutdown()
    srv2 = _serve(enc)                                                       # may chu tra loi binh thuong tro lai (cung URL goc vi cong khac -> sua event)
    try:
        saved_info, run_dir = sync._last_saved()
        saved_info["url"] = "http://127.0.0.1:%d/snap" % srv2.server_address[1]
        json.dump(saved_info, open(os.path.join(run_dir, "event.json"), "w"))
        sync.retry()
        _wait(lambda: sync.status()["stage"] in ("done", "error"))
    finally:
        srv2.shutdown()
    assert sync.status()["stage"] == "done" and pulls() == 1, (sync.status(), pulls())          # KHONG gui pull_mobile_msg lan nua
    # tien trinh khoi dong lai (trang thai mat): thu lai van duoc tu dia
    s2 = hs.HistorySync(tmp, lambda: svc, cookie_provider=lambda: "SEK", imei_provider=lambda: "imei-1", allow_local=True, log=lambda m: None)
    srv3 = _serve(enc)
    try:
        saved_info, run_dir = s2._last_saved()
        saved_info["url"] = "http://127.0.0.1:%d/snap" % srv3.server_address[1]
        json.dump(saved_info, open(os.path.join(run_dir, "event.json"), "w"))
        s2.retry()
        _wait(lambda: s2.status()["stage"] in ("done", "error"))
    finally:
        srv3.shutdown()
    assert s2.status()["stage"] == "done", s2.status()
    s3 = hs.HistorySync(tempfile.mkdtemp(prefix="hs-"), lambda: svc, allow_local=True, log=lambda m: None)
    try:
        s3.retry()
        raise AssertionError("chua co du lieu thi khong thu lai duoc")
    except hs.SyncError as e:
        assert "Bắt đầu" in str(e), e


def test_events_are_matched_to_own_request_and_phone_actions_are_understood():
    tmp = tempfile.mkdtemp(prefix="hs-")
    svc = FakeServices()
    logs = []
    sync = hs.HistorySync(tmp, lambda: svc, allow_local=True, log=logs.append)
    sync.start()
    mine = svc.calls[0][1]["public_key"]
    sync.on_event({"act": "user_confirm", "act_type": "syncmsgmb", "data": {"user_action": 0, "pc_name": hs.PC_NAME, "public_key": "KHAC"}})
    assert sync.status()["stage"] == "waiting_phone" and any("yeu cau khac" in m for m in logs), "su kien cua yeu cau khac phai bi bo qua"
    sync.on_event({"act": "user_confirm", "act_type": "syncmsgmb", "data": {"user_action": 3, "pc_name": hs.PC_NAME, "public_key": mine}})
    assert "đồng ý" in sync.status()["detail"] and sync.status()["stage"] == "waiting_phone"
    sync.on_event({"act": "user_confirm", "act_type": "syncmsgmb", "data": {"user_action": 2, "public_key": mine}})
    assert "khôi phục" in sync.status()["detail"]
    sync.on_event({"act": "transfer_error", "act_type": "transfer_msg", "data": {"status": 1, "error_code": 0, "public_key": mine}})
    assert "bận" in sync.status()["detail"] and sync.status()["stage"] == "waiting_phone"
    sync.on_event({"act": "user_confirm", "act_type": "syncmsgmb", "data": {"user_action": 0, "public_key": mine}})
    assert sync.status()["stage"] == "error" and "TỪ CHỐI" in sync.status()["detail"], sync.status()
    s2 = hs.HistorySync(tmp, lambda: svc, allow_local=True, log=lambda m: None)
    s2.start()
    s2.on_event({"act": "transfer_error", "act_type": "transfer_msg", "data": {"error_code": 5, "public_key": svc.calls[-1][1]["public_key"]}})
    assert s2.status()["stage"] == "error" and "mã 5" in s2.status()["detail"], s2.status()


def test_describe_url_hides_values():
    d = hs.describe_url("https://transfersync.zaloapp.com/api/transfer-sync-v2/download?key=ABC&exp=9&sig=SUPERSECRET")
    assert d == "transfersync.zaloapp.com/api/transfer-sync-v2/download ?exp,key,sig" and "SUPERSECRET" not in d, d


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("ALL HISTORY SYNC TESTS PASSED")
