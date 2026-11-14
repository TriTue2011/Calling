// Gọi nhóm trên WebUI: chỉ có gọi VIDEO nhóm, đổ chuông ĐỦ thành viên (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_group_call.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window, posts = [], errors = [];
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
w.fetch = async (url, opts) => {
  let data = {};
  if (opts && opts.method === "POST") { let b = null; try { b = JSON.parse(opts.body); } catch (e) {} posts.push([url, b]); data = { ok: true, request_sent: true }; }
  else if (url === "/api/status") data = { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } };
  else if (url.startsWith("/api/reaction/list")) data = { reactions: {} };
  else if (url.startsWith("/api/contacts")) data = { friends: { rows: [] }, groups: { rows: [] } };
  else if (url.startsWith("/api/calls")) data = { active: null, calls: [] };
  else if (url.includes("/history")) data = { messages: [] };
  return { status: 200, json: async () => data };
};
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  S.calls = { active: null, calls: [] };
  const grp = { id: "3133467193494275911", type: "group", name: "AI học hỏi", members: ["u1", "u2"], member_ids: ["u1", "u2", "u3", "u4", "u5"] };
  S.conv = {}; T.openThread(grp); await sleep(80);
  ok.push(["nhóm: ẩn nút gọi thoại, hiện nút gọi video", w.document.getElementById("btn-call").hidden === true && w.document.getElementById("btn-video").hidden === false]);
  posts.length = 0; await T.startCall(true); await sleep(40);
  const req = posts.find(([u]) => u === "/api/call/request");
  ok.push(["gọi nhóm gửi type=group và video=true (gọi VIDEO nhóm)", !!req && req[1].type === "group" && req[1].video === true, JSON.stringify(req)]);
  ok.push(["đổ chuông ĐỦ thành viên: partners lấy member_ids (5 người) chứ không chỉ topMember (2)", !!req && JSON.stringify(req[1].partners) === JSON.stringify(["u1", "u2", "u3", "u4", "u5"]), JSON.stringify(req && req[1].partners)]);
  const grp2 = { id: "g2", type: "group", name: "Nhóm cũ", members: ["a", "b"], member_ids: [] };
  T.openThread(grp2); await sleep(40); posts.length = 0; await T.startCall(true); await sleep(40);
  const req2 = posts.find(([u]) => u === "/api/call/request");
  ok.push(["chưa có member_ids: dùng members như cũ", !!req2 && JSON.stringify(req2[1].partners) === JSON.stringify(["a", "b"])]);
  const user = { id: "20001", type: "user", name: "Anh", members: [] };
  T.openThread(user); await sleep(40);
  ok.push(["hội thoại 1-1: cả hai nút gọi thoại và gọi video đều hiện", w.document.getElementById("btn-call").hidden === false && w.document.getElementById("btn-video").hidden === false]);
  posts.length = 0; await T.startCall(false); await sleep(40);
  const req3 = posts.find(([u]) => u === "/api/call/request");
  ok.push(["1-1 gọi thoại: type=user, video=false (không đổi so với trước)", !!req3 && req3[1].type === "user" && req3[1].video === false, JSON.stringify(req3)]);
  let bad = 0; for (const [n, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", n, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
