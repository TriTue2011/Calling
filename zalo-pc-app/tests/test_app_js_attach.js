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
// Multi-file (sendChatFiles): 3 photos -> 3 sendfile calls in
// order + "Đã gửi 3/3"; a failed middle file does not stop the
// rest and is named in the summary; an invalid middle file never
// reaches the server; single file behaves exactly as before.
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
let fetchMode = "ok"; // ok | error-json | reject | bad-json | hang
let failAtSendfile = 0; // 0 = khong fail rieng le; n>0: sendfile thu n tra loi 405
let sendfileCount = 0;
let imageStuck = false; // true: Image khong bao gio goi onload/onerror (giai ma ket)
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
    if (url.indexOf("/sendfile") !== -1) {
      sendfileCount++;
      if (failAtSendfile > 0 && sendfileCount === failAtSendfile) {
        return { status: 502,
                 json: async () => ({ error: "chat: POST /api/message/photo network status=405" }) };
      }
    }
    if (fetchMode === "hang") {
      // Treo mai nhung ton trong AbortSignal (nhu trinh duyet that):
      // abort -> reject AbortError; khong thi khong bao gio resolve.
      return new Promise((resolve, reject) => {
        const sig = opts && opts.signal;
        const onAbort = () => {
          const e = new Error("The user aborted a request.");
          e.name = "AbortError";
          reject(e);
        };
        if (!sig) return; // khong co signal: treo vinh vien
        if (sig.aborted) onAbort();
        else sig.addEventListener("abort", onAbort);
      });
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
      if (!imageStuck) setTimeout(() => { if (this.onload) this.onload(); }, 0);
    }
  },
  URL: { createObjectURL: () => "blob:x" },
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout, clearTimeout,
  Date, console, process, fetchCalls, AbortController,
};
sandbox.__setFetchMode = (m) => { fetchMode = m; };
sandbox.__setFailAtSendfile = (n) => { failAtSendfile = n; sendfileCount = 0; };
sandbox.__setImageStuck = (v) => { imageStuck = v; };

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

  // --- Test 11: 3 photos at once -> 3 sendfile calls, in order ---
  currentThread = { id: "20001", type: "user" };
  notice().textContent = "";
  __setFetchMode("ok");
  __setFailAtSendfile(0);
  const fileNameOf = (c) => {
    const f = c.form.fields.find((e) => e[0] === "file");
    return f ? f[1] : null;
  };
  const before4 = sendfileCalls().length;
  await sendChatFiles([
    { name: "a.jpg", type: "image/jpeg", size: 120 },
    { name: "b.jpg", type: "image/jpeg", size: 120 },
    { name: "c.jpg", type: "image/jpeg", size: 120 },
  ]);
  const calls11 = sendfileCalls().slice(before4);
  assert(calls11.length === 3,
    "3 files must make 3 sendfile calls, got: " + calls11.length);
  assert(fileNameOf(calls11[0]) === "a.jpg"
         && fileNameOf(calls11[1]) === "b.jpg"
         && fileNameOf(calls11[2]) === "c.jpg",
    "files must go in selection order");
  assert(notice().textContent.indexOf("Đã gửi 3/3") !== -1,
    "summary must say 3/3, got: " + JSON.stringify(notice().textContent));
  assert(document.getElementById("btn-chat-attach").disabled === false,
    "attach button must be re-enabled after multi send");

  // --- Test 12: middle file fails -> others still go, summary names it ---
  notice().textContent = "";
  __setFailAtSendfile(2);
  const before5 = sendfileCalls().length;
  await sendChatFiles([
    { name: "a.jpg", type: "image/jpeg", size: 120 },
    { name: "b.jpg", type: "image/jpeg", size: 120 },
    { name: "c.jpg", type: "image/jpeg", size: 120 },
  ]);
  const calls12 = sendfileCalls().slice(before5);
  assert(calls12.length === 3,
    "a failed file must not stop the rest, got: " + calls12.length + " calls");
  assert(notice().textContent.indexOf("Đã gửi 2/3") !== -1,
    "summary must say 2/3, got: " + JSON.stringify(notice().textContent));
  assert(notice().textContent.indexOf("b.jpg") !== -1,
    "summary must name the failed file, got: " + JSON.stringify(notice().textContent));
  __setFailAtSendfile(0);

  // --- Test 13: single file via sendChatFiles -> same as before ---
  notice().textContent = "";
  const before6 = sendfileCalls().length;
  await sendChatFiles([{ name: "mot.jpg", type: "image/jpeg", size: 120 }]);
  assert(sendfileCalls().length === before6 + 1,
    "single file must make exactly 1 call");
  assert(notice().hidden === true,
    "single-file success must hide the notice as before");

  // --- Test 14: invalid file in the middle -> no fetch, counted failed ---
  notice().textContent = "";
  const before7 = sendfileCalls().length;
  await sendChatFiles([
    { name: "a.jpg", type: "image/jpeg", size: 120 },
    { name: "rong.jpg", type: "image/jpeg", size: 0 },
    { name: "c.jpg", type: "image/jpeg", size: 120 },
  ]);
  assert(sendfileCalls().length === before7 + 2,
    "invalid file must not reach the server, got: "
    + (sendfileCalls().length - before7) + " calls");
  assert(notice().textContent.indexOf("Đã gửi 2/3") !== -1,
    "summary must say 2/3, got: " + JSON.stringify(notice().textContent));
  assert(notice().textContent.indexOf("rong.jpg") !== -1,
    "summary must name the invalid file, got: " + JSON.stringify(notice().textContent));

  // --- Test 15: no thread + multiple files -> no fetch, specific message ---
  notice().textContent = "";
  const before8 = sendfileCalls().length;
  currentThread = null;
  await sendChatFiles([
    { name: "a.jpg", type: "image/jpeg", size: 120 },
    { name: "b.jpg", type: "image/jpeg", size: 120 },
  ]);
  assert(sendfileCalls().length === before8,
    "no thread must not fetch");
  assert(notice().textContent.indexOf("Chưa mở đoạn chat") !== -1,
    "no thread needs a specific message, got: " + JSON.stringify(notice().textContent));

  // --- Test 16: fetch treo -> timeout cua apiForm phai bao loi ---
  // (loi cam 07/11: khong co timeout thi UI ket o "Dang gui..."
  // mai, khong co loi nao). Test 15 de currentThread = null nen
  // mo lai thread truoc.
  currentThread = { id: "20001", type: "user" };
  notice().textContent = "";
  API_FORM_TIMEOUT_MS = 100;
  __setFetchMode("hang");
  const t16 = await sendChatFile({ name: "anh.jpg", type: "image/jpeg", size: 120 });
  assert(t16.ok === false,
    "hung fetch must fail, got: " + JSON.stringify(t16));
  assert(notice().textContent.indexOf("hết thời gian chờ") !== -1,
    "hung fetch must show the timeout error, got: " + JSON.stringify(notice().textContent));
  assert(document.getElementById("btn-chat-attach").disabled === false,
    "attach button must be re-enabled after timeout");
  __setFetchMode("ok");
  API_FORM_TIMEOUT_MS = 90000;

  // --- Test 17: giai ma anh ket -> gui voi 0x0, khong treo ---
  notice().textContent = "";
  IMAGE_DIMS_TIMEOUT_MS = 50;
  __setImageStuck(true);
  const before9 = sendfileCalls().length;
  const t17 = await sendChatFile({ name: "anh.jpg", type: "image/jpeg", size: 120 });
  __setImageStuck(false);
  IMAGE_DIMS_TIMEOUT_MS = 5000;
  assert(t17.ok === true,
    "stuck image decode must still send, got: " + JSON.stringify(t17));
  assert(sendfileCalls().length === before9 + 1,
    "stuck decode must reach the server");
  const stuckForm = sendfileCalls()[sendfileCalls().length - 1].form;
  assert(stuckForm.get("width") === "0" && stuckForm.get("height") === "0",
    "stuck decode must fall back to 0x0, got: "
    + stuckForm.get("width") + "x" + stuckForm.get("height"));

  // --- Test 18: banner loi gui khong bi xoa khi mo lai thread ---
  // (loi cam 07/11: gui anh loi, mo lai doan chat de goi thi
  // loadThreadHistory an banner, tuong la khong co loi gi).
  notice().textContent = "";
  __setFetchMode("error-json");
  await sendChatFile({ name: "x.txt", type: "text/plain", size: 5 });
  assert(notice().textContent.indexOf("Lỗi gửi file:") !== -1,
    "setup: send must fail first, got: " + JSON.stringify(notice().textContent));
  // Lich su tai lai thanh cong (chi sendfile loi) — banner loi gui
  // van phai con sau khi mo lai thread.
  __setFetchMode("ok");
  await loadThreadHistory();
  assert(notice().hidden === false,
    "send error must survive reopening the thread");
  assert(notice().textContent.indexOf("Lỗi gửi file:") !== -1,
    "send error text must survive, got: " + JSON.stringify(notice().textContent));

  // --- Test 19: loi cua thread khac khong hien sang thread nay ---
  currentThread = { id: "30001", type: "group" };
  await loadThreadHistory();
  assert(notice().hidden === true,
    "another thread's send error must not show here, got: "
    + JSON.stringify(notice().textContent));
  currentThread = { id: "20001", type: "user" };

  // --- Test 20: gui thanh cong xoa loi cu — mo lai thread het banner ---
  notice().textContent = "";
  __setFetchMode("ok");
  await sendChatFile({ name: "hello.txt", type: "text/plain", size: 5 });
  assert(notice().hidden === true,
    "setup: success must hide the notice");
  await loadThreadHistory();
  assert(notice().hidden === true,
    "after a success, reopening must not resurrect the old error");

  console.log("APP_JS_ATTACH_TESTS_PASSED");
})().catch((e) => { console.error("APP_JS_ATTACH_TESTS_FAILED", e); process.exit(1); });
`;

vm.runInNewContext(src + test, sandbox);
