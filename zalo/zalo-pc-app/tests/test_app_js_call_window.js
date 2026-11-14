// WebUI chính: tách cuộc gọi ra CỬA SỔ RIÊNG (/call) — tự mở khi gọi video/nghe video, nút Tách cửa sổ / Đưa về đây (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_call_window.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window, opened = [], errors = [];
let blocked = false;
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
w.open = (url, name, feat) => { if (blocked) return null; const win = { url, name, feat, closed: false, focused: 0, focus() { this.focused++; }, close() { this.closed = true; } }; opened.push(win); return win; };
w.fetch = async (url, opts) => ({ status: 200, json: async () => (url === "/api/status" ? { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } } : url.startsWith("/api/calls") ? { active: null, calls: [] } : url.startsWith("/api/contacts") ? { friends: { rows: [] }, groups: { rows: [] } } : { ok: true, request_sent: true }) });
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (id) => w.document.getElementById(id);
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  S.calls = { active: null, calls: [] }; S.cur = { id: "20001", type: "user", name: "Nguyễn Việt", members: [] };
  // 1) gọi video: cửa sổ mở NGAY trong lúc bấm (trước mọi await), đúng địa chỉ và tên cửa sổ
  const p = T.startCall(true);
  ok.push(["gọi video: mở cửa sổ /call NGAY trong lúc bấm (đồng bộ, trước mọi await)", opened.length === 1 && opened[0].url === "/call" && opened[0].name === "zalo-call" && /popup=yes/.test(opened[0].feat) && /resizable=yes/.test(opened[0].feat), JSON.stringify(opened.map((o) => o.url))]);
  await p;
  // 2) gọi thoại không mở; đã mở rồi thì chỉ đưa lên trước
  S.calls = { active: null, calls: [] }; await T.startCall(false);
  ok.push(["gọi thoại: KHÔNG mở cửa sổ riêng", opened.length === 1]);
  S.calls = { active: null, calls: [] }; await T.startCall(true);
  ok.push(["đã có cửa sổ: không mở thêm, chỉ đưa lên trước", opened.length === 1 && opened[0].focused >= 1, "đã mở " + opened.length]);
  // 3) cuộc gọi video đang nói + cửa sổ đang mở: trang chính không vẽ khung video, ghi chú + nút «Đưa về đây»
  const call = { call_id: 41, status: "answered", answered_at: 1700000000, started_at: 1700000000, type: "video", direction: "out", thread_id: "20001", peer: "Nguyễn Việt" };
  S.calls = { active: call, calls: [call] }; S.vv = null; S.cm.id = "41"; T.renderCallCard();
  ok.push(["đã tách: #vidwin ẩn (không vẽ thêm luồng hình ở trang chính)", $("vidwin").hidden === true && !$("vidwin").firstChild]);
  ok.push(["thẻ ghi «Đang mở ở cửa sổ riêng» và có nút «Đưa về đây»", /Đang mở ở cửa sổ riêng/.test($("callcard").textContent) && /Đưa về đây/.test($("callcard").textContent) && !/Tách cửa sổ/.test($("callcard").textContent)]);
  // 4) Đưa về đây: đóng cửa sổ, nhớ lựa chọn, khung video trở lại trong trang
  Array.from($("callcard").querySelectorAll("button.link")).find((b) => /Đưa về đây/.test(b.textContent)).click();
  ok.push(["«Đưa về đây»: đóng cửa sổ rời, video trở lại trang chính, hiện nút «Tách cửa sổ»", opened[0].closed === true && $("vidwin").hidden === false && !!$("vidwin").querySelector(".vvbox") && /Tách cửa sổ/.test($("callcard").textContent)]);
  S.calls = { active: null, calls: [] }; T.renderCallCard(); const n = opened.length; await T.startCall(true);
  ok.push(["đã chọn «Đưa về đây»: lần gọi video sau KHÔNG tự mở cửa sổ", opened.length === n]);
  // 5) nút Tách cửa sổ mở lại cửa sổ và nhớ ý muốn mở
  S.calls = { active: call, calls: [call] }; S.vv = null; T.renderCallCard();
  Array.from($("callcard").querySelectorAll("button.link")).find((b) => /Tách cửa sổ/.test(b.textContent)).click();
  ok.push(["bấm «Tách cửa sổ»: mở /call và ẩn khung video trong trang", opened.length === n + 1 && opened[n].url === "/call" && $("vidwin").hidden === true]);
  // 6) người dùng tự đóng cửa sổ: trang chính lấy lại khung video ở lần vẽ kế tiếp
  opened[n].closed = true; T.renderCallCard();
  ok.push(["tự đóng cửa sổ rời: trang chính vẽ lại khung video", $("vidwin").hidden === false && !!$("vidwin").querySelector(".vvbox")]);
  // 7) trình duyệt chặn cửa sổ bật lên: báo cách khắc phục, không lỗi
  blocked = true; S.callWin = null; T.openCallWindow();
  ok.push(["bị chặn cửa sổ bật lên: báo hướng dẫn bằng thông báo", !$("toast").hidden && /chặn cửa sổ bật lên/.test($("toast").textContent), $("toast").textContent]);
  blocked = false;
  // 8) nghe máy cuộc gọi video đến: cũng mở cửa sổ trong lúc bấm; cuộc thoại thì không
  S.callWin = null; try { localStorage.setItem("zalo-callwin", "1"); } catch (e) { /* ignore */ }
  const m = opened.length; T.answerCall({ call_id: 42, type: "voice" });
  ok.push(["nghe cuộc THOẠI: không mở cửa sổ", opened.length === m]);
  T.answerCall({ call_id: 43, type: "video" });
  ok.push(["nghe cuộc VIDEO: mở cửa sổ ngay trong lúc bấm", opened.length === m + 1 && opened[m].url === "/call"]);
  let bad = 0; for (const [nm, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", nm, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
