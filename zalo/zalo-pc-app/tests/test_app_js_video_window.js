// Khung hình đối tác là CỬA SỔ RIÊNG (#vidwin), không gộp vào thẻ điều khiển cuộc gọi (#callcard) (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_video_window.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const rawHtml = fs.readFileSync(path.join(dir, "index.html"), "utf8");
const html = rawHtml.replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const css = fs.readFileSync(path.join(dir, "app.css"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window, errors = [];
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
w.fetch = async (url) => ({ status: 200, json: async () => (url === "/api/status" ? { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } } : url.startsWith("/api/calls") ? { active: null, calls: [] } : url.startsWith("/api/contacts") ? { friends: { rows: [] }, groups: { rows: [] } } : {}) });
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (id) => w.document.getElementById(id);
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  ok.push(["index.html có #vidwin riêng, đứng ngoài #callcard", !!$("vidwin") && !$("callcard").contains($("vidwin")) && !$("vidwin").contains($("callcard"))]);
  const call = { call_id: 21, status: "answered", answered_at: 1700000000, started_at: 1700000000, type: "video", direction: "out", thread_id: "20001", peer: "Nguyễn Việt" };
  S.calls = { active: call, calls: [call] }; S.vv = null; S.cm.id = "21";
  T.renderCallCard();
  ok.push(["đang gọi video: khung hình nằm trong #vidwin, KHÔNG nằm trong thẻ #callcard", !!$("vidwin").querySelector(".vvbox") && !$("callcard").querySelector(".vvbox") && !$("vidwin").hidden]);
  ok.push(["thẻ #callcard vẫn đủ nút Mic/Loa/Camera, âm lượng và Kết thúc", !!$("callcard").querySelector(".tgs") && !!$("callcard").querySelector(".gns") && !!$("callcard").querySelector("button.end")]);
  const box = $("vidwin").querySelector(".vvbox"), img = box.querySelector("img.vview"), src = img.getAttribute("src");
  T.renderCallCard(); T.renderCallCard();
  ok.push(["vẽ lại thẻ nhiều lần: giữ NGUYÊN phần tử khung (luồng hình không khởi động lại)", $("vidwin").querySelector(".vvbox") === box && box.querySelector("img.vview").getAttribute("src") === src]);
  S.calls = { active: Object.assign({}, call, { status: "incoming", answered_at: 0, direction: "in" }), calls: [] }; S.vv = null;
  T.renderCallCard();
  ok.push(["cuộc gọi đến chưa nghe: không có cửa sổ video", $("vidwin").hidden === true && !$("vidwin").firstChild]);
  S.calls = { active: call, calls: [call] }; T.renderCallCard();
  ok.push(["nghe máy: cửa sổ video hiện", $("vidwin").hidden === false && !!$("vidwin").querySelector(".vvbox")]);
  S.calls = { active: null, calls: [] }; T.renderCallCard();
  ok.push(["hết cuộc gọi: cửa sổ video ẩn và xóa sạch, thẻ cũng ẩn", $("vidwin").hidden === true && !$("vidwin").firstChild && $("callcard").hidden === true]);
  // CSS: cửa sổ riêng, bên trái thẻ trên máy tính, phía trên trên điện thoại; mọi quy tắc khung không còn lồng trong .callcard
  ok.push(["CSS: .vidwin đứng riêng (position: fixed) và các quy tắc .vvbox/.vview không còn lồng trong .callcard", /\.vidwin \{[^}]*position: fixed/.test(css) && !/\.callcard \.vvbox|\.callcard \.vview|\.callcard \.vv-wait/.test(css)]);
  ok.push(["CSS: điện thoại đặt cửa sổ video phía trên (top) và hạ trần chiều cao video (--vcap: 40vh)", /html\[data-bp="phone"\] \.vidwin \{[^}]*top: \.625rem[^}]*--vcap: 40vh/.test(css)]);
  let bad = 0; for (const [n, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", n, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
