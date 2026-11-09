/* Zalo — giao diện web của zalo-pc-app. Không cần bước build.
   Chữ do người dùng/Zalo gửi tới luôn đi qua textContent, không innerHTML.
   Tin mới tới qua SSE (/api/events) nên hiện tức thì; vòng hỏi lại chỉ là lưới an toàn. */
(() => {
"use strict";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const ICONS = {
  chat: '<path d="M21 12a8 8 0 0 1-11.7 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z"/>',
  contact: '<rect x="4" y="3" width="15" height="18" rx="2.5"/><circle cx="11.5" cy="10" r="2.5"/><path d="M7 17c.6-2 2.4-3 4.5-3s3.9 1 4.5 3M20.5 8v2M20.5 13v2"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.2a6.5 6.5 0 0 1 3.5 5.8"/>',
  user: '<circle cx="12" cy="8" r="3.8"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
  userplus: '<circle cx="10" cy="8" r="3.6"/><path d="M3.5 20a6.5 6.5 0 0 1 11-4.6M18 14v6M15 17h6"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
  video: '<rect x="2.5" y="6" width="13" height="12" rx="2.5"/><path d="M15.5 10.5 21.5 7v10l-6-3.5"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  cog: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-3.6-3.6"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  back: '<path d="m15 5-7 7 7 7"/>',
  clip: '<path d="m20.5 11.5-8.4 8.4a5 5 0 0 1-7-7l8.8-8.8a3.3 3.3 0 0 1 4.7 4.7l-8.8 8.8a1.7 1.7 0 0 1-2.4-2.4L15 7"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="m4 18 5-5 4 4 3-3 4 4"/>',
  mic: '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  smile: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14c.8 1.4 2 2.2 3.5 2.2s2.7-.8 3.5-2.2M9 9.5v.5M15 9.5v.5"/>',
  thumb: '<path d="M7 11v9H4v-9zM7 11l4-7c1.5 0 2.5 1 2.2 2.6L12.7 9H19a2 2 0 0 1 2 2.4l-1.2 6A2.5 2.5 0 0 1 17.4 19H7"/>',
  send: '<path d="M21 3 10 14M21 3l-7 18-4-7-7-4z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  hang: '<path d="M3 14c4.5-4 13.5-4 18 0l-1.5 3-4-1.2v-2.3a10 10 0 0 0-7 0v2.3L4.5 17z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  panel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M15 4.5v15"/>',
  more: '<circle cx="5.5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18.5" cy="12" r="1.3"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2.2"/><path d="M15.5 8.5V6.7A2.2 2.2 0 0 0 13.3 4.5H6.7A2.2 2.2 0 0 0 4.5 6.7v6.6a2.2 2.2 0 0 0 2.2 2.2h1.8"/>',
  db: '<ellipse cx="12" cy="6" rx="7.5" ry="3"/><path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 3.5 5.4 3.5 8.5s-1 6-3.5 8.5c-2.5-2.5-3.5-5.4-3.5-8.5s1-6 3.5-8.5z"/>',
  help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 16.5v.1"/>',
  logout: '<path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l4 4-4 4M19 12H9"/>',
};
function svg(name) {
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("class", "i"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true");
  s.innerHTML = ICONS[name] || "";
  return s;
}
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") el.style.cssText = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) { if (c == null || c === false) continue; el.append(c.nodeType ? c : document.createTextNode(String(c))); }
  return el;
}
// replaceChildren(null) sẽ chèn chữ "null": luôn lọc giá trị rỗng.
const put = (el, ...kids) => el.replaceChildren(...kids.flat().filter((k) => k != null && k !== false));
document.querySelectorAll("[data-i]").forEach((n) => n.replaceWith(svg(n.dataset.i)));

// ---- mạng ----------------------------------------------------------------
async function api(path, method, body) {
  const r = await fetch(path, { method: method || "GET", headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (r.status === 401) { location.href = "/login"; throw new Error("chua_dang_nhap_app"); }
  try { return await r.json(); } catch (e) { return { error: "HTTP " + r.status }; }
}
async function apiForm(path, form, ms) {
  const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), ms || 90000);
  try { const r = await fetch(path, { method: "POST", body: form, signal: ctrl.signal }); try { return await r.json(); } catch (e) { return { error: "HTTP " + r.status }; } }
  catch (e) { if (e && e.name === "AbortError") return { error: "Hết thời gian chờ — máy chủ không trả lời." }; throw e; }
  finally { clearTimeout(t); }
}

// ---- trạng thái ----------------------------------------------------------
const S = {
  tab: "chats", status: null, uid: "", q: "",
  friends: [], groups: [], contactsErr: "", contactsMeta: null,
  conv: {}, convReady: false, sse: false,
  filter: { chats: "all", contacts: "friends", calls: "all" }, kind: "all", cmenu: "friends", csort: "az", cfilter: "all",
  cur: null, msgs: [], files: {}, lastTime: 0, pollT: null, stick: true, info: false,
  calls: { active: null, calls: [] },
  catalog: null, svcGroup: "all", svcQ: "", svcOpen: null,
  watchOpen: null, watchMsgs: {}, rec: null, qrT: null, sound: true, me: { avatar: "" },
};
const rowKey = (r) => (r.type || r.thread_type) + "|" + (r.id || r.thread_id);
const allRows = () => [...S.friends, ...S.groups];
const rowOf = (type, id) => allRows().find((r) => r.type === type && r.id === String(id));
const unreadTotal = () => Object.values(S.conv).reduce((n, c) => n + (c.unread || 0), 0);
const strangerList = () => Object.values(S.conv).filter((c) => c.stranger && c.incoming_count !== 0);

// ---- tiện ích --------------------------------------------------------------
function toast(text, ms) {
  const t = $("toast"); t.textContent = text; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, ms || 3600);
}
async function copyText(text, what) {
  try { await navigator.clipboard.writeText(text); toast("Đã sao chép " + (what || "")); }
  catch (e) { const ta = h("textarea", { style: "position:fixed;opacity:0" }); ta.value = text; document.body.append(ta); ta.select(); try { document.execCommand("copy"); toast("Đã sao chép " + (what || "")); } catch (e2) { toast("Không sao chép được", 4000); } ta.remove(); }
}
function initials(name, id) {
  const w = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!w.length) return String(id || "?").slice(-2);
  return ((w[0][0] || "") + (w.length > 1 ? w[w.length - 1][0] : "")).toUpperCase();
}
function hue(id) { let x = 0; for (const c of String(id)) x = (x * 31 + c.charCodeAt(0)) % 360; return x; }
function avatar(row, cls) {
  const a = h("span", { class: "av " + (cls || ""), style: "--h:" + hue(row.id || row.thread_id || "") });
  const fb = () => { a.textContent = initials(row.name, row.id || row.thread_id); };
  if (row.avatar) { const img = h("img", { src: row.avatar, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }); img.addEventListener("error", () => { img.remove(); fb(); }); a.append(img); } else fb();
  return a;
}
const pad = (n) => String(n).padStart(2, "0");
function fmtTime(sec) { if (!sec) return ""; const d = new Date(Number(sec) * 1000); return pad(d.getHours()) + ":" + pad(d.getMinutes()); }
function fmtRel(sec) {
  if (!sec) return "";
  const diff = Math.max(0, Date.now() / 1000 - Number(sec));
  if (diff < 45) return "Vài giây";
  if (diff < 3600) return Math.max(1, Math.round(diff / 60)) + " phút";
  if (diff < 86400) return Math.round(diff / 3600) + " giờ";
  const d = new Date(Number(sec) * 1000); return pad(d.getDate()) + "/" + pad(d.getMonth() + 1);
}
function fmtDay(sec) {
  const d = new Date(Number(sec) * 1000), n = new Date(), y = new Date(Date.now() - 864e5);
  if (d.toDateString() === n.toDateString()) return "Hôm nay";
  if (d.toDateString() === y.toDateString()) return "Hôm qua";
  return pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + "/" + d.getFullYear();
}
const fmtDT = (sec) => (sec ? fmtDay(sec) + " " + fmtTime(sec) : "");
const fmtDur = (sec) => { sec = Math.max(0, Math.round(sec)); return pad(Math.floor(sec / 60)) + ":" + pad(sec % 60); };
function fmtSize(n) { n = Number(n); if (!n) return ""; return n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " KB" : (n / 1048576).toFixed(1) + " MB"; }
const typeParam = () => (S.cur && S.cur.type === "group" ? "group" : "user");
const plain = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();

// ---- thu phóng theo thiết bị ----------------------------------------------------
// Cỡ giao diện = hệ số nhân của font-size gốc (mọi kích thước dùng rem). "Tự động" tính từ độ rộng
// khung nhìn + kiểu con trỏ; người dùng chọn tay thì nhớ riêng từng thiết bị (localStorage).
// Điểm gãy bố cục (data-bp) tính theo độ rộng ĐÃ chia hệ số, nên thu phóng không làm vỡ bố cục.
const root = document.documentElement;
function scalePref() { try { return localStorage.getItem("zalo-scale") || "auto"; } catch (e) { return "auto"; } }
function autoScale() {
  const w = window.innerWidth, touch = matchMedia("(pointer: coarse)").matches;
  let s = w >= 3000 ? 1.6 : w >= 2400 ? 1.35 : w >= 1900 ? 1.15 : w < 380 ? 0.94 : 1;
  return touch ? s * 1.06 : s;
}
function applyScale() {
  const pref = scalePref(), s = pref === "auto" ? autoScale() : Number(pref) / 100;
  root.style.fontSize = (16 * s).toFixed(2) + "px";
  const eff = window.innerWidth / s;
  root.dataset.bp = eff <= 900 ? "phone" : eff < 1280 ? "mid" : "wide";
  root.dataset.dev = matchMedia("(pointer: coarse)").matches ? "touch" : "pointer";
  syncInfo();
}
let scaleT; window.addEventListener("resize", () => { clearTimeout(scaleT); scaleT = setTimeout(applyScale, 120); });
window.addEventListener("orientationchange", () => setTimeout(applyScale, 200));
function setScale(v) { try { localStorage.setItem("zalo-scale", v); } catch (e) { /* riêng tư */ } applyScale(); }
function applyTheme(t) { root.dataset.theme = t; try { localStorage.setItem("zalo-theme", t); } catch (e) { /* riêng tư */ } }

