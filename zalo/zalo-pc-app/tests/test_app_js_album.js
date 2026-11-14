// Album ảnh thành một lưới + loại tin giữ chỗ trùng trên WebUI (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_album.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window, errors = [];
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
w.fetch = async (url) => {
  let data = {};
  if (url === "/api/status") data = { login: true, version: "t", uid: "475796162066271393", sync: "running", engine: { detail: "" } };
  else if (url.startsWith("/api/reaction/list")) data = { reactions: {} };
  else if (url.startsWith("/api/contacts")) data = { friends: { rows: [] }, groups: { rows: [] } };
  else if (url.startsWith("/api/calls")) data = { active: null, calls: [] };
  return { status: 200, json: async () => data };
};
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ME = "475796162066271393";
const echo = (mid, cli, idx, total, gid) => ({ id: mid, sender_id: ME, direction: "out", is_self: true, time: 1794623122, kind: "photo", file_url: "https://f.zdn.vn/" + mid + ".jpg",
  raw: { msgId: mid, cliMsgId: cli, content: { href: "https://f.zdn.vn/" + mid + ".jpg", thumb: "https://t.zdn.vn/480/" + mid + ".jpg", params: JSON.stringify({ group_layout_id: gid, id_in_group: idx, total_item_in_group: total, is_group_layout: 1 }) } } });
const ph = (cid, name) => ({ id: cid, client_id: cid, sender_id: "me", direction: "out", time: 1794623122, kind: "photo", file_name: name, text: name });
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  S.uid = ME; S.cur = { id: "3295299208151385728", type: "group", name: "Nhóm" };
  S.files = {}; S.msgs = [];
  // thứ tự đến lẫn lộn + 3 tin giữ chỗ + 1 ảnh lẻ
  T.mergeMsgs([ph("c3", "gui3.jpg"), ph("c1", "gui1.jpg"), ph("c2", "gui2.jpg"), ph("c9", "chua-doi-lai.jpg"),
    echo("m3", "c3", 2, 3, 77), echo("m1", "c1", 0, 3, 77), echo("m2", "c2", 1, 3, 77),
    { id: "solo", sender_id: ME, direction: "out", time: 1794623200, kind: "photo", file_url: "https://f.zdn.vn/solo.jpg", raw: { msgId: "solo", cliMsgId: "c50", content: { params: "{}" } } }]);
  ok.push(["tin giữ chỗ đã có bản dội lại bị loại; tin chưa dội lại vẫn giữ", !S.msgs.some((m) => ["c1", "c2", "c3"].includes(m._id)) && S.msgs.some((m) => m._id === "c9"), S.msgs.map((m) => m._id).join(",")]);
  T.renderMsgs(); await sleep(30);
  const box = w.document.getElementById("msgs");
  const albums = box.querySelectorAll(".album");
  ok.push(["3 ảnh album gom thành MỘT lưới n3 (không phải 3 bong bóng)", albums.length === 1 && albums[0].classList.contains("n3") && albums[0].querySelectorAll("a").length === 3, "lưới: " + albums.length]);
  const srcs = Array.from(albums[0].querySelectorAll("img")).map((i) => i.src);
  ok.push(["ảnh xếp đúng thứ tự id_in_group dù đến lẫn lộn, dùng ảnh thu nhỏ", srcs.join("|") === "https://t.zdn.vn/480/m1.jpg|https://t.zdn.vn/480/m2.jpg|https://t.zdn.vn/480/m3.jpg", srcs.join("|")]);
  const links = Array.from(albums[0].querySelectorAll("a")).map((a) => a.href + "~" + a.rel);
  ok.push(["bấm ảnh mở bản đầy đủ, không gửi Referer", links[0] === "https://f.zdn.vn/m1.jpg~noopener noreferrer", links[0]]);
  ok.push(["ảnh lẻ không bị gom vào lưới; tin giữ chỗ chưa dội lại vẫn hiện", box.querySelectorAll(".msg").length === 3, "số bong bóng: " + box.querySelectorAll(".msg").length]);
  // album 2 ảnh -> n2, album 12 ảnh -> n10
  S.msgs = []; T.mergeMsgs([echo("a1", "x1", 0, 2, 5), echo("a2", "x2", 1, 2, 5)]); T.renderMsgs(); await sleep(20);
  ok.push(["album 2 ảnh dùng lưới n2", !!box.querySelector(".album.n2") && box.querySelectorAll(".album a").length === 2]);
  S.msgs = []; const many = []; for (let i = 0; i < 12; i++) many.push(echo("k" + i, "y" + i, i, 12, 9)); T.mergeMsgs(many); T.renderMsgs(); await sleep(20);
  ok.push(["album 12 ảnh dùng lưới n10 (4 cột)", !!box.querySelector(".album.n10") && box.querySelectorAll(".album a").length === 12]);
  S.msgs = []; T.mergeMsgs([echo("p1", "z1", 0, 3, 3)]); T.renderMsgs(); await sleep(20);      // mới đến 1/3 ảnh
  ok.push(["mới đến một phần album vẫn hiện (chưa đủ ảnh)", box.querySelectorAll(".album a").length === 1]);
  let bad = 0; for (const [n, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", n, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
