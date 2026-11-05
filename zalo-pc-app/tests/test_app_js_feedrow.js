// Node harness for the rail feed-row thread-ID fix. The rail
// ("Cuộc gọi" sidebar) is the tracking view the user watches while
// a call is live, but feedRow() previously rendered only the peer
// name + time/type + status — no thread ID, while the active card
// and the history table both showed it. This test loads app.js in
// a vm with a recording DOM stub and asserts every feed row carries
// its thread_id in a .feed-tid.mono element.
//
// Run: node tests/test_app_js_feedrow.js  (exit 0 = pass)
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
const sandbox = {
  document: {
    getElementById: (id) => (els[id] || (els[id] = makeEl())),
    createElement: (tag) => makeEl(tag),
    querySelectorAll: () => [],
  },
  fetch: async (url) => {
    let data = {};
    if (url === "/api/status") {
      data = { login: false, version: "test", engine: { detail: "" } };
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

// 1. Named peer: row shows the name AND the thread ID.
const row1 = sandbox.feedRow({
  peer: "Ban A", thread_id: "20001", type: "user",
  status: "ended", started_at: 1762346001, call_id: "1762346001",
});
assert.strictEqual(row1.tagName, "LI");
const tid1 = findByClass(row1, "feed-tid");
assert.ok(tid1, "feed row must contain a .feed-tid element");
assert.ok((tid1.className || "").split(" ").includes("mono"),
          ".feed-tid must use the mono class");
assert.strictEqual(tid1.textContent, "20001");
assert.ok(texts(row1).includes("Ban A"), "peer name must still render");

// 2. Unnamed peer (peer empty): name falls back to the thread ID,
// and the .feed-tid line still carries it.
const row2 = sandbox.feedRow({
  peer: "", thread_id: "6643404425553198601", type: "group",
  status: "sent", started_at: 1762346001, call_id: "1762346002",
});
const tid2 = findByClass(row2, "feed-tid");
assert.ok(tid2, "peer-less feed row must contain a .feed-tid element");
assert.strictEqual(tid2.textContent, "6643404425553198601");

// 3. loadCalls() + renderCalls() end-to-end through the rail: the
// history feed contains the thread ID for each entry. (callsData
// is a script-level `let`, not a sandbox property, so drive it
// through the real /api/calls fetch path instead of assigning it.)
(async () => {
  await sandbox.loadCalls();
  const feed = els["rail-history"];
  assert.ok(feed, "rail-history element must exist");
  assert.ok(texts(feed).includes("20001"),
            "rail history feed must show the thread ID");

  console.log("test_app_js_feedrow: OK (feed rows carry thread_id)");
})().catch((e) => { console.error(e); process.exit(1); });