// ---- menu nổi ----------------------------------------------------------------------
let popEl = null;
function closePop() { if (popEl) { popEl.remove(); popEl = null; } }
function popup(anchor, items, opts) {
  closePop();
  const el = h("div", { class: "pop", role: "menu" }, items.map((it) => it === "-" ? h("hr") :
    h("button", { type: "button", role: "menuitem", class: it.red ? "red" : "", onclick: () => { closePop(); it.run(); } }, it.icon ? svg(it.icon) : null, it.label)));
  document.body.append(el); popEl = el;
  const r = anchor.getBoundingClientRect(), w = el.offsetWidth, hgt = el.offsetHeight;
  let left = (opts && opts.right) ? r.right + 6 : r.left, top = (opts && opts.up) ? r.bottom - hgt : r.bottom + 4;
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8)); top = Math.max(8, Math.min(top, window.innerHeight - hgt - 8));
  el.style.left = left + "px"; el.style.top = top + "px";
  el.querySelector("button") && el.querySelector("button").focus();
}
document.addEventListener("click", (e) => { if (popEl && !popEl.contains(e.target) && !e.target.closest("[data-pop]")) closePop(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePop(); });

// ---- điều hướng ---------------------------------------------------------------------
const WIDE = new Set(["watch", "services", "settings"]);
const LIST_TABS = new Set(["chats", "contacts", "calls"]);
function setTab(tab) {
  S.tab = tab; closePop();
  const app = $("app"); app.dataset.tab = tab;
  document.querySelectorAll(".rail-btn[data-tab]").forEach((b) => { if (b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  S.q = ""; $("q").value = "";
  if (WIDE.has(tab)) { app.dataset.pane = "main"; showPane("pane-" + tab); }
  else {
    app.dataset.pane = "list";
    showPane(tab === "calls" ? "pane-calls" : tab === "contacts" ? "pane-contacts" : S.cur ? "pane-chat" : "pane-empty");
    renderChips(); renderList();
    if (tab === "calls") renderCallsPage();
    if (tab === "contacts") renderContactsPage();
  }
  if (tab === "services") renderServices();
  if (tab === "settings") renderSettings();
  if (tab === "watch") renderWatch();
  syncInfo();
}
function showPane(id) { document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("on", p.id === id)); }
function toList() {
  $("app").dataset.pane = "list";
  if (S.tab === "chats") { S.cur = null; stopPoll(); history.replaceState(null, "", location.pathname); showPane("pane-empty"); renderList(); syncInfo(); }
}

// ---- danh sách bên trái ----------------------------------------------------------------
function renderChips() {
  const box = $("chips"); box.replaceChildren();
  if (S.tab === "chats") {
    box.append(h("div", { class: "tabs" },
      ...[["all", "Tất cả"], ["unread", "Chưa đọc"]].map(([id, label]) => h("button", { class: "tab", type: "button", "aria-pressed": String(S.filter.chats === id), onclick: () => { S.filter.chats = id; renderChips(); renderList(); } }, label)),
      h("span", { class: "sp" }),
      h("select", { class: "sel", "aria-label": "Phân loại", onchange: (e) => { S.kind = e.target.value; renderList(); } },
        ...[["all", "Phân loại"], ["user", "Cá nhân"], ["group", "Nhóm"], ["stranger", "Người lạ"]].map(([v, l]) => h("option", { value: v, selected: S.kind === v }, l)))));
  } else if (S.tab === "calls") {
    box.append(h("div", { class: "chips", style: "padding-bottom:.5rem" }, ...[["all", "Tất cả"], ["missed", "Nhỡ / lỗi"]].map(([id, label]) =>
      h("button", { class: "chip", type: "button", "aria-pressed": String(S.filter.calls === id), onclick: () => { S.filter.calls = id; renderChips(); renderCallRows($("list")); renderCallsPage(); } }, label))));
  }
}
function convRow(c) {
  const row = rowOf(c.thread_type, c.thread_id) || { id: c.thread_id, type: c.thread_type, name: c.name || "", avatar: "" };
  return Object.assign({}, row, { name: row.name || c.name || "", stranger: !!c.stranger });
}
const convName = (c) => (rowOf(c.thread_type, c.thread_id) || {}).name || c.name || c.thread_id;
function renderList() {
  const ul = $("list"), foot = $("list-foot"); ul.replaceChildren(); foot.replaceChildren();
  $("btn-reload").hidden = !(S.tab === "chats" || S.tab === "contacts");
  $("q").parentElement.parentElement.hidden = !LIST_TABS.has(S.tab);
  if (S.tab === "calls") return renderCallRows(ul);
  if (S.tab === "contacts") return renderContactMenu(ul);
  const q = plain(S.q.trim());
  let list = Object.values(S.conv).filter((c) => c.count !== 0);
  if (S.filter.chats === "unread") list = list.filter((c) => c.unread > 0);
  if (S.kind === "user") list = list.filter((c) => c.thread_type === "user");
  if (S.kind === "group") list = list.filter((c) => c.thread_type === "group");
  if (S.kind === "stranger") list = list.filter((c) => c.stranger);
  if (q) list = list.filter((c) => plain(convName(c)).includes(q) || c.thread_id.includes(q) || plain(c.last_text).includes(q));
  list.sort((a, b) => (b.last_ts || 0) - (a.last_ts || 0));
  for (const c of list) {
    const row = convRow(c), unread = c.unread > 0;
    const sub = (c.last_out ? "Bạn: " : (c.thread_type === "group" && c.last_sender_name ? c.last_sender_name + ": " : "")) + (c.last_text || "");
    ul.append(h("li", {}, h("button", { class: "row" + (unread ? " unread" : ""), type: "button", "aria-current": S.cur && rowKey(S.cur) === rowKey(c) ? "true" : null, onclick: () => openThread(row) },
      avatar(row), h("div", { class: "row-main" },
        h("div", { class: "row-top" }, h("span", { class: "row-name" }, convName(c)), h("span", { class: "row-time" }, fmtRel(c.last_ts))),
        h("div", { class: "row-sub" }, row.stranger ? h("span", { class: "pill warn", style: "margin-right:.375rem" }, "Người lạ") : null, sub)),
      unread ? h("span", { class: "badge", "aria-label": c.unread + " tin chưa đọc" }, c.unread > 99 ? "99+" : c.unread) : null)));
  }
  if (q) {   // tìm cả trong danh bạ để bắt đầu trò chuyện mới
    const have = new Set(list.map((c) => c.thread_type + "|" + c.thread_id));
    const more = allRows().filter((r) => !have.has(rowKey(r)) && (plain(r.name).includes(q) || r.id.includes(q))).slice(0, 30);
    if (more.length) ul.append(h("li", { class: "list-note", style: "text-align:left;margin:.75rem 1rem .25rem" }, "Trong danh bạ"));
    for (const r of more) ul.append(h("li", {}, h("button", { class: "row", type: "button", onclick: () => openThread(r) }, avatar(r), h("div", { class: "row-main" }, h("div", { class: "row-name" }, r.name || r.id), h("div", { class: "row-sub" }, r.type === "group" ? "Nhóm" : "Bạn bè · " + r.id)))));
  }
  if (!ul.children.length) {
    ul.append(h("li", { class: "list-note" }, S.contactsErr || (S.filter.chats === "unread" ? "Không có tin chưa đọc." : q ? "Không tìm thấy kết quả." : "Chưa có tin nhắn nào."),
      !q && S.filter.chats !== "unread" ? h("div", { style: "margin-top:.75rem" }, h("button", { class: "btn", type: "button", onclick: () => setTab("contacts") }, "Mở danh bạ")) : null));
  }
  const total = unreadTotal();
  foot.append(h("span", {}, list.length + " hội thoại" + (total ? " · " + total + " chưa đọc" : "")), h("span", { class: "pill" }, h("span", { class: "live" + (S.sse ? "" : " off") }), S.sse ? "tức thì" : "đang nối…"));
}
function renderBadges() {
  const total = unreadTotal(), dot = $("dot-chats");
  dot.hidden = total <= 0; dot.textContent = total > 99 ? "99+" : String(total);
  const st = strangerList().reduce((n, c) => n + (c.unread || 0), 0), w = $("dot-watch");
  w.hidden = st <= 0; w.textContent = st > 99 ? "99+" : String(st);
  document.title = (total > 0 ? "(" + total + ") " : "") + "Zalo";
}

// ---- khung chat --------------------------------------------------------------------------------
function openThread(row) {
  if (S.tab !== "chats") setTab("chats");
  S.cur = row; S.msgs = []; S.files = {}; S.lastTime = 0; S.stick = true;
  $("app").dataset.pane = "main"; showPane("pane-chat");
  $("chat-av").replaceWith(Object.assign(avatar(row), { id: "chat-av" }));
  $("chat-name").textContent = row.name || row.id;
  const kind = row.type === "group" ? "Nhóm" + (row.members && row.members.length ? " · " + row.members.length + " thành viên" : "") : (row.stranger || (S.conv[rowKey(row)] || {}).stranger ? "Người lạ" : "Bạn bè");
  $("chat-sub").replaceChildren(kind + " · ", h("button", { class: "link mono", type: "button", title: "Sao chép threadId", onclick: () => copyText(row.id, "threadId") }, row.id));
  $("btn-video").hidden = row.type === "group";
  setNotice(""); $("msg-in").value = ""; autosize();
  history.replaceState(null, "", "#/" + row.type + "/" + encodeURIComponent(row.id));
  const c = S.conv[rowKey(row)]; if (c) c.unread = 0;
  renderBadges(); renderList(); renderMsgs(); syncInfo(); syncCallButtons();
  loadHistory(); startPoll();
}
function normMsg(m) {
  const out = m.direction === "out" || m.sender_id === "me" || (S.uid && String(m.sender_id) === S.uid);
  return Object.assign({}, m, { _id: String(m.id || m.client_id || ""), _out: out, _t: Number(m.time || m.ts || 0) });
}
function mergeMsgs(list) {
  const seen = new Map(S.msgs.map((m, i) => [m._id || "x" + i, m]));
  let n = 0;
  for (const raw of list) { const m = normMsg(raw); seen.set(m._id || "n" + (n++) + Math.random(), m); }
  S.msgs = [...seen.values()].sort((a, b) => a._t - b._t);
  S.lastTime = S.msgs.reduce((x, m) => Math.max(x, m._t), 0);
}
async function loadHistory() {
  const cur = S.cur; if (!cur) return;
  const d = await api("/api/thread/" + encodeURIComponent(cur.id) + "/history?type=" + typeParam() + "&count=50");
  if (S.cur !== cur) return;
  if (d.error) return setNotice("Lỗi tải lịch sử: " + d.error, true);
  setNotice(d.notice || "");
  await loadFiles(); mergeMsgs(d.messages || []); renderMsgs();
  const ids = (d.messages || []).map((m) => m.id).filter((x) => x && x !== "me");
  if (ids.length) api("/api/thread/" + encodeURIComponent(cur.id) + "/seen", "POST", { type: typeParam(), msg_ids: ids }).catch(() => {});
}
async function loadFiles() {
  if (!S.cur) return;
  try { const d = await api("/api/file/list?thread_type=" + typeParam() + "&thread_id=" + encodeURIComponent(S.cur.id)); S.files = {}; for (const f of d.files || []) S.files[String(f.msg_id)] = f; } catch (e) { /* giữ bản cũ */ }
}
function stopPoll() { if (S.pollT) { clearInterval(S.pollT); S.pollT = null; } }
function startPoll() {   // lưới an toàn: SSE lo việc tức thì, vòng này chỉ bù khi SSE đứt
  stopPoll();
  S.pollT = setInterval(async () => {
    if (!S.cur || document.hidden || S.sse) return;
    const cur = S.cur;
    try {
      const d = await api("/api/thread/" + encodeURIComponent(cur.id) + "/updates?type=" + typeParam() + "&after=" + Math.max(0, S.lastTime - 1));
      if (S.cur !== cur || d.error || !(d.messages || []).length) return;
      const before = S.msgs.length; mergeMsgs(d.messages);
      if (S.msgs.length !== before) { await loadFiles(); renderMsgs(); }
    } catch (e) { /* tick sau */ }
  }, 3000);
}
const downloadUrl = (m) => "/api/file/download?thread_type=" + typeParam() + "&thread_id=" + encodeURIComponent(S.cur.id) + "&msg_id=" + encodeURIComponent(m._id);
function photoSrc(m) { const rec = S.files[m._id]; return m.localUrl || (rec && rec.status === "downloaded" ? downloadUrl(m) : ""); }
function bubbleBody(m) {
  const rec = S.files[m._id], dl = rec && rec.status === "downloaded";
  if (m.kind === "photo") { const src = photoSrc(m); if (src) return h("img", { class: "photo", src, alt: m.file_name || "Ảnh" }); }
  if (m.kind === "voice") return h("div", { class: "filecard" }, h("span", { class: "ficon" }, svg("mic")), h("div", {}, h("div", { class: "fname" }, "Tin nhắn thoại"), m.file_url ? h("audio", { controls: true, preload: "none", src: m.file_url, style: "height:2rem;margin-top:.25rem;max-width:100%" }) : h("div", { class: "fmeta" }, m.file_name || "")));
  if (m.kind === "file" || m.kind === "photo") {
    let act = null;
    if (!m._out) {
      if (dl) act = h("a", { class: "link", href: downloadUrl(m) }, "Tải xuống");
      else if (rec && rec.status === "failed") act = h("button", { class: "link", type: "button", onclick: () => redownload(m) }, "Tải lại");
      else if (m.file_url) act = h("a", { class: "link", href: m.file_url, target: "_blank", rel: "noopener" }, "Mở");
    }
    return h("div", { class: "filecard" }, h("span", { class: "ficon" }, svg("file")), h("div", {}, h("div", { class: "fname" }, m.file_name || m.text || "Tệp đính kèm"), h("div", { class: "fmeta" }, fmtSize(m.file_size)), act));
  }
  return document.createTextNode(m.text || "");
}
async function redownload(m) {
  const r = await api("/api/file/redownload", "POST", { thread_type: typeParam(), thread_id: S.cur.id, msg_id: m._id });
  toast(r.error ? "Tải lại lỗi: " + r.error : "Đang tải lại tệp…");
  setTimeout(async () => { await loadFiles(); renderMsgs(); }, 2500);
}
function renderMsgs() {
  const box = $("msgs"), near = box.scrollHeight - box.scrollTop - box.clientHeight < 90, frag = document.createDocumentFragment();
  let day = "", prev = null;
  if (!S.msgs.length) frag.append(h("div", { class: "empty", style: "margin:auto" }, "Chưa có tin nhắn. Hãy gửi lời chào."));
  for (const m of S.msgs) {
    const d = m._t ? new Date(m._t * 1000).toDateString() : "";
    if (d && d !== day) { day = d; frag.append(h("div", { class: "day" }, fmtDay(m._t))); prev = null; }
    const first = !(prev && prev._out === m._out && prev.sender_id === m.sender_id && m._t - prev._t < 120);
    const sender = { id: String(m.sender_id), name: m.sender_name || (S.cur.type === "user" && !m._out ? S.cur.name : ""), avatar: S.cur.type === "user" && !m._out ? S.cur.avatar : "" };
    frag.append(h("div", { class: "msg " + (m._out ? "out" : "in") },
      m._out ? null : (first ? avatar(sender, "sm") : h("span", { class: "gap" })),
      h("div", { class: "mcol" },
        !m._out && S.cur.type === "group" && first && (m.sender_name || m.sender_id) ? h("div", { class: "who" }, m.sender_name || m.sender_id) : null,
        h("div", { class: "bub" }, bubbleBody(m), h("span", { class: "bt" }, fmtTime(m._t))))));
    prev = m;
  }
  box.replaceChildren(frag);
  if (near || S.stick) { box.scrollTop = box.scrollHeight; S.stick = false; }
  if (S.info) syncInfo();
}
function setNotice(text, bad) { const n = $("chat-notice"); n.hidden = !text; n.textContent = text || ""; n.className = "notice" + (bad ? " bad" : ""); }
function autosize() { const t = $("msg-in"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; updateSendButtons(); }
function updateSendButtons() { const has = $("msg-in").value.trim() !== ""; $("btn-send").hidden = !has; $("btn-like").hidden = has; }
function touchConv(type, id, msg, opts) {   // cập nhật dòng hội thoại ngay, không chờ gọi lại máy chủ
  const key = type + "|" + id;
  const c = S.conv[key] || (S.conv[key] = { thread_type: type, thread_id: String(id), count: 0, incoming_count: 0, unread: 0, name: "", stranger: false });
  const m = normMsg(msg);
  c.count++; c.last_ts = m._t || Date.now() / 1000; c.last_out = m._out;
  c.last_text = m.kind === "photo" ? "[Ảnh]" : m.kind === "voice" ? "[Tin nhắn thoại]" : m.kind === "file" ? "[Tệp] " + (m.file_name || "") : (m.text || "");
  c.last_sender_name = m.sender_name || c.last_sender_name || "";
  if (!m._out) { c.incoming_count++; if (m.sender_name && type === "user") c.name = m.sender_name; if (!(opts && opts.open)) c.unread++; }
  if (opts && opts.stranger != null) c.stranger = !!opts.stranger;
  return c;
}
async function sendRaw(text) {
  if (!text || !S.cur) return;
  const r = await api("/api/thread/" + encodeURIComponent(S.cur.id) + "/send", "POST", { type: typeParam(), message: text });
  if (r.error) { setNotice("Lỗi gửi tin: " + r.error, true); return false; }
  setNotice("");
  if (r.message) { mergeMsgs([r.message]); touchConv(S.cur.type, S.cur.id, r.message, { open: true }); S.stick = true; renderMsgs(); renderList(); }
  return true;
}
async function sendText() {
  const input = $("msg-in"), text = input.value.trim(); if (!text) return;
  input.value = ""; autosize();
  if (!(await sendRaw(text))) { input.value = text; autosize(); }
}
function imageDims(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file), img = new Image(), done = (w, hh) => { URL.revokeObjectURL(url); resolve({ w, h: hh }); }, t = setTimeout(() => done(0, 0), 5000);
    img.onload = () => { clearTimeout(t); done(img.naturalWidth, img.naturalHeight); }; img.onerror = () => { clearTimeout(t); done(0, 0); }; img.src = url;
  });
}
const PHOTO = /^image\/(jpeg|png|webp)$/;
async function sendFiles(files) {
  if (!S.cur) return toast("Hãy mở một cuộc trò chuyện trước.");
  const list = [...files]; let ok = 0;
  for (let i = 0; i < list.length; i++) {
    const f = list[i]; toast("Đang gửi " + (i + 1) + "/" + list.length + ": " + f.name, 30000);
    const form = new FormData(); form.append("type", typeParam());
    const photo = PHOTO.test(f.type); form.append("kind", photo ? "photo" : "file");
    if (photo) { const d = await imageDims(f); form.append("width", d.w); form.append("height", d.h); }
    form.append("file", f, f.name);
    const r = await apiForm("/api/thread/" + encodeURIComponent(S.cur.id) + "/sendfile", form);
    if (r.error) { setNotice("Không gửi được “" + f.name + "”: " + r.error, true); continue; }
    ok++;
    if (r.message) { if (photo) r.message.localUrl = URL.createObjectURL(f); mergeMsgs([r.message]); touchConv(S.cur.type, S.cur.id, r.message, { open: true }); S.stick = true; renderMsgs(); renderList(); }
  }
  if (ok) { setNotice(""); toast("Đã gửi " + ok + " tệp."); } else $("toast").hidden = true;
}
async function toggleRecord() {
  const btn = $("btn-rec");
  if (S.rec) { S.rec.stop(); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return toast("Trình duyệt không cho ghi âm (cần micro và HTTPS hoặc localhost).", 5000);
  let stream; try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { return toast("Không mở được micro: " + (e.message || e), 5000); }
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m));
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined), chunks = []; let cancelled = false; const started = Date.now();
  const bar = h("div", { class: "recbar" }, h("span", { class: "rdot" }), h("span", { id: "rec-t" }, "00:00"), h("span", { style: "flex:1" }), h("button", { class: "link", type: "button", style: "color:inherit", onclick: () => { cancelled = true; rec.stop(); } }, "Huỷ"));
  const timer = setInterval(() => { const t = $("rec-t"); if (t) t.textContent = fmtDur((Date.now() - started) / 1000); }, 500);
  $("msg-in").hidden = true; $("msg-in").after(bar); btn.replaceChildren(svg("stop")); btn.setAttribute("aria-label", "Dừng và gửi");
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  rec.onstop = async () => {
    clearInterval(timer); stream.getTracks().forEach((t) => t.stop()); bar.remove(); $("msg-in").hidden = false;
    btn.replaceChildren(svg("mic")); btn.setAttribute("aria-label", "Ghi âm tin nhắn thoại"); S.rec = null;
    if (cancelled || !chunks.length || !S.cur) return;
    const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" }), form = new FormData();
    form.append("type", typeParam()); form.append("file", new File([blob], "voice." + (blob.type.includes("mp4") ? "mp4" : "webm"), { type: blob.type }));
    toast("Đang chuyển sang AAC và gửi…", 60000);
    const r = await apiForm("/api/thread/" + encodeURIComponent(S.cur.id) + "/sendvoice", form, 180000);
    if (r.error) return setNotice("Lỗi gửi tin nhắn thoại: " + r.error, true);
    $("toast").hidden = true; setNotice("");
    if (r.message) { mergeMsgs([r.message]); touchConv(S.cur.type, S.cur.id, r.message, { open: true }); S.stick = true; renderMsgs(); renderList(); }
  };
  S.rec = rec; rec.start();
}
const EMOJI = "😀 😁 😂 🤣 😊 😍 😘 😎 🤔 😅 😢 😭 😡 😱 🙄 😴 👍 👎 👏 🙏 💪 🤝 👌 ✌️ ❤️ 💔 🔥 ⭐ 🎉 🎂 🌹 ☕ 🍻 🍜 🏠 📞 📷 ✅ ❌ ⚠️ 💡 🚗 ⏰ 💰 🎁 🌧️ ☀️".split(" ");
function toggleEmoji() {
  const box = $("emoji"); if (!box.hidden) { box.hidden = true; return; }
  box.replaceChildren(...EMOJI.map((e) => h("button", { type: "button", "aria-label": e, onclick: () => { const t = $("msg-in"), a = t.selectionStart, b = t.selectionEnd; t.value = t.value.slice(0, a) + e + t.value.slice(b); t.focus(); t.setSelectionRange(a + e.length, a + e.length); autosize(); } }, e)));
  box.hidden = false;
}

