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
  sticker: '<path d="M20 12.5V7a3 3 0 0 0-3-3H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h5.5a8 8 0 0 0 7.5-7.5z"/><path d="M20 12.5h-3.5A2.5 2.5 0 0 0 14 15v3.5"/><path d="M8.5 9.5v.5M13.5 9.5v.5M8.5 13c.8 1 1.8 1.4 3 1.4"/>',
  smile: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14c.8 1.4 2 2.2 3.5 2.2s2.7-.8 3.5-2.2M9 9.5v.5M15 9.5v.5"/>',
  thumb: '<path d="M7 11v9H4v-9zM7 11l4-7c1.5 0 2.5 1 2.2 2.6L12.7 9H19a2 2 0 0 1 2 2.4l-1.2 6A2.5 2.5 0 0 1 17.4 19H7"/>',
  send: '<path d="M21 3 10 14M21 3l-7 18-4-7-7-4z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  hang: '<path d="M3 14c4.5-4 13.5-4 18 0l-1.5 3-4-1.2v-2.3a10 10 0 0 0-7 0v2.3L4.5 17z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  panel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M15 4.5v15"/>',
  more: '<circle cx="5.5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18.5" cy="12" r="1.3"/>',
  share: '<path d="M14 5l6 6-6 6M20 11H9a5 5 0 0 0-5 5v2"/>',
  check: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12.5l2.7 2.7L16 9.5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2.2"/><path d="M15.5 8.5V6.7A2.2 2.2 0 0 0 13.3 4.5H6.7A2.2 2.2 0 0 0 4.5 6.7v6.6a2.2 2.2 0 0 0 2.2 2.2h1.8"/>',
  db: '<ellipse cx="12" cy="6" rx="7.5" ry="3"/><path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 3.5 5.4 3.5 8.5s-1 6-3.5 8.5c-2.5-2.5-3.5-5.4-3.5-8.5s1-6 3.5-8.5z"/>',
  help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 16.5v.1"/>',
  logout: '<path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l4 4-4 4M19 12H9"/>',
  mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3"/>',
  speaker: '<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5zM15.5 9a4 4 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
  cam: '<rect x="3.5" y="6.5" width="12" height="11" rx="2.2"/><path d="m15.5 11 5-3v8l-5-3z"/>',
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
  if (r.status === 423) { showPrivacyLock(); throw new Error("privacy_locked"); }
  try { return await r.json(); } catch (e) { return { error: "HTTP " + r.status }; }
}
// ---- mã PIN riêng tư (chỉ hiện khi máy chủ bật ZALO_PC_APP_PIN / _HASH) ------------------------------------------------------------
function showPrivacyLock() {
  if (document.getElementById("privacy-lock")) return;
  const msg = h("div", { style: "min-height:1.2em;margin:.6rem 0;color:#f87171" });
  const pin = h("input", { type: "password", inputmode: "numeric", autocomplete: "off", placeholder: "Nhập mã PIN",
    style: "width:100%;padding:.7rem;border-radius:.5rem;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:1.1rem;text-align:center" });
  const go = async () => {
    msg.textContent = "";
    const r = await fetch("/api/privacy/unlock", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin: pin.value }) });
    if (r.status === 401 && (await r.clone().json().catch(() => ({}))).error === "chua_dang_nhap_app") { location.href = "/login"; return; }
    if (r.ok) { location.reload(); return; }
    const e = (await r.json().catch(() => ({}))).error;
    msg.textContent = e === "qua_nhieu_lan_sai" ? "Nhập sai quá nhiều lần, thử lại sau 15 phút." : "Sai mã PIN.";
    pin.value = ""; pin.focus();
  };
  pin.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });
  const box = h("div", { style: "background:#1e293b;color:#e2e8f0;padding:2rem;border-radius:1rem;width:min(22rem,90vw);text-align:center;box-shadow:0 10px 40px #0008" },
    h("div", { style: "font-size:2rem" }, "🔒"), h("h2", { style: "margin:.5rem 0" }, "Màn hình riêng tư"),
    h("p", { style: "opacity:.75;margin:0 0 1rem" }, "Nhập mã PIN để xem tin nhắn."), pin, msg,
    h("button", { class: "btn primary", type: "button", style: "width:100%", onclick: go }, "Mở khoá"));
  document.body.append(h("div", { id: "privacy-lock", style: "position:fixed;inset:0;z-index:99999;background:#020617f2;display:flex;align-items:center;justify-content:center" }, box));
  pin.focus();
}
async function privacyInit() {
  try { const r = await fetch("/api/privacy/status"); if (r.ok) { const st = await r.json(); S.privacy = st; if (st.enabled && !st.unlocked) showPrivacyLock(); } } catch (e) { /* khong co mang: bo qua */ }
}
async function apiForm(path, form, ms) {
  const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), ms || 90000);
  try { const r = await fetch(path, { method: "POST", body: form, signal: ctrl.signal }); if (r.status === 423) { showPrivacyLock(); throw new Error("privacy_locked"); } try { return await r.json(); } catch (e) { return { error: "HTTP " + r.status }; } }
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
  catalog: null, svcGroup: "all", svcQ: "", svcOpen: null, setSec: "account", pending: [], replyTo: null, mentions: [], recalled: new Set(), deleted: new Set(), reacts: {}, sel: null, ringId: "",
  watchOpen: null, watchMsgs: {}, rec: null, qrT: null, sound: true, me: { avatar: "" },
};
const rowKey = (r) => (r.type || r.thread_type) + "|" + (r.id || r.thread_id);
const allRows = () => [...S.friends, ...S.groups];
const rowOf = (type, id) => allRows().find((r) => r.type === type && r.id === String(id));
const unreadTotal = () => Object.values(S.conv).reduce((n, c) => n + (c.unread || 0), 0);
const peerName = (c) => c.peer || (rowOf(c.type === "group" ? "group" : "user", c.thread_id) || {}).name || String(c.thread_id || "");
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
  $("btn-call").hidden = row.type === "group"; $("btn-video").hidden = false;     // nhóm chỉ có gọi VIDEO nhóm (không có gọi thoại nhóm)
  setNotice(""); $("msg-in").value = ""; autosize(); setReply(null); S.mentions = []; S.pending = []; renderTray(); updateSendButtons();
  history.replaceState(null, "", "#/" + row.type + "/" + encodeURIComponent(row.id));
  const c = S.conv[rowKey(row)]; if (c) c.unread = 0;
  renderBadges(); renderList(); renderMsgs(); syncInfo(); syncCallButtons();
  loadHistory(); startPoll();
}
// Ảnh nhiều tấm gửi một lúc (album): Zalo ghi vị trí trong raw.content.params (group_layout_id, id_in_group, total_item_in_group).
function albumOf(m) {
  const c = m.raw && m.raw.content; let p = c && c.params;
  if (typeof p === "string") { try { p = JSON.parse(p); } catch (e) { p = null; } }
  if (!p || !p.group_layout_id || !(Number(p.total_item_in_group) > 1)) return null;
  return { gid: String(p.group_layout_id), idx: Number(p.id_in_group) || 0, total: Number(p.total_item_in_group) };
}
function normMsg(m) {
  const out = m.direction === "out" || m.sender_id === "me" || (S.uid && String(m.sender_id) === S.uid);
  const n = Object.assign({}, m, { _id: String(m.id || m.client_id || ""), _out: out, _t: Number(m.time || m.ts || 0) });
  n._album = n.kind === "photo" ? albumOf(n) : null;
  return n;
}
function mergeMsgs(list) {
  const seen = new Map(S.msgs.map((m, i) => [m._id || "x" + i, m]));
  let n = 0;
  for (const raw of list) { const m = normMsg(raw); seen.set(m._id || "n" + (n++) + Math.random(), m); }
  const echoed = new Set();
  for (const m of seen.values()) { const c = m.raw && m.raw.cliMsgId; if (c) echoed.add(String(c)); }
  for (const [k, m] of seen) { if (m.sender_id === "me" && m.client_id && echoed.has(String(m.client_id))) seen.delete(k); }     // tin giữ chỗ đã có bản thật: bỏ, khỏi hiện trùng / thẻ tệp trống
  S.msgs = [...seen.values()].sort((a, b) => a._t - b._t);
  S.lastTime = S.msgs.reduce((x, m) => Math.max(x, m._t), 0);
}
async function loadHistory() {
  const cur = S.cur; if (!cur) return;
  const d = await api("/api/thread/" + encodeURIComponent(cur.id) + "/history?type=" + typeParam() + "&count=50");
  if (S.cur !== cur) return;
  if (d.error) return setNotice("Lỗi tải lịch sử: " + d.error, true);
  setNotice(d.notice || "");
  await loadFiles(); await loadReactions(); mergeMsgs(d.messages || []); renderMsgs();
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
const VIDEO_EXT = /\.(mp4|mov|m4v|webm|mkv|3gp)$/i, IMAGE_EXT = /\.(jpe?g|png|webp|gif)$/i;
const isVideoMsg = (m) => m.kind === "video" || (m.kind === "file" && VIDEO_EXT.test(m.file_name || ""));
const isImageMsg = (m) => m.kind === "photo" || (m.kind === "file" && IMAGE_EXT.test(m.file_name || ""));
// Một bong bóng lưới cho cả album (như Zalo PC): 2 ảnh = 2 cột; 3 ảnh = 2 ảnh trên + 1 ảnh to dưới; 4 = lưới 2x2; 5–9 = 3 cột; từ 10 = 4 cột.
function albumBody(m) {
  const mates = S.msgs.filter((x) => x._album && x._album.gid === m._album.gid && x.sender_id === m.sender_id && !S.deleted.has(x._id)).sort((a, b) => a._album.idx - b._album.idx);
  const n = Math.max(mates.length, 1), cls = n >= 10 ? "n10" : n >= 5 ? "n5" : "n" + n;
  const tiles = mates.map((x) => {
    const full = photoSrc(x) || x.file_url || "", thumb = photoSrc(x) || (x.raw && x.raw.content && x.raw.content.thumb) || x.thumb_url || x.file_url || "";
    const img = h("img", { class: "photo", src: thumb, alt: x.file_name || "Ảnh", loading: "lazy" });
    if (thumb !== full && full) img.addEventListener("error", () => { if (img.src !== full) img.src = full; }, { once: true });
    return h("a", { href: full || thumb, target: "_blank", rel: "noopener noreferrer" }, img);
  });
  const cap = m.text && m.text !== m.file_name ? m.text : "";
  return h("div", {}, h("div", { class: "album " + cls }, tiles), cap ? h("div", { class: "photo-cap" }, cap) : null);
}
function bubbleBody(m) {
  const rec = S.files[m._id], dl = rec && rec.status === "downloaded";
  if (isImageMsg(m) && !photoSrc(m) && m.thumb_url) { const cap = m.text && m.text !== m.file_name ? m.text : ""; const img = h("img", { class: "photo", src: m.thumb_url, alt: m.file_name || "Ảnh", loading: "lazy" }); const a = h("a", { href: m.file_url, target: "_blank", rel: "noopener" }, img); return cap ? h("div", {}, a, h("div", { class: "photo-cap" }, cap)) : a; }
  if (isImageMsg(m) && !photoSrc(m) && m.file_url && m.kind === "photo") {   // ảnh đến chưa có bản tải về: hiện thẳng từ địa chỉ Zalo (lỗi tải ảnh thì quay về thẻ tệp)
    const cap = m.text && m.text !== m.file_name ? m.text : "";
    const img = h("img", { class: "photo", src: m.file_url, alt: m.file_name || "Ảnh", loading: "lazy" });
    const a = h("a", { href: m.file_url, target: "_blank", rel: "noopener" }, img), wrap = h("div", {}, a, cap ? h("div", { class: "photo-cap" }, cap) : null);
    img.addEventListener("error", () => { wrap.replaceChildren(h("div", { class: "filecard" }, h("span", { class: "ficon" }, svg("file")), h("div", {}, h("div", { class: "fname" }, m.file_name || "Ảnh"), h("a", { class: "link", href: m.file_url, target: "_blank", rel: "noopener" }, "Mở")))); });
    return wrap;
  }
  if (isImageMsg(m)) { const src = photoSrc(m); if (src) { const cap = m.text && m.text !== m.file_name ? m.text : ""; const img = h("img", { class: "photo", src, alt: m.file_name || "Ảnh" }); const el = h("a", { href: src, target: "_blank", rel: "noopener" }, img); return cap ? h("div", {}, el, h("div", { class: "photo-cap" }, cap)) : el; } }
  if (m.kind === "voice") return h("div", { class: "filecard" }, h("span", { class: "ficon" }, svg("mic")), h("div", {}, h("div", { class: "fname" }, "Tin nhắn thoại"), m.file_url ? h("audio", { controls: true, preload: "none", src: m.file_url, style: "height:2rem;margin-top:.25rem;max-width:100%" }) : h("div", { class: "fmeta" }, m.file_name || "")));
  if (isVideoMsg(m)) {   // video: phát ngay trong bong bóng (bản đã tải về, hoặc địa chỉ Zalo nếu chưa tải), kèm tên/cỡ/nút tải như Zalo PC
    const src = dl ? downloadUrl(m) : (m.file_url || "");
    const card = h("div", { class: "filecard" }, h("span", { class: "ficon" }, svg("file")), h("div", {}, h("div", { class: "fname" }, (rec && rec.file_name) || m.file_name || m.text || "Video"), h("div", { class: "fmeta" }, fmtSize(m.file_size || (rec && rec.size_bytes))),
      dl ? h("a", { class: "link", href: downloadUrl(m), download: (rec && rec.file_name) || m.file_name || "video.mp4" }, "Tải xuống") : (rec && rec.status === "failed" ? h("button", { class: "link", type: "button", onclick: () => redownload(m) }, "Tải lại") : (m.file_url ? h("a", { class: "link", href: m.file_url, target: "_blank", rel: "noopener" }, "Mở") : null))));
    const vcap = m.kind === "video" && m.text && m.text !== m.file_name && m.text !== "video" ? h("div", { class: "photo-cap" }, m.text) : null;
    // Có hình để phát: CHỈ trình phát (+ chú thích); Tải/Mở/Tải lại nằm trong menu ba chấm. Không có gì để phát: giữ thẻ để còn bấm Mở/Tải lại.
    return src ? h("div", { class: "vidwrap" }, h("video", { class: "vid", controls: true, preload: "metadata", playsinline: true, src }), vcap) : h("div", { class: "vidwrap" }, vcap, card);
  }
  if (m.kind === "file" || m.kind === "photo") {
    let act = null;
    if (dl) act = h("a", { class: "link", href: downloadUrl(m), download: (rec && rec.file_name) || m.file_name || "tep" }, "Tải xuống");
    else if (!m._out) {
      if (rec && rec.status === "failed") act = h("button", { class: "link", type: "button", onclick: () => redownload(m) }, "Tải lại");
      else if (m.file_url) act = h("a", { class: "link", href: m.file_url, target: "_blank", rel: "noopener" }, "Mở");
    }
    return h("div", { class: "filecard" }, h("span", { class: "ficon" }, svg("file")), h("div", {}, h("div", { class: "fname" }, (rec && rec.file_name) || m.file_name || m.text || "Tệp đính kèm"), h("div", { class: "fmeta" }, fmtSize(m.file_size || (rec && rec.size_bytes))), act));
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
  const albumDone = new Set();
  if (!S.msgs.length) frag.append(h("div", { class: "empty", style: "margin:auto" }, "Chưa có tin nhắn. Hãy gửi lời chào."));
  for (const m0 of S.msgs) {
    if (S.deleted.has(m0._id)) continue;            // tin da bi xoa (chat.delete): khong ve
    let m = m0;
    if (S.recalled.has(m._id)) m = Object.assign({}, m, { kind: "system", text: "Tin nhắn đã được thu hồi", reply_to: null, call_record: null, raw: null });
    if (m._album) { const key = m.sender_id + "|" + m._album.gid; if (albumDone.has(key)) continue; albumDone.add(key); }     // album: các ảnh còn lại đã nằm trong lưới
    const d = m._t ? new Date(m._t * 1000).toDateString() : "";
    if (d && d !== day) { day = d; frag.append(h("div", { class: "day" }, fmtDay(m._t))); prev = null; }
    if (m.kind === "system" && m.text) {           // tin he thong / ban ghi cuoc goi: dai giua nhu Zalo PC, khong phai bong bong
      const cr = m.call_record;
      frag.append(h("div", { class: "sysmsg" + (cr && cr.missed ? " missed" : "") },
        cr ? h("span", { class: "sysico" }, svg("phone")) : null,
        h("span", {}, m.text), h("span", { class: "bt" }, fmtTime(m._t))));
      prev = null;
      continue;
    }
    const first = !(prev && prev._out === m._out && prev.sender_id === m.sender_id && m._t - prev._t < 120);
    const sender = { id: String(m.sender_id), name: m.sender_name || (S.cur.type === "user" && !m._out ? S.cur.name : ""), avatar: S.cur.type === "user" && !m._out ? S.cur.avatar : "" };
    frag.append(h("div", { class: "msg " + (m._out ? "out" : "in") + (S.sel ? " selmode" + (S.sel.has(m._id) ? " picked" : "") : "") },
      m._out ? null : (first ? avatar(sender, "sm") : h("span", { class: "gap" })),
      h("div", { class: "mcol" },
        !m._out && S.cur.type === "group" && first && (m.sender_name || m.sender_id) ? h("div", { class: "who" }, m.sender_name || m.sender_id) : null,
        h("div", { class: "bub", oncontextmenu: (e) => { e.preventDefault(); openMsgMenu(m, e.clientX, e.clientY); }, onclick: (e) => { if (S.sel) { toggleSel(m); return; } if (window.matchMedia("(hover: none)").matches && !e.target.closest("a,button,audio")) e.currentTarget.closest(".msg").classList.toggle("acts"); } }, quoteBlock(m), m._album && m.kind === "photo" ? albumBody(m) : bubbleBody(m), h("span", { class: "bt" }, fmtTime(m._t))),
        reactChips(m),
        S.sel ? null : msgActions(m)),
      S.sel ? h("span", { class: "selbox" + (S.sel.has(m._id) ? " on" : ""), "aria-hidden": "true" }, S.sel.has(m._id) ? "✓" : "") : null));
    prev = m;
  }
  box.replaceChildren(frag);
  if (near || S.stick) { box.scrollTop = box.scrollHeight; S.stick = false; }
  if (S.info) syncInfo();
}
function setNotice(text, bad) { const n = $("chat-notice"); n.hidden = !text; n.textContent = text || ""; n.className = "notice" + (bad ? " bad" : ""); }
function autosize() { const t = $("msg-in"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; updateSendButtons(); }
function updateSendButtons() { const has = $("msg-in").value.trim() !== "" || S.pending.length > 0; $("btn-send").hidden = !has; $("btn-like").hidden = has; }
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
async function sendRaw(text, extra) {
  if (!text || !S.cur) return;
  const r = await api("/api/thread/" + encodeURIComponent(S.cur.id) + "/send", "POST", Object.assign({ type: typeParam(), message: text }, extra || {}));
  if (r.error) { setNotice("Lỗi gửi tin: " + r.error, true); return false; }
  setNotice("");
  if (r.message) { mergeMsgs([r.message]); touchConv(S.cur.type, S.cur.id, r.message, { open: true }); S.stick = true; renderMsgs(); renderList(); }
  return true;
}
async function sendText() {
  const input = $("msg-in"), text = input.value.trim();
  if (S.pending.length) { const list = S.pending; S.pending = []; renderTray(); input.value = ""; autosize(); await sendFiles(list, text); return; }
  if (!text) return;
  const reply = S.replyTo, keep = S.mentions;
  const ments = S.cur && S.cur.type === "group" ? keep.filter((x) => text.includes("@" + x.name)).map((x) => ({ uid: x.uid, name: x.name })) : [];
  input.value = ""; autosize(); S.mentions = []; $("mentions").hidden = true;
  const ok = reply ? await sendReply(text, reply) : await sendRaw(text, ments.length ? { mentions: ments } : null);
  if (!ok) { input.value = text; S.mentions = keep; autosize(); }
}
// ---- thao tác trên tin: trả lời, cảm xúc, thu hồi, sao chép (dùng dịch vụ có sẵn của app) ----
const msgRaw = (m) => (m && m.raw && typeof m.raw === "object") ? m.raw : {};
const QUICK_REACTIONS = [["like", "👍 Thích"], ["heart", "❤️ Yêu thích"], ["haha", "😆 Haha"], ["wow", "😮 Wow"], ["cry", "😢 Buồn"], ["angry", "😡 Phẫn nộ"]];
const canReply = (m) => !!(m && m.id && m.kind !== "system" && msgRaw(m).cliMsgId && (msgRaw(m).uidFrom || m.sender_id));
const msgPreview = (m) => (m.kind || "text") === "text" ? String(m.text || "") : isVideoMsg(m) ? "[Video]" + (m.file_name ? " " + m.file_name : "") : isImageMsg(m) ? "[Ảnh]" + (m.file_name ? " " + m.file_name : "") : m.kind === "voice" ? "[Tin nhắn thoại]" : "[Tệp]" + (m.file_name ? " " + m.file_name : "");
const canReact = (m) => !!(m && m.kind !== "system" && msgRaw(m).msgId && msgRaw(m).cliMsgId);
const canUndo = (m) => !!(m && m._out && m.kind !== "system" && msgRaw(m).msgId && msgRaw(m).cliMsgId);
const threadBody = () => ({ thread_id: String(S.cur.id), type: typeParam() });
function setReply(m) {
  S.replyTo = m || null; const bar = $("reply-bar"); if (!bar) return;
  if (!m) { bar.hidden = true; bar.replaceChildren(); return; }
  const who = m._out ? "chính mình" : (m.sender_name || (S.cur && S.cur.type === "user" ? S.cur.name : "") || "");
  put(bar, h("div", { class: "rb-main" }, h("div", { class: "rb-t" }, "Trả lời" + (who ? " " + who : "")), h("div", { class: "rb-x" }, msgPreview(m).slice(0, 120))),
    h("button", { class: "icon-btn", type: "button", "aria-label": "Bỏ trả lời", onclick: () => setReply(null) }, "✕"));
  bar.hidden = false; $("msg-in").focus();
}
async function sendReply(text, m) {
  const raw = msgRaw(m);
  const r = await api("/api/svc/quote_message", "POST", Object.assign(threadBody(), { text, msg_id: String(m.id), qmsg_owner: String(raw.uidFrom || m.sender_id), qmsg_cli_id: String(raw.cliMsgId), qmsg_type: 1, qmsg_ts: Number(raw.ts || 0) || 0, qmsg: msgPreview(m) }));
  if (r.error) { setNotice("Lỗi trả lời: " + r.error, true); return false; }
  setReply(null); setNotice(""); await loadHistory(); return true;
}
async function reactTo(m, icon) {
  const raw = msgRaw(m), r = await api("/api/svc/add_reaction", "POST", Object.assign(threadBody(), { icon, msg_id: String(raw.msgId), cli_msg_id: String(raw.cliMsgId) }));
  toast(r.error ? "Lỗi thả cảm xúc: " + r.error : "Đã thả cảm xúc", r.error ? 5000 : 2000);
}
async function undoMsg(m) {
  if (!confirm("Thu hồi tin này? Người nhận sẽ thấy tin đã bị thu hồi.")) return;
  const raw = msgRaw(m), r = await api("/api/svc/undo_message", "POST", Object.assign(threadBody(), { msg_id: String(raw.msgId), cli_msg_id: String(raw.cliMsgId) }));
  if (r.error) return toast("Lỗi thu hồi: " + r.error, 5000);
  S.recalled.add(m._id); renderMsgs(); toast("Đã thu hồi tin nhắn");
}
// ---- cảm xúc hiện dưới tin, menu chuột phải / «⋯», chuyển tiếp, lưu về máy, chọn nhiều, xóa phía tôi (như Zalo PC) ----
const REACT_EMOJI = { "/-heart": "❤️", "/-strong": "👍", ":>": "😆", ":o": "😮", ":-((": "😢", ":-h": "😡", ":-*": "😘", ":')": "😂", "/-weak": "👎", "/-rose": "🌹", "/-break": "💔", "/-shit": "💩", ";xx": "😍", ";-/": "😕", ";-)": "😉" };
const reactKey = (m) => String(msgRaw(m).msgId || m.id || "");
function reactChips(m) {
  const r = S.reacts[reactKey(m)]; if (!r) return null;
  const by = {}; for (const [uid, ic] of Object.entries(r)) { (by[ic] = by[ic] || []).push(uid); }
  const chips = Object.entries(by).map(([ic, uids]) => h("span", { class: "rchip" + (uids.includes(S.uid) ? " mine" : ""), title: uids.length + " người" }, (REACT_EMOJI[ic] || ic), uids.length > 1 ? h("b", {}, String(uids.length)) : null));
  return chips.length ? h("div", { class: "rchips" }, chips) : null;
}
async function loadReactions() {
  if (!S.cur) return; const cur = S.cur;
  try {
    const d = await api("/api/reaction/list?thread_type=" + typeParam() + "&thread_id=" + encodeURIComponent(cur.id));
    if (S.cur !== cur || d.error) return;
    const now = JSON.stringify(d.reactions || {});
    if (now !== S._reactsJson) { S._reactsJson = now; S.reacts = d.reactions || {}; renderMsgs(); }
  } catch (e) { /* lần sau */ }
}
setInterval(() => { if (S.cur && !document.hidden) loadReactions(); }, 4000);
const mediaSrc = (m) => { const rec = S.files[m._id]; return rec && rec.status === "downloaded" ? downloadUrl(m) : (m.localUrl || ""); };
function saveToDevice(m) {
  const src = mediaSrc(m) || (!m._out && m.file_url) || "";
  if (!src) return toast("Tệp chưa có trên máy chủ để lưu.", 3000);
  const a = h("a", { href: src, download: (S.files[m._id] && S.files[m._id].file_name) || m.file_name || "tep", target: "_blank", rel: "noopener" }); document.body.append(a); a.click(); a.remove();
}
async function deleteMine(list) {
  const items = list.filter((m) => msgRaw(m).msgId && msgRaw(m).cliMsgId);
  if (!items.length) return toast("Tin này chưa có mã để xóa phía mình.", 3500);
  if (!confirm("Xóa " + items.length + " tin chỉ ở phía bạn? Người kia vẫn còn thấy.")) return;
  let ok = 0, err = "";
  for (const m of items) {
    const raw = msgRaw(m), r = await api("/api/svc/delete_message", "POST", Object.assign(threadBody(), { msg_id: String(raw.msgId), cli_msg_id: String(raw.cliMsgId), owner_id: String(raw.uidFrom || m.sender_id || ""), only_me: true }));
    if (r.error) err = r.error; else { ok++; S.deleted.add(m._id); }
  }
  renderMsgs(); toast(ok ? "Đã xóa " + ok + " tin ở phía bạn" + (err ? " (một số lỗi: " + err + ")" : "") : "Lỗi xóa: " + err, ok ? 2500 : 5000);
}
function msgMenuItems(m) {
  const it = [];
  if (canReply(m)) it.push({ label: "Trả lời", icon: "chat", run: () => setReply(m) });
  it.push({ label: "Chuyển tiếp", icon: "share", run: () => openForward([m]) });
  if ((m.kind || "text") !== "text" && (mediaSrc(m) || (!m._out && m.file_url))) {
    it.push({ label: "Lưu về máy", icon: "file", run: () => saveToDevice(m) });
    it.push({ label: "Mở trong tab mới", icon: "file", run: () => window.open(mediaSrc(m) || m.file_url, "_blank", "noopener,noreferrer") });
  }
  const frec = S.files[m._id];
  if ((m.kind || "text") !== "text" && frec && frec.status === "failed") it.push({ label: "Tải lại", icon: "file", run: () => redownload(m) });
  if ((m.kind || "text") === "text" && m.text) it.push({ label: "Sao chép", icon: "copy", run: () => copyText(m.text, "tin nhắn") });
  it.push({ label: "Chọn nhiều tin", icon: "check", run: () => enterSelect(m) });
  it.push("-");
  if (msgRaw(m).msgId && msgRaw(m).cliMsgId) it.push({ label: "Xóa chỉ ở phía tôi", icon: "trash", red: true, run: () => deleteMine([m]) });
  if (canUndo(m)) it.push({ label: "Thu hồi", icon: "trash", red: true, run: () => undoMsg(m) });
  return it;
}
function openMsgMenu(m, x, y) {
  closePop();
  const bar = canReact(m) ? h("div", { class: "rbar" }, QUICK_REACTIONS.map(([icon, label]) => h("button", { type: "button", title: label, "aria-label": label, onclick: () => { closePop(); reactTo(m, icon); } }, label.split(" ")[0]))) : null;
  const el = h("div", { class: "pop msgmenu", role: "menu" }, bar, msgMenuItems(m).map((it) => it === "-" ? h("hr") :
    h("button", { type: "button", role: "menuitem", class: it.red ? "red" : "", onclick: () => { closePop(); it.run(); } }, it.icon ? svg(it.icon) : null, it.label)));
  document.body.append(el); popEl = el;
  const w = el.offsetWidth, hgt = el.offsetHeight;
  el.style.left = Math.max(8, Math.min(x, window.innerWidth - w - 8)) + "px"; el.style.top = Math.max(8, Math.min(y, window.innerHeight - hgt - 8)) + "px";
  const first = el.querySelector("button"); if (first) first.focus();
}
function enterSelect(m) { S.sel = new Set(m ? [m._id] : []); renderSelBar(); renderMsgs(); }
function exitSelect() { S.sel = null; renderSelBar(); renderMsgs(); }
function toggleSel(m) { if (!S.sel) return; if (S.sel.has(m._id)) S.sel.delete(m._id); else S.sel.add(m._id); renderSelBar(); renderMsgs(); }
const selectedMsgs = () => S.msgs.filter((m) => S.sel && S.sel.has(m._id));
function renderSelBar() {
  const bar = $("selbar"); if (!bar) return;
  if (!S.sel) { bar.hidden = true; bar.replaceChildren(); return; }
  const n = S.sel.size;
  put(bar, h("span", { class: "sel-n" }, "Đã chọn " + n + " tin"),
    h("button", { class: "link", type: "button", disabled: !n, onclick: () => openForward(selectedMsgs()) }, "Chuyển tiếp"),
    h("button", { class: "link red", type: "button", disabled: !n, onclick: async () => { await deleteMine(selectedMsgs()); exitSelect(); } }, "Xóa phía tôi"),
    h("button", { class: "link", type: "button", onclick: exitSelect }, "Hủy"));
  bar.hidden = false;
}
function openForward(list) {
  if (!list.length) return;
  const old = document.getElementById("fwd-dlg"); if (old) old.remove();
  const rows = Object.values(S.conv).filter((c) => c.thread_id && !(S.cur && c.thread_type === S.cur.type && String(c.thread_id) === String(S.cur.id))).sort((a, b) => (b.last_ts || 0) - (a.last_ts || 0));
  const box = h("div", { class: "fwd-list" });
  const q = h("input", { type: "search", placeholder: "Tìm hội thoại…", "aria-label": "Tìm hội thoại để chuyển tiếp" });
  const draw = () => { const k = plain(q.value); put(box, rows.filter((c) => !k || plain(c.name || c.thread_id).includes(k)).slice(0, 60).map((c) =>
    h("button", { type: "button", class: "fwd-row", onclick: () => doForward(list, c, dlg) }, avatar({ id: c.thread_id, name: c.name, avatar: c.avatar }, "sm"), h("span", {}, c.name || c.thread_id)))); };
  q.addEventListener("input", draw);
  const dlg = h("div", { class: "fwd-dlg", id: "fwd-dlg", role: "dialog", "aria-label": "Chuyển tiếp tin nhắn" },
    h("div", { class: "fwd-box" }, h("div", { class: "fwd-t" }, "Chuyển tiếp " + list.length + " tin"), q, box, h("button", { class: "link", type: "button", onclick: () => dlg.remove() }, "Đóng")));
  document.body.append(dlg); draw(); q.focus();
}
async function doForward(list, conv, dlg) {
  let ok = 0, err = "";
  for (const m of list) {
    let r;
    if ((m.kind || "text") === "text") r = await api("/api/thread/" + encodeURIComponent(conv.thread_id) + "/send", "POST", { type: conv.thread_type, message: m.text || "" });
    else if (S.files[m._id] && S.files[m._id].status === "downloaded") r = await api("/api/file/forward", "POST", { thread_type: typeParam(), thread_id: String(S.cur.id), msg_id: m._id, to_thread_type: conv.thread_type, to_thread_id: String(conv.thread_id) });
    else r = { error: "tệp chưa tải về máy chủ" };
    if (r && r.error) err = r.error; else ok++;
  }
  dlg.remove(); if (S.sel) exitSelect();
  toast(ok ? "Đã chuyển tiếp " + ok + " tin tới " + (conv.name || conv.thread_id) + (err ? " (một số lỗi: " + err + ")" : "") : "Lỗi chuyển tiếp: " + err, ok ? 2500 : 5000);
}
function msgActions(m) {
  const b = [];
  if (canReact(m)) b.push(h("button", { class: "mact", type: "button", "data-pop": "1", onclick: (e) => popup(e.currentTarget, QUICK_REACTIONS.map(([icon, label]) => ({ label, run: () => reactTo(m, icon) }))) }, "Cảm xúc"));
  if (canReply(m)) b.push(h("button", { class: "mact", type: "button", onclick: () => setReply(m) }, "Trả lời"));
  if ((m.kind || "text") === "text" && m.text) b.push(h("button", { class: "mact", type: "button", onclick: () => copyText(m.text, "tin nhắn") }, "Sao chép"));
  if (canUndo(m)) b.push(h("button", { class: "mact red", type: "button", onclick: () => undoMsg(m) }, "Thu hồi"));
  b.push(h("button", { class: "mact more", type: "button", "aria-label": "Thêm", title: "Thêm", "data-pop": "1", onclick: (e) => { const r = e.currentTarget.getBoundingClientRect(); openMsgMenu(m, r.left, r.bottom + 4); } }, "⋯"));
  return h("div", { class: "macts" }, b);
}
const REPLY_KIND = { photo: "Ảnh", file: "Tệp", voice: "Tin nhắn thoại", video: "Video" };
function quoteBlock(m) {
  const q = m.reply_to; if (!q) return null;
  const member = groupMembers().find((x) => x.id === String(q.owner)), friend = rowOf("user", q.owner);
  const who = q.owner && String(q.owner) === S.uid ? "Bạn" : (S.cur && S.cur.type === "user" ? S.cur.name : (member && member.name) || (friend && friend.name)) || q.owner || "";
  const txt = q.text || (q.attach_kind ? "[" + (REPLY_KIND[q.attach_kind] || "Tệp") + "]" + (q.attach_name ? " " + q.attach_name : "") : "");
  return h("div", { class: "quote" }, h("div", { class: "qwho" }, who), h("div", { class: "qtxt" }, txt.slice(0, 160)));
}
// ---- nhắc tên (@) trong nhóm ----
function groupMembers() {
  return ((S.cur && S.cur.members) || []).map((m) => typeof m === "object" ? { id: String(m.id || m.userId || ""), name: m.name || m.dName || m.displayName || "" } : { id: String(m), name: "" })
    .map((m) => ({ id: m.id, name: m.name || (rowOf("user", m.id) || {}).name || "" })).filter((m) => m.id && m.name && m.id !== S.uid);
}
function updateMentions() {
  const box = $("mentions"), ta = $("msg-in"); if (!box) return;
  if (!S.cur || S.cur.type !== "group") { box.hidden = true; return; }
  const mt = /(^|\s)@([^\s@]*)$/.exec(ta.value.slice(0, ta.selectionStart)); if (!mt) { box.hidden = true; return; }
  const q = plain(mt[2]), list = groupMembers().filter((m) => !q || plain(m.name).includes(q)).slice(0, 8);
  if (!list.length) { box.hidden = true; return; }
  const tokenLen = mt[0].length - mt[1].length;
  put(box, list.map((m) => h("button", { type: "button", role: "option", onmousedown: (e) => e.preventDefault(), onclick: () => pickMention(m, tokenLen) }, avatar({ id: m.id, name: m.name, avatar: (rowOf("user", m.id) || {}).avatar }, "sm"), h("span", {}, m.name))));
  box.hidden = false;
}
function pickMention(m, tokenLen) {
  const ta = $("msg-in"), pos = ta.selectionStart, start = pos - tokenLen, ins = "@" + m.name + " ";
  ta.value = ta.value.slice(0, start) + ins + ta.value.slice(pos); ta.setSelectionRange(start + ins.length, start + ins.length); ta.focus();
  if (!S.mentions.some((x) => x.uid === m.id)) S.mentions.push({ uid: m.id, name: m.name });
  $("mentions").hidden = true; autosize();
}
function imageDims(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file), img = new Image(), done = (w, hh) => { URL.revokeObjectURL(url); resolve({ w, h: hh }); }, t = setTimeout(() => done(0, 0), 5000);
    img.onload = () => { clearTimeout(t); done(img.naturalWidth, img.naturalHeight); }; img.onerror = () => { clearTimeout(t); done(0, 0); }; img.src = url;
  });
}
const PHOTO = /^image\/(jpeg|png|webp)$/;
// Khay «chờ gửi» (như Zalo PC): chọn/dán/thả ảnh thì xếp vào khay, người dùng gõ chú thích rồi mới bấm Gửi.
function stageFiles(files) {
  if (!S.cur) return toast("Hãy mở một cuộc trò chuyện trước.");
  S.pending = S.pending.concat([...files]).slice(0, 20); renderTray(); updateSendButtons(); $("msg-in").focus();
}
function renderTray() {
  const tray = $("attach-tray"); if (!tray) return;
  tray.hidden = !S.pending.length;
  put(tray, S.pending.map((f, i) => h("div", { class: "tray-item" },
    PHOTO.test(f.type) || /^image\//.test(f.type) ? h("img", { src: URL.createObjectURL(f), alt: f.name }) : h("span", { class: "tray-file" }, svg("file"), h("span", {}, f.name.slice(0, 18))),
    h("button", { class: "tray-x", type: "button", "aria-label": "Bỏ " + f.name, onclick: () => { S.pending.splice(i, 1); renderTray(); updateSendButtons(); } }, "✕"))),
    S.pending.length ? h("div", { class: "tray-hint" }, S.pending.length + " tệp · gõ chú thích rồi bấm Gửi") : null);
}
// Gửi: nhiều ảnh (không phải GIF) gắn chung một nhóm để bên nhận thấy thành MỘT album; ảnh đơn kèm chú thích thì chú thích đi cùng ảnh
// (desc), còn nhiều ảnh/tệp thì chú thích gửi thành tin chữ riêng (cách zca-js làm).
async function sendFiles(files, caption) {
  if (!S.cur) return toast("Hãy mở một cuộc trò chuyện trước.");
  const list = [...files]; let ok = 0;
  const photoIdx = list.map((f, i) => (PHOTO.test(f.type) ? i : -1)).filter((i) => i >= 0), nPhoto = photoIdx.length, layoutId = String(Date.now());
  const single = list.length === 1 && nPhoto === 1;
  const isVideoFile = (f) => /^video\//.test(f.type || "") || /\.(mp4|mov|m4v|webm|mkv|3gp)$/i.test(f.name || ""), singleVideo = list.length === 1 && isVideoFile(list[0]);
  for (let i = 0; i < list.length; i++) {
    const f = list[i]; toast("Đang gửi " + (i + 1) + "/" + list.length + ": " + f.name, 30000);
    const form = new FormData(); form.append("type", typeParam());
    const photo = PHOTO.test(f.type); form.append("kind", photo ? "photo" : "file");
    if (photo) { const d = await imageDims(f); form.append("width", d.w); form.append("height", d.h); }
    if (photo && nPhoto > 1) { form.append("groupLayoutId", layoutId); form.append("totalItemInGroup", String(nPhoto)); form.append("isGroupLayout", "1"); form.append("idInGroup", String(photoIdx.indexOf(i))); }
    if ((photo && single && caption) || (singleVideo && caption)) form.append("desc", caption);      // ảnh đơn / video đơn: chú thích đi cùng tin
    form.append("file", f, f.name);
    const r = await apiForm("/api/thread/" + encodeURIComponent(S.cur.id) + "/sendfile", form);
    if (r.error) { setNotice("Không gửi được “" + f.name + "”: " + r.error, true); continue; }
    ok++;
    if (r.message) { if (photo) r.message.localUrl = URL.createObjectURL(f); mergeMsgs([r.message]); touchConv(S.cur.type, S.cur.id, r.message, { open: true }); S.stick = true; renderMsgs(); renderList(); }
  }
  if (caption && !single && !singleVideo && ok) await sendRaw(caption);
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

// ---- nhãn dán: tìm / gợi ý (zca-js) rồi bấm để gửi vào hội thoại đang mở ----------------------------------------------
let stickerTimer = null;
function closeStickers() { $("stickers").hidden = true; }
async function loadStickers(grid, url) {
  grid.replaceChildren(h("p", { class: "snote" }, "Đang tải…"));
  let r; try { r = await api(url); } catch (e) { r = { error: String(e) }; }
  if (r.error) return grid.replaceChildren(h("p", { class: "snote" }, "Không tải được nhãn dán: " + r.error));
  const items = r.items || [];
  if (!items.length) return grid.replaceChildren(h("p", { class: "snote" }, "Không có nhãn dán nào."));
  grid.replaceChildren(...items.map((it) => h("button", { type: "button", title: it.text || "Nhãn dán", "aria-label": it.text || "Nhãn dán", onclick: () => sendSticker(it) }, h("img", { src: it.url, alt: it.text || "", loading: "lazy" }))));
}
async function sendSticker(it) {
  if (!S.cur) return toast("Hãy mở một cuộc trò chuyện trước.");
  closeStickers();
  const r = await api("/api/svc/send_sticker", "POST", { thread_id: S.cur.id, type: typeParam(), sticker_id: it.id, cate_id: it.cate_id, sticker_type: it.type });
  if (r.error) return setNotice("Lỗi gửi nhãn dán: " + r.error, true);
  setNotice(""); toast("Đã gửi nhãn dán");
}
function toggleStickers() {
  const box = $("stickers"); if (!box.hidden) return closeStickers();
  if (!S.cur) return toast("Hãy mở một cuộc trò chuyện trước.");
  const grid = h("div", { class: "sgrid" });
  const q = h("input", { type: "search", placeholder: "Tìm nhãn dán…", "aria-label": "Tìm nhãn dán", oninput: () => { clearTimeout(stickerTimer); const v = q.value.trim(); stickerTimer = setTimeout(() => loadStickers(grid, v ? "/api/stickers/search?q=" + encodeURIComponent(v) : "/api/stickers/recommended"), 350); } });
  box.replaceChildren(q, grid); box.hidden = false; q.focus();
  loadStickers(grid, "/api/stickers/recommended");
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
  const members = ((row.member_ids && row.member_ids.length ? row.member_ids : row.members) || []).map((m) => typeof m === "object" ? { id: String(m.id || m.userId || ""), name: m.name || m.dName || m.displayName || "" } : { id: String(m), name: "" });
  const nameOf = (m) => m.name || (rowOf("user", m.id) || {}).name || m.id;
  const photos = S.msgs.filter((m) => m.kind === "photo" && (photoSrc(m) || m.thumb_url)).slice(-8).reverse();
  const files = S.msgs.filter((m) => m.kind === "file").slice(-6).reverse();
  put(box,
    h("div", { class: "info-h" }, isGroup ? "Thông tin nhóm" : "Thông tin hội thoại"),
    h("div", { class: "info-top" }, avatar(row, "xl"), h("div", { class: "info-name" }, row.name || row.id),
      h("div", { class: "info-sub" }, isGroup ? "Nhóm" : c.stranger || row.stranger ? "Người lạ (không có trong danh bạ)" : "Bạn bè"),
      h("div", { style: "margin-top:.5rem;display:flex;justify-content:center;align-items:center;gap:.25rem" }, h("span", { class: "mono" }, row.id), h("button", { class: "icon-btn", type: "button", "aria-label": "Sao chép threadId", title: "Sao chép threadId", onclick: () => copyText(row.id, "threadId") }, svg("copy"))),
      h("div", { class: "info-acts" },
        isGroup ? null : h("button", { class: "iact", type: "button", disabled: !!S.calls.active, onclick: () => startCall(false) }, h("span", { class: "c" }, svg("phone")), "Gọi thoại"),
        h("button", { class: "iact", type: "button", disabled: !!S.calls.active, onclick: () => startCall(true) }, h("span", { class: "c" }, svg("video")), isGroup ? "Gọi video nhóm" : "Gọi video"),
        h("button", { class: "iact", type: "button", onclick: () => setTab("services") }, h("span", { class: "c" }, svg("grid")), "Dịch vụ"))),
    isGroup ? infoSection("Thành viên (" + members.length + ")", members.length ? h("div", { class: "imembers" }, members.slice(0, 100).map((m) => h("div", { class: "imember" }, avatar({ id: m.id, name: nameOf(m), avatar: (rowOf("user", m.id) || {}).avatar }, "sm"), h("span", {}, nameOf(m))))) : h("p", { class: "inote" }, "Chưa tải được danh sách thành viên.")) : null,
    infoSection("Ảnh/Video", photos.length ? h("div", { class: "igrid" }, photos.map((m) => h("a", { href: photoSrc(m) || m.file_url, target: "_blank", rel: "noopener" }, h("img", { src: photoSrc(m) || m.thumb_url, alt: m.file_name || "Ảnh", loading: "lazy" })))) : h("p", { class: "inote" }, "Chưa có ảnh nào được tải trong cuộc trò chuyện này.")),
    infoSection("Tệp", files.length ? h("div", { class: "imembers" }, files.map((m) => h("div", { class: "imember" }, svg("file"), h("span", { style: "flex:1;min-width:0;overflow-wrap:anywhere" }, m.file_name || m.text || "Tệp"), h("span", { class: "inote" }, fmtSize(m.file_size))))) : h("p", { class: "inote" }, "Chưa có tệp nào.")));
}

// ---- cuộc gọi ------------------------------------------------------------------------------------------------
const END_REASON = { ring_timeout: "Không ai nghe máy", user_end: "Đã kết thúc", server_rejected: "Máy chủ Zalo từ chối", superseded_by_new_call: "Bị thay bằng cuộc gọi mới", peer_ended: "Bên kia đã cúp", answered: "Đã nghe máy",
  missed: "Cuộc gọi nhỡ", peer_declined: "Bên kia từ chối", user_rejected: "Bạn đã từ chối", busy_rejected: "Đang có cuộc khác nên đã từ chối" };
// Loại lỗi cuộc gọi đi (server ghi error_kind, xem call_errors.py); chuỗi kỹ thuật gốc nằm ở c.detail.
const endText = (d) => END_REASON[d] || d || "";
// Loại lỗi cuộc gọi đi (server ghi error_kind, xem call_errors.py); chuỗi kỹ thuật gốc nằm ở c.detail.
const ERROR_KIND = { already_answered: "Cuộc gọi đã được nghe ở nơi khác", server_rejected: "Zalo từ chối cuộc gọi", timeout: "Hết thời gian chờ Zalo", network: "Lỗi mạng tới Zalo", unknown: "Lỗi không rõ" };
const callResult = (c) => (c.error_kind ? (ERROR_KIND[c.error_kind] || "Lỗi") : endText(c.detail) || c.status);
function syncCallButtons() { const busy = !!S.calls.active; $("btn-call").disabled = busy; $("btn-video").disabled = busy; }
async function loadCalls() {
  let d; try { d = await api("/api/calls"); } catch (e) { return; }
  if (d.error) return;
  const prev = S.calls.active; S.calls = { active: d.active || null, calls: d.calls || [] };
  const inc = S.calls.active;
  if (inc && inc.direction === "in" && inc.status === "incoming" && S.ringId !== String(inc.call_id)) { S.ringId = String(inc.call_id); beep(); }
  if (prev && !S.calls.active) { const done = S.calls.calls.find((c) => String(c.call_id) === String(prev.call_id)); toast("Cuộc gọi với " + peerName(prev) + " đã kết thúc" + (done && done.detail ? ": " + endText(done.detail) : "."), 5000); }
  renderCallCard(); syncCallButtons(); $("dot-calls").hidden = !S.calls.active;
  if (S.cur && S.info) syncInfo();
  if (S.tab === "calls") { renderCallRows($("list")); renderCallsPage(); }
}
async function startCall(video) {
  const row = S.cur; if (!row || S.calls.active) return;
  const type = row.type === "group" ? "group" : video ? "video" : "user";
  toast("Đang gọi " + (row.name || row.id) + "…");
  // Nhóm: gọi VIDEO nhóm (typeRequest 6) và đổ chuông ĐỦ thành viên (member_ids = topMember + memberIds + currentMems; topMember chỉ là danh sách rút gọn).
  const partners = (row.member_ids && row.member_ids.length >= (row.members || []).length ? row.member_ids : row.members) || [];
  const r = await api("/api/call/request", "POST", { callee_id: row.id, type, video: row.type === "group" || video, peer_name: row.name || row.id, partners });
  if (r.error) return toast("Không gọi được: " + r.error, 6000);
  if (r.request_sent === false) toast("Đã gửi yêu cầu nhưng bước 2 chưa gửi được: " + (r.request_error || "không rõ"), 7000);
  await loadCalls();
}
async function answerCall(a) {
  const r = await api("/api/call/answer", "POST", { call_id: a.call_id });
  if (r.error || r.ok === false) toast("Không nghe máy được: " + (r.error || r.detail || "không rõ"), 6000);
  await loadCalls();
}
async function rejectCall(a) {
  const r = await api("/api/call/reject", "POST", { call_id: a.call_id });
  if (r.error || r.ok === false) toast("Không từ chối được: " + (r.error || r.detail || "không rõ"), 6000);
  await loadCalls();
}
// Nút bật/tắt mic, loa, camera của cuộc gọi: điều khiển THIẾT BỊ TRONG NHÀ (mic/loa R1, camera) qua /api/call/media và /api/call/video.
S.cm = { id: "", mic: false, speaker: false, video: false, busy: "", gain: { mic: 100, speaker: 100 } };
function applyCm(id, r) {
  const on = (x) => !!x && x.alive !== false;
  S.cm = Object.assign(S.cm, { id: String(id), mic: on(r.mic), speaker: on(r.speaker), video: on(r.video) });
  if (r.gain && typeof r.gain === "object") S.cm.gain = { mic: Number(r.gain.mic) || 0, speaker: Number(r.gain.speaker) || 0 };
  renderCallCard();
}
async function refreshCallMedia() {
  const a = S.calls.active; if (!a || S.cm.busy) return;
  try { const r = await api("/api/call/media", "POST", { call_id: a.call_id, action: "status" }); if (!r.error && r.ok !== false) applyCm(a.call_id, r); } catch (e) { /* mạng: thử lại lần sau */ }
}
// Tăng/giảm âm lượng mic hoặc loa của cuộc gọi bằng phần mềm (mỗi lần bấm ±10%, 0–300%): hoạt động cả khi loa R1 không nghe lệnh set_volume.
async function changeGain(target, step) {
  const a = S.calls.active; if (!a) return;
  try {
    const r = await api("/api/call/media", "POST", { call_id: a.call_id, action: "gain", target, step });
    if (r.error || r.ok === false) { toast("Không chỉnh được âm lượng " + (target === "mic" ? "mic" : "loa") + ": " + (r.error || "lỗi"), 4000); return; }
    S.cm.gain = Object.assign({}, S.cm.gain, r.gain || {}); renderCallCard();
  } catch (e) { toast("Lỗi mạng khi chỉnh âm lượng", 4000); }
}
// Lỗi thiếu thiết bị của cuộc gọi: nói bằng lời thường (thiết bị do quy tắc/automation chọn, không còn mặc định).
const MEDIA_ERR = { chua_co_camera: "chưa có camera — quy tắc (automation) của người này chưa chọn camera", chua_co_speaker_url: "chưa có loa — quy tắc (automation) của người này chưa chọn loa", no_live_transport: "cuộc gọi chưa sẵn sàng", no_live_call: "không có cuộc gọi đang diễn ra" };
const mediaErr = (e) => MEDIA_ERR[e] || e || "lỗi";
async function toggleMedia(target) {
  const a = S.calls.active; if (!a || S.cm.busy) return;
  const turnOn = !S.cm[target === "video" ? "video" : target];
  S.cm.busy = target; renderCallCard();
  try {
    // Cuộc gọi THOẠI mà bật camera = xin chuyển sang VIDEO (12056 tới điện thoại + phát hình nhà), không chỉ phát hình vào cuộc gọi thoại.
    const upgrade = target === "video" && turnOn && a.type !== "video";
    const r = await api(upgrade ? "/api/call/upgrade_video" : target === "video" ? "/api/call/video" : "/api/call/media", "POST", upgrade ? { call_id: a.call_id } : { call_id: a.call_id, action: turnOn ? "start" : "stop", target });
    if (r.error || r.ok === false) toast((turnOn ? "Không bật được " : "Không tắt được ") + ({ mic: "mic", speaker: "loa", video: "camera" })[target] + ": " + mediaErr(r.error), 6000);
    S.cm.busy = ""; applyCm(a.call_id, r.error ? {} : r);
    if (r.error || r.ok === false) refreshCallMedia();
  } catch (e) { S.cm.busy = ""; toast("Lỗi mạng khi điều khiển cuộc gọi", 4000); renderCallCard(); }
}
// Hình điện thoại gửi sang: <img> MJPEG (/api/call/video/view). Giữ MỘT nút ảnh suốt cuộc gọi (thẻ vẽ lại mỗi vài giây — tạo ảnh mới sẽ nối lại luồng liên tục).
S.vv = null;
// Hai đường lấy hình: luồng liên tục (MJPEG, trễ thấp) và, nếu luồng không lên sau 6 giây hoặc lỗi 2 lần (proxy/tunnel gom bộ đệm), từng ảnh mới nhất
// (/api/call/video/snapshot, hỏi ~4 lần/giây, chạy qua mọi proxy).
function videoView(a, mc) {
  if (!(a.type === "video" || (mc && mc.video_rx > 0))) { S.vv = null; return null; }
  if (!S.vv || S.vv.id !== String(a.call_id)) {
    const id = encodeURIComponent(a.call_id);
    const streamUrl = () => "/api/call/video/view?call_id=" + id + "&t=" + Date.now();
    const snapUrl = () => "/api/call/video/snapshot?call_id=" + id + "&t=" + Date.now();
    const wait = h("div", { class: "vv-wait" }, "Đang chờ hình từ điện thoại…");
    const el = h("img", { class: "vview", alt: "Hình từ điện thoại", src: streamUrl() });
    const box = h("div", { class: "vvbox" }, el, wait);
    const vv = { id: String(a.call_id), el: box, mode: "stream", errors: 0, timer: null, ratio: 0 };
    const current = () => S.vv === vv;
    // Khung theo ĐÚNG chiều của hình: điện thoại quay dọc (khung đứng), máy tính nằm ngang. Hình dọc: khung đứng cao tối đa --vcap (70% màn hình; điện thoại 40%), căn giữa; hình ngang: rộng hết thẻ.
    // Kiểm lại mỗi giây vì luồng liên tục không báo khi người kia xoay điện thoại.
    const fit = () => {
      const w = el.naturalWidth, h = el.naturalHeight;
      if (!w || !h || !current()) return;
      const r = Math.max(0.5, Math.min(2, w / h));
      if (Math.abs(vv.ratio - r) < 0.01) return;
      vv.ratio = r; box.dataset.ratio = r.toFixed(4);
      box.style.aspectRatio = r.toFixed(4);
      box.style.width = r >= 1 ? "100%" : "min(100%, calc(var(--vcap, 70vh) * " + r.toFixed(4) + "))";
      box.style.marginInline = "auto";
    };
    vv.fit = fit; vv.fitTimer = setInterval(() => { if (!current()) return clearInterval(vv.fitTimer); fit(); }, 1000);
    box.title = "Bấm để chuyển giữa «vừa khung» và «phủ đầy khung»";
    box.addEventListener("click", () => box.classList.toggle("fill"));
    const snapLoop = () => {
      if (!current() || vv.mode !== "snap") return;
      const img = new Image();
      img.onload = () => { if (!current()) return; el.src = img.src; box.classList.add("on"); fit(); vv.timer = setTimeout(snapLoop, 250); };
      img.onerror = () => { if (!current()) return; vv.timer = setTimeout(snapLoop, 700); };      // 204 = chưa có ảnh: thử lại
      img.src = snapUrl();
    };
    vv.fallback = () => { if (vv.mode === "snap" || !current()) return; vv.mode = "snap"; clearTimeout(vv.timer); box.dataset.mode = "snap"; snapLoop(); };
    el.addEventListener("load", () => { fit(); if (vv.mode === "stream") { clearTimeout(vv.timer); box.classList.add("on"); } });
    el.addEventListener("error", () => {
      if (vv.mode !== "stream") return;
      box.classList.remove("on"); vv.errors++;
      if (vv.errors >= 2) return vv.fallback();
      setTimeout(() => { if (current() && vv.mode === "stream") el.src = streamUrl(); }, 3000);      // chưa có hình (409) / ffmpeg đang dậy: thử lại một lần
    });
    vv.timer = setTimeout(() => { if (current() && !box.classList.contains("on")) vv.fallback(); }, 6000);      // luồng không ra hình sau 6 giây
    S.vv = vv;
  }
  return S.vv.el;
}
function mediaToggles() {
  const row = [["mic", "mic", "Mic"], ["speaker", "speaker", "Loa"], ["video", "cam", "Camera"]].map(([key, icon, label]) =>
    h("button", { class: "tg" + (S.cm[key] ? " on" : ""), type: "button", "aria-pressed": S.cm[key] ? "true" : "false", disabled: !!S.cm.busy,
      title: label + " trong nhà (R1/camera): " + (S.cm[key] ? "đang bật, bấm để tắt" : "đang tắt, bấm để bật"), onclick: () => toggleMedia(key) },
      svg(icon), h("span", {}, label + (S.cm[key] ? " bật" : " tắt"))));
  const gains = [["mic", "Mic"], ["speaker", "Loa"]].map(([key, label]) => {
    const g = (S.cm.gain && S.cm.gain[key]) ?? 100;
    return h("div", { class: "gn" + (g === 0 ? " mute" : "") },
      h("button", { type: "button", "aria-label": "Giảm âm lượng " + label.toLowerCase(), disabled: g <= 0, onclick: () => changeGain(key, -10) }, "−"),
      h("span", { class: "gv", title: "Âm lượng " + label.toLowerCase() + " (100% = giữ nguyên)" }, label + " " + g + "%"),
      h("button", { type: "button", "aria-label": "Tăng âm lượng " + label.toLowerCase(), disabled: g >= 300, onclick: () => changeGain(key, 10) }, "+"));
  });
  return h("div", {}, h("div", { class: "tgs" }, row), h("div", { class: "gns" }, gains));
}
setInterval(() => { const a = S.calls.active; if (a && (a.status === "answered" || a.answered_at)) refreshCallMedia(); }, 3000);
async function endCall() { const a = S.calls.active; if (!a) return; const r = await api("/api/call/end", "POST", { call_id: a.call_id }); if (r.error) toast("Lỗi kết thúc cuộc gọi: " + r.error, 5000); await loadCalls(); }
// Cửa sổ riêng của hình đối tác (#vidwin): giữ NGUYÊN phần tử khung giữa các lần vẽ lại thẻ để luồng hình không bị khởi động lại.
function showVideoWin(box) {
  const win = $("vidwin");
  if (!box) { win.hidden = true; if (win.firstChild) win.replaceChildren(); return; }
  win.hidden = false;
  if (win.firstChild !== box) put(win, box);
}
function renderCallCard() {
  const card = $("callcard"), a = S.calls.active;
  if (!a) { S.vv = null; card.hidden = true; card.replaceChildren(); showVideoWin(null); return; }
  const row = rowOf(a.type === "group" ? "group" : "user", a.thread_id) || { id: String(a.thread_id), name: a.peer, type: a.type === "group" ? "group" : "user" };
  if (a.direction === "in" && a.status === "incoming" && !a.answered_at) {       // cuộc gọi ĐẾN, chưa ai nghe: popup hai nút như Zalo PC
    card.hidden = false; card._since = a.started_at; showVideoWin(null);
    put(card, h("div", { class: "top" }, avatar(row), h("div", { style: "flex:1;min-width:0" }, h("div", { class: "nm" }, peerName(a)), h("div", { class: "st" }, a.type === "video" ? "Cuộc gọi video đến…" : "Cuộc gọi đến…"), h("div", { class: "tm", id: "call-t" }, fmtDur(Date.now() / 1000 - a.started_at)))),
      h("div", { class: "acts" }, h("button", { class: "end", type: "button", onclick: () => rejectCall(a) }, svg("hang"), "Từ chối"), h("button", { class: "ok", type: "button", onclick: () => answerCall(a) }, svg("phone"), "Nghe")));
    return;
  }
  const answered = a.status === "answered" || !!a.answered_at, ringing = !answered && a.request_sent === true;
  // Cảnh báo CHỈ khi đã nối >8 giây mà chưa thấy gói tiếng/hình nào chạy (số đếm thật của cuộc gọi) — không dựa vào cờ «engine» của cuộc gọi đi
    // (ảnh 12/11: cuộc gọi đến chạy bình thường vẫn bị báo sai ngay giây đầu).
    const since = (answered && a.answered_at) || a.started_at, mc = a.media && a.media.counters, flowing = !!(mc && (mc.rtp_tx > 0 || mc.rtp_rx > 0));
    const noMedia = answered && Date.now() / 1000 - since > 8 && !flowing;
  card.hidden = false;
  put(card,
    h("div", { class: "top" }, avatar(row), h("div", { style: "flex:1;min-width:0" }, h("div", { class: "nm" }, (a.type === "video" ? "Video · " : "") + peerName(a)), h("div", { class: "st" }, answered ? "Đang trong cuộc gọi" : ringing ? "Đang đổ chuông…" : "Đang kết nối…"), h("div", { class: "tm", id: "call-t" }, fmtDur(Date.now() / 1000 - since)))),
    answered && noMedia ? h("div", { class: "warn" }, "Đã nối hơn 8 giây nhưng chưa thấy gói tiếng/hình nào chạy qua; bên kia có thể báo “kết nối không ổn định”.") : null,
    a.request_sent === false ? h("div", { class: "warn" }, "Bước 2 chưa gửi được, bên kia có thể chưa đổ chuông.") : null,
    answered ? mediaToggles() : null,
    h("div", { class: "acts" }, h("button", { class: "end", type: "button", onclick: endCall }, svg("hang"), "Kết thúc")));
  showVideoWin(answered ? videoView(a, mc) : null);        // khung hình đối tác là CỬA SỔ RIÊNG, không nằm trong thẻ điều khiển cuộc gọi
  if (answered && S.cm.id !== String(a.call_id)) { S.cm.id = String(a.call_id); S.cm.mic = S.cm.speaker = S.cm.video = false; refreshCallMedia(); }
  card._since = since;
}
setInterval(() => { const c = $("callcard"), t = $("call-t"); if (t && c._since) t.textContent = fmtDur(Date.now() / 1000 - c._since); }, 1000);
function callPill(c) {
  if (c.status === "answered" || c.answered_at) return h("span", { class: "pill ok" }, "Đã nghe máy");
  if (c.status === "error" || c.detail === "server_rejected") return h("span", { class: "pill bad", title: String(c.detail || "") }, c.error_kind ? (ERROR_KIND[c.error_kind] || "Lỗi") : "Lỗi");
  if (c.detail === "missed") return h("span", { class: "pill warn" }, "Cuộc gọi nhỡ");
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
      h("div", { class: "row-top" }, h("span", { class: "row-name" }, peerName(c)), h("span", { class: "row-time" }, fmtRel(c.started_at))),
      h("div", { class: "row-sub" }, (c.type === "video" ? "Video · " : c.type === "group" ? "Nhóm · " : "Thoại · ") + callResult(c))))));
  }
}
function renderCallsPage() {
  const box = $("calls-page"); box.replaceChildren(); const list = callList();
  $("calls-sub").textContent = S.calls.active ? "Đang có cuộc gọi" : list.length + " cuộc gần đây";
  box.append(h("div", { class: "card wide" }, h("h3", {}, "Lịch sử cuộc gọi"),
    !list.length ? h("p", { style: "color:var(--muted);margin:0" }, "Chưa có cuộc gọi nào. Mở một cuộc trò chuyện và bấm biểu tượng điện thoại hoặc video.") :
      h("div", {}, list.map((c) => h("div", { style: "display:flex;gap:.625rem;align-items:center;padding:.5rem 0;border-top:1px solid var(--line)" },
        h("div", { style: "flex:1;min-width:0" }, h("div", { style: "font-weight:500" }, peerName(c)), h("div", { style: "color:var(--muted);font-size:.78rem" }, (c.type === "video" ? "Video" : c.type === "group" ? "Nhóm" : "Thoại") + " · " + fmtDT(c.started_at) + (c.ended_at ? " · " + fmtDur(c.ended_at - c.started_at) : ""))), callPill(c))))));
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
    // Mục "ngoài 96" (quote_message, mark_seen, get_settings, update_label…) không có addon_no nhưng CHẠY ĐƯỢC: khóa theo action để không bị ẩn.
    const keyOf = (s) => (s.addon_no != null ? s.addon_no : "x:" + (s.action || s.addon));
    S.catalog = { groups: d.groups || [], items: (d.services || []).filter((s) => { const k = keyOf(s); if (seen.has(k)) return false; seen.add(k); s._key = k; return true; })
      .sort((a, b) => (a.addon_no == null ? 1e6 : a.addon_no) - (b.addon_no == null ? 1e6 : b.addon_no)) };
    // 333 API của zca-js: những cái chưa có trong 96 dịch vụ PC được thêm vào (gọi bằng bộ gọi chung, CHƯA kiểm với Zalo thật).
    const snake = (n) => n.replace(/[A-Z]/g, (c, k) => (k ? "_" : "") + c.toLowerCase());
    const have = new Set(); for (const x of S.catalog.items) { have.add(x.addon); if (x.action) have.add(x.action); }
    const ZG = { auth: "Xác thực & phiên", chat: "Tin nhắn & hội thoại", group: "Nhóm & cộng đồng", friend: "Bạn bè & danh bạ", profile: "Hồ sơ cá nhân", sync: "Đồng bộ", zcloud: "Đám mây", call: "Cuộc gọi", media: "Kho lưu trữ & giọng nói", sticker: "Nhãn dán", board: "Bảng tin & bình chọn", business: "Business & OA" };
    const zitems = (((d.zca || {}).apis) || []).filter((a) => !a.covered_by && !have.has(snake(a.name))).map((a) => {
      const fields = (a.args || []).map((f) => ({ key: f.name, label: (f.description || f.name) + " (" + f.type + ")", required: !!f.required }));
      if (a.mode === "raw") fields.push({ key: "params", label: "params — JSON đúng như zca-js gửi", required: true });
      return { addon: snake(a.name), action: snake(a.name), addon_no: "zca:" + a.name, _key: "zca:" + a.name, group: "zca_" + a.domain, label: a.name, desc: a.summary, status: a.mode === "manual" ? "manual" : "supported", reason: a.reason, fields, thread: "none", danger: !!a.danger, zca: true };
    });
    const zgroups = Object.keys(ZG).filter((k) => zitems.some((x) => x.group === "zca_" + k)).map((k) => ({ id: "zca_" + k, label: "zca · " + ZG[k] }));
    S.catalog.items = S.catalog.items.concat(zitems); S.catalog.groups = S.catalog.groups.concat(zgroups);
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
  const open = S.svcOpen === s._key;
  const pill = s.status === "supported" ? h("span", { class: "pill ok" }, "dùng được") : h("span", { class: "pill" }, s.status === "chat" ? "trong chat" : s.status === "view" ? "ở danh bạ" : s.status === "manual" ? "chưa tự động" : "zalobot");
  const el = h("div", { class: "svc" }, h("button", { type: "button", "aria-expanded": String(open), onclick: () => { S.svcOpen = open ? null : s._key; renderServices(); } }, h("span", { class: "svc-name" }, s.label && s.label !== s.addon ? s.label : s.addon, h("div", { class: "svc-sub" }, s.addon + (s.danger ? " · không hoàn tác" : ""))), pill));
  if (open) el.append(svcBody(s)); return el;
}
function svcBody(s) {
  const body = h("div", { class: "svc-body" });
  if (s.status !== "supported") { body.append(h("p", { style: "color:var(--muted)" }, STATUS_HINT[s.status] || s.reason || "")); return body; }
  const need = s.thread && s.thread !== "none";
  if (need) body.append(h("p", { class: "notice", style: "margin:.625rem 0" }, S.cur ? "Áp dụng cho: " + (S.cur.name || S.cur.id) + (S.cur.type === "group" ? " (nhóm)" : "") : "Cần chọn hội thoại: mở một cuộc trò chuyện trước rồi quay lại đây."));
  if (s.zca) body.append(h("p", { class: "notice", style: "margin:.625rem 0" }, (s.desc || "") + " — API lấy từ zca-js, CHƯA kiểm với máy chủ Zalo thật."));
  const inputs = {};
  for (const f of s.fields || []) { const input = h("input", { type: f.key === "file" ? "file" : "text", id: "svc-" + f.key, autocomplete: "off", accept: f.key === "file" ? "image/*" : null }); inputs[f.key] = input; body.append(h("div", { class: "field", style: "margin-top:.625rem" }, h("label", { for: "svc-" + f.key }, f.label + (f.required ? " *" : "")), input)); }
  const out = h("pre", { class: "out", hidden: true });
  const btn = h("button", { class: "btn primary", type: "button", style: "margin-top:.375rem", onclick: async () => {
    if (need && !S.cur) return toast("Hãy mở một cuộc trò chuyện trước.");
    if (s.danger && !confirm("“" + (s.label || s.addon) + "” không hoàn tác được. Tiếp tục?")) return;
    const payload = need ? { thread_id: S.cur.id, type: S.cur.type } : {}; if (s.zca && s.danger) payload.confirm = true;
    for (const [k, el] of Object.entries(inputs)) if (el.type !== "file" && el.value.trim() !== "") payload[k] = el.value.trim();
    const fileEl = inputs.file && inputs.file.type === "file" ? inputs.file : null;       // dịch vụ tải ảnh (đổi ảnh đại diện): gửi multipart
    if (fileEl && !fileEl.files.length) return toast("Hãy chọn tệp ảnh trước.");
    btn.disabled = true; let r;
    if (fileEl) { const form = new FormData(); for (const [k, v] of Object.entries(payload)) form.append(k, String(v)); form.append("file", fileEl.files[0], fileEl.files[0].name); r = await apiForm("/api/svc/" + s.action, form); }
    else r = await api("/api/svc/" + s.action, "POST", payload);
    btn.disabled = false; out.hidden = false;
    out.textContent = r.error ? "Lỗi: " + r.error : JSON.stringify(r.data === undefined ? r : r.data, null, 2);
  } }, "Chạy");
  body.append(btn, out); return body;
}

