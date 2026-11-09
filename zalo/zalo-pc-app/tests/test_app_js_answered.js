// Node harness for the answered-call UI (2026-11-08 fix). Before
// this fix the app had no "answered" state at all: a call the peer
// picked up still showed "Đang đổ chuông" until the ring timer
// killed it at 30s. Now statusPill() says "Đang gọi" for
// "answered", the top-bar pill follows, and the active card says
// plainly "Đã nối — chưa có tiếng (thiếu khoá SRTP)" when the call
// is connected but SRTP is unwired.
//
// Run: node tests/test_app_js_answered.js  (exit 0 = pass)
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function makeEl(tag) {
  const el = {
    tagName: (tag || "div").toUpperCase(),
    children: [],
    style: {}, dataset: {}, hidden: false, textContent: "",
    value: "", src: "", className: "", innerHTML: "",
    classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {},
    appendChild(child) { el.children.push(child); return child; },
    querySelectorAll() { return []; },
  };
  return el;
}

const els = {};
let callsPayload = { calls: [], active: null };
const posted = []; // {url, body} of every POST the UI makes
const sandbox = {
  document: {
    getElementById: (id) => (els[id] || (els[id] = makeEl())),
    createElement: (tag) => makeEl(tag),
    createTextNode: (text) => {
      const el = makeEl();
      el.textContent = text;
      return el;
    },
    querySelectorAll: () => [],
  },
  fetch: async (url, opts) => {
    if (opts && opts.method === "POST") {
      posted.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
    }
    let data = {};
    if (url === "/api/status") {
      data = { login: false, version: "test", engine: { detail: "" } };
    } else if (url === "/api/calls") {
      data = callsPayload;
    }
    return { json: async () => data };
  },
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout, clearTimeout,
  Date, console, process,
};

const src = fs.readFileSync(
  path.join(__dirname, "..", "zalo_pc_app", "static", "app.js"), "utf-8");
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

function texts(el, out) {
  out = out || [];
  if (el.textContent) out.push(el.textContent);
  for (const child of (el.children || [])) texts(child, out);
  return out;
}

function findByClass(el, cls) {
  if ((el.className || "").split(" ").includes(cls)) return el;
  for (const child of (el.children || [])) {
    const found = findByClass(child, cls);
    if (found) return found;
  }
  return null;
}

// statusPill() returns an array created inside the vm realm, so
// compare element-wise: deepStrictEqual fails on the cross-realm
// Array prototype even when the values match.
const pillIs = (got, cls, label) => {
  assert.strictEqual(got[0], cls);
  assert.strictEqual(got[1], label);
};

// 1. An answered call is connected, NOT ringing — whatever
// request_sent says (step 2 was sent long ago by then).
pillIs(sandbox.statusPill("answered", true),
  "pill pill-accent", "Đang gọi");
pillIs(sandbox.statusPill("answered", false),
  "pill pill-accent", "Đang gọi");
pillIs(sandbox.statusPill("answered"),
  "pill pill-accent", "Đang gọi");
// Unchanged: a ringing call still says ringing only when step 2
// was really sent.
pillIs(sandbox.statusPill("sent", true),
  "pill pill-accent", "Đang đổ chuông");

// 2. activeCard() for an answered call with SRTP unwired shows
// the pill "Đang gọi" AND the honest media note.
const cardUnwired = sandbox.activeCard({
  call_id: "1763200001", peer: "Đại ca",
  thread_id: "6643404425553198601", type: "user",
  status: "answered", started_at: 1763200001, detail: "",
  request_sent: true, request_detail: "",
  answered_at: 1763200005, answer_source: "media",
  media: { srtp: "not-wired" },
});
assert.ok(texts(cardUnwired).includes("Đang gọi"),
  "answered card must say Đang gọi, got: " + texts(cardUnwired));
assert.ok(!texts(cardUnwired).includes("Đang đổ chuông"),
  "answered card must not say ringing");