// ---- bảng thông tin bên phải ---------------------------------------------------------------------------
function syncInfo() {
  const app = $("app"), on = S.info && S.tab === "chats" && !!S.cur && root.dataset.bp === "wide";
  app.dataset.info = on ? "on" : "off"; $("btn-info").setAttribute("aria-pressed", String(!!S.info));
  if (on) renderInfo();
}
function infoSection(title, ...body) { return h("section", { class: "isec" }, h("h4", {}, title), ...body); }
function renderInfo() {
  const row = S.cur, box = $("info"), isGroup = row.type === "group", c = S.conv[rowKey(row)] || {};
  const members = (row.members || []).map((m) => typeof m === "object" ? { id: String(m.id || m.userId || ""), name: m.name || m.dName || m.displayName || "" } : { id: String(m), name: "" });
  const nameOf = (m) => m.name || (rowOf("user", m.id) || {}).name || m.id;
  const photos = S.msgs.filter((m) => m.kind === "photo" && photoSrc(m)).slice(-8).reverse();
  const files = S.msgs.filter((m) => m.kind === "file").slice(-6).reverse();
  put(box,
    h("div", { class: "info-h" }, isGroup ? "Thông tin nhóm" : "Thông tin hội thoại"),
    h("div", { class: "info-top" }, avatar(row, "xl"), h("div", { class: "info-name" }, row.name || row.id),
      h("div", { class: "info-sub" }, isGroup ? "Nhóm" : c.stranger || row.stranger ? "Người lạ (không có trong danh bạ)" : "Bạn bè"),
      h("div", { style: "margin-top:.5rem;display:flex;justify-content:center;align-items:center;gap:.25rem" }, h("span", { class: "mono" }, row.id), h("button", { class: "icon-btn", type: "button", "aria-label": "Sao chép threadId", title: "Sao chép threadId", onclick: () => copyText(row.id, "threadId") }, svg("copy"))),
      h("div", { class: "info-acts" },
        h("button", { class: "iact", type: "button", disabled: !!S.calls.active, onclick: () => startCall(false) }, h("span", { class: "c" }, svg("phone")), "Gọi thoại"),
        isGroup ? null : h("button", { class: "iact", type: "button", disabled: !!S.calls.active, onclick: () => startCall(true) }, h("span", { class: "c" }, svg("video")), "Gọi video"),
        h("button", { class: "iact", type: "button", onclick: () => setTab("services") }, h("span", { class: "c" }, svg("grid")), "Dịch vụ"))),
    isGroup ? infoSection("Thành viên (" + members.length + ")", members.length ? h("div", { class: "imembers" }, members.slice(0, 100).map((m) => h("div", { class: "imember" }, avatar({ id: m.id, name: nameOf(m), avatar: (rowOf("user", m.id) || {}).avatar }, "sm"), h("span", {}, nameOf(m))))) : h("p", { class: "inote" }, "Chưa tải được danh sách thành viên.")) : null,
    infoSection("Ảnh/Video", photos.length ? h("div", { class: "igrid" }, photos.map((m) => h("a", { href: photoSrc(m), target: "_blank", rel: "noopener" }, h("img", { src: photoSrc(m), alt: m.file_name || "Ảnh", loading: "lazy" })))) : h("p", { class: "inote" }, "Chưa có ảnh nào được tải trong cuộc trò chuyện này.")),
    infoSection("Tệp", files.length ? h("div", { class: "imembers" }, files.map((m) => h("div", { class: "imember" }, svg("file"), h("span", { style: "flex:1;min-width:0;overflow-wrap:anywhere" }, m.file_name || m.text || "Tệp"), h("span", { class: "inote" }, fmtSize(m.file_size))))) : h("p", { class: "inote" }, "Chưa có tệp nào.")));
}

// ---- cuộc gọi ------------------------------------------------------------------------------------------------
const END_REASON = { ring_timeout: "Không ai nghe máy", user_end: "Đã kết thúc", server_rejected: "Máy chủ Zalo từ chối", superseded_by_new_call: "Bị thay bằng cuộc gọi mới", peer_ended: "Bên kia đã cúp", answered: "Đã nghe máy" };
const endText = (d) => END_REASON[d] || d || "";
function syncCallButtons() { const busy = !!S.calls.active; $("btn-call").disabled = busy; $("btn-video").disabled = busy; }
async function loadCalls() {
  let d; try { d = await api("/api/calls"); } catch (e) { return; }
  if (d.error) return;
  const prev = S.calls.active; S.calls = { active: d.active || null, calls: d.calls || [] };
  if (prev && !S.calls.active) { const done = S.calls.calls.find((c) => String(c.call_id) === String(prev.call_id)); toast("Cuộc gọi với " + (prev.peer || prev.thread_id) + " đã kết thúc" + (done && done.detail ? ": " + endText(done.detail) : "."), 5000); }
  renderCallCard(); syncCallButtons(); $("dot-calls").hidden = !S.calls.active;
  if (S.cur && S.info) syncInfo();
  if (S.tab === "calls") { renderCallRows($("list")); renderCallsPage(); }
}
async function startCall(video) {
  const row = S.cur; if (!row || S.calls.active) return;
  const type = row.type === "group" ? "group" : video ? "video" : "user";
  toast("Đang gọi " + (row.name || row.id) + "…");
  const r = await api("/api/call/request", "POST", { callee_id: row.id, type, peer_name: row.name || row.id, partners: row.members || [] });
  if (r.error) return toast("Không gọi được: " + r.error, 6000);
  if (r.request_sent === false) toast("Đã gửi yêu cầu nhưng bước 2 chưa gửi được: " + (r.request_error || "không rõ"), 7000);
  await loadCalls();
}
async function endCall() { const a = S.calls.active; if (!a) return; const r = await api("/api/call/end", "POST", { call_id: a.call_id }); if (r.error) toast("Lỗi kết thúc cuộc gọi: " + r.error, 5000); await loadCalls(); }
function renderCallCard() {
  const card = $("callcard"), a = S.calls.active;
  if (!a) { card.hidden = true; card.replaceChildren(); return; }
  const row = rowOf(a.type === "group" ? "group" : "user", a.thread_id) || { id: String(a.thread_id), name: a.peer, type: a.type === "group" ? "group" : "user" };
  const answered = a.status === "answered" || !!a.answered_at, ringing = !answered && a.request_sent === true;
  const since = (answered && a.answered_at) || a.started_at, noMedia = !S.status || !S.status.engine || !S.status.engine.attached;
  card.hidden = false;
  put(card,
    h("div", { class: "top" }, avatar(row), h("div", { style: "flex:1;min-width:0" }, h("div", { class: "nm" }, (a.type === "video" ? "Video · " : "") + (a.peer || a.thread_id)), h("div", { class: "st" }, answered ? "Đang trong cuộc gọi" : ringing ? "Đang đổ chuông…" : "Đang kết nối…"), h("div", { class: "tm", id: "call-t" }, fmtDur(Date.now() / 1000 - since)))),
    answered && noMedia ? h("div", { class: "warn" }, "Máy bên kia đã nghe nhưng app chưa có tiếng/hình trong cuộc gọi (đang phát triển), nên họ có thể báo “kết nối không ổn định”.") : null,
    a.request_sent === false ? h("div", { class: "warn" }, "Bước 2 chưa gửi được, bên kia có thể chưa đổ chuông.") : null,
    h("div", { class: "acts" }, h("button", { class: "end", type: "button", onclick: endCall }, svg("hang"), "Kết thúc")));
  card._since = since;
}
setInterval(() => { const c = $("callcard"), t = $("call-t"); if (t && c._since) t.textContent = fmtDur(Date.now() / 1000 - c._since); }, 1000);
function callPill(c) {
  if (c.status === "answered" || c.answered_at) return h("span", { class: "pill ok" }, "Đã nghe máy");
  if (c.status === "error" || c.detail === "server_rejected") return h("span", { class: "pill bad" }, "Lỗi");
  if (c.detail === "ring_timeout") return h("span", { class: "pill warn" }, "Không nghe máy");
  if (c.status === "sent") return h("span", { class: "pill" }, "Đang gọi");
  return h("span", { class: "pill" }, endText(c.detail) || "Đã kết thúc");
}
function callList() {
  let list = S.calls.calls.filter((c) => !S.q || plain(c.peer).includes(plain(S.q)) || String(c.thread_id).includes(S.q));
  if (S.filter.calls === "missed") list = list.filter((c) => !(c.status === "answered" || c.answered_at));
  return list;
}
function renderCallRows(ul) {
  ul.replaceChildren(); const list = callList();
  if (!list.length) ul.append(h("li", { class: "list-note" }, "Chưa có cuộc gọi nào."));
  for (const c of list) {
    const row = rowOf(c.type === "group" ? "group" : "user", c.thread_id) || { id: String(c.thread_id), name: c.peer, type: c.type === "group" ? "group" : "user" };
    ul.append(h("li", {}, h("button", { class: "row", type: "button", onclick: () => openThread(row) }, avatar(row), h("div", { class: "row-main" },
      h("div", { class: "row-top" }, h("span", { class: "row-name" }, c.peer || c.thread_id), h("span", { class: "row-time" }, fmtRel(c.started_at))),
      h("div", { class: "row-sub" }, (c.type === "video" ? "Video · " : c.type === "group" ? "Nhóm · " : "Thoại · ") + (endText(c.detail) || c.status))))));
  }
}
function renderCallsPage() {
  const box = $("calls-page"); box.replaceChildren(); const list = callList();
  $("calls-sub").textContent = S.calls.active ? "Đang có cuộc gọi" : list.length + " cuộc gần đây";
  box.append(h("div", { class: "card wide" }, h("h3", {}, "Lịch sử cuộc gọi"),
    !list.length ? h("p", { style: "color:var(--muted);margin:0" }, "Chưa có cuộc gọi nào. Mở một cuộc trò chuyện và bấm biểu tượng điện thoại hoặc video.") :
      h("div", {}, list.map((c) => h("div", { style: "display:flex;gap:.625rem;align-items:center;padding:.5rem 0;border-top:1px solid var(--line)" },
        h("div", { style: "flex:1;min-width:0" }, h("div", { style: "font-weight:500" }, c.peer || c.thread_id), h("div", { style: "color:var(--muted);font-size:.78rem" }, (c.type === "video" ? "Video" : c.type === "group" ? "Nhóm" : "Thoại") + " · " + fmtDT(c.started_at) + (c.ended_at ? " · " + fmtDur(c.ended_at - c.started_at) : ""))), callPill(c))))));
}

// ---- danh bạ --------------------------------------------------------------------------------------------------
const CMENU = [["friends", "Danh sách bạn bè", "user"], ["groups", "Danh sách nhóm và cộng đồng", "users"], ["invites", "Lời mời kết bạn", "userplus"], ["ginvites", "Lời mời vào nhóm và cộng đồng", "users"]];
function renderContactMenu(ul) {
  for (const [id, label, icon] of CMENU) ul.append(h("li", { class: "cmenu" }, h("button", { class: "row", type: "button", "aria-current": S.cmenu === id ? "true" : null, onclick: () => { S.cmenu = id; renderContactMenu(ul.replaceChildren() || ul); renderContactsPage(); $("app").dataset.pane = "main"; } }, svg(icon), label)));
  $("list-foot").replaceChildren(h("span", {}, S.friends.length + " bạn · " + S.groups.length + " nhóm"));
}
function contactMenu(anchor, r) {
  popup(anchor, [{ label: "Nhắn tin", icon: "chat", run: () => openThread(r) }, { label: "Gọi thoại", icon: "phone", run: () => { openThread(r); setTimeout(() => startCall(false), 50); } },
    r.type === "user" ? { label: "Gọi video", icon: "video", run: () => { openThread(r); setTimeout(() => startCall(true), 50); } } : null,
    { label: "Sao chép threadId", icon: "copy", run: () => copyText(r.id, "threadId") }, { label: "Dịch vụ…", icon: "grid", run: () => { S.cur = r; setTab("services"); } }].filter(Boolean));
}
async function renderContactsPage() {
  const box = $("contacts-page"); box.replaceChildren();
  const title = CMENU.find((m) => m[0] === S.cmenu)[1]; $("contacts-title").textContent = title;
  if (S.cmenu === "invites") {
    box.append(h("div", { class: "card wide" }, h("h3", {}, "Lời mời kết bạn đã gửi"), h("p", { id: "inv-body", style: "color:var(--muted);margin:0" }, "Đang tải…")));
    const d = await api("/api/svc/get_sent_friend_requests", "POST", {}); const body = $("inv-body"); if (!body) return;
    const list = Array.isArray(d.data) ? d.data : d.data && Array.isArray(d.data.requests) ? d.data.requests : null;
    if (d.error) body.textContent = "Không tải được: " + d.error;
    else if (list && list.length) body.replaceChildren(...list.map((x) => h("div", { class: "crow" }, h("span", { class: "cname", style: "cursor:default" }, x.displayName || x.zaloName || x.userId || x.uid || JSON.stringify(x).slice(0, 80)))));
    else body.textContent = "Không có lời mời nào đang chờ.";
    return;
  }
  if (S.cmenu === "ginvites") return void box.append(h("div", { class: "card wide" }, h("h3", {}, title), h("p", { style: "color:var(--muted);margin:0" }, "Zalo PC chưa cho app đọc danh sách lời mời vào nhóm. Khi có người mời, tin báo sẽ hiện trong mục Tin nhắn.")));
  let rows = S.cmenu === "groups" ? S.groups : S.friends;
  const q = plain(S.q);
  rows = rows.filter((r) => !q || plain(r.name).includes(q) || r.id.includes(q));
  rows = [...rows].sort((a, b) => (a.name || "").localeCompare(b.name || "", "vi") * (S.csort === "za" ? -1 : 1));
  box.append(h("p", { style: "font-weight:600;margin:0 0 .625rem" }, (S.cmenu === "groups" ? "Nhóm" : "Bạn bè") + " (" + rows.length + ")"));
  const local = h("input", { type: "search", placeholder: S.cmenu === "groups" ? "Tìm nhóm" : "Tìm bạn", "aria-label": "Tìm trong danh bạ", value: S.q, oninput: (e) => { S.q = e.target.value; $("q").value = S.q; renderContactsPage(); } });
  box.append(h("div", { class: "cbar" }, h("div", { class: "search" }, svg("search"), local), h("select", { "aria-label": "Sắp xếp", onchange: (e) => { S.csort = e.target.value; renderContactsPage(); } }, h("option", { value: "az", selected: S.csort === "az" }, "Tên (A-Z)"), h("option", { value: "za", selected: S.csort === "za" }, "Tên (Z-A)"))));
  if (!rows.length) return void box.append(h("p", { style: "color:var(--muted)" }, S.contactsErr || "Không có kết quả."));
  let letter = "";
  const card = h("div", { class: "card wide" });
  for (const r of rows) {
    const L = (plain(r.name)[0] || "#").toUpperCase(); const key = /[A-Z]/.test(L) ? L : "#";
    if (key !== letter) { letter = key; card.append(h("div", { class: "letter" }, key)); }
    const more = h("button", { class: "icon-btn", type: "button", "data-pop": "1", "aria-label": "Tuỳ chọn", onclick: () => contactMenu(more, r) }, svg("more"));
    card.append(h("div", { class: "crow" }, avatar(r), h("div", { class: "cname", role: "button", tabindex: "0", onclick: () => openThread(r), onkeydown: (e) => { if (e.key === "Enter") openThread(r); } }, r.name || r.id, h("div", { class: "mono", style: "color:var(--muted);font-weight:400" }, r.id)), more));
  }
  box.append(card);
}

// ---- theo dõi người lạ ---------------------------------------------------------------------------------------------
async function renderWatch() {
  const box = $("watch-page"); box.replaceChildren();
  const list = strangerList().sort((a, b) => (b.last_ts || 0) - (a.last_ts || 0));
  $("watch-sub").textContent = list.length + " người lạ đã nhắn" + (S.contactsMeta ? "" : " · đang tải danh bạ");
  box.append(h("div", { class: "card wide" }, h("h3", {}, "Người lạ nhắn tin vào"),
    h("p", { style: "color:var(--muted);margin:0 0 .75rem;font-size:.85rem" }, "Người không có trong danh bạ nhắn cho tài khoản này sẽ hiện ở đây ngay khi tin tới, kèm tên hiển thị và threadId (dùng được cho dịch vụ, webhook, trợ lý AI). Bấm một dòng để xem các tin gần nhất."),
    !list.length ? h("p", { style: "margin:0" }, "Chưa có người lạ nào nhắn.") :
      h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ...["Tên", "threadId", "Tin gần nhất", "Số tin", ""].map((t) => h("th", {}, t)))),
        h("tbody", {}, ...list.flatMap((c) => {
          const open = S.watchOpen === c.thread_id, row = convRow(c);
          const tr = h("tr", { class: open ? "sel" : "", style: "cursor:pointer", onclick: async () => { S.watchOpen = open ? null : c.thread_id; if (S.watchOpen && !S.watchMsgs[c.thread_id]) { const d = await api("/api/thread/" + c.thread_id + "/history?type=user&count=10"); S.watchMsgs[c.thread_id] = d.messages || []; } renderWatch(); } },
            h("td", {}, h("div", { style: "display:flex;gap:.625rem;align-items:center" }, avatar(row, "sm"), h("div", {}, h("div", { style: "font-weight:500" }, convName(c)), h("div", { style: "color:var(--muted);font-size:.75rem" }, "Từ " + fmtDT(c.first_ts))))),
            h("td", { class: "nw" }, h("span", { class: "mono" }, c.thread_id), " ", h("button", { class: "icon-btn", type: "button", "aria-label": "Sao chép threadId", onclick: (e) => { e.stopPropagation(); copyText(c.thread_id, "threadId"); } }, svg("copy"))),
            h("td", {}, h("div", { style: "max-width:22rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, c.last_text || ""), h("div", { style: "color:var(--muted);font-size:.75rem" }, fmtRel(c.last_ts))),
            h("td", {}, c.unread > 0 ? h("span", { class: "badge" }, c.unread) : String(c.incoming_count || 0)),
            h("td", {}, h("button", { class: "btn sm", type: "button", onclick: (e) => { e.stopPropagation(); openThread(row); } }, "Mở chat")));
          const out = [tr];
          if (open) out.push(h("tr", {}, h("td", { colspan: "5" }, h("div", { class: "watch-msgs" }, (S.watchMsgs[c.thread_id] || []).slice(-10).map((m) => h("div", { class: "wm" }, h("span", { class: "wt" }, fmtTime(m.time)), h("span", {}, (m.sender_id === c.thread_id ? "" : "Bạn: ") + (m.text || m.file_name || "[" + (m.kind || "tệp") + "]")))), h("div", {}, h("button", { class: "btn sm", type: "button", onclick: () => copyText(JSON.stringify({ thread_id: c.thread_id, name: convName(c), last: c.last_text }), "JSON") }, "Sao chép JSON"))))));
          return out;
        })))));
}

