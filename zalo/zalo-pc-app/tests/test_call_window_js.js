// Trang cuộc gọi TÁCH RỜI (/call): vẽ đúng, điều khiển đúng API, tự đóng khi hết cuộc gọi (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_call_window_js.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "call.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "call.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/call" });
const w = dom.window, posts = [], errors = [], snapReq = [];
let active = null, closed = 0, mediaBody = { ok: true, mic: null, speaker: null, video: null, gain: { mic: 100, speaker: 100 } }, failNext = null;
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.close = () => { closed++; };
const realST = w.setTimeout.bind(w);
w.setTimeout = (fn, ms) => realST(fn, ms >= 2000 && ms < 5000 ? 30 : ms);        // chỉ rút ngắn chờ đóng cửa sổ (2,5 s); chờ luồng 6 s và thông báo 4–6 s giữ nguyên
w.Image = function () { const img = {}; Object.defineProperty(img, "src", { set(v) { img._src = v; snapReq.push(v); realST(() => img.onload && img.onload(), 5); }, get() { return img._src; } }); return img; };
w.fetch = async (url, opts) => {
  if (opts && opts.method === "POST") {
    const b = JSON.parse(opts.body); posts.push([url, b]);
    if (failNext) { const f = failNext; failNext = null; return { status: 200, json: async () => f }; }
    if (url === "/api/call/media" && b.action === "gain") { mediaBody.gain = Object.assign({}, mediaBody.gain, { [b.target]: Math.max(0, Math.min(300, mediaBody.gain[b.target] + b.step)) }); return { status: 200, json: async () => Object.assign({}, mediaBody) }; }
    if (url === "/api/call/media" && b.action === "start") { mediaBody = Object.assign({}, mediaBody, { [b.target]: { alive: true } }); return { status: 200, json: async () => mediaBody }; }
    if (url === "/api/call/media" && b.action === "stop") { mediaBody = Object.assign({}, mediaBody, { [b.target]: null }); return { status: 200, json: async () => mediaBody }; }
    return { status: 200, json: async () => (url === "/api/call/media" ? mediaBody : { ok: true }) };
  }
  if (url === "/api/calls") return { status: 200, json: async () => ({ active, calls: active ? [active] : [] }) };
  return { status: 200, json: async () => ({}) };
};
w.__CALL_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (id) => w.document.getElementById(id);
(async () => {
  await sleep(120);
  const T = w.__t, S = T.S, ok = [];
  ok.push(["chưa có cuộc gọi: báo đã kết thúc và đóng cửa sổ", $("cw").dataset.state === "end" && /đã kết thúc/.test($("cw-st").textContent) && closed >= 1, "đóng " + closed]);
  active = { call_id: 31, status: "answered", answered_at: 1700000000, started_at: 1700000000, type: "video", direction: "out", thread_id: "20001", peer: "Nguyễn Việt" };
  await T.loadCalls(); await sleep(60);
  ok.push(["cuộc gọi video đang nói: tên, trạng thái, tiêu đề cửa sổ", /Video · Nguyễn Việt/.test($("cw-nm").textContent) && /Đang trong cuộc gọi/.test($("cw-st").textContent) && /Nguyễn Việt/.test(w.document.title)]);
  ok.push(["có ba nút Mic/Loa/Camera, hai ô âm lượng và nút Kết thúc", $("cw-toggles").querySelectorAll(".cw-tg").length === 3 && $("cw-gains").querySelectorAll(".cw-gn").length === 2 && !!$("cw-acts").querySelector(".cw-btn.end")]);
  ok.push(["luồng hình bắt đầu bằng /api/call/video/view", /\/api\/call\/video\/view\?call_id=31/.test($("cw-vview").getAttribute("src") || "") && $("cw-vview").hidden === false]);
  // luồng lỗi hai lần -> ảnh mới nhất
  $("cw-vview").dispatchEvent(new w.Event("error")); $("cw-vview").dispatchEvent(new w.Event("error")); await sleep(120);
  ok.push(["luồng lỗi hai lần: chuyển sang ảnh mới nhất /api/call/video/snapshot, khung hiện hình", snapReq.some((u) => /snapshot\?call_id=31/.test(u)) && $("cw-vbox").classList.contains("on")]);
  // điều khiển
  posts.length = 0;
  $("cw-toggles").querySelectorAll(".cw-tg")[0].click(); await sleep(60);
  ok.push(["bấm Mic -> POST /api/call/media {action start, target mic}", posts.some(([u, b]) => u === "/api/call/media" && b.action === "start" && b.target === "mic" && b.call_id === 31), JSON.stringify(posts)]);
  ok.push(["nút Mic chuyển sang «bật»", $("cw-toggles").querySelectorAll(".cw-tg")[0].classList.contains("on")]);
  posts.length = 0; $("cw-toggles").querySelectorAll(".cw-tg")[2].click(); await sleep(60);
  ok.push(["cuộc gọi VIDEO: bấm Camera -> /api/call/video (start), không phải xin chuyển video", posts.some(([u, b]) => u === "/api/call/video" && b.action === "start" && b.target === "video"), JSON.stringify(posts)]);
  posts.length = 0; $("cw-gains").querySelectorAll(".cw-gn")[1].querySelectorAll("button")[1].click(); await sleep(60);
  ok.push(["bấm + của Loa -> action gain, target speaker, step 10; hiện Loa 110%", posts.some(([u, b]) => b.action === "gain" && b.target === "speaker" && b.step === 10) && /Loa 110%/.test($("cw-gains").textContent), $("cw-gains").textContent]);
  failNext = { ok: false, error: "chua_co_camera" }; $("cw-toggles").querySelectorAll(".cw-tg")[2].click(); await sleep(60);
  ok.push(["thiếu camera: báo bằng lời thường, không hiện mã lỗi", !$("cw-toast").hidden && /chưa có camera — quy tắc/.test($("cw-toast").textContent), $("cw-toast").textContent]);
  posts.length = 0; $("cw-acts").querySelector(".cw-btn.end").click(); await sleep(60);
  ok.push(["bấm Kết thúc -> POST /api/call/end", posts.some(([u, b]) => u === "/api/call/end" && b.call_id === 31)]);
  // bộ gửi im lặng không phải mic bật
  T.applyCm({ mic: { alive: true, idle: true }, speaker: null, video: null });
  ok.push(["mic chỉ là bộ gửi im lặng giữ luồng: nút Mic vẫn «tắt»", !$("cw-toggles").querySelectorAll(".cw-tg")[0].classList.contains("on")]);
  // cuộc gọi thoại: Camera = xin chuyển video
  active = Object.assign({}, active, { call_id: 32, type: "voice" }); S.cm.video = false; await T.loadCalls(); await sleep(40); posts.length = 0;
  $("cw-toggles").querySelectorAll(".cw-tg")[2].click(); await sleep(60);
  ok.push(["cuộc gọi THOẠI: bấm Camera -> /api/call/upgrade_video", posts.some(([u]) => u === "/api/call/upgrade_video")]);
  // cuộc gọi đến chưa nghe
  active = { call_id: 33, status: "incoming", answered_at: 0, started_at: 1700000000, type: "video", direction: "in", thread_id: "20001", peer: "Nguyễn Việt" };
  await T.loadCalls(); await sleep(40); posts.length = 0;
  ok.push(["cuộc gọi đến: chỉ có Nghe và Từ chối (không nút Mic/Loa/Camera)", $("cw-acts").querySelectorAll(".cw-btn").length === 2 && $("cw-toggles").children.length === 0 && /Cuộc gọi video đến/.test($("cw-st").textContent)]);
  $("cw-acts").querySelector(".cw-btn.ok").click(); await sleep(40);
  ok.push(["bấm Nghe -> POST /api/call/answer", posts.some(([u, b]) => u === "/api/call/answer" && b.call_id === 33)]);
  // bấm khung video: phủ đầy
  $("cw-vbox").click(); ok.push(["bấm khung video: chuyển sang «phủ đầy khung»", $("cw-vbox").classList.contains("fill")]); $("cw-vbox").click();
  // hết cuộc gọi
  const before = closed; active = null; await T.loadCalls(); await sleep(120);
  ok.push(["hết cuộc gọi: ngừng luồng hình, báo kết thúc, đóng cửa sổ", $("cw-vview").hidden === true && !$("cw-vview").getAttribute("src") && closed > before]);
  let bad = 0; for (const [n, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", n, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
