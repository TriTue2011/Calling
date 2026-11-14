"""WebUI ở khổ điện thoại bám Zalo di động, đo bằng Chrome thật (14/11/2026).

Kiểm trên 390 px và 320 px: không tràn ngang; thanh đầu gradient xanh; tab dưới có nhãn; chat soạn tin MỘT hàng (cảm xúc, ô nhập, «…», ảnh, mic cùng hàng; nút
ít dùng gom vào «…»); gõ chữ thì hiện nút gửi và ẩn mic/ảnh; nút ≡ mở trang «Thông tin» phủ toàn màn hình và nút quay lại đóng được; không có ngoại lệ JS.
Tự bỏ qua khi máy không có google-chrome hoặc node >= 22. Chạy: python3 tests/test_phone_layout.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
tmp = tempfile.mkdtemp(prefix="zalo-pc-phone-")
os.environ.update(ZALO_PC_DATA_DIR=tmp, ZALO_PC_PORT="0", ZALO_PC_APP_USER="u", ZALO_PC_APP_PASSWORD="mat-khau-thu-123")
os.environ.pop("ZALO_PC_APP_PASSWORD_HASH", None)
os.environ.pop("ZALO_PC_INGRESS", None)
from zalo_pc_app import server as sv  # noqa: E402

NOW = int(time.time())


def conv(tid, name, text, ago, typ="user", unread=0, out=False, stranger=False):
    return {"thread_type": typ, "thread_id": tid, "name": name, "last_text": text, "last_ts": NOW - ago * 60, "count": 5, "incoming_count": 3,
            "unread": unread, "last_out": out, "last_sender_name": "", "stranger": stranger, "first_ts": NOW - 90000}


THREADS = [conv("2", "Vợ Yêu", "[Cuộc gọi video đi]", 6, out=True), conv("3", "AI học hỏi", "Em vừa tắt ir quạt", 9, "group", 3),
           conv("5", "Dịch vụ Hoàng Thành", "Đã giao 5 bình cho PH1 và còn rất nhiều chữ nữa để thử cắt chữ ở khổ hẹp", 24, "group", 120),
           conv("7", "BenBap", "Chiều nay bố đã về nhà rồi", 180),
           conv("14730638310096377", "Thời Tiết", "Chúc một ngày tốt lành, thời tiết hôm nay nhiều mây rải rác", 660, stranger=True),
           conv("23284958255181415", "Nạp Điện Thoại Nguyễn Văn A", "+20% VinaPhone - Thứ Sáu hàng tuần", 1500, stranger=True)]
MSGS = [{"id": "m1", "sender_id": "7", "direction": "in", "kind": "text", "time": NOW - 600, "text": "Chiều nay bố đã về nhà rồi, anh Trí Anh cũng đã trở về từ sáng. " * 3},
        {"id": "m2", "sender_id": "me", "direction": "out", "kind": "text", "time": NOW - 500, "text": "Ok em"}]
GROUPS = [{"id": "g%d" % i, "label": "Nhóm dịch vụ số %d" % i} for i in range(12)]
CATALOG = {"groups": GROUPS, "services": [{"addon": "svc_%d" % i, "addon_no": i, "action": "svc_%d" % i, "label": "Dịch vụ %d" % i, "group": "g%d" % (i % 12), "status": "supported", "fields": [], "thread": "none"}
                                          for i in range(30)]}
DATA = {"/api/svc/catalog": CATALOG, "/api/status": {"login": True, "uid": "10001", "phonenum": "+84000000000", "version": "t", "sync": "running", "engine": {"attached": True}},
        "/api/contacts": {"friends": {"rows": [{"id": "2", "name": "Vợ Yêu"}, {"id": "7", "name": "BenBap"}]}, "groups": {"rows": []}},
        "/api/conversations": {"threads": THREADS}, "/api/calls": {"calls": [], "active": None}, "/api/inbox/summary": {"threads": []},
        "/api/privacy/status": {"enabled": False, "unlocked": True}, "/api/file/list": {"files": []}, "/api/reaction/list": {"reactions": []}}


CALL_MODE = {"mode": "none"}
SEEN = {"mic_posts": [], "listen_gets": []}                 # yêu cầu mic / nghe mà máy chủ giả nhận được
WAV_SILENCE = (b"RIFF\xff\xff\xff\xffWAVEfmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (16000).to_bytes(4, "little")
               + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little") + b"data\xff\xff\xff\xff" + bytes(32000))


def active_call():
    m = CALL_MODE["mode"]
    if m == "none":
        return {"calls": [], "active": None}
    c = {"call_id": "555", "thread_id": "7", "peer": "BenBap", "direction": "out", "type": "user", "status": "answered", "started_at": NOW - 75, "answered_at": NOW - 62,
         "request_sent": True, "media": {"counters": {"rtp_tx": 500, "rtp_rx": 480, "video_rx": 0}, "audio_token": "tok123"}}
    if m == "incoming":
        c.update(direction="in", status="incoming", answered_at=None, type="video", media={})
    elif m == "video":
        c.update(type="video", media={"counters": {"rtp_tx": 900, "rtp_rx": 880, "video_rx": 300}})
    return {"calls": [c], "active": c}


class FakeHandler(sv.Handler):
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/__call":
            CALL_MODE["mode"] = self.path.split("mode=", 1)[1]
            return self._send_json({"ok": True})
        if p == "/api/calls":
            return self._send_json(active_call())
        if p.startswith("/api/call/audio/out/"):
            SEEN["listen_gets"].append(p)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(WAV_SILENCE)))
            self.end_headers()
            return self.wfile.write(WAV_SILENCE)
        if p == "/api/call/video/snapshot":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if p == "/api/call/video/view":
            return self._send_json({"error": "x"}, status=409)
        if p in DATA:
            return self._send_json(DATA[p])
        if p.startswith("/api/thread/") and p.endswith("/history"):
            return self._send_json({"messages": MSGS, "notice": "Lịch sử 1-1 chỉ có từ khi app bắt đầu lưu tin xuống DB local (tin cũ hơn chưa có)."})
        if p.startswith("/api/thread/") and p.endswith("/updates"):
            return self._send_json({"messages": []})
        if p == "/api/events":
            return self._send_json({"error": "x"}, status=404)
        if p.startswith("/api/") and p not in ("/api/app/status", "/api/app/logout"):
            return self._send_json({})                              # API chưa mô phỏng: 200 rỗng (thật thì 401 vì chưa đăng nhập Zalo → giao diện chuyển sang /login, làm hỏng phép đo)
        return super().do_GET()

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        if p.startswith("/api/call/audio/in/"):
            n = int(self.headers.get("Content-Length") or 0)
            SEEN["mic_posts"].append((p, len(self.rfile.read(n)) if n else 0))
            return self._send_json({"ok": True})
        if p.startswith("/api/") and p not in ("/api/app/login", "/api/app/logout"):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n) if n else None
            return self._send_json({"ok": True})
        return super().do_POST()


def _node_ok():
    node = shutil.which("node")
    if not node:
        return False
    try:
        return int(subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")[0]) >= 22
    except (ValueError, OSError):
        return False


def measure():
    sv.STATE = sv.AppState(tmp)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    base = "http://127.0.0.1:%d/" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(base + "api/app/login", method="POST", data=json.dumps({"username": "u", "password": "mat-khau-thu-123"}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            cookie = r.headers.get("Set-Cookie").split(";", 1)[0]
        p = subprocess.run(["node", os.path.join(HERE, "phone_layout_cdp.js"), base, cookie, "390,320,1280"], capture_output=True, text=True, timeout=240)
        assert p.returncode == 0 and p.stdout.strip(), p.stderr[-800:]
        return json.loads(p.stdout.strip().splitlines()[-1])
    finally:
        httpd.shutdown()


def test_phone_layout_in_real_chrome():
    if not (shutil.which("google-chrome") and _node_ok()):
        print("SKIP: không có google-chrome / node >= 22")
        return
    m = measure()
    assert m["exceptions"] == [], m["exceptions"]
    posts = SEEN["mic_posts"]
    assert posts and all(p == "/api/call/audio/in/555" and n == 3200 for p, n in posts), "mic máy này phải gửi các gói PCM16 16 kHz 100 ms (3200 byte) vào đúng cuộc gọi: %s" % posts[:3]
    assert len(posts) >= 6, "mic chỉ gửi %d gói trong ~3 giây" % len(posts)
    assert SEEN["listen_gets"] and SEEN["listen_gets"][0] == "/api/call/audio/out/tok123", "nút Nghe phải mở luồng tiếng bằng audio_token của cuộc gọi: %s" % SEEN["listen_gets"]
    for w in (390, 320):
        for name in ("list", "chat", "info", "contacts", "calls", "services", "watch", "svc_chip"):
            s = m["%s@%d" % (name, w)]
            assert s["bp"] == "phone", (name, w, s["bp"])
            assert s["sw"] <= s["cw"], "%s@%d tràn ngang: scrollWidth %s > %s" % (name, w, s["sw"], s["cw"])
            assert not s["clipped"], "%s@%d phần tử vượt mép phải: %s" % (name, w, s["clipped"])
        lst = m["list@%d" % w]
        assert "linear-gradient" in lst["listHead"], "thanh tìm kiếm phải là gradient xanh"
        assert lst["rail"]["y"] > 700 and lst["rail"]["w"] == w, "tab dưới phải nằm đáy màn hình, rộng hết khổ"
        assert lst["railLabels"] == ["Tin nhắn", "Danh bạ", "Cuộc gọi", "Theo dõi", "Dịch vụ", "Cài đặt"], lst["railLabels"]
        ch = m["chat@%d" % w]
        assert ch["pane"] == "main" and "linear-gradient" in ch["head"], ch["head"]
        assert ch["rail"]["disp"] == "none", "đang chat thì ẩn tab dưới (như Zalo)"
        row = [ch[k] for k in ("emoji", "input", "more", "img", "rec")]
        assert all(r and r["w"] > 0 for r in row), row
        ys = [r["y"] + r["h"] / 2 for r in row]
        assert max(ys) - min(ys) < 24, "soạn tin phải MỘT hàng, lệch %s" % ys
        assert ch["attach"]["disp"] == "none" and ch["like"]["disp"] == "none", "nút ít dùng phải gom vào «…»"
        assert ch["btnInfo"]["w"] > 0 and ch["icPhone"]["w"] > 0 and ch["icWide"]["disp"] == "none", "nút ≡ (không phải biểu tượng bảng bên)"
        assert ch["noticeHidden"] is True, "dòng «Lịch sử 1-1 chỉ có từ khi…» không được hiện trong khung chat"
        assert ch["moreMenu"] == ["Đính kèm tệp", "Nhãn dán", "Gửi 👍", "Dịch vụ cho hội thoại này"], ch["moreMenu"]
        assert ch["typing"]["send"] != "none" and ch["typing"]["tools"] == "none", "gõ chữ thì hiện Gửi và ẩn mic/ảnh"
        # ---- cuộc gọi trên điện thoại: màn hình toàn màn hình, nút tròn, hàng nút ở nửa dưới, hình phủ cả màn hình ----
        H = 844
        for mode in ("incoming", "voice", "video"):
            c = m["call_%s@%d" % (mode, w)]
            cc = c["cc"]
            assert cc and cc["x"] == 0 and cc["y"] == 0 and cc["w"] == w and cc["h"] >= H, "%s@%d thẻ cuộc gọi phải phủ toàn màn hình: %s" % (mode, w, cc)
            assert c["ccState"] == {"incoming": "incoming", "voice": "live", "video": "live"}[mode], c["ccState"]
            assert c["sw"] <= c["cw"], "%s@%d tràn ngang" % (mode, w)
            assert c["popout"] is None or c["popout"]["disp"] == "none", "điện thoại không có «Tách cửa sổ»"
            for k in (("end", "ok") if mode == "incoming" else ("end",)):
                b = c[k]
                assert abs(b["w"] - b["h"]) < 2 and b["w"] >= 56, "nút %s phải tròn, đủ lớn để chạm: %s" % (k, b)
                assert b["y"] > H * 0.7, "nút %s phải ở đáy màn hình: %s" % (k, b)
            if mode == "incoming":
                assert abs(c["end"]["y"] - c["ok"]["y"]) < 2 and c["end"]["x"] < c["ok"]["x"], "Từ chối bên trái, Nghe bên phải, cùng hàng"
            else:
                assert c["mt"]["y"] > H * 0.4 and c["mt"]["y"] + c["mt"]["h"] < c["end"]["y"] + 1, "hàng nút mic/loa/camera ở nửa dưới, trên nút cúp: %s" % c["mt"]
            if mode != "video":
                assert c["endVis"] == "visible" and c["topVis"] == "visible", "gọi thoại/đến: thao tác luôn hiện"
            if mode == "voice":
                own = json.loads(c["steps"][0])
                assert own["mic"] == "true" and own["listen"] == "true", "bấm xong, hai nút phải ở trạng thái bật: %s" % own
                assert [l for l in own["labels"] if "nhà" in l] and any("Mic máy này" in l for l in own["labels"]), own["labels"]
                assert any("Mic nhà" in l for l in own["labels"]) and any("Camera nhà" in l for l in own["labels"]), "nhãn thiết bị trong nhà phải ghi rõ «nhà»"
            if mode == "video":
                assert c["endVis"] == "hidden" and c["topVis"] == "hidden", "gọi video: mặc định ẨN thao tác để nhường chỗ cho hình"
                t = c["tapped"]
                assert t["ui"] == "1" and t["end"] == "visible" and t["top"] == "visible" and t["endPe"] == "auto", "chạm vào hình phải hiện thao tác (bấm được): %s" % t
                assert c["tappedAgain"] == "hidden", "chạm lần nữa thì ẩn lại"
                assert c["autoHide"] == "hidden", "tự ẩn sau vài giây không chạm"
                v = c["vid"]
                assert c["ccVideo"] == "1" and c["ccPe"] == "none", "có hình: thẻ chỉ là lớp nút, không chặn chạm vào hình"
                assert v["x"] == 0 and v["y"] == 0 and v["w"] == w and v["h"] >= H and v["disp"] != "none", "hình phải phủ toàn màn hình: %s" % v
            else:
                assert c["vid"] is None or c["vid"]["disp"] == "none" or c["vid"]["w"] == 0, "chưa có video thì không hiện khung hình"
        # ---- bảng «Theo dõi» thành thẻ, không tràn ngang; hàng chip giữ chip đang chọn trong tầm nhìn ----
        wt = m["watch@%d" % w]
        assert wt["tblRowDisp"] == "block" and wt["tblHeadDisp"] == "none", "bảng Theo dõi phải thành thẻ trên điện thoại: %s" % wt
        assert wt["sw"] <= wt["cw"] and not wt["clipped"], "Theo dõi tràn ngang: %s %s" % (wt["sw"], wt["clipped"])
        sc = m["svc_chip@%d" % w]
        assert sc["chips"] and sc["chips"]["sel"], "không thấy chip đang chọn"
        cr, sr = sc["chips"]["box"], sc["chips"]["sel"]
        assert sc["chips"]["scrollLeft"] > 0 and sr["x"] >= cr["x"] - 1 and sr["x"] + sr["w"] <= cr["x"] + cr["w"] + 1, "chip vừa chọn phải nằm trong tầm nhìn sau khi dựng lại: %s" % sc["chips"]
        inf = m["info@%d" % w]
        assert inf["info"] == "page" and inf["infoPos"] == "fixed", inf["info"]
        box = inf["infoBox"]
        assert box["x"] == 0 and box["y"] == 0 and box["w"] == w and box["h"] >= 844, "trang Thông tin phải phủ toàn màn hình: %s" % box
        assert inf["back"]["w"] > 0 and inf["afterBack"] == "off", "nút quay lại phải đóng trang Thông tin"


def test_settings_menu_opens_exactly_the_chosen_section():
    """Cài đặt: bấm mục nào hiện ĐÚNG trang mục đó (9 mục, 9 trang khác nhau) — ở khổ điện thoại (danh sách → trang → quay lại) và khổ rộng (menu bánh răng)."""
    if not (shutil.which("google-chrome") and _node_ok()):
        print("SKIP: không có google-chrome / node >= 22")
        return
    m = measure()
    want = {"account": "Tài khoản và kết nối", "security": "Bảo mật", "privacy": "Quyền riêng tư", "history": "Đồng bộ lịch sử chat từ điện thoại",
            "data": "Dữ liệu và tự xóa", "calls": "Mic (tiếng gửi sang bên kia)", "ui": "Giao diện", "webhook": "Webhook (Home Assistant, n8n…)", "proxy": "Proxy ra Zalo"}
    for w in (390, 320, 1280):
        r = json.loads(m["settings_all@%d" % w]["steps"][0])
        assert len(r["items"]) == 9, r
        got = {i["sec"]: i["h3"] for i in r["items"]}
        assert got == want, "%d px: bấm mục nào phải ra đúng trang mục đó: %s" % (w, got)
        assert len(set(got.values())) == 9, "mỗi mục một trang khác nhau"
        if r["phone"]:
            assert sorted(r["sections"]) == sorted(want), r["sections"]
            for i in r["items"]:
                assert i["menuHidden"] is True and i["backToMenu"] is True, "điện thoại: mở trang thì ẩn danh sách, nút quay lại về danh sách: %s" % i
                assert i["head"] != "Cài đặt", "tiêu đề phải là tên mục: %s" % i
        else:
            assert r["menuOnOpen"] >= 9, "menu bánh răng liệt kê đủ 9 mục: %s" % r["menuOnOpen"]


if __name__ == "__main__":
    test_phone_layout_in_real_chrome()
    test_settings_menu_opens_exactly_the_chosen_section()
    print("ALL PHONE LAYOUT TESTS PASSED")