// ---- cài đặt: mỗi mục một trang riêng (bấm mục nào chỉ hiện mục đó) ------------------------------------------------------------
const section = (id, title, ...kids) => h("div", { class: "card", id }, h("h3", {}, title), ...kids);
const SET_SECS = [["account", "Tài khoản"], ["privacy", "Quyền riêng tư"], ["history", "Đồng bộ lịch sử"], ["data", "Dữ liệu và tự xóa"], ["calls", "Cuộc gọi và thiết bị"], ["ui", "Giao diện"], ["webhook", "Webhook"], ["proxy", "Proxy"], ["security", "Bảo mật"]];
function openSettings(sec) { S.setSec = sec || S.setSec || "account"; setTab("settings"); }
const PW_ERRORS = { sai_mat_khau_cu: "Mật khẩu hiện tại không đúng.", mat_khau_qua_ngan: "Mật khẩu mới phải từ 8 ký tự.", mat_khau_qua_dai: "Mật khẩu mới quá dài (tối đa 256 ký tự).", mat_khau_trung: "Mật khẩu mới phải khác mật khẩu cũ.", managed_by_env: "Mật khẩu đang đặt bằng biến môi trường ZALO_PC_APP_PASSWORD_HASH của container: đổi ở cấu hình container, không đổi được ở đây.", qua_nhieu_lan_sai: "Sai quá nhiều lần, thử lại sau 15 phút." };
const pillOf = (t, c) => h("span", { class: "pill " + (c || "") }, t);
const runPill = (v) => (v === "running" ? pillOf("đang chạy", "ok") : pillOf(v || "?", "warn"));
async function renderSettings(focusId) {
  const box = $("set-page");
  if (focusId && String(focusId).startsWith("set-")) S.setSec = String(focusId).slice(4);
  if (!SET_SECS.some(([id]) => id === S.setSec)) S.setSec = "account";
  const sec = S.setSec;
  const nav = h("div", { class: "chips setnav", role: "tablist", "aria-label": "Mục cài đặt" }, SET_SECS.map(([id, label]) => h("button", { class: "chip", type: "button", role: "tab", "aria-selected": String(sec === id), "aria-pressed": String(sec === id), onclick: () => { S.setSec = id; renderSettings(); } }, label)));
  box.replaceChildren(nav);
  const build = { account: setAccount, privacy: setPrivacy, history: setHistory, data: setData, calls: setCalls, ui: setUi, webhook: setWebhook, proxy: setProxy, security: setSecurity }[sec];
  let body; try { body = await build(); } catch (e) { body = h("p", { class: "notice bad" }, "Không tải được mục này: " + (e && e.message || e)); }
  if (box.firstChild === nav) box.append(body);        // người dùng đã bấm mục khác trong lúc chờ thì bỏ kết quả cũ
}
async function setAccount() {
  let st = S.status; try { st = await api("/api/status"); S.status = st; } catch (e) { /* giữ */ }
  const lag = st.sync_lag_ms, note = h("p", { class: "inote", role: "status" });
  const fOld = h("input", { type: "password", id: "acc-old", autocomplete: "current-password" }), fNew = h("input", { type: "password", id: "acc-new", autocomplete: "new-password", minlength: "8" }), fNew2 = h("input", { type: "password", id: "acc-new2", autocomplete: "new-password", minlength: "8" });
  const change = async () => {
    if (fNew.value !== fNew2.value) { note.textContent = "Hai ô mật khẩu mới không giống nhau."; return; }
    const r = await fetch("/api/app/password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ old_password: fOld.value, new_password: fNew.value }) });
    let d = {}; try { d = await r.json(); } catch (e) { /* không phải JSON */ }
    if (r.ok && d.ok) { note.textContent = "Đã đổi mật khẩu" + (d.other_sessions_revoked ? " (đã đăng xuất " + d.other_sessions_revoked + " phiên khác)." : "."); fOld.value = fNew.value = fNew2.value = ""; }
    else note.textContent = PW_ERRORS[d.error] || ("Không đổi được mật khẩu (" + (d.error || r.status) + ").");
  };
  return h("div", {},
    section("set-account", "Tài khoản và kết nối",
      h("dl", { class: "kv" },
        h("dt", {}, "Zalo"), h("dd", {}, st.login ? (st.phonenum || "") + " · " + st.uid : "Chưa đăng nhập"),
        h("dt", {}, "Kênh nhận tin"), h("dd", {}, runPill(st.sync), st.sync_error ? " " + st.sync_error : ""),
        h("dt", {}, "Kênh điều khiển"), h("dd", {}, runPill(st.ctrl), st.ctrl_error ? " " + st.ctrl_error : ""),
        h("dt", {}, "Đẩy tức thì"), h("dd", {}, h("span", { class: "live" + (S.sse ? "" : " off") }), S.sse ? "đang nối (tin hiện ngay khi tới)" : "đang nối lại…"),
        h("dt", {}, "Độ trễ nhận tin"), h("dd", {}, lag ? lag.last + " ms gần nhất · trung bình " + lag.avg + " ms (" + lag.n + " tin)" : "chưa có tin nào trong phiên này"),
        h("dt", {}, "Tiếng cuộc gọi"), h("dd", {}, st.engine && st.engine.attached ? pillOf("đã gắn", "ok") : pillOf("chưa có", "warn"), " ", (st.engine && st.engine.detail) || ""),
        h("dt", {}, "Phiên bản"), h("dd", { class: "mono" }, st.version || ""))),
    section("set-password", "Đổi mật khẩu đăng nhập app",
      h("p", { class: "inote" }, "Đây là mật khẩu vào app này, không phải mật khẩu Zalo. Đổi xong, các thiết bị khác bị đăng xuất."),
      h("div", { class: "field" }, h("label", { for: "acc-old" }, "Mật khẩu hiện tại"), fOld),
      h("div", { class: "field" }, h("label", { for: "acc-new" }, "Mật khẩu mới (từ 8 ký tự)"), fNew),
      h("div", { class: "field" }, h("label", { for: "acc-new2" }, "Nhập lại mật khẩu mới"), fNew2),
      h("button", { class: "btn primary", type: "button", onclick: change }, "Đổi mật khẩu"), note));
}
// Quyền riêng tư: ĐỌC giá trị thật (get_settings = /api/setting/me); bật/tắt hoặc chọn là ÁP DỤNG NGAY (update_settings), không có nút Lưu,
// lỗi thì trả công tắc về như cũ. Ý nghĩa giá trị theo zca-js updateSettings (view_birthday 0 ẩn/1 đủ/2 ngày-tháng; receive_message 1 mọi người/
// 2 chỉ bạn bè; accept_stranger_call 2 bạn bè/3 mọi người/4 bạn bè và người từng liên hệ; còn lại 0 tắt/1 bật). Khóa chưa có nhãn thì chỉ liệt kê tên.
const PRIVACY_TOGGLES = [["show_online_status", "Hiện trạng thái hoạt động"], ["display_seen_status", "Hiện «Đã xem» cho người nhắn"],
  ["add_friend_via_phone", "Cho tìm và kết bạn qua số điện thoại"], ["add_friend_via_qr", "Cho kết bạn qua mã QR"], ["add_friend_via_group", "Cho kết bạn qua nhóm chung"],
  ["add_friend_via_contact", "Cho kết bạn qua danh bạ"], ["display_on_recommend_friend", "Hiện trong gợi ý kết bạn"]];
const PRIVACY_CHOICES = [["view_birthday", "Hiển thị ngày sinh", [[0, "Ẩn"], [1, "Ngày, tháng và năm"], [2, "Chỉ ngày và tháng"]]],
  ["receive_message", "Ai được nhắn tin cho bạn", [[1, "Mọi người"], [2, "Chỉ bạn bè"]]],
  ["accept_stranger_call", "Ai được gọi cho bạn", [[3, "Mọi người"], [2, "Chỉ bạn bè"], [4, "Bạn bè và người từng liên hệ"]]]];
const PRIVACY_VIEWONLY = [["setting_show_stranger_msg_directly", "Hiện thẳng tin nhắn người lạ"], ["quick_message_status", "Tin nhắn nhanh"],
  ["archived_chat_status", "Lưu trữ hội thoại"], ["setting_2FA_status", "Xác thực hai lớp (đổi trong Zalo trên điện thoại)"]];
async function setPrivacy() {
  const r = await api("/api/svc/get_settings", "POST", {}), d = r.error ? null : (r.data === undefined ? r : r.data);
  if (!d || typeof d !== "object") return section("set-privacy", "Quyền riêng tư", h("p", { class: "notice bad" }, "Không đọc được cài đặt: " + (r.error || "phản hồi lạ")));
  const num = (v) => (v === true ? 1 : v === false ? 0 : Number(v)), note = h("p", { class: "inote", role: "status" });
  const apply = async (key, label, value) => {
    const x = await api("/api/svc/update_settings", "POST", { setting_type: key, status: value });
    note.textContent = x.error ? "Không đổi được “" + label + "”: " + x.error : "Đã áp dụng: " + label + ".";
    return !x.error;
  };
  const row = (label, key, control) => h("div", { class: "field-row", style: "padding:.5rem 0;border-top:1px solid var(--line);align-items:center" }, h("div", { style: "flex:1;min-width:0" }, label), control);
  const toggles = PRIVACY_TOGGLES.filter(([k]) => k in d).map(([k, label]) => {
    const box = h("input", { type: "checkbox", class: "tog", id: "pv-" + k, role: "switch", "aria-label": label, checked: num(d[k]) === 1 });
    box.addEventListener("change", async () => { const want = box.checked; box.disabled = true; if (!(await apply(k, label, want ? 1 : 0))) box.checked = !want; box.disabled = false; });
    return row(label, k, box);
  });
  const choices = PRIVACY_CHOICES.filter(([k]) => k in d).map(([k, label, opts]) => {
    let cur = num(d[k]); const list = opts.some(([v]) => v === cur) ? opts : opts.concat([[cur, "Khác (mức " + cur + ")"]]);
    const sel = h("select", { id: "pv-" + k, "aria-label": label }, list.map(([v, t]) => h("option", { value: String(v), selected: v === cur }, t)));
    sel.addEventListener("change", async () => { const want = Number(sel.value); sel.disabled = true; if (await apply(k, label, want)) cur = want; else sel.value = String(cur); sel.disabled = false; });
    return row(label, k, sel);
  });
  const view = PRIVACY_VIEWONLY.filter(([k]) => k in d).map(([k, label]) => row(label, k, h("span", { class: "pill" }, num(d[k]) ? "Bật" : "Tắt")));
  const known = new Set([...PRIVACY_TOGGLES, ...PRIVACY_CHOICES, ...PRIVACY_VIEWONLY].map((x) => x[0])), extra = Object.keys(d).filter((k) => !known.has(k));
  return section("set-privacy", "Quyền riêng tư",
    h("p", { class: "inote" }, "Giá trị đọc trực tiếp từ Zalo. Bật/tắt hoặc chọn là áp dụng ngay, không cần lưu."),
    ...toggles, ...choices, view.length ? h("div", { class: "inote", style: "margin-top:.75rem" }, "Chỉ xem") : null, ...view,
    extra.length ? h("p", { class: "inote" }, "Cài đặt khác chưa có nhãn: " + extra.join(", ")) : null, note);
}
// Đồng bộ lịch sử chat từ ĐIỆN THOẠI (cách Zalo PC lấy tin cũ): bấm bắt đầu → điện thoại hỏi xác nhận → app tải, giải mã, lưu các tệp SQLite.
const HS_STAGE = { idle: "Chưa chạy", requesting: "Đang gửi yêu cầu", waiting_phone: "Chờ bạn xác nhận trên điện thoại", downloading: "Đang tải", decrypting: "Đang giải mã", done: "Xong", error: "Lỗi", cancelled: "Đã huỷ" };
let hsTimer = null;
async function setHistory() {
  const box = h("div", {}), note = h("p", { class: "inote", role: "status" });
  const draw = async () => {
    const st = await api("/api/history-sync/status");
    if (st.error) { put(box, h("p", { class: "notice bad" }, "Không đọc được trạng thái: " + st.error)); return; }
    const busy = !!st.busy, tables = Object.entries(st.schema || {});
    put(box, section("set-history", "Đồng bộ lịch sử chat từ điện thoại",
      h("p", { class: "inote" }, "Tin nhắn cũ nằm trên điện thoại. Bấm bắt đầu rồi mở Zalo trên ĐIỆN THOẠI và xác nhận đồng bộ; app sẽ tải bản sao lưu, giải mã và lưu các tệp dữ liệu vào máy chủ này. Giải mã xong thì bấm «Nhập vào khung chat» để tin cũ hiện trong danh sách trò chuyện (chạy lại không nhân đôi tin)."),
      h("dl", { class: "kv" }, h("dt", {}, "Trạng thái"), h("dd", {}, h("span", { class: "pill " + (st.stage === "done" ? "ok" : st.stage === "error" ? "bad" : busy ? "warn" : "") }, HS_STAGE[st.stage] || st.stage)),
        h("dt", {}, "Chi tiết"), h("dd", {}, st.detail || "—")),
      h("div", { class: "field-row", style: "margin:.5rem 0" },
        h("button", { class: "btn primary", type: "button", disabled: busy, onclick: async () => { const r = await api("/api/history-sync/start", "POST", {}); note.textContent = r.error ? "Không bắt đầu được: " + r.error : "Đã gửi yêu cầu."; draw(); } }, "Bắt đầu đồng bộ"),
        busy ? h("button", { class: "btn", type: "button", onclick: async () => { await api("/api/history-sync/cancel", "POST", {}); draw(); } }, "Huỷ") : null,
        st.can_retry ? h("button", { class: "btn", type: "button", title: "Tải lại từ gói dữ liệu điện thoại đã gửi, không cần xác nhận lại", onclick: async () => { const r = await api("/api/history-sync/retry", "POST", {}); note.textContent = r.error ? "Không thử lại được: " + r.error : "Đang thử tải lại."; draw(); } }, "Thử tải lại") : null),
      st.stage === "done" ? h("div", { class: "field-row", style: "margin:.5rem 0;align-items:center" },
        h("button", { class: "btn primary", type: "button", disabled: !!(st.import_state && st.import_state.stage === "running"), onclick: async () => { const r = await api("/api/history-sync/import", "POST", {}); note.textContent = r.error ? "Không nhập được: " + r.error : "Đang nhập…"; draw(); } }, "Nhập vào khung chat"),
        st.import_state ? h("span", { class: "inote" }, st.import_state.detail) : null) : null,
      st.files && st.files.length ? h("div", {}, h("h4", {}, "Đã giải mã " + st.files.length + " tệp"), tables.map(([name, tbs]) => h("div", { class: "inote" }, name + ": " + Object.entries(tbs).map(([t, v]) => t + " (" + v.rows + " dòng)").join(", ")))) : null,
      note));
  };
  await draw();
  clearInterval(hsTimer); hsTimer = setInterval(() => { if (!document.getElementById("set-history")) { clearInterval(hsTimer); return; } draw(); }, 3000);
  return box;
}
// Dữ liệu và tự xóa: đổi là áp dụng ngay (không nút Lưu); «Dọn ngay» chạy một lượt dọn.
const RET_OPTS = {
  messages_days: ["Xóa tin nhắn cũ hơn", [[0, "Không tự xóa"], [30, "30 ngày"], [90, "90 ngày"], [180, "6 tháng"], [365, "1 năm"], [730, "2 năm"]]],
  max_per_thread: ["Mỗi cuộc trò chuyện giữ tối đa", [[0, "Không giới hạn"], [1000, "1.000 tin"], [5000, "5.000 tin"], [20000, "20.000 tin"], [50000, "50.000 tin"]]],
  files_days: ["Xóa ảnh/tệp đã tải về cũ hơn", [[0, "Không tự xóa"], [7, "7 ngày"], [30, "30 ngày"], [90, "90 ngày"]]],
  sync_days: ["Xóa dữ liệu đồng bộ đã giải mã cũ hơn", [[0, "Không tự xóa"], [1, "1 ngày"], [7, "7 ngày"], [30, "30 ngày"]]] };
async function setData() {
  const r = await api("/api/retention");
  if (r.error) return section("set-data", "Dữ liệu và tự xóa", h("p", { class: "notice bad" }, "Không đọc được: " + r.error));
  const note = h("p", { class: "inote", role: "status" }), u = r.usage || {}, cfg = r.settings || {}, sz = (n) => (n ? fmtSize(n) : "0 B");
  const rows = Object.entries(RET_OPTS).map(([key, [label, opts]]) => {
    const cur = Number(cfg[key]), list = opts.some(([v]) => v === cur) ? opts : opts.concat([[cur, "Khác (" + cur + ")"]]);
    const sel = h("select", { id: "ret-" + key, "aria-label": label }, list.map(([v, t]) => h("option", { value: String(v), selected: v === cur }, t)));
    let last = cur;
    sel.addEventListener("change", async () => {
      const want = Number(sel.value), x = await api("/api/retention", "POST", { [key]: want });
      if (x.error) { sel.value = String(last); note.textContent = "Không đổi được: " + x.error; } else { last = want; note.textContent = "Đã áp dụng: " + label + "."; }
    });
    return h("div", { class: "field-row", style: "padding:.5rem 0;border-top:1px solid var(--line);align-items:center" }, h("div", { style: "flex:1;min-width:0" }, label), sel);
  });
  const clean = h("button", { class: "btn", type: "button", onclick: async () => {
    clean.disabled = true; const x = await api("/api/retention/run", "POST", {}); clean.disabled = false;
    const rep = x.report || {}; note.textContent = x.error ? "Không dọn được: " + x.error : "Đã dọn: " + (rep.messages_deleted || 0) + " tin, " + (rep.files_deleted || 0) + " tệp, " + (rep.sync_dirs_deleted || 0) + " thư mục đồng bộ; giải phóng " + sz(rep.freed_bytes || 0) + ".";
  } }, "Dọn ngay");
  return section("set-data", "Dữ liệu và tự xóa",
    h("p", { class: "inote" }, "Đổi là áp dụng ngay. App dọn mỗi 6 giờ; tin cũ bị xóa vĩnh viễn khỏi máy chủ này (tin trên Zalo vẫn còn, chạy lại Đồng bộ lịch sử để lấy lại nếu cần)."),
    h("dl", { class: "kv" }, h("dt", {}, "Tin nhắn đang lưu"), h("dd", {}, (u.messages || 0) + " tin · " + (u.threads || 0) + " cuộc trò chuyện · " + sz(u.messages_bytes || 0)),
      h("dt", {}, "Ảnh/tệp đã tải"), h("dd", {}, sz(u.files_bytes || 0)), h("dt", {}, "Dữ liệu đồng bộ đã giải mã"), h("dd", {}, sz(u.sync_bytes || 0))),
    ...rows, h("div", { style: "margin-top:.75rem" }, clean), note);
}
async function setCalls() {
  const r = await api("/api/settings/devices"), d = (r && r.devices) || {}, v = d.video || {}, note = h("p", { class: "inote", role: "status" });
  const txt = (id, label, val, ph) => h("div", { class: "field" }, h("label", { for: id }, label), h("input", { type: "text", id, value: val || "", placeholder: ph || "", spellcheck: "false", autocomplete: "off" }));
  const num = (id, label, val, min, max, step) => h("div", { class: "field" }, h("label", { for: id }, label), h("input", { type: "number", id, value: String(val), min, max, step }));
  const chk = (id, label, val) => h("label", { class: "chk" }, h("input", { type: "checkbox", id, checked: !!val }), label);
  const fmt = h("select", { id: "dev-mic-format" }, h("option", { value: "auto", selected: (d.mic_format || "auto") === "auto" }, "Tự nhận (rtsp, http, tệp)"), h("option", { value: "s16le16k", selected: d.mic_format === "s16le16k" }, "PCM16 mono 16 kHz thô (mic loa R1)"));
  const save = async () => {
    const g = (id) => $(id), body = { mic_url: g("dev-mic-url").value.trim(), mic_format: g("dev-mic-format").value, auto_mic: g("dev-auto-mic").checked, speaker_url: g("dev-speaker-url").value.trim(), echo_guard: g("dev-echo-guard").checked,
      camera_url: g("dev-camera-url").value.trim(), auto_video_on_request: g("dev-auto-video").checked, auto_video_delay: +g("dev-auto-delay").value || 0,
      video: { width: +g("dev-width").value, height: +g("dev-height").value, fps: +g("dev-fps").value, bitrate_kbps: +g("dev-bitrate").value } };
    const res = await api("/api/settings/devices", "POST", body);
    note.textContent = res.ok ? "Đã lưu." : "Không lưu được: " + (res.error || "không rõ");
  };
  return h("div", {},
    section("set-calls", "Mic (tiếng gửi sang bên kia)",
      txt("dev-mic-url", "Nguồn mic (URL)", d.mic_url, "rtsp://… (camera/go2rtc) · http://HA:8123/api/r1_speaker/mic/…?k=… (loa R1) · test"),
      h("div", { class: "field" }, h("label", { for: "dev-mic-format" }, "Định dạng"), fmt),
      chk("dev-auto-mic", "Tự phát mic khi cuộc gọi được nghe máy", d.auto_mic)),
    section("set-speaker", "Loa (tiếng bên kia phát ra)",
      txt("dev-speaker-url", "URL bộ đàm (http/https, nhận A-law 8 kHz bằng POST)", d.speaker_url, "http://HA:8123/api/r1_speaker/intercom/…?k=… (loa R1)"),
      chk("dev-echo-guard", "Chống vọng: tạm ngừng gửi mic khi loa đang phát tiếng bên kia (dùng khi mic và loa là cùng một thiết bị)", d.echo_guard),
      h("p", { class: "inote" }, "Để trống = không dùng; loa HA bình thường vẫn do tích hợp Home Assistant điều khiển.")),
    section("set-camera", "Camera (hình gửi sang bên kia)",
      txt("dev-camera-url", "Nguồn camera (URL)", d.camera_url, "rtsp://… (go2rtc, nên dùng luồng -sub) · http(s)://… · test"),
      h("div", { class: "grid4" }, num("dev-width", "Rộng", v.width || 640, 160, 1280, 2), num("dev-height", "Cao", v.height || 360, 120, 720, 2), num("dev-fps", "Khung/giây", v.fps || 15, 5, 30, 1), num("dev-bitrate", "Kbps", v.bitrate_kbps || 300, 50, 1500, 10)),
      chk("dev-auto-video", "Bên kia xin chuyển sang video: tự đồng ý và phát camera mặc định", d.auto_video_on_request),
      num("dev-auto-delay", "Chờ trước khi tự đồng ý (giây, 0 = ngay)", d.auto_video_delay || 0, 0, 120, 1)),
    h("button", { class: "btn primary", type: "button", onclick: save }, "Lưu cài đặt cuộc gọi"), note);
}
async function setUi() {
  const cur = root.dataset.theme || "auto", sc = scalePref();
  return section("set-ui", "Giao diện",
    h("div", { class: "field" }, h("label", {}, "Chế độ màu"), h("div", { class: "seg", role: "group" }, [["auto", "Theo máy"], ["light", "Sáng"], ["dark", "Tối"]].map(([id, l]) => h("button", { type: "button", "aria-pressed": String(cur === id), onclick: () => { applyTheme(id); renderSettings("set-ui"); } }, l)))),
    h("div", { class: "field" }, h("label", {}, "Cỡ giao diện (nhớ riêng cho thiết bị này)"), h("div", { class: "seg", role: "group" }, [["auto", "Tự động"], ["90", "90%"], ["100", "100%"], ["115", "115%"], ["130", "130%"], ["160", "160%"]].map(([id, l]) => h("button", { type: "button", "aria-pressed": String(sc === id), onclick: () => { setScale(id); renderSettings("set-ui"); } }, l))),
      h("p", { style: "color:var(--muted);margin:.375rem 0 0;font-size:.8rem" }, "Tự động: tính từ độ rộng màn hình và kiểu cảm ứng/chuột (màn lớn và TV tự to hơn, điện thoại gọn hơn). Hiện " + root.style.fontSize + " · " + (root.dataset.bp === "phone" ? "bố cục điện thoại" : root.dataset.bp === "mid" ? "bố cục vừa" : "bố cục rộng"))),
    h("label", { style: "display:flex;gap:.5rem;align-items:center" }, h("input", { type: "checkbox", checked: S.sound, onchange: (e) => { S.sound = e.target.checked; try { localStorage.setItem("zalo-sound", S.sound ? "1" : "0"); } catch (x) { /* bỏ qua */ } } }), "Phát tiếng báo khi có tin mới lúc tab đang ẩn và khi có cuộc gọi đến"));
}
async function setWebhook() {
  let wh = S.webhooks; try { wh = await api("/api/webhooks"); S.webhooks = wh; } catch (e) { /* giữ */ }
  const kinds = [["message", "Tin nhắn"], ["group_event", "Sự kiện nhóm"], ["reaction", "Cảm xúc"], ["call", "Cuộc gọi"]], ins = {}, ens = {};
  return section("set-webhook", "Webhook (Home Assistant, n8n…)",
    h("p", { style: "color:var(--muted);margin:0 0 .75rem;font-size:.85rem" }, "App gửi sự kiện JSON tới các địa chỉ này. Tin nhắn có kèm tên người gửi (sender_name) và cờ người lạ (is_stranger). Tích hợp Home Assistant “Zalo Call” tự điền khi được thêm."),
    ...kinds.map(([k, label]) => {
      ins[k] = h("input", { type: "url", id: "wh-" + k, value: (wh && wh[k + "_webhook_url"]) || "", placeholder: "http://…" });
      ens[k] = h("input", { type: "checkbox", id: "wh-en-" + k, checked: !wh || wh[k + "_enabled"] !== false, "aria-label": "Bật " + label });
      return h("div", { class: "field" }, h("label", { for: "wh-" + k }, label), h("div", { class: "field-row" }, ins[k], ens[k], h("button", { class: "btn sm", type: "button", onclick: async () => { const r = await api("/api/webhooks/test", "POST", { kind: k }); toast(r.error ? "Gửi thử lỗi: " + r.error : r.ok ? "Gửi thử thành công" : "Gửi thử: " + JSON.stringify(r).slice(0, 120), 4500); } }, "Gửi thử")));
    }),
    h("button", { class: "btn primary", type: "button", onclick: async () => { const cfg = {}; for (const [k] of kinds) { cfg[k + "_webhook_url"] = ins[k].value.trim(); cfg[k + "_enabled"] = ens[k].checked; } const r = await api("/api/webhooks", "POST", cfg); toast(r.error ? "Lưu lỗi: " + r.error : "Đã lưu webhook"); } }, "Lưu webhook"));
}
async function setProxy() {
  const px = await api("/api/proxy"), pUrl = h("input", { type: "text", id: "px-url", placeholder: "http://user:mật-khẩu@địa-chỉ:cổng", autocomplete: "off" }), pName = h("input", { type: "text", id: "px-name", placeholder: "Tên gợi nhớ (không bắt buộc)" });
  const pAct = async (body, okMsg) => { const r = await api("/api/proxy", "POST", body); if (r.error) return toast(r.error, 5000); if (okMsg) toast(okMsg); renderSettings("set-proxy"); };
  return section("set-proxy", "Proxy ra Zalo",
    h("p", { style: "color:var(--muted);margin:0 0 .75rem;font-size:.85rem" }, "Chỉ áp cho kết nối HTTPS tới Zalo (nhắn tin, danh bạ, báo hiệu gọi). Tiếng cuộc gọi (UDP) không đi qua proxy HTTP. Đổi proxy là đổi địa chỉ IP ra ngoài, Zalo có thể yêu cầu xác nhận lại."),
    !px.items || !px.items.length ? h("p", { style: "margin:0 0 .75rem" }, "Chưa có proxy nào. Đang đi thẳng ra Internet.") :
      h("div", {}, px.items.map((p) => h("div", { class: "prow" }, h("div", { class: "pmain" }, h("div", { style: "font-weight:500" }, p.name || p.display, p.id === px.active ? h("span", { class: "pill ok", style: "margin-left:.5rem" }, "đang dùng") : null), h("div", { class: "mono", style: "color:var(--muted)" }, p.display + (p.has_auth ? " · có tài khoản" : ""))),
        h("button", { class: "btn sm", type: "button", onclick: async () => { const r = await api("/api/proxy", "POST", { action: "test", id: p.id }); toast(r.ok ? "Proxy thông: HTTP " + r.status + " · " + r.ms + " ms" : "Proxy lỗi: " + (r.error || "không rõ"), 5000); } }, "Thử"),
        p.id === px.active ? h("button", { class: "btn sm", type: "button", onclick: () => pAct({ action: "deactivate" }, "Đã tắt proxy") }, "Tắt") : h("button", { class: "btn sm", type: "button", onclick: () => pAct({ action: "activate", id: p.id }, "Đã bật proxy") }, "Dùng"),
        h("button", { class: "btn sm danger", type: "button", onclick: () => { if (confirm("Xoá proxy này?")) pAct({ action: "remove", id: p.id }); } }, "Xoá")))),
    h("div", { class: "field", style: "margin-top:.75rem" }, h("label", { for: "px-url" }, "Thêm proxy"), pUrl), h("div", { class: "field" }, pName),
    h("button", { class: "btn primary", type: "button", onclick: () => { if (!pUrl.value.trim()) return toast("Nhập địa chỉ proxy"); pAct({ action: "add", url: pUrl.value.trim(), name: pName.value.trim() }, "Đã thêm proxy"); } }, "Thêm"));
}
async function setSecurity() {
  const sec = await api("/api/security");
  return section("set-security", "Bảo mật",
    h("dl", { class: "kv" }, h("dt", {}, "Tài khoản app"), h("dd", {}, sec.app_user || ""), h("dt", {}, "Thiết bị đang đăng nhập"), h("dd", {}, String(sec.sessions)), h("dt", {}, "Hạn phiên"), h("dd", {}, (sec.session_hours || "?") + " giờ"),
      h("dt", {}, "Chặn dò mật khẩu"), h("dd", {}, "sai " + (sec.login_max_fails || 5) + " lần thì khoá địa chỉ 15 phút" + (sec.blocked_ips ? " · đang khoá " + sec.blocked_ips + " địa chỉ" : "")),
      h("dt", {}, "Đổi mật khẩu"), h("dd", {}, "ở mục Tài khoản")),
    h("div", { class: "field-row", style: "margin-top:.75rem;flex-wrap:wrap" },
      h("button", { class: "btn", type: "button", onclick: async () => { const r = await api("/api/security", "POST", { action: "revoke_others" }); toast("Đã đăng xuất " + (r.revoked || 0) + " thiết bị khác"); renderSettings("set-security"); } }, "Đăng xuất thiết bị khác"),
      h("button", { class: "btn", type: "button", onclick: async () => { await api("/api/security", "POST", { action: "revoke_all" }); location.href = "/login"; } }, "Đăng xuất mọi thiết bị"),
      (S.privacy && S.privacy.enabled ? h("button", { class: "btn", type: "button", onclick: async () => { await fetch("/api/privacy/lock", { method: "POST" }); location.reload(); } }, "🔒 Khoá màn hình") : null),
      h("button", { class: "btn danger", type: "button", onclick: async () => { if (confirm("Đăng xuất Zalo? Phải quét lại QR để vào lại.")) { await api("/api/zalo/logout", "POST"); S.qrClient = null; location.reload(); } } }, "Đăng xuất Zalo (xoá phiên QR)")));
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
  es.addEventListener("call", () => { loadCalls(); });
  es.addEventListener("history_imported", () => { loadConversations(); if (S.cur) loadHistory(); });
  es.addEventListener("recall", (e) => {            // tin bị thu hồi ở nơi khác (điện thoại/Zalo khác): đổi ngay thành «Tin nhắn đã được thu hồi»
    try {
      const d = JSON.parse(e.data);
      if (S.cur && S.cur.type === d.thread_type && String(S.cur.id) === String(d.thread_id)) { for (const id of d.msg_ids || []) S.recalled.add(String(id)); renderMsgs(); }
      loadConversations();
    } catch (x) { /* bỏ sự kiện hỏng */ }
  });        // cuộc gọi vừa đến/đổi trạng thái: hiện popup ngay, không chờ vòng hỏi 2 giây
  es.addEventListener("delete", (e) => {           // tin bị xóa (tự xóa hẹn giờ / xóa ở nơi khác): bỏ bong bóng ngay
    try {
      const d = JSON.parse(e.data);
      if (S.cur && S.cur.type === d.thread_type && String(S.cur.id) === String(d.thread_id)) { for (const id of d.msg_ids || []) S.deleted.add(String(id)); renderMsgs(); }
      loadConversations();
    } catch (x) { /* bỏ sự kiện hỏng */ }
  });
  es.addEventListener("names", () => { loadConversations(); });         // vừa tra được tên người lạ
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
  if (s.qr_image) { $("qr-slot").replaceChildren(h("img", { src: s.qr_image, alt: "Mã QR đăng nhập Zalo" })); st.textContent = "Mã có hiệu lực khoảng " + (s.countdown || 90) + " giây." + (s.warning ? " ⚠ " + s.warning : ""); }
  const stop = (msg) => { clearInterval(S.qrT); S.qrT = null; st.textContent = msg; $("qr-again").hidden = false; };
  if (s.state === "scanned") st.textContent = "Đã quét. Bấm xác nhận trên điện thoại…";
  else if (s.state === "done") { clearInterval(S.qrT); $("qr").hidden = true; boot(); }
  else if (s.state === "expired") stop("Mã đã hết hạn."); else if (s.state === "rejected") stop("Bạn đã từ chối trên điện thoại.");
  else if (s.state === "rate_limited") stop("Tạo mã quá nhanh, chờ " + (s.wait_seconds || 90) + " giây rồi thử lại."); else if (s.state === "error") stop("Lỗi: " + (s.error || "không rõ"));
}
function qrView(scan) { $("qr-choose").hidden = scan; $("qr-scan").hidden = !scan; }
function startQr(client) {
  $("qr").hidden = false; $("qr-again").hidden = true;
  if (client) S.qrClient = client;
  for (const b of document.querySelectorAll("#qr [data-client]")) { const on = b.dataset.client === S.qrClient; b.classList.toggle("on", on); b.setAttribute("aria-checked", on ? "true" : "false"); }
  if (!S.qrClient) { clearInterval(S.qrT); S.qrT = null; qrView(false); return; }   // chưa chọn kiểu: chỉ hiện hai thẻ, KHÔNG tự tạo mã
  qrView(true); $("qr-status").textContent = "";
  $("qr-slot").replaceChildren(h("div", { class: "qrph" }, "Đang tạo mã…"));
  api("/api/qr/new", "POST", { client: S.qrClient }).then(() => { clearInterval(S.qrT); S.qrT = setInterval(pollQr, 3000); pollQr(); });
}
function qrBack() { clearInterval(S.qrT); S.qrT = null; S.qrClient = null; startQr(); }
for (const b of document.querySelectorAll("#qr [data-client]")) b.addEventListener("click", () => startQr(b.dataset.client));

// ---- khởi động ------------------------------------------------------------------------------------------------------------------------------------
let booted = false;
function cogMenu() {
  popup($("btn-cog"), [
    { label: "Thông tin tài khoản", icon: "user", run: () => openSettings("account") },
    { label: "Cài đặt cuộc gọi và thiết bị", icon: "phone", run: () => openSettings("calls") },
    { label: "Cài đặt chung", icon: "cog", run: () => openSettings("ui") }, "-",
    { label: "Webhook, proxy, bảo mật", icon: "db", run: () => openSettings("webhook") },
    { label: "Ngôn ngữ: Tiếng Việt", icon: "globe", run: () => toast("Hiện chỉ có Tiếng Việt.") },
    { label: "Hỗ trợ", icon: "help", run: () => window.open("https://github.com/TriTue2011/Zalo-calling/issues", "_blank", "noopener") }, "-",
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
  setInterval(() => { if (!document.hidden) loadCalls(); }, 2000);
  setInterval(() => { if (S.tab === "chats") renderList(); }, 30000);   // "x phút" tự cũ đi
  setInterval(async () => { try { S.status = await api("/api/status"); S.uid = String(S.status.uid || ""); } catch (e) { /* bỏ qua */ } }, 30000);
}
async function loadContacts(force) {
  let d; try { d = await api("/api/contacts" + (force ? "?force=1" : "")); } catch (e) { return; }
  if (d.error) { S.contactsErr = "Lỗi tải danh bạ: " + d.error + (d.retry_after_seconds ? " (thử lại sau " + d.retry_after_seconds + " giây)" : ""); if (S.tab === "chats" || S.tab === "contacts") renderList(); return; }
  S.contactsErr = ""; S.contactsMeta = d;
  const rows = (x) => (x && x.rows) || [];
  S.friends = rows(d.friends).map((r) => ({ id: String(r.id), name: r.name || "", avatar: r.avatar || "", type: "user" }));
  S.groups = rows(d.groups).map((r) => ({ id: String(r.id), name: r.name || "", avatar: r.avatar || "", type: "group", members: r.members || [], member_ids: r.member_ids || [] }));
  if (S.cur) { const again = rowOf(S.cur.type, S.cur.id); if (again) S.cur = again; }
  renderList(); if (S.tab === "contacts") renderContactsPage();
  if (d.stale) setTimeout(() => loadContacts(false), 3000);
}

document.querySelectorAll(".rail-btn[data-tab]").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
$("me-btn").addEventListener("click", () => openSettings("account"));
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
for (const id of ["file-in", "img-in"]) $(id).addEventListener("change", (e) => { const f = [...e.target.files]; e.target.value = ""; if (f.length) stageFiles(f); });
$("btn-sticker").addEventListener("click", toggleStickers); $("btn-rec").addEventListener("click", toggleRecord); $("btn-emoji").addEventListener("click", toggleEmoji); $("qr-again").addEventListener("click", () => startQr()); $("qr-back").addEventListener("click", qrBack);
{ const comp = $("composer"); comp.insertBefore(h("div", { class: "attach-tray", id: "attach-tray", hidden: true }), comp.firstChild); comp.insertBefore(h("div", { class: "replybar", id: "reply-bar", hidden: true }), comp.firstChild); document.querySelector(".cinput").append(h("div", { class: "mentions", id: "mentions", role: "listbox", hidden: true })); }
$("msg-in").addEventListener("input", autosize);
for (const ev of ["input", "click", "keyup"]) $("msg-in").addEventListener(ev, updateMentions);
$("msg-in").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendText(); } });
$("msg-in").addEventListener("paste", (e) => { const f = [...(e.clipboardData ? e.clipboardData.files : [])]; if (f.length) { e.preventDefault(); stageFiles(f); } });
document.addEventListener("click", (e) => { const st = $("stickers"); if (!st.hidden && !st.contains(e.target) && !e.target.closest("#btn-sticker")) st.hidden = true; });
document.addEventListener("click", (e) => { const em = $("emoji"); if (!em.hidden && !em.contains(e.target) && !e.target.closest("#btn-emoji")) em.hidden = true; });
const mp = $("mainpane"); let dragN = 0; const dz = h("div", { class: "dropzone", hidden: true }, "Thả tệp để gửi"); mp.append(dz);
mp.addEventListener("dragenter", (e) => { if (S.cur && S.tab === "chats" && e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { dragN++; dz.hidden = false; } });
mp.addEventListener("dragleave", () => { dragN = Math.max(0, dragN - 1); if (!dragN) dz.hidden = true; });
mp.addEventListener("dragover", (e) => { if (S.cur) e.preventDefault(); });
mp.addEventListener("drop", (e) => { e.preventDefault(); dragN = 0; dz.hidden = true; if (S.cur && e.dataTransfer.files.length) stageFiles(e.dataTransfer.files); });
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $("q").focus(); }
  if (e.key === "Escape" && document.activeElement === $("q")) { $("q").value = ""; S.q = ""; renderList(); $("q").blur(); }
});
try { applyTheme(localStorage.getItem("zalo-theme") || "auto"); S.sound = localStorage.getItem("zalo-sound") !== "0"; S.info = localStorage.getItem("zalo-info") !== "0"; } catch (e) { /* mặc định */ }
if (typeof window.__ZALO_TEST_HOOK__ === "function") window.__ZALO_TEST_HOOK__({ S, bubbleBody, renderMsgs, openMsgMenu, msgMenuItems, canReply, loadReactions, enterSelect, exitSelect, normMsg, sendFiles, mediaToggles, changeGain, mergeMsgs, startCall, openThread, videoView, showVideoWin, renderCallCard });   // chỉ để kiểm thử giao diện (jsdom)
applyScale(); setTab("chats"); updateSendButtons(); privacyInit(); boot();
})();