const note = findByClass(cardUnwired, "row-sub");
assert.ok(note, "answered unwired card must carry a .row-sub note");
assert.strictEqual(note.textContent,
  "Đã nối — chưa có tiếng (thiếu khoá SRTP).");

// 3. activeCard() for an answered call with SRTP wired (or no
// media key at all) shows no such note.
const cardWired = sandbox.activeCard({
  call_id: "1763200002", peer: "Đại ca",
  thread_id: "6643404425553198601", type: "user",
  status: "answered", started_at: 1763200001, detail: "",
  request_sent: true, request_detail: "",
  answered_at: 1763200005, answer_source: "api",
  media: { srtp: "wired" },
});
assert.ok(!texts(cardWired).includes("chưa có tiếng"),
  "wired answered card must not warn about missing voice");
const cardNoMedia = sandbox.activeCard({
  call_id: "1763200003", peer: "Đại ca",
  thread_id: "6643404425553198601", type: "user",
  status: "answered", started_at: 1763200001, detail: "",
  request_sent: true, request_detail: "",
  answered_at: 1763200005, answer_source: "api",
});
assert.ok(!texts(cardNoMedia).includes("chưa có tiếng"),
  "answered card without media info must not warn");

(async () => {
  // 4. Top-bar pill through renderCalls(): an answered active call
  // says "Đang gọi: Đại ca" even though request_sent is true.
  const answeredCall = {
    calls: [{ call_id: "1763200001", peer: "Đại ca",
              thread_id: "6643404425553198601", type: "user",
              status: "answered", started_at: 1763200001, detail: "",
              request_sent: true, request_detail: "",
              answered_at: 1763200005, answer_source: "media",
              media: { srtp: "not-wired" } }],
    active: { call_id: "1763200001", peer: "Đại ca",
              thread_id: "6643404425553198601", type: "user",
              status: "answered", started_at: 1763200001, detail: "",
              request_sent: true, request_detail: "",
              answered_at: 1763200005, answer_source: "media",
              media: { srtp: "not-wired" } },
  };
  callsPayload = answeredCall;
  await sandbox.loadCalls();
  const pill = els["topbar-call"];
  assert.strictEqual(pill.hidden, false);
  assert.strictEqual(pill.textContent, "Đang gọi: Đại ca");

  // 5. The "Bên kia đã nhấc máy" button shows while the call is
  // still ringing and hides once it is answered (renderCallDetail
  // toggles it from the freshest /api/calls entry).
  const ringingCall = {
    calls: [{ call_id: "1763200001", peer: "Đại ca",
              thread_id: "6643404425553198601", type: "user",
              status: "sent", started_at: 1763200001, detail: "",
              request_sent: true, request_detail: "" }],
    active: { call_id: "1763200001", peer: "Đại ca",
              thread_id: "6643404425553198601", type: "user",
              status: "sent", started_at: 1763200001, detail: "",
              request_sent: true, request_detail: "" },
  };
  callsPayload = ringingCall;
  await sandbox.loadCalls();
  sandbox.showCallDetail(ringingCall.calls[0]);
  assert.strictEqual(els["btn-answered"].style.display, "",
    "answered button must show while ringing");
  callsPayload = answeredCall;
  await sandbox.loadCalls();
  sandbox.showCallDetail(answeredCall.calls[0]);
  assert.strictEqual(els["btn-answered"].style.display, "none",
    "answered button must hide once answered");

  // 6. markAnswered() POSTs /api/call/answered with the live
  // call's id (uint32 number), then refreshes.
  callsPayload = ringingCall;
  await sandbox.loadCalls();
  posted.length = 0;
  await sandbox.markAnswered();
  assert.strictEqual(posted.length, 1, JSON.stringify(posted));
  assert.strictEqual(posted[0].url, "/api/call/answered");
  assert.strictEqual(posted[0].body.call_id, 1763200001);

  console.log("test_app_js_answered: OK (answered pill is Đang gọi; "
    + "unwired card warns about missing voice; answered button "
    + "shows while ringing and posts /api/call/answered)");
})().catch((e) => { console.error(e); process.exit(1); });
