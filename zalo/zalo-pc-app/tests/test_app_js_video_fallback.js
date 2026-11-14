// Hình đối tác trên WebUI: luồng liên tục, tự chuyển sang hỏi ảnh mới nhất khi luồng không lên (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_video_fallback.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window, errors = [], snapReq = [];
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
const realST = w.setTimeout.bind(w);
w.setTimeout = (fn, ms) => realST(fn, ms >= 5000 ? 40 : Math.min(ms, 40));          // rút ngắn: chờ 6 s thành 40 ms
w.Image = function () { const img = {}; Object.defineProperty(img, "src", { set(v) { img._src = v; snapReq.push(v); realST(() => img.onload && img.onload(), 5); }, get() { return img._src; } }); return img; };
w.fetch = async (url) => ({ status: 200, json: async () => (url === "/api/status" ? { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } } : url.startsWith("/api/calls") ? { active: null, calls: [] } : url.startsWith("/api/contacts") ? { friends: { rows: [] }, groups: { rows: [] } } : {}) });
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  // 1) luồng ra hình bình thường: không chuyển sang ảnh
  S.vv = null; let box = T.videoView({ call_id: 7, type: "video" }, {}), img = box.querySelector("img.vview");
  ok.push(["bắt đầu bằng luồng liên tục /api/call/video/view", /\/api\/call\/video\/view\?call_id=7/.test(img.getAttribute("src"))]);
  img.dispatchEvent(new w.Event("load")); await sleep(120);
  ok.push(["luồng có hình: hiện ngay, KHÔNG chuyển sang hỏi ảnh", box.classList.contains("on") && S.vv.mode === "stream" && snapReq.length === 0, "mode=" + S.vv.mode]);
  // 2) luồng lỗi hai lần -> chuyển sang ảnh mới nhất
  S.vv = null; box = T.videoView({ call_id: 8, type: "video" }, {}); img = box.querySelector("img.vview");
  img.dispatchEvent(new w.Event("error")); await sleep(20);
  ok.push(["lỗi lần đầu: vẫn thử lại luồng", S.vv.mode === "stream"]);
  img.dispatchEvent(new w.Event("error")); await sleep(120);
  ok.push(["lỗi lần hai: chuyển sang hỏi ảnh mới nhất /api/call/video/snapshot", S.vv.mode === "snap" && snapReq.some((u) => /\/api\/call\/video\/snapshot\?call_id=8/.test(u)), snapReq.join(" ")]);
  ok.push(["ảnh nhận được hiện lên khung và đổi liên tục (hỏi lại sau mỗi ảnh)", box.classList.contains("on") && snapReq.length >= 2 && /snapshot/.test(img.getAttribute("src")), "yêu cầu: " + snapReq.length]);
  // 3) luồng không ra hình sau thời gian chờ (proxy gom bộ đệm, không có sự kiện lỗi) -> chuyển sang ảnh
  const before = snapReq.length; S.vv = null; box = T.videoView({ call_id: 9, type: "video" }, {}); await sleep(250);
  ok.push(["luồng im lặng quá thời gian chờ: tự chuyển sang ảnh", S.vv.mode === "snap" && snapReq.length > before && snapReq.some((u) => /call_id=9/.test(u))]);
  // 4) đổi sang cuộc gọi khác: bộ hỏi ảnh của cuộc cũ dừng
  S.vv = null; await sleep(60); const n = snapReq.length; await sleep(200);
  ok.push(["hết cuộc gọi (S.vv = null): ngừng hỏi ảnh", snapReq.length === n, n + " -> " + snapReq.length]);
  let bad = 0; for (const [nm, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", nm, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
