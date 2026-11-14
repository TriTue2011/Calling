// Bong bóng ảnh/video/tệp trên WebUI (14/11/2026): video phát ngay trong bong bóng + nút tải; ảnh gửi từ HA (tệp .jpg) hiện ảnh; tin CỦA MÌNH có nút tải khi đã có bản sao.
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_media_bubbles.js  (không có jsdom thì BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window; const errors = [];
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
w.fetch = async (url) => ({ status: 200, json: async () => (url === "/api/status" ? { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } } : url.startsWith("/api/contacts") ? { friends: { rows: [] }, groups: { rows: [] } } : {}) });
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };   // app.js đưa S/bubbleBody ra qua móc kiểm thử
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  await sleep(300);
  const T = w.__t; T.S.cur = { id: "20001", type: "user", name: "Anh" };
  const render = (m, rec) => { T.S.files = rec ? { [m._id]: rec } : {}; const el = T.bubbleBody(m); const box = w.document.createElement("div"); if (el.nodeType) box.appendChild(el); return box; };
  const ok = [];
  // 1) video đã tải: có <video controls src=/api/file/download…> + «Tải xuống»
  let b = render({ _id: "v1", kind: "file", file_name: "cam.mp4", file_size: 1500000 }, { status: "downloaded", file_name: "cam.mp4", size_bytes: 1500000 });
  let v = b.querySelector("video.vid");
  ok.push(["video đã tải -> có <video controls>", !!v && v.hasAttribute("controls") && /\/api\/file\/download\?.*msg_id=v1/.test(v.getAttribute("src"))]);
  ok.push(["video đã tải -> nút Tải xuống", !!Array.from(b.querySelectorAll("a")).find((a) => a.textContent === "Tải xuống" && a.getAttribute("download"))]);
  ok.push(["video đã tải -> hiện cỡ tệp", /1\.4 MB/.test(b.textContent)]);
  // 2) video chưa tải nhưng có địa chỉ Zalo: phát từ địa chỉ, nút Mở
  b = render({ _id: "v2", kind: "file", file_name: "cam.mp4", file_url: "https://f.example/v.mp4" }, null);
  v = b.querySelector("video.vid");
  ok.push(["video chưa tải có file_url -> <video src=file_url>", !!v && v.getAttribute("src") === "https://f.example/v.mp4"]);
  // 3) tin video của MÌNH (kind video) có bản sao -> phát được
  b = render({ _id: "v3", kind: "video", _out: true, file_name: "video" }, { status: "downloaded", file_name: "clip.mp4", size_bytes: 2048 });
  ok.push(["video của mình có bản sao -> <video>", !!b.querySelector("video.vid")]);
  // 4) ảnh gửi từ HA ghi là «tệp» .jpg và có bản sao -> hiện <img>
  b = render({ _id: "p1", kind: "file", _out: true, file_name: "go2rtc_cua_gui1.jpg" }, { status: "downloaded", file_name: "go2rtc_cua_gui1.jpg", size_bytes: 120000 });
  ok.push(["tệp .jpg của mình đã có bản sao -> <img>", !!b.querySelector("img.photo") && /api\/file\/download/.test(b.querySelector("img.photo").getAttribute("src"))]);
  // 5) tệp thường của MÌNH có bản sao -> có nút Tải xuống (trước đây bị ẩn với tin của mình)
  b = render({ _id: "f1", kind: "file", _out: true, file_name: "bao-cao.pdf", file_size: 5000 }, { status: "downloaded", file_name: "bao-cao.pdf", size_bytes: 5000 });
  ok.push(["tệp của mình có bản sao -> Tải xuống", !!Array.from(b.querySelectorAll("a")).find((a) => a.textContent === "Tải xuống")]);
  // 6) tệp của mình CHƯA có bản sao: không có nút tải, vẫn hiện tên
  b = render({ _id: "f2", kind: "file", _out: true, file_name: "cu.pdf" }, null);
  ok.push(["tệp của mình chưa có bản sao -> chỉ tên, không nút", /cu\.pdf/.test(b.textContent) && !Array.from(b.querySelectorAll("a")).length]);
  // 7) tin đến thường: không đổi
  b = render({ _id: "f3", kind: "file", file_name: "tai-lieu.docx" }, { status: "downloaded", file_name: "tai-lieu.docx", size_bytes: 10 });
  ok.push(["tệp đến đã tải -> Tải xuống", !!Array.from(b.querySelectorAll("a")).find((a) => a.textContent === "Tải xuống") && !b.querySelector("video")]);
  let bad = 0; for (const [n, v2] of ok) { console.log(v2 ? "ĐẠT " : "HỎNG", n); if (!v2) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
