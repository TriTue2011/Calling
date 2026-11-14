// Thẻ cuộc gọi: bật Camera trong cuộc gọi THOẠI phải xin chuyển sang VIDEO (POST /api/call/upgrade_video), trong cuộc gọi VIDEO chỉ bật/tắt hình (POST /api/call/video).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_callcard_upgrade.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
async function run(callType) {
  const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
  const w = dom.window, posts = [], errors = [];
  w.addEventListener("error", (e) => errors.push(e.message));
  w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
  w.fetch = async (url, opts) => {
    let data = {};
    if (url === "/api/status") data = { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } };
    else if (url.startsWith("/api/calls")) data = { active: { call_id: 111, direction: "out", status: "answered", type: callType, thread_id: "5", peer: "Anh", started_at: Date.now() / 1000 - 5, answered_at: Date.now() / 1000 - 4, media: { counters: { rtp_rx: 10 } } }, calls: [] };
    else if (url === "/api/call/media" || url === "/api/call/video" || url === "/api/call/upgrade_video") { const b = JSON.parse(opts.body); posts.push([url, b]); data = { ok: true, call_id: 111, mic: null, speaker: null, video: (b.action === "stop" || b.action === "status") ? null : { alive: true } }; }
    else if (url.startsWith("/api/contacts")) data = { friends: { rows: [] }, groups: { rows: [] } };
    return { status: 200, json: async () => data };
  };
  w.eval(js);
  await new Promise((r) => setTimeout(r, 900));
  const btns = Array.from(w.document.getElementById("callcard").querySelectorAll(".tg"));
  btns[2].click();
  await new Promise((r) => setTimeout(r, 300));
  return { posts, errors };
}
(async () => {
  const ok = [];
  const v = await run("user");
  ok.push(["cuộc THOẠI: bật Camera -> POST /api/call/upgrade_video {call_id}", v.posts.some(([u, b]) => u === "/api/call/upgrade_video" && b.call_id === 111) && !v.posts.some(([u]) => u === "/api/call/video")]);
  const d = await run("video");
  ok.push(["cuộc VIDEO: bật Camera -> POST /api/call/video start (không xin chuyển)", d.posts.some(([u, b]) => u === "/api/call/video" && b.action === "start") && !d.posts.some(([u]) => u === "/api/call/upgrade_video")]);
  let bad = 0; for (const [n, x] of ok) { console.log(x ? "ĐẠT " : "HỎNG", n); if (!x) bad++; }
  console.log("lỗi trình duyệt:", v.errors.concat(d.errors)); process.exit(bad || v.errors.length || d.errors.length ? 1 : 0);
})();
