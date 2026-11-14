// Ảnh/video đến xem được trên WebUI và video gửi đi kèm chú thích (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_video_caption.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window, forms = [], errors = [];
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
w.URL.createObjectURL = () => "blob:x";
w.fetch = async (url, opts) => {
  let data = {};
  if (opts && opts.method === "POST" && opts.body instanceof w.FormData) {
    const o = {}; for (const [k, v] of opts.body.entries()) o[k] = typeof v === "string" ? v : "(tệp " + v.name + ")";
    forms.push([url, o]); data = { ok: true, message: { id: "m" + forms.length, kind: o.kind === "photo" ? "photo" : "video", text: o.desc || "", file_name: "cam.mp4", direction: "out", sender_id: "1", time: 1700000100 } };
  } else if (url === "/api/status") data = { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } };
  else if (url.startsWith("/api/reaction/list")) data = { reactions: {} };
  else if (url.startsWith("/api/contacts")) data = { friends: { rows: [] }, groups: { rows: [] } };
  else if (url.startsWith("/api/calls")) data = { active: null, calls: [] };
  return { status: 200, json: async () => data };
};
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  S.uid = "1"; S.cur = { id: "20001", type: "user", name: "Anh" }; S.files = {};
  const mk = (o) => T.normMsg(Object.assign({ sender_id: "20001", direction: "in", time: 1700000000 }, o));
  // ảnh đến, chưa tải về, chỉ có file_url
  let el = T.bubbleBody(mk({ id: "p1", kind: "photo", file_name: "a.jpg", text: "Ảnh đẹp", file_url: "https://cdn.example/a.jpg" }));
  let img = el.querySelector("img.photo");
  ok.push(["ảnh đến chưa tải: hiện <img> từ file_url kèm chú thích", !!img && img.src === "https://cdn.example/a.jpg" && /Ảnh đẹp/.test(el.textContent)]);
  img.dispatchEvent(new w.Event("error"));
  ok.push(["ảnh lỗi tải: quay về thẻ tệp có liên kết Mở", !el.querySelector("img.photo") && !!el.querySelector(".filecard a[href='https://cdn.example/a.jpg']")]);
  // video có chú thích
  el = T.bubbleBody(mk({ id: "v1", kind: "video", file_name: "cam.mp4", text: "🔔 Phát hiện chuyển động!", file_url: "https://cdn.example/cam.mp4" }));
  ok.push(["video đến: có trình phát và chú thích", !!el.querySelector("video.vid") && /Phát hiện chuyển động/.test(el.textContent)]);
  ok.push(["video có hình để phát: KHÔNG còn thẻ «Video 1.4 MB / Mở» dưới trình phát", !el.querySelector(".filecard") && !/Tải xuống|Mở/.test(el.textContent.replace("Phát hiện chuyển động!", "")), el.textContent]);
  el = T.bubbleBody(mk({ id: "v2", kind: "video", file_name: "cam.mp4", text: "cam.mp4", file_url: "https://cdn.example/cam.mp4" }));
  ok.push(["video không chú thích (text = tên tệp): không dòng chú thích", !el.querySelector(".photo-cap")]);
  el = T.bubbleBody(mk({ id: "v3", kind: "video", file_name: "x.mp4", text: "x.mp4" }));
  ok.push(["video chưa có địa chỉ nào để phát: giữ thẻ (còn chỗ bấm Tải lại/Mở)", !el.querySelector("video") && !!el.querySelector(".filecard")]);
  S.cur = S.cur; T.openMsgMenu(mk({ id: "v4", kind: "video", file_name: "cam.mp4", file_url: "https://cdn.example/cam.mp4", raw: { msgId: "v4", cliMsgId: "c4", uidFrom: "20001", ts: 1700000000 } }), 10, 10);
  const items = Array.from(w.document.querySelectorAll(".pop.msgmenu [role=menuitem]")).map((b) => b.textContent.trim());
  ok.push(["menu ba chấm của video có «Lưu về máy» và «Mở trong tab mới»", items.includes("Lưu về máy") && items.includes("Mở trong tab mới"), items.join("|")]);
  w.document.body.click();
  // gửi một video + chú thích: desc đi cùng, KHÔNG gửi thêm tin chữ riêng
  const f = new w.File([new Uint8Array(10)], "cam.mp4", { type: "video/mp4" });
  await T.sendFiles([f], "Xem cái này"); await sleep(50);
  const posts = forms.filter(([u]) => /sendfile/.test(u));
  ok.push(["gửi 1 video + chú thích: 1 lần sendfile, desc = chú thích", posts.length === 1 && posts[0][1].desc === "Xem cái này", JSON.stringify(forms)]);
  ok.push(["không gửi tin chữ riêng cho chú thích", forms.length === 1, JSON.stringify(forms)]);
  // video + chú thích kiểu đuôi .mov không có mime
  forms.length = 0;
  await T.sendFiles([new w.File([new Uint8Array(5)], "x.mov", { type: "" })], "Clip"); await sleep(50);
  ok.push(["video đuôi .mov (không mime) cũng nhận chú thích", forms.length === 1 && forms[0][1].desc === "Clip", JSON.stringify(forms)]);
  let bad = 0; for (const [n, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", n, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
