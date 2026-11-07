// Node harness for the app.js End-button fix (§7m). Runs app.js in
// a vm with stubbed DOM/fetch and exercises endCall() in the exact
// live-broken shape: a call that is active on the server but
// currentCall/detailCall are null (page reloaded after the call
// started) — the old endCall() sent NOTHING then, so the rail's End
// button was dead. Also checks the detail view shows the step-2
// diagnostic (request_sent / request_error). No browser needed.
//
// Run: node tests/test_app_js_end.js  (exit 0 = pass)
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEl() {
  return {
    style: {}, dataset: {}, hidden: false, textContent: "",
    value: "", src: "", className: "", innerHTML: "",
    classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {}, appendChild() {}, querySelectorAll() { return []; },
  };
}

const els = {};
const fetchCalls = [];
const sandbox = {
  document: {
    getElementById: (id) => (els[id] || (els[id] = makeEl())),
    createElement: () => makeEl(),
    querySelectorAll: () => [],
  },
  fetch: async (url, opts) => {
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    fetchCalls.push({ url, method: (opts && opts.method) || "GET", body });
    let data = {};
    if (url === "/api/status") {
      data = { login: false, version: "test", engine: { detail: "" } };
    } else if (url === "/api/call/end") {
      data = { ok: true, ended_call_id: body.call_id,
               zalo_endcall_ok: true, zalo_error: "", data: {} };
    } else if (url === "/api/calls") {
      data = { calls: [{ call_id: "1762346001", peer: "Ban A",
                         thread_id: "20001", type: "user",
                         status: "ended", started_at: 1762346001,
                         ended_at: 1762346010, detail: "",
                         request_sent: true, request_detail: "" }],
               active: null };
    }
    return { json: async () => data };
  },
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout, clearTimeout,
  Date, console, process, fetchCalls,
};

const src = fs.readFileSync(
  path.join(__dirname, "..", "zalo_pc_app", "static", "app.js"), "utf-8");

const test = `
;(async () => {
  const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
  // Let the startup loadMain() settle (it takes the not-logged-in
  // path and returns before any contacts fetch).
  await new Promise((r) => setTimeout(r, 0));

  // --- Test 1: End from server state after a reload ---
  // currentCall/detailCall are null (page reloaded after the call
  // started); the live call is known only via callsData.active.
  callsData = { calls: [{ call_id: "1762346001", peer: "Ban A",
    thread_id: "20001", type: "user", status: "sent",
    started_at: 1762346001, ended_at: null, detail: "",
    request_sent: true, request_detail: "" }], active: null };
  callsData.active = callsData.calls[0];
  currentCall = null;
  detailCall = null;
  await endCall();
  const endReq = fetchCalls.find((c) => c.url === "/api/call/end");
  assert(endReq, "endCall must POST /api/call/end");
  assert(endReq.body.call_id === 1762346001,
    "call_id must be a JSON number, got: " + JSON.stringify(endReq.body));
  assert(endReq.body.uid_to === "20001",
    "uid_to must be the thread id, got: " + JSON.stringify(endReq.body));
  assert(callsData.active === null,
    "active must clear optimistically, before the poll returns");

  // --- Test 2: detail view shows the step-2 diagnostic ---
  callsData = { calls: [], active: null };
  showCallDetail({ call_id: "1762346002", peer: "Ban B",
    thread_id: "20002", type: "user", status: "sent",
    started_at: 1762346002, request_sent: false,
    request_detail: "response inner error_code=114 Tham số không hợp lệ" });
  const reqText = document.getElementById("call-request").textContent;
  assert(reqText.indexOf("KHÔNG gửi được") !== -1,
    "detail must show the failed step-2, got: " + JSON.stringify(reqText));
  assert(reqText.indexOf("114") !== -1,
    "detail must carry the step-2 error code, got: " + JSON.stringify(reqText));

  // --- Test 3: end reason maps to Vietnamese ---
  // The server records WHY a call ended in the entry's detail
  // ("user_end", "superseded_by_new_call", "user_end; zalo_endcall:
  // ..."); the history must show it in plain Vietnamese, not the
  // raw key. (historyRow itself builds stub DOM elements whose
  // children cannot be read back here, so the mapping is tested
  // directly.)
  assert(endReasonText("user_end").indexOf("Kết thúc") !== -1,
    "endReasonText must map user_end to Vietnamese");
  assert(endReasonText("superseded_by_new_call")
      .indexOf("thay bằng cuộc gọi mới") !== -1,
    "endReasonText must map superseded_by_new_call to Vietnamese");
  assert(endReasonText("user_end; zalo_endcall: mock endcall rejected")
      .indexOf("chưa xác nhận") !== -1,
    "endReasonText must keep the Zalo failure after user_end");

  // --- Test 4: double tap on "Gọi" sends one invitation only ---
  // startCall has no server round-trip guard in the old code: two
  // rapid taps fired two concurrent /api/call/request calls (two
  // different callIds), so the peer's phone got TWO invitations.
  // The second tap while a request is in flight must be ignored.
  const reqBefore = fetchCalls.filter(
    (c) => c.url === "/api/call/request").length;
  const p1 = startCall({ id: "20001", name: "Ban A", type: "user" });
  const p2 = startCall({ id: "20001", name: "Ban A", type: "user" });
  await Promise.all([p1, p2]);
  const reqAfter = fetchCalls.filter(
    (c) => c.url === "/api/call/request");
  assert(reqAfter.length - reqBefore === 1,
    "double tap must send exactly one /api/call/request, got: "
    + (reqAfter.length - reqBefore));
  // The guard clears after the request finishes: a later tap works.
  await startCall({ id: "20001", name: "Ban A", type: "user" });
  const reqFinal = fetchCalls.filter(
    (c) => c.url === "/api/call/request");
  assert(reqFinal.length - reqBefore === 2,
    "a later tap after the first request must send again, got: "
    + (reqFinal.length - reqBefore));

  console.log("APP_JS_END_TESTS_PASSED");
})().catch((e) => { console.error("APP_JS_END_TESTS_FAILED", e); process.exit(1); });
`;

vm.runInNewContext(src + test, sandbox);