// ---- 96 dịch vụ ------------------------------------------------------------------------------------------------------------
async function renderServices() {
  const box = $("svc-page");
  if (!S.catalog) {
    box.replaceChildren(h("p", { style: "color:var(--muted)" }, "Đang tải danh mục…"));
    const d = await api("/api/svc/catalog"); if (d.error) return box.replaceChildren(h("p", { class: "notice bad" }, "Lỗi: " + d.error));
    const seen = new Set();
    S.catalog = { groups: d.groups || [], items: (d.services || []).filter((s) => s.addon_no != null && !seen.has(s.addon_no) && seen.add(s.addon_no)).sort((a, b) => a.addon_no - b.addon_no) };
  }
  const { groups, items } = S.catalog, q = S.svcQ.trim().toLowerCase();
  const shown = items.filter((s) => (S.svcGroup === "all" || s.group === S.svcGroup) && (!q || s.addon.includes(q) || (s.label || "").toLowerCase().includes(q)));
  $("svc-sub").textContent = items.length + " dịch vụ" + (S.cur ? " · đang chọn: " + (S.cur.name || S.cur.id) : "");
  const keep = document.activeElement && document.activeElement.dataset && document.activeElement.dataset.svcq;
  box.replaceChildren(
    h("div", { class: "search", style: "max-width:48rem;margin-bottom:.625rem" }, svg("search"), h("input", { type: "search", "data-svcq": "1", placeholder: "Tìm dịch vụ…", value: S.svcQ, "aria-label": "Tìm dịch vụ", oninput: (e) => { S.svcQ = e.target.value; renderServices(); } })),
    h("div", { class: "chips", style: "margin-bottom:.75rem;max-width:48rem" }, [{ id: "all", label: "Tất cả" }, ...groups].map((g) => h("button", { class: "chip", type: "button", "aria-pressed": String(S.svcGroup === g.id), onclick: () => { S.svcGroup = g.id; renderServices(); } }, g.label))),
    ...shown.map(svcItem));
  if (keep) { const i = box.querySelector("[data-svcq]"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
}
const STATUS_HINT = { chat: "Dùng ngay trong khung chat (nhắn tin, đính kèm, ghi âm).", view: "Xem ở tab Danh bạ.", zalobot: "Chỉ có ở máy chủ zalobot (webhook, proxy, đa tài khoản): xem mục Cài đặt, hoặc tích hợp Home Assistant mô phỏng." };
function svcItem(s) {
  const open = S.svcOpen === s.addon_no;
  const pill = s.status === "supported" ? h("span", { class: "pill ok" }, "dùng được") : h("span", { class: "pill" }, s.status === "chat" ? "trong chat" : s.status === "view" ? "ở danh bạ" : "zalobot");
  const el = h("div", { class: "svc" }, h("button", { type: "button", "aria-expanded": String(open), onclick: () => { S.svcOpen = open ? null : s.addon_no; renderServices(); } }, h("span", { class: "svc-name" }, s.label && s.label !== s.addon ? s.label : s.addon, h("div", { class: "svc-sub" }, s.addon + (s.danger ? " · không hoàn tác" : ""))), pill));
  if (open) el.append(svcBody(s)); return el;
}
function svcBody(s) {
  const body = h("div", { class: "svc-body" });
  if (s.status !== "supported") { body.append(h("p", { style: "color:var(--muted)" }, STATUS_HINT[s.status] || s.reason || "")); return body; }
  const need = s.thread && s.thread !== "none";
  if (need) body.append(h("p", { class: "notice", style: "margin:.625rem 0" }, S.cur ? "Áp dụng cho: " + (S.cur.name || S.cur.id) + (S.cur.type === "group" ? " (nhóm)" : "") : "Cần chọn hội thoại: mở một cuộc trò chuyện trước rồi quay lại đây."));
  const inputs = {};
  for (const f of s.fields || []) { const input = h("input", { type: "text", id: "svc-" + f.key, autocomplete: "off" }); inputs[f.key] = input; body.append(h("div", { class: "field", style: "margin-top:.625rem" }, h("label", { for: "svc-" + f.key }, f.label + (f.required ? " *" : "")), input)); }
  const out = h("pre", { class: "out", hidden: true });
  const btn = h("button", { class: "btn primary", type: "button", style: "margin-top:.375rem", onclick: async () => {
    if (need && !S.cur) return toast("Hãy mở một cuộc trò chuyện trước.");
    if (s.danger && !confirm("“" + (s.label || s.addon) + "” không hoàn tác được. Tiếp tục?")) return;
    const payload = need ? { thread_id: S.cur.id, type: S.cur.type } : {};
    for (const [k, el] of Object.entries(inputs)) if (el.value.trim() !== "") payload[k] = el.value.trim();
    btn.disabled = true; const r = await api("/api/svc/" + s.action, "POST", payload); btn.disabled = false; out.hidden = false;
    out.textContent = r.error ? "Lỗi: " + r.error : JSON.stringify(r.data === undefined ? r : r.data, null, 2);
  } }, "Chạy");
  body.append(btn, out); return body;
}

// ---- cài đặt: kết nối Zalo (webhook, proxy, bảo mật) ---------------------------------------------------------------------
const section = (id, title, ...kids) => h("div", { class: "card", id }, h("h3", {}, title), ...kids);
async function renderSettings(focusId) {
  const box = $("set-page"); box.replaceChildren();
  let st = S.status; try { st = await api("/api/status"); S.status = st; } catch (e) { /* giữ */ }
  const pill = (t, c) => h("span", { class: "pill " + (c || "") }, t), run = (v) => (v === "running" ? pill("đang chạy", "ok") : pill(v || "?", "warn"));
  const lag = st.sync_lag_ms;
  box.append(section("set-account", "Tài khoản và kết nối",
    h("dl", { class: "kv" },
      h("dt", {}, "Zalo"), h("dd", {}, st.login ? (st.phonenum || "") + " · " + st.uid : "Chưa đăng nhập"),
      h("dt", {}, "Kênh nhận tin"), h("dd", {}, run(st.sync), st.sync_error ? " " + st.sync_error : ""),
      h("dt", {}, "Kênh điều khiển"), h("dd", {}, run(st.ctrl), st.ctrl_error ? " " + st.ctrl_error : ""),
      h("dt", {}, "Đẩy tức thì"), h("dd", {}, h("span", { class: "live" + (S.sse ? "" : " off") }), S.sse ? "đang nối (tin hiện ngay khi tới)" : "đang nối lại…"),
      h("dt", {}, "Độ trễ nhận tin"), h("dd", {}, lag ? lag.last + " ms gần nhất · trung bình " + lag.avg + " ms (" + lag.n + " tin)" : "chưa có tin nào trong phiên này"),
      h("dt", {}, "Tiếng cuộc gọi"), h("dd", {}, st.engine && st.engine.attached ? pill("đã gắn", "ok") : pill("chưa có", "warn"), " ", (st.engine && st.engine.detail) || ""),
      h("dt", {}, "Phiên bản"), h("dd", { class: "mono" }, st.version || ""))));
  let wh = S.webhooks; try { wh = await api("/api/webhooks"); S.webhooks = wh; } catch (e) { /* giữ */ }
  const kinds = [["message", "Tin nhắn"], ["group_event", "Sự kiện nhóm"], ["reaction", "Cảm xúc"], ["call", "Cuộc gọi"]], ins = {}, ens = {};
  box.append(section("set-webhook", "Webhook (Home Assistant, n8n…)",
    h("p", { style: "color:var(--muted);margin:0 0 .75rem;font-size:.85rem" }, "App gửi sự kiện JSON tới các địa chỉ này. Tin nhắn có kèm tên người gửi (sender_name) và cờ người lạ (is_stranger). Tích hợp Home Assistant “Zalo Call” tự điền khi được thêm."),
    ...kinds.map(([k, label]) => {
      ins[k] = h("input", { type: "url", id: "wh-" + k, value: (wh && wh[k + "_webhook_url"]) || "", placeholder: "http://…" });
      ens[k] = h("input", { type: "checkbox", id: "wh-en-" + k, checked: !wh || wh[k + "_enabled"] !== false, "aria-label": "Bật " + label });
      return h("div", { class: "field" }, h("label", { for: "wh-" + k }, label), h("div", { class: "field-row" }, ins[k], ens[k], h("button", { class: "btn sm", type: "button", onclick: async () => { const r = await api("/api/webhooks/test", "POST", { kind: k }); toast(r.error ? "Gửi thử lỗi: " + r.error : r.ok ? "Gửi thử thành công" : "Gửi thử: " + JSON.stringify(r).slice(0, 120), 4500); } }, "Gửi thử")));
    }),
    h("button", { class: "btn primary", type: "button", onclick: async () => { const cfg = {}; for (const [k] of kinds) { cfg[k + "_webhook_url"] = ins[k].value.trim(); cfg[k + "_enabled"] = ens[k].checked; } const r = await api("/api/webhooks", "POST", cfg); toast(r.error ? "Lưu lỗi: " + r.error : "Đã lưu webhook"); } }, "Lưu webhook")));
  // proxy
  const px = await api("/api/proxy"), pUrl = h("input", { type: "text", id: "px-url", placeholder: "http://user:mật-khẩu@địa-chỉ:cổng", autocomplete: "off" }), pName = h("input", { type: "text", id: "px-name", placeholder: "Tên gợi nhớ (không bắt buộc)" });
  const pAct = async (body, okMsg) => { const r = await api("/api/proxy", "POST", body); if (r.error) return toast(r.error, 5000); if (okMsg) toast(okMsg); renderSettings("set-proxy"); };
  box.append(section("set-proxy", "Proxy ra Zalo",
    h("p", { style: "color:var(--muted);margin:0 0 .75rem;font-size:.85rem" }, "Chỉ áp cho kết nối HTTPS tới Zalo (nhắn tin, danh bạ, báo hiệu gọi). Tiếng cuộc gọi (UDP) không đi qua proxy HTTP. Đổi proxy là đổi địa chỉ IP ra ngoài, Zalo có thể yêu cầu xác nhận lại."),
    !px.items || !px.items.length ? h("p", { style: "margin:0 0 .75rem" }, "Chưa có proxy nào. Đang đi thẳng ra Internet.") :
      h("div", {}, px.items.map((p) => h("div", { class: "prow" }, h("div", { class: "pmain" }, h("div", { style: "font-weight:500" }, p.name || p.display, p.id === px.active ? h("span", { class: "pill ok", style: "margin-left:.5rem" }, "đang dùng") : null), h("div", { class: "mono", style: "color:var(--muted)" }, p.display + (p.has_auth ? " · có tài khoản" : ""))),
        h("button", { class: "btn sm", type: "button", onclick: async () => { const r = await api("/api/proxy", "POST", { action: "test", id: p.id }); toast(r.ok ? "Proxy thông: HTTP " + r.status + " · " + r.ms + " ms" : "Proxy lỗi: " + (r.error || "không rõ"), 5000); } }, "Thử"),
        p.id === px.active ? h("button", { class: "btn sm", type: "button", onclick: () => pAct({ action: "deactivate" }, "Đã tắt proxy") }, "Tắt") : h("button", { class: "btn sm", type: "button", onclick: () => pAct({ action: "activate", id: p.id }, "Đã bật proxy") }, "Dùng"),
        h("button", { class: "btn sm danger", type: "button", onclick: () => { if (confirm("Xoá proxy này?")) pAct({ action: "remove", id: p.id }); } }, "Xoá")))),
    h("div", { class: "field", style: "margin-top:.75rem" }, h("label", { for: "px-url" }, "Thêm proxy"), pUrl), h("div", { class: "field" }, pName),
    h("button", { class: "btn primary", type: "button", onclick: () => { if (!pUrl.value.trim()) return toast("Nhập địa chỉ proxy"); pAct({ action: "add", url: pUrl.value.trim(), name: pName.value.trim() }, "Đã thêm proxy"); } }, "Thêm")));
  // bảo mật
  const sec = await api("/api/security");
  box.append(section("set-security", "Bảo mật",
    h("dl", { class: "kv" }, h("dt", {}, "Tài khoản app"), h("dd", {}, sec.app_user || ""), h("dt", {}, "Thiết bị đang đăng nhập"), h("dd", {}, String(sec.sessions)), h("dt", {}, "Hạn phiên"), h("dd", {}, (sec.session_hours || "?") + " giờ"),
      h("dt", {}, "Chặn dò mật khẩu"), h("dd", {}, "sai " + (sec.login_max_fails || 5) + " lần thì khoá địa chỉ 15 phút" + (sec.blocked_ips ? " · đang khoá " + sec.blocked_ips + " địa chỉ" : "")),
      h("dt", {}, "Đổi mật khẩu"), h("dd", {}, "sửa ZALO_PC_APP_PASSWORD (hoặc ZALO_PC_APP_PASSWORD_HASH) trong .env rồi khởi động lại container")),
    h("div", { class: "field-row", style: "margin-top:.75rem;flex-wrap:wrap" },
      h("button", { class: "btn", type: "button", onclick: async () => { const r = await api("/api/security", "POST", { action: "revoke_others" }); toast("Đã đăng xuất " + (r.revoked || 0) + " thiết bị khác"); renderSettings("set-security"); } }, "Đăng xuất thiết bị khác"),
      h("button", { class: "btn", type: "button", onclick: async () => { await api("/api/security", "POST", { action: "revoke_all" }); location.href = "/login"; } }, "Đăng xuất mọi thiết bị"),
      h("button", { class: "btn danger", type: "button", onclick: async () => { if (confirm("Đăng xuất Zalo? Phải quét lại QR để vào lại.")) { await api("/api/logout", "POST"); location.reload(); } } }, "Đăng xuất Zalo (xoá phiên QR)"))));
  // giao diện
  const cur = root.dataset.theme || "auto", sc = scalePref();
  box.append(section("set-ui", "Giao diện",
    h("div", { class: "field" }, h("label", {}, "Chế độ màu"), h("div", { class: "seg", role: "group" }, [["auto", "Theo máy"], ["light", "Sáng"], ["dark", "Tối"]].map(([id, l]) => h("button", { type: "button", "aria-pressed": String(cur === id), onclick: () => { applyTheme(id); renderSettings("set-ui"); } }, l)))),
    h("div", { class: "field" }, h("label", {}, "Cỡ giao diện (nhớ riêng cho thiết bị này)"), h("div", { class: "seg", role: "group" }, [["auto", "Tự động"], ["90", "90%"], ["100", "100%"], ["115", "115%"], ["130", "130%"], ["160", "160%"]].map(([id, l]) => h("button", { type: "button", "aria-pressed": String(sc === id), onclick: () => { setScale(id); renderSettings("set-ui"); } }, l))),
      h("p", { style: "color:var(--muted);margin:.375rem 0 0;font-size:.8rem" }, "Tự động: tính từ độ rộng màn hình và kiểu cảm ứng/chuột (màn lớn và TV tự to hơn, điện thoại gọn hơn). Hiện " + root.style.fontSize + " · " + (root.dataset.bp === "phone" ? "bố cục điện thoại" : root.dataset.bp === "mid" ? "bố cục vừa" : "bố cục rộng"))),
    h("label", { style: "display:flex;gap:.5rem;align-items:center" }, h("input", { type: "checkbox", checked: S.sound, onchange: (e) => { S.sound = e.target.checked; try { localStorage.setItem("zalo-sound", S.sound ? "1" : "0"); } catch (x) { /* bỏ qua */ } } }), "Phát tiếng báo khi có tin mới lúc tab đang ẩn")));
  if (focusId) { const el = $(focusId); if (el) el.scrollIntoView({ block: "start" }); }
}

// ---- tin mới tức thì (SSE) -----------------------------------------------------------------------------------------------------------
let beepCtx = null;
function beep() {
  if (!S.sound) return;
  try { beepCtx = beepCtx || new (window.AudioContext || window.webkitAudioContext)(); const o = beepCtx.createOscillator(), g = beepCtx.createGain(); o.connect(g); g.connect(beepCtx.destination); o.frequency.value = 880; g.gain.value = 0.04; o.start(); o.stop(beepCtx.currentTime + 0.12); } catch (e) { /* không có âm thanh */ }
}
function onMessageEvent(ev) {
  const type = ev.thread_type, id = String(ev.thread_id), msg = ev.msg || {}, key = type + "|" + id;
  const m = normMsg(msg), isOpen = !!S.cur && rowKey(S.cur) === key && !document.hidden;
  if (m._out && S.conv[key] && S.msgs.some((x) => x._id === m._id)) return;   // tin vừa tự gửi đã có
  const c = touchConv(type, id, msg, { open: isOpen, stranger: ev.stranger });
  if (S.cur && rowKey(S.cur) === key) {
    mergeMsgs([msg]); S.stick = true; loadFiles().then(renderMsgs); renderMsgs();
    if (isOpen && !m._out) api("/api/thread/" + encodeURIComponent(id) + "/seen", "POST", { type, msg_ids: [msg.id] }).catch(() => {});
  } else if (!m._out) {
    if (document.hidden) beep();
    if (ev.stranger && type === "user") toast("Người lạ nhắn: " + (c.name || id) + " — " + (msg.text || "[tệp]").slice(0, 60), 6000);
  }
  renderBadges(); if (S.tab === "chats") renderList(); if (S.tab === "watch") renderWatch();
}
function connectSse() {
  if (!window.EventSource) return;
  const es = new EventSource("/api/events");
  es.onopen = () => { S.sse = true; if (S.tab === "chats") renderList(); loadConversations(); };
  es.onerror = () => { S.sse = false; if (S.tab === "chats") renderList(); };
  es.addEventListener("message", (e) => { try { onMessageEvent(JSON.parse(e.data)); } catch (x) { /* bỏ sự kiện hỏng */ } });
}
async function loadConversations() {
  let d; try { d = await api("/api/conversations"); } catch (e) { return; }
  if (d.error) return;
  const next = {}; for (const t of d.threads || []) next[t.thread_type + "|" + t.thread_id] = t;
  for (const [k, c] of Object.entries(S.conv)) if (!next[k] && c.count) next[k] = c;   // giữ dòng vừa tạo cục bộ
  if (S.cur && next[rowKey(S.cur)]) next[rowKey(S.cur)].unread = 0;
  S.conv = next; S.convReady = true; renderBadges(); if (S.tab === "chats") renderList(); if (S.tab === "watch") renderWatch();
}

// ---- đăng nhập QR ----------------------------------------------------------------------------------------------------------------------------
async function pollQr() {
  const s = await api("/api/qr/status"), st = $("qr-status");
  if (s.qr_image) { $("qr-slot").replaceChildren(h("img", { src: s.qr_image, alt: "Mã QR đăng nhập Zalo" })); st.textContent = "Mã có hiệu lực khoảng " + (s.countdown || 90) + " giây."; }
  const stop = (msg) => { clearInterval(S.qrT); S.qrT = null; st.textContent = msg; $("qr-again").hidden = false; };
  if (s.state === "scanned") st.textContent = "Đã quét. Bấm xác nhận trên điện thoại…";
  else if (s.state === "done") { clearInterval(S.qrT); $("qr").hidden = true; boot(); }
  else if (s.state === "expired") stop("Mã đã hết hạn."); else if (s.state === "rejected") stop("Bạn đã từ chối trên điện thoại.");
  else if (s.state === "rate_limited") stop("Tạo mã quá nhanh, chờ " + (s.wait_seconds || 90) + " giây rồi thử lại."); else if (s.state === "error") stop("Lỗi: " + (s.error || "không rõ"));
}
function startQr() { $("qr").hidden = false; $("qr-again").hidden = true; $("qr-slot").replaceChildren(h("div", { class: "qrph" }, "Đang tạo mã…")); api("/api/qr/new", "POST").then(() => { clearInterval(S.qrT); S.qrT = setInterval(pollQr, 3000); pollQr(); }); }

// ---- khởi động ------------------------------------------------------------------------------------------------------------------------------------
let booted = false;
function cogMenu() {
  popup($("btn-cog"), [
    { label: "Thông tin tài khoản", icon: "user", run: () => { setTab("settings"); setTimeout(() => $("set-account") && $("set-account").scrollIntoView(), 80); } },
    { label: "Cài đặt", icon: "cog", run: () => setTab("settings") }, "-",
    { label: "Webhook, proxy, bảo mật", icon: "db", run: () => { setTab("settings"); setTimeout(() => $("set-webhook") && $("set-webhook").scrollIntoView(), 80); } },
    { label: "Ngôn ngữ: Tiếng Việt", icon: "globe", run: () => toast("Hiện chỉ có Tiếng Việt.") },
    { label: "Hỗ trợ", icon: "help", run: () => window.open("https://github.com/TriTue2011/calling/issues", "_blank", "noopener") }, "-",
    { label: "Đăng xuất", icon: "logout", red: true, run: async () => { await api("/api/app/logout", "POST"); location.href = "/login"; } }], { right: true, up: true });
}
async function boot() {
  let st; try { st = await api("/api/status"); } catch (e) { return; }
  S.status = st; S.uid = String(st.uid || "");
  const meRow = { id: S.uid, name: st.phonenum || "Tôi", avatar: "" }; $("me-btn").replaceChildren(avatar(meRow));
  if (!st.login) return startQr();
  $("qr").hidden = true;
  await Promise.all([loadContacts(false), loadCalls(), loadConversations()]);
  const m = /^#\/(user|group)\/(.+)$/.exec(location.hash);
  if (m) { const id = decodeURIComponent(m[2]), r = rowOf(m[1], id) || (S.conv[m[1] + "|" + id] ? convRow(S.conv[m[1] + "|" + id]) : null); if (r) openThread(r); }
  if (booted) return; booted = true;
  connectSse();
  setInterval(() => { if (!document.hidden) loadConversations(); }, 20000);
  setInterval(() => { if (!document.hidden) loadCalls(); }, 3000);
  setInterval(() => { if (S.tab === "chats") renderList(); }, 30000);   // "x phút" tự cũ đi
  setInterval(async () => { try { S.status = await api("/api/status"); S.uid = String(S.status.uid || ""); } catch (e) { /* bỏ qua */ } }, 30000);
}
async function loadContacts(force) {
  let d; try { d = await api("/api/contacts" + (force ? "?force=1" : "")); } catch (e) { return; }
  if (d.error) { S.contactsErr = "Lỗi tải danh bạ: " + d.error + (d.retry_after_seconds ? " (thử lại sau " + d.retry_after_seconds + " giây)" : ""); if (S.tab === "chats" || S.tab === "contacts") renderList(); return; }
  S.contactsErr = ""; S.contactsMeta = d;
  const rows = (x) => (x && x.rows) || [];
  S.friends = rows(d.friends).map((r) => ({ id: String(r.id), name: r.name || "", avatar: r.avatar || "", type: "user" }));
  S.groups = rows(d.groups).map((r) => ({ id: String(r.id), name: r.name || "", avatar: r.avatar || "", type: "group", members: r.members || [] }));
  if (S.cur) { const again = rowOf(S.cur.type, S.cur.id); if (again) S.cur = again; }
  renderList(); if (S.tab === "contacts") renderContactsPage();
  if (d.stale) setTimeout(() => loadContacts(false), 3000);
}

document.querySelectorAll(".rail-btn[data-tab]").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
$("me-btn").addEventListener("click", () => { setTab("settings"); });
$("btn-cog").addEventListener("click", cogMenu); $("btn-cog").dataset.pop = "1";
document.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => { $("app").dataset.pane = "list"; if (WIDE.has(S.tab)) setTab("chats"); else toList(); }));
$("chat-back").addEventListener("click", toList);
$("q").addEventListener("input", (e) => { S.q = e.target.value; if (S.tab === "calls") { renderCallRows($("list")); renderCallsPage(); } else if (S.tab === "contacts") renderContactsPage(); else renderList(); });
$("btn-reload").addEventListener("click", async () => { toast("Đang tải lại…"); await Promise.all([loadContacts(true), loadConversations()]); });
$("btn-call").addEventListener("click", () => startCall(false)); $("btn-video").addEventListener("click", () => startCall(true));
$("btn-info").addEventListener("click", () => { S.info = !S.info; try { localStorage.setItem("zalo-info", S.info ? "1" : "0"); } catch (e) { /* bỏ qua */ } syncInfo(); });
$("btn-thread-svc").addEventListener("click", () => setTab("services"));
$("btn-send").addEventListener("click", sendText); $("btn-like").addEventListener("click", () => sendRaw("👍"));
$("btn-attach").addEventListener("click", () => $("file-in").click()); $("btn-img").addEventListener("click", () => $("img-in").click());
for (const id of ["file-in", "img-in"]) $(id).addEventListener("change", (e) => { const f = [...e.target.files]; e.target.value = ""; if (f.length) sendFiles(f); });
$("btn-rec").addEventListener("click", toggleRecord); $("btn-emoji").addEventListener("click", toggleEmoji); $("qr-again").addEventListener("click", startQr);
$("msg-in").addEventListener("input", autosize);
$("msg-in").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendText(); } });
$("msg-in").addEventListener("paste", (e) => { const f = [...(e.clipboardData ? e.clipboardData.files : [])]; if (f.length) { e.preventDefault(); sendFiles(f); } });
document.addEventListener("click", (e) => { const em = $("emoji"); if (!em.hidden && !em.contains(e.target) && !e.target.closest("#btn-emoji")) em.hidden = true; });
const mp = $("mainpane"); let dragN = 0; const dz = h("div", { class: "dropzone", hidden: true }, "Thả tệp để gửi"); mp.append(dz);
mp.addEventListener("dragenter", (e) => { if (S.cur && S.tab === "chats" && e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { dragN++; dz.hidden = false; } });
mp.addEventListener("dragleave", () => { dragN = Math.max(0, dragN - 1); if (!dragN) dz.hidden = true; });
mp.addEventListener("dragover", (e) => { if (S.cur) e.preventDefault(); });
mp.addEventListener("drop", (e) => { e.preventDefault(); dragN = 0; dz.hidden = true; if (S.cur && e.dataTransfer.files.length) sendFiles(e.dataTransfer.files); });
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $("q").focus(); }
  if (e.key === "Escape" && document.activeElement === $("q")) { $("q").value = ""; S.q = ""; renderList(); $("q").blur(); }
});
try { applyTheme(localStorage.getItem("zalo-theme") || "auto"); S.sound = localStorage.getItem("zalo-sound") !== "0"; S.info = localStorage.getItem("zalo-info") !== "0"; } catch (e) { /* mặc định */ }
applyScale(); setTab("chats"); updateSendButtons(); boot();
})();
