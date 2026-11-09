// Node harness for the incoming-file UI (file_inbox.py + app.js).
// Runs app.js in a vm with stubbed DOM/fetch and checks the file
// bubble rendering in the exact shapes that used to show an empty
// bubble:
//  - incoming file (kind=file, direction=in): bubbleText shows
//    "📎 <name> (<size>)" — never "Đã gửi file:" (that is for
//    outgoing only); the card shows a download anchor
//    (/api/file/download?...) + a "Chuyển tiếp" button once the
//    server reports status=downloaded.
//  - incoming file still downloading (has file_url, no registry
//    record yet): card shows "Đang tải về…", no download anchor.
//  - incoming file failed: card shows the error + "Tải lại" button.
//  - incoming photo with a downloaded record: renders <img> with
//    src=/api/file/download?... instead of an empty bubble.
//  - incoming photo without a record: file card (name + status),
//    never an empty bubble.
//  - outgoing file: plain "Đã gửi file: <name> (<size>)" text,
//    no download/forward actions.
// No browser needed.
//
// Run: node tests/test_app_js_filein.js  (exit 0 = pass)
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEl() {
  return {
    style: {}, dataset: {}, hidden: false, textContent: "",
    value: "", src: "", href: "", className: "", innerHTML: "",
    disabled: false, scrollTop: 0, scrollHeight: 0,
    children: [],
    classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {},
    appendChild(c) { this.children.push(c); },
    querySelectorAll() { return []; },
  };
}

const els = {};
const sandbox = {
  document: {
    getElementById: (id) => (els[id] || (els[id] = makeEl())),
    createElement: () => makeEl(),
    querySelectorAll: () => [],
  },
  fetch: async (url) => {
    if (url.indexOf("/api/file/list") !== -1) {
      return { status: 200, json: async () => ({ files: [] }) };
    }
    return { status: 200, json: async () => ({}) };
  },
  FormData: class {
    constructor() { this.fields = []; }
    append(k, v, name) { this.fields.push([k, name !== undefined ? name : v, v]); }
    get(k) { const f = this.fields.find((e) => e[0] === k); return f ? f[1] : null; }
  },
  Image: class {
    constructor() { setTimeout(() => { if (this.onload) this.onload(); }, 0); }
  },
  URL: { createObjectURL: () => "blob:x" },
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout, clearTimeout,
  Date, console, process, AbortController,
};

const src = fs.readFileSync(
  path.join(__dirname, "..", "zalo_pc_app", "static", "app.js"), "utf-8");

function findBubble() {
  const box = els["chat-history"];
  if (!box || !box.children.length) throw new Error("no bubble rendered");
  return box.children[box.children.length - 1];
}
function findByClass(el, cls) {
  if (!el) return null;
  if ((el.className || "").split(" ").indexOf(cls) !== -1) return el;
  for (const c of (el.children || [])) {
    const hit = findByClass(c, cls);
    if (hit) return hit;
  }
  return null;
}
function findByText(el, text) {
  if (!el) return null;
  if ((el.textContent || "").indexOf(text) !== -1) return el;
  for (const c of (el.children || [])) {
    const hit = findByText(c, text);
    if (hit) return hit;
  }
  return null;
}

const test = `
;(async () => {
  const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
  await new Promise((r) => setTimeout(r, 0));
  currentThread = { id: "20001", type: "user", name: "BenBap" };

  // 1. bubbleText: file den khong dung chu "Da gui file:".
  const inFile = { id: "f1", kind: "file", direction: "in",
    sender_id: "20001", file_name: "bao-cao.pdf", file_size: 11,
    file_url: "https://files.example/f/abc", time: 1762345700 };
  assert(bubbleText(inFile) === "📎 bao-cao.pdf (11 B)",
    "incoming bubbleText: " + bubbleText(inFile));
  const outFile = { id: "f2", kind: "file", direction: "out",
    sender_id: "me", file_name: "bao-cao.pdf", file_size: 11,
    time: 1762345700 };
  assert(bubbleText(outFile) === "Đã gửi file: bao-cao.pdf (11 B)",
    "outgoing bubbleText: " + bubbleText(outFile));

  // 2. File den da tai xong: the file co nut Tai xuong + Chuyen tiep.
  _threadFiles = { f1: { msg_id: "f1", file_name: "bao-cao.pdf",
    size_bytes: 11, status: "downloaded" } };
  renderMessages([inFile]);
  let b = findBubble();
  let card = findByClass(b, "bubble-file");
  assert(card, "incoming downloaded file must render a file card");
  const dl = findByText(card, "Tải xuống");
  assert(dl && dl.href && dl.href.indexOf("/api/file/download") !== -1
    && dl.href.indexOf("msg_id=f1") !== -1,
    "download anchor href: " + (dl && dl.href));
  assert(findByText(card, "Chuyển tiếp"), "forward button missing");

  // 3. File den dang tai: "Dang tai ve…", khong co nut Tai xuong.
  _threadFiles = {};
  renderMessages([inFile]);
  b = findBubble();
  card = findByClass(b, "bubble-file");
  assert(card, "incoming downloading file must render a file card");
  assert(findByText(card, "Đang tải về…"), "waiting text missing");
  assert(!findByText(card, "Tải xuống"), "no download anchor while pending");

  // 4. File den tai loi: hien loi + nut Tai lai.
  _threadFiles = { f1: { msg_id: "f1", file_name: "bao-cao.pdf",
    status: "failed", error: "tai file that bai (HTTP 404)" } };
  renderMessages([inFile]);
  b = findBubble();
  card = findByClass(b, "bubble-file");
  assert(findByText(card, "Tải lỗi"), "failed status missing");
  assert(findByText(card, "Tải lại"), "retry button missing");

  // 5. Anh den da tai xong: <img> voi src la download endpoint.
  const inPhoto = { id: "p1", kind: "photo", direction: "in",
    sender_id: "20001", file_name: "", file_url: "https://files.example/p/1",
    time: 1762345700 };
  _threadFiles = { p1: { msg_id: "p1", file_name: "anh.jpg",
    status: "downloaded" } };
  renderMessages([inPhoto]);
  b = findBubble();
  const img = findByClass(b, "bubble-img");
  assert(img && img.src && img.src.indexOf("/api/file/download") !== -1
    && img.src.indexOf("msg_id=p1") !== -1,
    "incoming photo img src: " + (img && img.src));

  // 6. Anh den chua tai xong: the file (khong bong bong trong).
  _threadFiles = {};
  renderMessages([inPhoto]);
  b = findBubble();
  assert(findByClass(b, "bubble-file"), "incoming pending photo needs a card");
  assert(findByText(b, "Đang tải về…"), "pending photo waiting text missing");

  // 7. File gui di: chi chu, khong co nut Tai xuong / Chuyen tiep.
  renderMessages([outFile]);
  b = findBubble();
  assert(!findByClass(b, "bubble-file"), "outgoing file must not render a card");
  assert(findByText(b, "Đã gửi file: bao-cao.pdf"),
    "outgoing file text missing");
})();
`;

vm.createContext(sandbox);
sandbox.findBubble = findBubble;
sandbox.findByClass = findByClass;
sandbox.findByText = findByText;
vm.runInContext(src + test, sandbox, { filename: "app.js+test" });
setTimeout(() => {
  console.log("ALL FILEIN JS TESTS PASSED");
}, 500);
