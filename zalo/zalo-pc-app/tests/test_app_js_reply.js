// Node harness cho Tra loi (quote) + Thu hoi tin cua WebUI (nhu Zalo PC): dieu kien hien nut, gan nut dung bong bong, gui quote_message,
// thu hoi qua undo_message. Chay: node tests/test_app_js_reply.js (exit 0 = pass).
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function makeEl(tag) {
  const el = {
    tagName: (tag || "div").toUpperCase(),
    children: [], style: {}, dataset: {}, hidden: false, textContent: "",
    value: "", src: "", className: "", innerHTML: "", id: "",
    classList: { add() {}, remove() {}, toggle() { return false; } },
    setAttribute() {},
    focus() {},
    appendChild(child) { el.children.push(child); return child; },
    insertBefore(child) { el.children.push(child); return child; },
    querySelectorAll() { return []; },
  };
  el.parentNode = { insertBefore(child) { el.children.push(child); return child; } };
  return el;
}

const els = {};
const posted = [];
const sandbox = {
  document: {
    getElementById: (id) => (els[id] || (els[id] = makeEl())),
    createElement: (tag) => makeEl(tag),
    createTextNode: (text) => { const el = makeEl(); el.textContent = text; return el; },
    querySelectorAll: () => [],
  },
  fetch: async (url, opts) => {
    if (opts && opts.method === "POST") posted.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
    return { json: async () => ({}) };
  },
  confirm: () => true,
  setInterval: () => 0, clearInterval: () => {},
  setTimeout, clearTimeout, Date, console, process,
};
const src = fs.readFileSync(path.join(__dirname, "..", "zalo_pc_app", "static", "app.js"), "utf-8");
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
vm.runInContext("loadThreadHistory = async function () { globalThis.__reloaded = (globalThis.__reloaded || 0) + 1; };", sandbox);
vm.runInContext("currentThread = { id: '777', type: 'group', name: 'Nhóm A' };", sandbox);

const inMsg = { id: "9001", kind: "text", direction: "in", sender_id: "222", sender_name: "Nam", text: "Xin chào", raw: { msgId: "9001", cliMsgId: "8001", uidFrom: "222", ts: "1794443203003" } };
const outMsg = { id: "9002", kind: "text", direction: "out", sender_id: "me", text: "Tôi đây", raw: { msgId: "9002", cliMsgId: "8002", uidFrom: "111" } };
const localOut = { id: "c1", kind: "text", direction: "out", sender_id: "me", text: "vừa gửi" };         // tin vua gui tu day: chua co msgId/cliMsgId
const photo = { id: "9003", kind: "photo", direction: "in", sender_id: "222", text: "", raw: { msgId: "9003", cliMsgId: "8003", uidFrom: "222" } };

// 1. Dieu kien hien nut
assert.strictEqual(sandbox.canReply(inMsg), true);
assert.strictEqual(sandbox.canReply(photo), false, "chi tin chu moi tra loi duoc");
assert.strictEqual(sandbox.canReply(localOut), false, "thieu cliMsgId -> khong tra loi");
assert.strictEqual(sandbox.canUndo(outMsg), true);
assert.strictEqual(sandbox.canUndo(inMsg), false, "tin nguoi khac gui khong thu hoi");
assert.strictEqual(sandbox.canUndo(localOut), false, "tin chua co msgId/cliMsgId khong thu hoi");

// 2. Gan nut dung bong bong (theo thu tu, bo qua tin he thong); lech so luong thi khong gan
const bubbles = [makeEl(), makeEl(), makeEl()];
els["chat-history"] = makeEl();
els["chat-history"].querySelectorAll = () => bubbles;
sandbox.decorateBubbles([inMsg, { kind: "system", text: "x" }, outMsg, localOut]);
const labels = (b) => (b.children[0] ? b.children[0].children.map((c) => c.textContent).filter((t) => t) : []);
assert.deepStrictEqual(labels(bubbles[0]), ["Cảm xúc", "Trả lời"]);
assert.deepStrictEqual(labels(bubbles[1]), ["Cảm xúc", "Trả lời", "Thu hồi"]);
assert.deepStrictEqual(labels(bubbles[2]), [], "tin vua gui chua co id: khong nut");
const fresh = [makeEl()];
els["chat-history"].querySelectorAll = () => fresh;
sandbox.decorateBubbles([inMsg, outMsg]);                       // 1 bong bong, 2 tin: lech -> khong gan nham
assert.strictEqual(fresh[0].children.length, 0);

// 3. Tra loi: gui qua quote_message roi tai lai lich su
(async () => {
  sandbox.setReplyTo(inMsg);
  assert.strictEqual(els["chat-reply-bar"].hidden, false);
  els["chat-input"].value = "Chào bạn";
  await vm.runInContext("sendChatText()", sandbox);
  const q = posted.find((p) => p.url === "/api/svc/quote_message");
  assert.ok(q, "phai goi quote_message");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(q.body)), {
    thread_id: "777", type: "group", text: "Chào bạn", msg_id: "9001", qmsg_owner: "222", qmsg_cli_id: "8001",
    qmsg_type: 1, qmsg_ts: 1794443203003, qmsg: "Xin chào",
  });
  assert.strictEqual(els["chat-reply-bar"].hidden, true, "gui xong thi bo thanh tra loi");
  assert.strictEqual(sandbox.__reloaded, 1);
  // khong tra loi: duong gui cu (/send), khong goi quote_message nua
  posted.length = 0;
  els["chat-input"].value = "tin thuong";
  await vm.runInContext("sendChatText()", sandbox);
  assert.ok(posted.some((p) => p.url === "/api/thread/777/send") && !posted.some((p) => p.url === "/api/svc/quote_message"), JSON.stringify(posted));

  // 4. Thu hoi
  posted.length = 0;
  await sandbox.undoMessage(outMsg);
  const u = posted.find((p) => p.url === "/api/svc/undo_message");
  assert.ok(u, "phai goi undo_message");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(u.body)), { thread_id: "777", type: "group", msg_id: "9002", cli_msg_id: "8002" });
  // 5. Cam xuc: gui add_reaction voi msgId + cliMsgId cua tin goc; tin chua co id khong co nut cam xuc
  posted.length = 0;
  assert.strictEqual(sandbox.canReact(localOut), false);
  assert.strictEqual(sandbox.canReact(inMsg), true);
  const picker = { hidden: false };
  await sandbox.sendReaction(inMsg, "heart", picker);
  const rx = posted.find((p) => p.url === "/api/svc/add_reaction");
  assert.ok(rx, "phai goi add_reaction");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(rx.body)), { thread_id: "777", type: "group", icon: "heart", msg_id: "9001", cli_msg_id: "8001" });
  assert.strictEqual(picker.hidden, true, "tha xong thi dong bang chon");
  console.log("APP JS REPLY/UNDO/REACT TESTS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });
