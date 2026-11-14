// Nút tăng/giảm âm lượng Mic/Loa trên thẻ cuộc gọi WebUI (14/11/2026).
// Cần jsdom: NODE_PATH=<thư mục có node_modules/jsdom> node tests/test_app_js_gain.js  (không có jsdom: BỎ QUA, mã thoát 0)
"use strict";
let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { console.log("BỎ QUA: không có jsdom"); process.exit(0); }
const fs = require("fs"), path = require("path");
const dir = path.join(__dirname, "..", "zalo_pc_app", "static", "zalo");
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8").replace(/<script[^>]*src=[^>]*><\/script>/g, "");
const js = fs.readFileSync(path.join(dir, "app.js"), "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
const w = dom.window, posts = [], errors = [];
let gain = { mic: 100, speaker: 100 }, failNext = false;
w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
w.confirm = () => true; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
w.fetch = async (url, opts) => {
  let data = {};
  if (opts && opts.method === "POST") {
    const b = JSON.parse(opts.body); posts.push([url, b]);
    if (url === "/api/call/media" && b.action === "gain") {
      if (failNext) { failNext = false; return { status: 400, json: async () => ({ ok: false, error: "target phai la mic hoac speaker" }) }; }
      gain = Object.assign({}, gain, { [b.target]: Math.max(0, Math.min(300, gain[b.target] + b.step)) });
      data = { ok: true, gain, mic: null, speaker: null };
    } else data = { ok: true, gain, mic: null, speaker: null, video: null };
  } else if (url === "/api/status") data = { login: true, version: "t", uid: "1", sync: "running", engine: { detail: "" } };
  else if (url.startsWith("/api/reaction/list")) data = { reactions: {} };
  else if (url.startsWith("/api/contacts")) data = { friends: { rows: [] }, groups: { rows: [] } };
  else if (url.startsWith("/api/calls")) data = { active: null, calls: [] };
  return { status: 200, json: async () => data };
};
w.__ZALO_TEST_HOOK__ = (o) => { w.__t = o; };
w.eval(js);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  await sleep(300);
  const T = w.__t, S = T.S, ok = [];
  S.calls = { active: { call_id: 5, status: "answered", answered_at: 1, type: "voice", direction: "in", thread_id: "20001", peer: "Anh", started_at: 1 }, calls: [] };
  const box = () => T.mediaToggles();
  let el = box(), gn = el.querySelectorAll(".gn");
  ok.push(["có hai nhóm âm lượng: Mic và Loa, mặc định 100%", gn.length === 2 && /Mic 100%/.test(gn[0].textContent) && /Loa 100%/.test(gn[1].textContent), el.textContent]);
  ok.push(["mỗi nhóm có nút giảm và nút tăng có nhãn truy cập", gn[0].querySelectorAll("button").length === 2 && /Giảm âm lượng mic/.test(gn[0].innerHTML) && /Tăng âm lượng loa/.test(gn[1].innerHTML)]);
  gn[1].querySelectorAll("button")[1].click(); await sleep(60);
  ok.push(["bấm + của Loa -> POST action gain target speaker step +10", posts.some(([u, b]) => u === "/api/call/media" && b.action === "gain" && b.target === "speaker" && b.step === 10 && b.call_id === 5), JSON.stringify(posts)]);
  ok.push(["trạng thái cập nhật theo phản hồi máy chủ: Loa 110%", S.cm.gain.speaker === 110 && S.cm.gain.mic === 100, JSON.stringify(S.cm.gain)]);
  T.changeGain("mic", -10); await sleep(60);
  ok.push(["bấm − của Mic -> step -10, Mic 90%", posts.some(([u, b]) => b.target === "mic" && b.step === -10) && S.cm.gain.mic === 90]);
  S.cm.gain = { mic: 0, speaker: 300 }; el = box(); gn = el.querySelectorAll(".gn");
  ok.push(["mic 0%: nút giảm bị khóa và nhóm đánh dấu tắt tiếng; loa 300%: nút tăng bị khóa", gn[0].querySelectorAll("button")[0].disabled && gn[0].classList.contains("mute") && gn[1].querySelectorAll("button")[1].disabled]);
  S.cm.gain = { mic: 100, speaker: 100 }; failNext = true; T.changeGain("mic", 10); await sleep(60);
  ok.push(["máy chủ báo lỗi: hiện thông báo và KHÔNG đổi mức hiển thị", S.cm.gain.mic === 100 && !w.document.getElementById("toast").hidden && /Không chỉnh được/.test(w.document.getElementById("toast").textContent), w.document.getElementById("toast").textContent]);
  S.cm.gain = { mic: 100, speaker: 100 };
  const a = S.calls.active; S.calls.active = null; const before = posts.length; await T.changeGain("mic", 10);
  ok.push(["không có cuộc gọi: không gửi yêu cầu", posts.length === before]); S.calls.active = a;
  let bad = 0; for (const [n, v, x] of ok) { console.log(v ? "ĐẠT " : "HỎNG", n, v ? "" : "(" + (x || "") + ")"); if (!v) bad++; }
  console.log("lỗi trình duyệt:", errors); process.exit(bad || errors.length ? 1 : 0);
})();
