// Node harness for the chat attach fix (bug 23:00 +07). Runs app.js
// in a vm with stubbed DOM/fetch and exercises sendChatFile() in the
// exact live-broken shapes:
//  - fetch rejects (network error) or returns non-JSON: the old code
//    let the promise reject unhandled (onchange does not catch), so
//    the user saw NOTHING. Now chat-notice must show the error.
//  - empty (0-byte) file: rejected client-side with a specific
//    message, no fetch at all.
//  - gif/heic: sent as kind=file, never kind=photo (Node.js EXT_ALBUM
//    rule: only jpg/jpeg/png/webp are photos).
//  - real jpg photo: kind=photo with width/height from the image.
//  - server error JSON: notice shows "Lỗi gửi file: ...".
//  - success: notice hidden, message appended.
// No browser needed.
//
// Run: node tests/test_app_js_attach.js  (exit 0 = pass)
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEl() {
  return {
    style: {}, dataset: {}, hidden: false, textContent: "",
    value: "", src: "", className: "", innerHTML: "",
    disabled: false, scrollTop: 0, scrollHeight: 0,
    classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {}, appendChild() {}, querySelectorAll() { return []; },
  };
}

const els = {};
let fetchMode = "ok"; // ok | error-json | reject | bad-json
const fetchCalls = [];
const sandbox = {
  document: {
    getElementById: (id) => (els[id] || (els[id] = makeEl())),
    createElement: () => makeEl(),
    querySelectorAll: () => [],
  },
  fetch: async (url, opts) => {
    fetchCalls.push({ url, method: (opts && opts.method) || "GET",
                      form: opts && opts.body });
    if (url === "/api/status") {
      return { status: 200, json: async () => ({ login: false }) };
    }
    if (fetchMode === "reject") throw new Error("Failed to fetch");
    if (fetchMode === "bad-json") {
      return { status: 502,
               json: async () => { throw new Error("Unexpected token < in JSON"); } };
    }
    if (fetchMode === "error-json") {
      return { status: 502,
               json: async () => ({ error: "chat: POST /api/message/sharefile_full error_code=133 File rong" }) };
    }
    return { status: 200,
             json: async () => ({ ok: true,
               message: { id: "1", kind: "file", text: "x.txt",
                          sender_id: "me", direction: "out",
                          time: 1762345600 } }) };
  },
  FormData: class {
    constructor() { this.fields = []; }
    append(k, v, name) { this.fields.push([k, name !== undefined ? name : v, v]); }
    get(k) { const f = this.fields.find((e) => e[0] === k); return f ? f[1] : null; }
  },
  Image: class {
    constructor() {
      this.naturalWidth = 800;
      this.naturalHeight = 600;
      setTimeout(() => { if (this.onload) this.onload(); }, 0);
    }
  },
  URL: { createObjectURL: () => "blob:x" },
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout, clearTimeout,
  Date, console, process, fetchCalls,
};
sandbox.__setFetchMode = (m) => { fetchMode = m; };

const src = fs.readFileSync(
  path.join(__dirname, "..", "zalo_pc_app", "static", "app.js"), "utf-8");

const test = `
;(async () => {
  const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
  const notice = () => document.getElementById("chat-notice");
  const sendfileCalls = () => fetchCalls.filter(
    (c) => c.url.indexOf("/sendfile") !== -1);
  await new Promise((r) => setTimeout(r, 0));
  currentThread = { id: "20001", type: "user" };

  // --- Test 1: server error JSON -> visible, specific message ---
  __setFetchMode("error-json");
  await sendChatFile({ name: "x.txt", type: "text/plain", size: 5 });
  assert(notice().textContent.indexOf("Lỗi gửi file:") !== -1,
    "error JSON must show notice, got: " + JSON.stringify(notice().textContent));
  assert(notice().textContent.indexOf("133") !== -1,
    "notice must carry the Zalo error, got: " + JSON.stringify(notice().textContent));
  assert(document.getElementById("btn-chat-attach").disabled === false,
    "attach button must be re-enabled after failure");

  // --- Test 2: fetch rejects -> MUST show an error (the live bug) ---
  notice().textContent = "";
  __setFetchMode("reject");
  await sendChatFile({ name: "x.txt", type: "text/plain", size: 5 });
  assert(notice().textContent.indexOf("Lỗi gửi file:") !== -1,
    "fetch reject must show notice, got: " + JSON.stringify(notice().textContent));
  assert(notice().textContent.indexOf("Failed to fetch") !== -1,
    "notice must name the cause, got: " + JSON.stringify(notice().textContent));

  // --- Test 3: non-JSON response -> MUST show an error ---
  notice().textContent = "";
  __setFetchMode("bad-json");
  await sendChatFile({ name: "x.txt", type: "text/plain", size: 5 });
  assert(notice().textContent.indexOf("Lỗi gửi file:") !== -1,
    "non-JSON response must show notice, got: " + JSON.stringify(notice().textContent));

  // --- Test 4: empty file (user's live case) -> blocked, no fetch ---
  notice().textContent = "";
  const before = sendfileCalls().length;
  __setFetchMode("ok");
  await sendChatFile({ name: "iptv-udpxy.m3u", type: "", size: 0 });
  assert(sendfileCalls().length === before,
    "empty file must not reach the server");
  assert(notice().textContent.indexOf("rỗng (0 byte)") !== -1,
    "empty file needs a specific message, got: " + JSON.stringify(notice().textContent));

  // --- Test 5: GIF sent as file, never as photo ---
  notice().textContent = "";
  await sendChatFile({ name: "a.gif", type: "image/gif", size: 120 });
  const gifForm = sendfileCalls()[sendfileCalls().length - 1].form;
  assert(gifForm.get("kind") === "file",
    "gif must go as kind=file, got: " + gifForm.get("kind"));
  assert(gifForm.get("width") === null,
    "gif-as-file must not carry photo width/height");

  // --- Test 6: HEIC sent as file, never as photo ---
  await sendChatFile({ name: "anh.heic", type: "image/heic", size: 120 });
  const heicForm = sendfileCalls()[sendfileCalls().length - 1].form;
  assert(heicForm.get("kind") === "file",
    "heic must go as kind=file, got: " + heicForm.get("kind"));

  // --- Test 7: real JPG photo -> kind=photo + width/height ---
  await sendChatFile({ name: "anh.jpg", type: "image/jpeg", size: 120 });
  const jpgForm = sendfileCalls()[sendfileCalls().length - 1].form;
  assert(jpgForm.get("kind") === "photo",
    "jpg must go as kind=photo, got: " + jpgForm.get("kind"));
  assert(jpgForm.get("width") === "800" && jpgForm.get("height") === "600",
    "photo must carry real dimensions, got: " + jpgForm.get("width") + "x" + jpgForm.get("height"));

  // --- Test 8: oversize photo blocked client-side ---
  notice().textContent = "";
  const before2 = sendfileCalls().length;
  await sendChatFile({ name: "lon.jpg", type: "image/jpeg",
                       size: 26 * 1024 * 1024 });
  assert(sendfileCalls().length === before2,
    "oversize photo must not reach the server");
  assert(notice().textContent.indexOf("quá lớn") !== -1
         && notice().textContent.indexOf("25 MB") !== -1,
    "oversize photo needs the limit in the message, got: " + JSON.stringify(notice().textContent));

  // --- Test 9: success -> notice hidden, no error left ---
  notice().textContent = "";
  await sendChatFile({ name: "hello.txt", type: "text/plain", size: 5 });
  assert(notice().hidden === true,
    "notice must hide on success");
  assert(document.getElementById("btn-chat-attach").disabled === false,
    "attach button must be re-enabled after success");

  // --- Test 10: no thread open -> specific message, no fetch ---
  const before3 = sendfileCalls().length;
  currentThread = null;
  await sendChatFile({ name: "hello.txt", type: "text/plain", size: 5 });
  assert(sendfileCalls().length === before3,
    "no thread must not fetch");
  assert(notice().textContent.indexOf("Chưa mở đoạn chat") !== -1,
    "no thread needs a specific message, got: " + JSON.stringify(notice().textContent));

  console.log("APP_JS_ATTACH_TESTS_PASSED");
})().catch((e) => { console.error("APP_JS_ATTACH_TESTS_FAILED", e); process.exit(1); });
`;

vm.runInNewContext(src + test, sandbox);
