/* View-decision harness: runs the REAL app.js (no browser) against a
   stub DOM + stub fetch and records which view is visible over time.
   Usage: node view_decision_harness.js <scenario>
   Scenarios:
     logged-in        /api/status -> login:true, contacts fresh
     logged-out       /api/status -> login:false (contacts never called)
     logged-in-stale  /api/status -> login:true, first contacts stale,
                      second contacts fresh (the SWR follow-up load)
     logged-in-reload-error
                      /api/status -> login:true, first contacts stale,
                      follow-up contacts returns a dry 429 error
                      (no cache to serve): the OLD list must stay
                      rendered (count-all stays 1, not 0) and the
                      error banner must show the 429, never an
                      empty 0/0/0 contacts page.
   Exit 0 + "PASS <scenario>" on success, non-zero with the failure
   on stdout otherwise. No real login, no real call.
   (Node only; driven by tests/test_view_decision.py.) */
"use strict";
const fs = require("fs");
const path = require("path");

const scenario = process.argv[2];
const APP_JS = path.join(__dirname, "..", "zalo_pc_app", "static", "app.js");

const VIEWS = ["view-loading", "view-login", "view-main", "view-calls", "view-call"];

function makeEl() {
  return {
    style: { display: "" },
    className: "",
    textContent: "",
    innerHTML: "",
    hidden: false,
    disabled: false,
    value: "",
    src: "",
    dataset: {},
    classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {},
    appendChild(child) { return child; },
    querySelectorAll() { return []; },
    onclick: null,
    oninput: null,
  };
}

const elements = {};
const documentStub = {
  getElementById(id) {
    if (!elements[id]) elements[id] = makeEl();
    return elements[id];
  },
  createElement() { return makeEl(); },
  createTextNode(text) { return { textContent: text }; },
  querySelectorAll() { return []; },
};

// Initial paint = the HTML as served: only view-loading visible,
// view-login hidden (the fix: it used to be visible by default).
for (const v of VIEWS) elements[v] = makeEl();
elements["view-loading"].style.display = "";
for (const v of ["view-login", "view-main", "view-calls", "view-call"]) {
  elements[v].style.display = "none";
}
elements["search"] = makeEl();
elements["search"].value = "";

const fetchLog = [];
let contactsCalls = 0;
function statusBody() {
  if (scenario === "logged-out") {
    return { login: false, uid: "", phonenum: "", version: "test",
             engine: { detail: "" } };
  }
  return { login: true, uid: "10001", phonenum: "+84000000000",
           version: "test", engine: { detail: "test engine" } };
}
function contactsBody() {
  contactsCalls += 1;
  if ((scenario === "logged-in-stale"
       || scenario === "logged-in-reload-error") && contactsCalls === 1) {
    return { friends: { rows: [{ id: "20001", name: "Ban A", members: [] }] },
             groups: { rows: [] }, source: "stale", stale: true,
             cached: true, fetched_at: Math.floor(Date.now() / 1000) - 200,
             age_seconds: 200, rate_limited: false, retry_after_seconds: 0 };
  }
  if (scenario === "logged-in-reload-error" && contactsCalls >= 2) {
    // Dry 429 on the follow-up load (no cache to serve): the server
    // answers an error body + retry_after_seconds, never rows.
    return { error: "friends: GET https://profile-wpa.zalo.me/api/social/"
             + "friend/getfriends network status=429",
             retry_after_seconds: 60 };
  }
  return { friends: { rows: [{ id: "20001", name: "Ban A", members: [] }] },
           groups: { rows: [] }, source: "fresh", stale: false,
           cached: false, fetched_at: Math.floor(Date.now() / 1000),
           age_seconds: 0, rate_limited: false, retry_after_seconds: 0 };
}
global.fetch = async (url) => {
  fetchLog.push(url);
  let body;
  if (url === "/api/status") body = statusBody();
  else if (url === "/api/contacts" || url === "/api/contacts?force=1") body = contactsBody();
  else if (url === "/api/calls") body = { calls: [], active: null };
  else body = {};
  return { json: async () => body };
};
global.document = documentStub;

// Track timers so the process can exit cleanly at the end.
const intervals = new Set();
const timeouts = new Set();
const realSetInterval = global.setInterval;
const realSetTimeout = global.setTimeout;
global.setInterval = (fn, ms, ...a) => {
  const id = realSetInterval(fn, ms, ...a);
  intervals.add(id);
  return id;
};
global.setTimeout = (fn, ms, ...a) => {
  const id = realSetTimeout((...args) => { timeouts.delete(id); fn(...args); }, ms, ...a);
  timeouts.add(id);
  return id;
};

const code = fs.readFileSync(APP_JS, "utf-8");
eval(code); // runs the app's top-level wiring + boot show/loadMain

const seen = [];
function snapshot() {
  const visible = VIEWS.find((v) => elements[v].style.display !== "none");
  if (visible && seen[seen.length - 1] !== visible) seen.push(visible);
}
const sleep = (ms) => new Promise((r) => realSetTimeout(r, ms));

(async () => {
  // Sample the visible view while the app settles.
  for (let i = 0; i < 40; i++) { snapshot(); await sleep(25); }
  if (scenario === "logged-in-stale"
      || scenario === "logged-in-reload-error") {
    // The SWR follow-up load fires 3s after the stale answer.
    await sleep(4500);
    for (let i = 0; i < 20; i++) { snapshot(); await sleep(25); }
  }
  snapshot();
  const fail = (msg) => {
    console.log("FAIL " + scenario + ": " + msg
      + " | sequence=" + seen.join("->")
      + " | fetch=" + fetchLog.join(","));
    process.exit(1);
  };
  if (seen[0] !== "view-loading") fail("first view is not view-loading");
  if (scenario === "logged-in") {
    if (seen[seen.length - 1] !== "view-main") fail("final view is not view-main");
    if (seen.includes("view-login")) fail("QR view flashed while logged in");
  } else if (scenario === "logged-out") {
    if (seen[seen.length - 1] !== "view-login") fail("final view is not view-login");
    if (seen.includes("view-main")) fail("main view shown while logged out");
    if (fetchLog.some((u) => u.startsWith("/api/contacts"))) {
      fail("contacts fetched while logged out");
    }
  } else if (scenario === "logged-in-stale") {
    if (seen[seen.length - 1] !== "view-main") fail("final view is not view-main");
    if (seen.includes("view-login")) fail("QR view flashed while logged in");
    if (contactsCalls < 2) fail("stale answer did not trigger a follow-up load");
  } else if (scenario === "logged-in-reload-error") {
    if (seen[seen.length - 1] !== "view-main") fail("final view is not view-main");
    if (seen.includes("view-login")) fail("QR view flashed while logged in");
    if (contactsCalls < 2) fail("stale answer did not trigger a follow-up load");
    // 2026-11-05 18:06: a dry 429 emptied the contacts page to 0/0/0.
    // The old list must stay rendered after the failed reload.
    if (String(elements["count-all"].textContent) !== "1") {
      fail("reload error cleared the old list (count-all="
           + elements["count-all"].textContent + ")");
    }
    const errText = elements["contacts-error-text"]
      ? elements["contacts-error-text"].textContent : "";
    if (!errText.includes("429")) {
      fail("reload error not shown in the error banner");
    }
  } else {
    fail("unknown scenario");
  }
  console.log("PASS " + scenario + " sequence=" + seen.join("->")
    + " contactsCalls=" + contactsCalls);
  for (const id of intervals) clearInterval(id);
  for (const id of timeouts) clearTimeout(id);
  process.exit(0);
})().catch((e) => { console.log("FAIL " + scenario + ": " + e.stack); process.exit(1); });
