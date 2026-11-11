// Mô hình thẻ bình chọn của WebUI (app.js): pollCardModel + lastPollEventIndexes, nạp trong vm với DOM giả.
// Chạy: node tests/test_poll_card.js (mã thoát 0 = đạt)
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function makeEl() {
  const el = { children: [], style: {}, dataset: {}, hidden: false, textContent: "", value: "", className: "", innerHTML: "", classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {}, appendChild(c) { el.children.push(c); return c; }, querySelectorAll() { return []; }, addEventListener() {} };
  return el;
}
const els = {};
const sandbox = { document: { getElementById: (id) => (els[id] || (els[id] = makeEl())), createElement: () => makeEl(), createTextNode: (t) => { const e = makeEl(); e.textContent = t; return e; },
                              querySelectorAll: () => [], addEventListener() {} },
  window: {}, localStorage: { getItem: () => null, setItem() {} }, console, setInterval() { return 0; }, clearInterval() {}, setTimeout() { return 0; }, clearTimeout() {},
  fetch: async () => ({ ok: true, json: async () => ({}) }), location: { hash: "" }, navigator: {} };
vm.createContext(sandbox);
const src = fs.readFileSync(path.join(__dirname, "..", "zalo_pc_app", "static", "app.js"), "utf8");
try { vm.runInContext(src, sandbox, { filename: "app.js" }); } catch (e) { /* khởi tạo cần DOM thật: chỉ cần các hàm đã khai báo */ }
const plain = (x) => JSON.parse(JSON.stringify(x));   // mảng tạo trong vm khác prototype: so sánh qua JSON
const get = (n) => vm.runInContext("typeof " + n + " === 'function' ? " + n + " : null", sandbox);
const model = get("pollCardModel"), last = get("lastPollEventIndexes");
assert(model && last, "app.js phải có pollCardModel và lastPollEventIndexes");

const poll = { poll_id: "1", question: "Kiểm tra", closed: false, anonymous: false, multi: false, num_vote: 1,
  options: [{ option_id: 10, content: "1234", votes: 1, voters: ["u"] }, { option_id: 11, content: "Test", votes: 0, voters: [] }] };
let m = model(poll);
assert.strictEqual(m.question, "Kiểm tra"); assert.strictEqual(m.summary, "1 người đã bình chọn");
assert.deepStrictEqual(plain(m.rows.map((r) => [r.id, r.pct, r.leader])), [["10", 100, true], ["11", 0, false]]);
assert.strictEqual(m.canVote, true); assert.deepStrictEqual(plain(m.flags), []);
m = model({ ...poll, closed: true, anonymous: true, multi: true });
assert.strictEqual(m.canVote, false); assert.deepStrictEqual(plain(m.flags), ["Đã đóng", "Ẩn danh", "Chọn nhiều phương án"]);
m = model({ poll_id: "2", options: [{ option_id: 1, content: "A", votes: 3 }, { option_id: 2, content: "B", votes: 1 }, { option_id: 3, content: "C", votes: 3 }] });
assert.deepStrictEqual(plain(m.rows.map((r) => [r.pct, r.leader])), [[100, true], [33, false], [100, true]]); assert.strictEqual(m.summary, "7 người đã bình chọn");
assert.strictEqual(model({ poll_id: "3", options: [{ option_id: 1, content: "A", votes: 0 }] }).rows[0].pct, 0);   // chưa ai chọn: không chia cho 0
// Chuỗi sự kiện của CÙNG một bình chọn chỉ dựng một thẻ, ở sự kiện mới nhất
const msgs = [{ kind: "system", poll_id: "1" }, { kind: "text" }, { kind: "system", poll_id: "2" }, { kind: "system", poll_id: "1" }, { kind: "system", poll_id: "" }];
assert.deepStrictEqual(plain(last(msgs)), { "1": 3, "2": 2 });
console.log("ALL POLL CARD TESTS PASSED");
