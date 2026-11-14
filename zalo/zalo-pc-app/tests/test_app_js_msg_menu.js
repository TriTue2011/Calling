// Menu tin nhắn kiểu Zalo PC trên WebUI (14/11/2026): cảm xúc dưới tin, menu chuột phải, trả lời cho ảnh/tệp, chuyển tiếp, lưu về máy, chọn nhiều, xóa phía tôi.
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_msg_menu.js  (không có jsdom: BỎ QUA, mã thoát 0)
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
const REACTS = { gid1: { "2": "/-heart", "1": "/-strong" } };
w.fetch = async (url, opts) => {
  let data = {};
  if (opts && opts.method === "POST") { let b = null; try { b = JSON.parse(opts.body); } catch (e) {} posts.push([url, b]); data = { ok: true }; }
  else if (url === "/api/status") data = { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } };
  else if (url.startsWith("/api/reaction/list")) data = { reactions: REACTS };
  else if (url.startsWith("/api/contacts")) data = { friends: { rows: [] }, groups: { rows: [] } };
  else if (url.startsWith("/api/calls")) data = { active: null, calls: [] };
  return { status: 200, json: async () => data };
};
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (id) => w.document.getElementById(id);
const tx = (t) => Array.from(w.document.querySelectorAll(".pop.msgmenu [role=menuitem]")).map((b) => b.textContent.trim()).filter((x) => x);
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  S.uid = "1"; S.cur = { id: "20001", type: "user", name: "Anh" };
  S.conv = { "user|20001": { thread_type: "user", thread_id: "20001", name: "Anh", last_ts: 5 }, "user|30002": { thread_type: "user", thread_id: "30002", name: "Chị Lan", last_ts: 9 }, "group|40003": { thread_type: "group", thread_id: "40003", name: "Nhóm nhà", last_ts: 7 } };
  const raw = (id, cli) => ({ msgId: id, cliMsgId: cli, uidFrom: "20001", ts: 1700000000 });
  const mk = (o) => T.normMsg(Object.assign({ sender_id: "20001", direction: "in", time: 1700000000 }, o));
  S.msgs = [mk({ id: "gid1", text: "Chào bạn", kind: "text", raw: raw("gid1", "c1") }),
            mk({ id: "gid2", kind: "photo", file_name: "a.jpg", text: "a.jpg", raw: raw("gid2", "c2") }),
            mk({ id: "gid3", kind: "text", text: "Tin của mình", sender_id: "1", direction: "out", raw: { msgId: "gid3", cliMsgId: "c3", uidFrom: "1", ts: 1700000001 } }),
            mk({ id: "gid4", kind: "text", text: "Tin cũ không mã", raw: null })];
  S.files = { gid2: { status: "downloaded", file_name: "a.jpg", size_bytes: 10 } };
  await T.loadReactions(); await sleep(50);
  const msgs = Array.from($("msgs").querySelectorAll(".msg"));
  const chips = msgs[0].querySelectorAll(".rchip");
  ok.push(["tin có cảm xúc hiện 2 chip (❤️ và 👍)", chips.length === 2 && /❤️/.test(msgs[0].textContent) && /👍/.test(msgs[0].textContent)]);
  ok.push(["chip của chính mình (uid 1) được tô nổi bật", !!msgs[0].querySelector(".rchip.mine")]);
  ok.push(["tin không có cảm xúc: không chip", msgs[1].querySelectorAll(".rchip").length === 0]);
  // menu chuột phải trên tin văn bản đến
  msgs[0].querySelector(".bub").dispatchEvent(new w.MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 50, clientY: 60 }));
  let items = tx();
  ok.push(["menu chuột phải mở, có thanh cảm xúc 6 nút", !!w.document.querySelector(".pop.msgmenu .rbar") && w.document.querySelectorAll(".pop.msgmenu .rbar button").length === 6]);
  ok.push(["tin văn bản đến: Trả lời, Chuyển tiếp, Sao chép, Chọn nhiều tin, Xóa chỉ ở phía tôi", ["Trả lời", "Chuyển tiếp", "Sao chép", "Chọn nhiều tin", "Xóa chỉ ở phía tôi"].every((x) => items.includes(x)), items.join("|")]);
  ok.push(["tin đến KHÔNG có «Thu hồi»", !items.includes("Thu hồi")]);
  w.document.querySelector(".pop.msgmenu .rbar button").click(); await sleep(50);
  ok.push(["bấm cảm xúc -> POST /api/svc/add_reaction đúng msg_id/cli_msg_id", posts.some(([u, b]) => u === "/api/svc/add_reaction" && b && b.msg_id === "gid1" && b.cli_msg_id === "c1" && b.icon === "like")]);
  // ảnh: trả lời được, lưu về máy có
  msgs[1].querySelector(".bub").dispatchEvent(new w.MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 50, clientY: 60 }));
  items = tx();
  ok.push(["tin ảnh: có Trả lời (trước đây chỉ tin văn bản) và Lưu về máy", items.includes("Trả lời") && items.includes("Lưu về máy"), items.join("|")]);
  Array.from(w.document.querySelectorAll(".pop.msgmenu [role=menuitem]")).find((b) => b.textContent.trim() === "Trả lời").click(); await sleep(30);
  ok.push(["trả lời ảnh: thanh trả lời hiện «[Ảnh] a.jpg»", !$("reply-bar").hidden && /\[Ảnh\] a\.jpg/.test($("reply-bar").textContent)]);
  $("msg-in").value = "đẹp quá"; $("btn-send").click(); await sleep(80);
  ok.push(["gửi trả lời ảnh -> POST quote_message kèm «[Ảnh] a.jpg»", posts.some(([u, b]) => u === "/api/svc/quote_message" && b && b.msg_id === "gid2" && b.qmsg === "[Ảnh] a.jpg" && b.text === "đẹp quá")]);
  // tin của mình: có Thu hồi
  msgs[2].querySelector(".bub").dispatchEvent(new w.MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
  ok.push(["tin của mình có «Thu hồi»", tx().includes("Thu hồi")]);
  w.document.body.click();
  // tin cũ không mã: không có Trả lời/cảm xúc/xóa phía tôi, vẫn chuyển tiếp được
  msgs[3].querySelector(".bub").dispatchEvent(new w.MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
  items = tx();
  ok.push(["tin cũ thiếu mã: không có Trả lời / Xóa phía tôi, không thanh cảm xúc", !items.includes("Trả lời") && !items.includes("Xóa chỉ ở phía tôi") && !w.document.querySelector(".pop.msgmenu .rbar") && items.includes("Chuyển tiếp"), items.join("|")]);
  w.document.body.click();
  // xóa chỉ phía tôi
  msgs[0].querySelector(".bub").dispatchEvent(new w.MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
  Array.from(w.document.querySelectorAll(".pop.msgmenu [role=menuitem]")).find((b) => b.textContent.trim() === "Xóa chỉ ở phía tôi").click(); await sleep(80);
  ok.push(["xóa phía tôi -> POST delete_message only_me + owner_id", posts.some(([u, b]) => u === "/api/svc/delete_message" && b && b.msg_id === "gid1" && b.only_me === true && b.owner_id === "20001")]);
  ok.push(["tin đã xóa biến khỏi khung chat", !/Chào bạn/.test($("msgs").textContent)]);
  // chuyển tiếp tin văn bản
  const m3 = S.msgs.find((m) => m._id === "gid3");
  T.openMsgMenu(m3, 10, 10);
  Array.from(w.document.querySelectorAll(".pop.msgmenu [role=menuitem]")).find((b) => b.textContent.trim() === "Chuyển tiếp").click(); await sleep(30);
  const rows = Array.from(w.document.querySelectorAll("#fwd-dlg .fwd-row"));
  ok.push(["hộp chuyển tiếp liệt kê hội thoại khác (không gồm hội thoại đang mở)", rows.length === 2 && !rows.some((r) => /Anh$/.test(r.textContent)), rows.map((r) => r.textContent).join("|")]);
  rows.find((r) => /Chị Lan/.test(r.textContent)).click(); await sleep(80);
  ok.push(["chuyển tiếp chữ -> POST /api/thread/30002/send kèm nội dung", posts.some(([u, b]) => u === "/api/thread/30002/send" && b && b.message === "Tin của mình" && b.type === "user")]);
  ok.push(["hộp chuyển tiếp đóng sau khi gửi", !w.document.getElementById("fwd-dlg")]);
  // chuyển tiếp ảnh đã tải -> /api/file/forward (loadHistory sau khi trả lời đã làm rỗng S.files: nạp lại như máy chủ thật sẽ trả)
  S.files = { gid2: { status: "downloaded", file_name: "a.jpg", size_bytes: 10 } };
  T.openMsgMenu(S.msgs.find((m) => m._id === "gid2"), 10, 10);
  Array.from(w.document.querySelectorAll(".pop.msgmenu [role=menuitem]")).find((b) => b.textContent.trim() === "Chuyển tiếp").click(); await sleep(30);
  Array.from(w.document.querySelectorAll("#fwd-dlg .fwd-row")).find((r) => /Nhóm nhà/.test(r.textContent)).click(); await sleep(80);
  ok.push(["chuyển tiếp ảnh đã tải -> POST /api/file/forward tới nhóm", posts.some(([u, b]) => u === "/api/file/forward" && b && b.msg_id === "gid2" && b.to_thread_type === "group" && b.to_thread_id === "40003")]);
  // chọn nhiều
  T.enterSelect(S.msgs.find((m) => m._id === "gid2")); await sleep(20);
  ok.push(["chọn nhiều: thanh «Đã chọn 1 tin» hiện", !$("selbar").hidden && /Đã chọn 1 tin/.test($("selbar").textContent)]);
  const bubs = $("msgs").querySelectorAll(".bub"); bubs[bubs.length - 1].click(); await sleep(20);
  ok.push(["bấm thêm tin -> «Đã chọn 2 tin»", /Đã chọn 2 tin/.test($("selbar").textContent)]);
  Array.from($("selbar").querySelectorAll("button")).find((b) => b.textContent === "Hủy").click(); await sleep(20);
  ok.push(["Hủy -> thoát chọn nhiều", $("selbar").hidden && S.sel === null]);
  let bad = 0; for (const [n, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", n, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
