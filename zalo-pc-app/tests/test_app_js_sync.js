// Node harness for the sync foot-note fix (issue 2). Runs app.js
// in a vm with stubbed DOM/fetch and proves the chat foot-note
// reflects the REAL /api/status sync state instead of the old
// hardcoded "kenh nhan tin (sync) chua co" text:
//
//   running       -> "dang chay", no retry button
//   no_endpoints  -> QR re-scan guidance + retry button shown
//   refresh_failed-> retry-first guidance + retry button shown
//   kicked_out    -> re-login guidance, no retry button
//   stopped       -> retry button shown
//
// Plus: the retry button POSTs /api/sync/retry and the note follows
// the response (running on success; 429 shows the wait in
// #chat-notice). No browser needed.
//
// Run: node tests/test_app_js_sync.js  (exit 0 = pass)
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEl() {
  return {
    style: {}, dataset: {}, hidden: false, textContent: "",
    value: "", src: "", className: "", innerHTML: "",
    options: [], selectedIndex: 0,
    classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {}, appendChild() {}, querySelectorAll() { return []; },
  };
}

const els = {};
const fetchCalls = [];
let statusSync = "running";
let retryResponse = { ok: true, sync: "running", sync_error: "" };
const sandbox = {
  document: {
    getElementById: (id) => (els[id] || (els[id] = makeEl())),
    createElement: () => makeEl(),
    createTextNode: (t) => ({ textContent: t }),
    querySelectorAll: () => [],
  },
  fetch: async (url, opts) => {
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    fetchCalls.push({ url, method: (opts && opts.method) || "GET", body });
    let data = {};
    if (url === "/api/status") {
      data = { login: true, uid: "10001", phonenum: "+84000000000",
               version: "test", engine: { detail: "" },
               sync: statusSync, sync_error: "" };
    } else if (url === "/api/contacts") {
      data = { friends: { rows: [] }, groups: { rows: [] } };
    } else if (url === "/api/calls") {
      data = { calls: [], active: null };
    } else if (url === "/api/inbox/summary") {
      data = { threads: [] };
    } else if (url === "/api/sync/retry") {
      data = retryResponse;
    }
    return { status: 200, json: async () => data };
  },
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout, clearTimeout,
  Date, console, process, fetchCalls,
  // The vm test code cannot reassign the Node-side retryResponse
  // variable (it would only set a vm global); route it through here.
  __setRetryResponse: (r) => { retryResponse = r; },
};

const src = fs.readFileSync(
  path.join(__dirname, "..", "zalo_pc_app", "static", "app.js"), "utf-8");

const test = `
;(async () => {
  const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
  const note = () => document.getElementById("chat-sync-note").textContent;
  const retryBtn = () => document.getElementById("btn-sync-retry");
  // Let the startup loadMain() settle (login:true path, empty lists).
  await new Promise((r) => setTimeout(r, 50));

  // --- Test 1: loadMain paints the note from /api/status ---
  // statusSync starts as "running": the old hardcoded "chua co"
  // text must be gone, replaced by the running text, no retry btn.
  assert(note().indexOf("đang chạy") !== -1,
    "running note must say dang chay, got: " + JSON.stringify(note()));
  assert(note().indexOf("chưa có") === -1,
    "running note must NOT keep the old 'chua co' text, got: "
    + JSON.stringify(note()));
  assert(retryBtn().hidden === true,
    "running must hide the retry button");

  // --- Test 2: mapping for every sync state ---
  const cases = [
    ["no_endpoints", "quét QR", true],
    ["refresh_failed", "Thử kết nối lại", true],
    ["kicked_out", "quét QR", false],
    ["stopped", "Thử kết nối lại", true],
    ["logged_out", "Chưa đăng nhập", false],
  ];
  for (const [state, frag, showRetry] of cases) {
    updateSyncNote(state);
    assert(note().indexOf(frag) !== -1,
      state + " note must mention " + JSON.stringify(frag)
      + ", got: " + JSON.stringify(note()));
    assert(retryBtn().hidden === !showRetry,
      state + " retry hidden must be " + (!showRetry)
      + ", got: " + retryBtn().hidden);
  }
  // refresh_failed must NOT tell the user to re-scan QR first —
  // the retry is the first action; QR is only the fallback.
  updateSyncNote("refresh_failed");
  assert(note().indexOf("Bấm “Thử kết nối lại”") !== -1,
    "refresh_failed must lead with retry, got: " + JSON.stringify(note()));
  // no_endpoints must name the QR re-scan (the only fix then).
  updateSyncNote("no_endpoints");
  assert(note().indexOf("quét QR lại") !== -1,
    "no_endpoints must name the QR re-scan, got: " + JSON.stringify(note()));

  // --- Test 3: retry button POSTs and follows the response ---
  updateSyncNote("refresh_failed");
  fetchCalls.length = 0;
  await retryBtn().onclick();
  const req = fetchCalls.find((c) => c.url === "/api/sync/retry");
  assert(req, "retry button must POST /api/sync/retry");
  assert(req.method === "POST", "retry must be a POST");
  assert(note().indexOf("đang chạy") !== -1,
    "after a successful retry the note must say running, got: "
    + JSON.stringify(note()));
  assert(retryBtn().hidden === true,
    "after a successful retry the button must hide");

  // --- Test 4: retry cooldown (429) shows the wait, keeps state ---
  __setRetryResponse({ ok: false, sync: "refresh_failed",
                       sync_error: "RuntimeError",
                       retry_after_seconds: 25 });
  updateSyncNote("refresh_failed");
  await retryBtn().onclick();
  assert(document.getElementById("chat-notice").hidden === false,
    "cooldown must show the wait in #chat-notice");
  assert(document.getElementById("chat-notice").textContent.indexOf("25") !== -1,
    "cooldown notice must carry the wait seconds, got: "
    + JSON.stringify(document.getElementById("chat-notice").textContent));
  assert(note().indexOf("Thử kết nối lại") !== -1,
    "after a failed retry the note must stay on refresh_failed, got: "
    + JSON.stringify(note()));

  console.log("APP_JS_SYNC_TESTS_PASSED");
})().catch((e) => { console.error("APP_JS_SYNC_TESTS_FAILED", e); process.exit(1); });
`;

vm.runInNewContext(src + test, sandbox);
