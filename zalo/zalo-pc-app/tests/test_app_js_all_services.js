// Moi dich vu trong danh muc (96 goc + API zca mo rong) phai co form/nut tren tab "Dich vu" cua WebUI,
// tru mot so it muc co ly do ro rang (ghi nhan bang tay duoi day). Chay: node tests/test_app_js_all_services.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");
const { execFileSync } = require("child_process");

const root = path.join(__dirname, "..");
const catalog = JSON.parse(execFileSync("python3", ["-c",
  "import sys,json; sys.path.insert(0,'.'); from zalo_pc_app import services as S; print(json.dumps(S.catalog_public()))"],
  { cwd: root, encoding: "utf-8", maxBuffer: 1 << 26 }));

function makeEl(tag) {
  const el = { tagName: (tag || "div").toUpperCase(), children: [], style: {}, dataset: {}, hidden: false, textContent: "",
    value: "", className: "", innerHTML: "", options: [], classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {}, appendChild(c) { el.children.push(c); return c; }, querySelectorAll() { return []; } };
  return el;
}
const els = {};
const sandbox = {
  document: { getElementById: (id) => (els[id] || (els[id] = makeEl())), createElement: (t) => makeEl(t),
    createTextNode: (t) => { const e = makeEl(); e.textContent = t; return e; }, querySelectorAll: () => [] },
  fetch: async () => ({ json: async () => ({}) }), setInterval: () => 0, clearInterval: () => {}, setTimeout, clearTimeout,
  Date, console, process, window: { confirm: () => true },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(root, "zalo_pc_app", "static", "app.js"), "utf-8"), sandbox);
vm.runInContext("svcCatalog = __cat; renderServices();", Object.assign(sandbox, { __cat: catalog }));

const rows = [];
(function walk(el) { if (el.dataset && el.dataset.svc !== undefined) rows.push(el); (el.children || []).forEach(walk); })(els["svc-groups"]);

const expectedService = catalog.services.length;
const zcaExtras = catalog.zca.apis.filter((a) => !a.covered_by &&
  !new Set(catalog.services.map((s) => s.action).filter(Boolean).concat(catalog.services.map((s) => s.addon))).has(a.action)).length;
assert.strictEqual(rows.length, expectedService + zcaExtras, "moi dich vu + moi API mo rong phai co mot dong");

// Muc duoc phep chi hien ly do (khong co form): ghi ro tung cai, them muc khac la test do.
const INFO_ONLY_OK = new Set(["send_card", "get_proxies", "add_proxy", "remove_proxy"]);
const bad = rows.filter((r) => r.dataset.ui === "info" && !INFO_ONLY_OK.has(r.dataset.svc)).map((r) => r.dataset.svc);
const nonSupported = catalog.services.filter((s) => s.status === "unsupported").map((s) => s.addon);
const badFiltered = bad.filter((n) => !nonSupported.includes(n));
assert.deepStrictEqual(badFiltered, [], "dich vu khong co form tren WebUI: " + badFiltered.join(", "));
console.log("ALL_SERVICES_WEBUI_OK rows=%d form/nut=%d info=%d (unsupported co ly do=%d)", rows.length,
  rows.filter((r) => r.dataset.ui !== "info").length, rows.filter((r) => r.dataset.ui === "info").length, nonSupported.length);
