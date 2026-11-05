// App UI logic: login view -> main view (contacts + calls rail) ->
// calls view (full history) -> call detail view.
// The page never sees session secrets; it only gets states + rows.
// Contacts are threads (addon model): a row's id IS the threadId
// (userId for a friend, groupId for a group); calls go by threadID.
const $ = (id) => document.getElementById(id);
let contacts = { friends: { rows: [] }, groups: { rows: [] } };
let callsData = { calls: [], active: null };
let currentFilter = "all";
let currentCall = null;
let detailCall = null; // the call shown in the detail view (may be
// an active call reloaded from /api/calls, not started here)
let pollTimer = null;
let callsTimer = null;
let clockTimer = null;

// -- views ---------------------------------------------------------------
const VIEWS = ["view-login", "view-main", "view-calls", "view-call"];
function show(view) {
  VIEWS.forEach((v) => { $(v).style.display = (v === view ? "" : "none"); });
  // No contacts to search before login — hide the search box there.
  $("search").style.display = (view === "view-login" ? "none" : "");
  $("nav-contacts").className =
    "nav-item" + ((view === "view-main" || view === "view-call") ? " on" : "");
  $("nav-calls").className =
    "nav-item" + (view === "view-calls" ? " on" : "");
  closeMenu();
}

async function api(path, method, body) {
  const r = await fetch(path, {
    method: method || "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}

// -- helpers ---------------------------------------------------------------
const TINTS = ["t0", "t1", "t2", "t3", "t4", "t5"];
function initials(name, id) {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return String(id || "?").slice(0, 2).toUpperCase();
}
function tintFor(id) {
  let h = 0;
  const s = String(id || "");
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return TINTS[h % TINTS.length];
}
function fmtTime(epochSec) {
  return new Date(epochSec * 1000).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}
function fmtElapsed(epochSec) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - epochSec));
  const m = Math.floor(s / 60);
  return String(m).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}
function statusPill(status) {
  if (status === "sent") return ["pill pill-accent", "Đang đổ chuông"];
  if (status === "error") return ["pill pill-negative", "Lỗi"];
  return ["pill pill-neutral", "Đã kết thúc"];
}
function typePill(type) {
  return type === "group" ? "Nhóm" : "Cá nhân";
}

// -- contacts list -----------------------------------------------------------
function allRows() {
  const f = (contacts.friends.rows || []).map((r) => ({ ...r, type: "user" }));
  const g = (contacts.groups.rows || []).map((r) => ({ ...r, type: "group" }));
  return { f, g, all: f.concat(g) };
}
function renderList() {
  const { f, g, all } = allRows();
  $("count-all").textContent = all.length;
  $("count-friends").textContent = f.length;
  $("count-groups").textContent = g.length;
  const rows = currentFilter === "friends" ? f
    : currentFilter === "groups" ? g : all;
  const q = $("search").value.trim().toLowerCase();
  const shown = rows.filter((r) =>
    !q || (r.name || "").toLowerCase().includes(q)
    || String(r.id || "").toLowerCase().includes(q));
  const ul = $("list");
  ul.innerHTML = "";
  shown.forEach((r) => {
    const li = document.createElement("li");
    const av = document.createElement("span");
    av.className = "avatar " + tintFor(r.id);
    av.textContent = initials(r.name, r.id);
    const main = document.createElement("div");
    main.className = "row-main";
    const name = document.createElement("div");
    name.className = "row-name";
    name.textContent = r.name || r.id;
    const sub = document.createElement("div");
    sub.className = "row-sub";
    const tid = document.createElement("span");
    tid.className = "mono";
    tid.textContent = r.id;
    sub.appendChild(document.createTextNode(typePill(r.type) + " · "));
    sub.appendChild(tid);
    if (r.type === "group" && r.members) {
      sub.appendChild(document.createTextNode(" · " + r.members.length + " thành viên"));
    }
    main.appendChild(name);
    main.appendChild(sub);
    const pill = document.createElement("span");
    pill.className = "pill " + (r.type === "group" ? "pill-accent" : "pill-neutral");
    pill.textContent = typePill(r.type);
    const call = document.createElement("button");
    call.type = "button";
    call.className = "btn btn-secondary row-call";
    call.textContent = "Gọi";
    call.onclick = (e) => { e.stopPropagation(); startCall(r); };
    li.appendChild(av);
    li.appendChild(main);
    li.appendChild(pill);
    li.appendChild(call);
    li.onclick = () => startCall(r);
    ul.appendChild(li);
  });
  const empty = $("list-empty");
  if (shown.length === 0) {
    empty.hidden = false;
    empty.textContent = q
      ? "Không tìm thấy tên hoặc threadID này."
      : currentFilter === "friends" ? "Chưa có bạn bè nào."
      : currentFilter === "groups" ? "Chưa có nhóm nào."
      : "Chưa có bạn bè hay nhóm nào.";
  } else {
    empty.hidden = true;
  }
}

async function loadMain() {
  const st = await api("/api/status");
  $("who").textContent = st.login
    ? ("Đã đăng nhập: " + (st.phonenum || st.uid)) : "Chưa đăng nhập";
  // Version marker: shows which image/commit the server is really
  // running, so a redeploy can be verified at a glance.
  if (st.version) $("app-version").textContent = "Phiên bản: " + st.version;
  $("engine-note").textContent = st.engine && st.engine.detail
    ? ("Tiếng: " + st.engine.detail) : "";
  if (!st.login) { show("view-login"); stopCallsTimers(); return; }
  const data = await api("/api/contacts");
  const err = $("contacts-error");
  if (data.error) {
    err.hidden = false;
    $("contacts-error-text").textContent = "Lỗi tải danh bạ: " + data.error;
  } else {
    err.hidden = true;
    contacts = data;
  }
  renderList();
  await loadCalls();
  startCallsTimers();
  show("view-main");
}

// -- calls: active + history ----------------------------------------------
function renderCalls() {
  const q = $("search").value.trim().toLowerCase();
  const active = callsData.active;
  // Nav dot + top-bar pill follow the live call.
  $("nav-call-dot").hidden = !active;
  const pill = $("topbar-call");
  if (active) {
    pill.hidden = false;
    pill.textContent = "Đang đổ chuông: " + (active.peer || active.thread_id);
  } else {
    pill.hidden = true;
  }
  // Rail: active card + recent 5.
  const railActive = $("rail-active");
  railActive.innerHTML = "";
  if (active) railActive.appendChild(activeCard(active));
  const shown = callsData.calls.filter((c) =>
    !q || (c.peer || "").toLowerCase().includes(q)
    || String(c.thread_id || "").toLowerCase().includes(q));
  const feed = $("rail-history");
  feed.innerHTML = "";
  shown.slice(0, 5).forEach((c) => feed.appendChild(feedRow(c)));
  $("rail-empty").hidden = shown.length !== 0;
  $("rail-view-all").style.display = shown.length > 5 ? "" : "none";
  // Full view: whole history as a table.
  const tb = $("calls-history");
  tb.innerHTML = "";
  shown.forEach((c) => tb.appendChild(historyRow(c)));
  $("calls-empty").hidden = shown.length !== 0;
  // Active card on the full view too.
  const full = $("calls-active");
  full.innerHTML = "";
  if (active) full.appendChild(activeCard(active));
}

function activeCard(c) {
  const div = document.createElement("div");
  div.className = "call-card";
  const peer = document.createElement("div");
  peer.className = "call-peer";
  peer.textContent = c.peer || c.thread_id;
  const meta = document.createElement("div");
  meta.className = "call-meta";
  const tid = document.createElement("span");
  tid.className = "mono";
  tid.textContent = c.thread_id;
  meta.appendChild(document.createTextNode(typePill(c.type) + " · "));
  meta.appendChild(tid);
  const row = document.createElement("div");
  row.className = "call-status-row";
  const pill = document.createElement("span");
  const [cls, label] = statusPill(c.status);
  pill.className = cls;
  pill.textContent = label;
  const timer = document.createElement("span");
  timer.className = "num";
  timer.dataset.timer = c.started_at;
  timer.textContent = fmtElapsed(c.started_at);
  row.appendChild(pill);
  row.appendChild(timer);
  const actions = document.createElement("div");
  actions.className = "call-actions";
  const end = document.createElement("button");
  end.type = "button";
  end.className = "btn btn-secondary";
  end.textContent = "Kết thúc";
  end.onclick = () => endCall();
  const open = document.createElement("button");
  open.type = "button";
  open.className = "btn btn-text";
  open.textContent = "Xem chi tiết";
  open.onclick = () => showCallDetail(c);
  actions.appendChild(end);
  actions.appendChild(open);
  div.appendChild(peer);
  div.appendChild(meta);
  div.appendChild(row);
  div.appendChild(actions);
  return div;
}

function feedRow(c) {
  const li = document.createElement("li");
  const main = document.createElement("div");
  main.className = "feed-main";
  const name = document.createElement("div");
  name.className = "feed-name";
  name.textContent = c.peer || c.thread_id;
  const sub = document.createElement("div");
  sub.className = "feed-sub";
  sub.textContent = fmtTime(c.started_at) + " · " + typePill(c.type);
  main.appendChild(name);
  main.appendChild(sub);
  const pill = document.createElement("span");
  const [cls, label] = statusPill(c.status);
  pill.className = cls;
  pill.textContent = label;
  if (c.status === "error" && c.detail) pill.title = c.detail;
  li.appendChild(main);
  li.appendChild(pill);
  return li;
}

function historyRow(c) {
  const tr = document.createElement("tr");
  const tdTime = document.createElement("td");
  tdTime.className = "num";
  tdTime.textContent = fmtTime(c.started_at);
  const tdPeer = document.createElement("td");
  tdPeer.textContent = c.peer || c.thread_id;
  const tdTid = document.createElement("td");
  const tid = document.createElement("span");
  tid.className = "mono";
  tid.textContent = c.thread_id;
  tdTid.appendChild(tid);
  const tdType = document.createElement("td");
  tdType.textContent = typePill(c.type);
  const tdRes = document.createElement("td");
  const pill = document.createElement("span");
  const [cls, label] = statusPill(c.status);
  pill.className = cls;
  pill.textContent = label;
  tdRes.appendChild(pill);
  if (c.status === "error" && c.detail) {
    const d = document.createElement("div");
    d.className = "row-sub";
    d.textContent = c.detail;
    tdRes.appendChild(d);
  }
  tr.appendChild(tdTime);
  tr.appendChild(tdPeer);
  tr.appendChild(tdTid);
  tr.appendChild(tdType);
  tr.appendChild(tdRes);
  return tr;
}

async function loadCalls() {
  try {
    callsData = await api("/api/calls");
  } catch (e) { /* keep the last good data; the rail stays as-is */ }
  renderCalls();
}

function startCallsTimers() {
  if (!callsTimer) callsTimer = setInterval(loadCalls, 5000);
  if (!clockTimer) {
    clockTimer = setInterval(() => {
      document.querySelectorAll("[data-timer]").forEach((el) => {
        el.textContent = fmtElapsed(parseFloat(el.dataset.timer));
      });
      const t = $("call-timer");
      if (currentCall) t.textContent = fmtElapsed(currentCall.started_at);
    }, 1000);
  }
}
function stopCallsTimers() {
  if (callsTimer) { clearInterval(callsTimer); callsTimer = null; }
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null; }
}

// -- QR flow ---------------------------------------------------------------
async function pollQr() {
  const s = await api("/api/qr/status");
  const st = $("qr-status");
  if (s.qr_image) {
    $("qr-img").src = s.qr_image;
    $("qr-img").style.display = "";
    $("qr-wait").style.display = "none";
    st.textContent = "Mã có hiệu lực khoảng " + (s.countdown || 90) + " giây. Quét bằng app Zalo.";
  }
  if (s.state === "scanned") st.textContent = "Đã quét. Chờ bạn bấm xác nhận trên điện thoại...";
  if (s.state === "done") { clearInterval(pollTimer); loadMain(); return; }
  if (s.state === "expired") { st.textContent = "Mã đã hết hạn. Lấy mã mới."; $("btn-qr-again").style.display = ""; clearInterval(pollTimer); }
  if (s.state === "rejected") { st.textContent = "Bạn đã từ chối trên điện thoại. Lấy mã mới để thử lại."; $("btn-qr-again").style.display = ""; clearInterval(pollTimer); }
  if (s.state === "rate_limited") { st.textContent = "Tạo mã quá nhanh, chờ " + (s.wait_seconds || 90) + " giây rồi thử lại."; clearInterval(pollTimer); }
  if (s.state === "error") { st.textContent = "Lỗi: " + (s.error || "?"); clearInterval(pollTimer); }
}

function startQr() {
  $("btn-qr-again").style.display = "none";
  api("/api/qr/new", "POST").then(() => {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollQr, 3000);
    pollQr();
  });
}

// -- calling ---------------------------------------------------------------
function showCallDetail(c) {
  // c is a call record ({peer, thread_id, type, started_at, call_id})
  // or a contact row ({name, id, type}).
  const peer = c.peer || c.name || c.thread_id || c.id;
  const threadId = c.thread_id || c.id;
  const type = c.type || "user";
  $("call-peer").textContent = peer;
  $("call-type").textContent = typePill(type);
  $("call-thread").textContent = threadId;
  $("call-timer").textContent =
    fmtElapsed(c.started_at || (currentCall && currentCall.started_at) || Date.now() / 1000);
  detailCall = { peer: { id: threadId }, callId: c.call_id || (currentCall && currentCall.callId) || "",
                 started_at: c.started_at || (currentCall && currentCall.started_at) };
  show("view-call");
}

async function startCall(peer) {
  // callId must be a JSON NUMBER in uint32 range (the native engine
  // stores it as %u) — epoch seconds. The old code sent
  // String(Date.now()): a 13-digit string, wrong type AND out of
  // uint32 range, one of the two 114 suspects (§7k). The server
  // normalizes again and returns the effective id, which we adopt
  // so /api/call/end carries the same callId the requestcall used.
  const callId = Math.floor(Date.now() / 1000);
  currentCall = { peer, callId, started_at: Date.now() / 1000 };
  detailCall = currentCall;
  $("call-peer").textContent = peer.name || peer.id;
  $("call-type").textContent = typePill(peer.type || "user");
  $("call-thread").textContent = peer.id;
  $("call-state").textContent = "Đang gửi yêu cầu gọi...";
  show("view-call");
  // Calls are addressed by threadID (addon model): the row's id IS
  // the threadId (userId for a friend, groupId for a group), and
  // the tab decides which endpoint the server uses (1-1 requestcall
  // vs group/requestcall). For a group, `partners` is the member
  // list loaded with the contacts (getmg-v2 topMember) — the server
  // rings those userIds.
  // type_request follows the real client's makeCall enum
  // (1-1 audio=1, group audio=5); 0 is not a valid call type and
  // drew inner 114 from the real server (§7k). The server derives
  // the same value from `type` and does not trust this field, but
  // the request is sent self-consistent anyway.
  const r = await api("/api/call/request", "POST",
    { callee_id: peer.id, call_id: callId,
      type_request: peer.type === "group" ? 5 : 1,
      type: peer.type === "group" ? "group" : "user",
      peer_name: peer.name || peer.id,
      partners: peer.members || [] });
  if (r.call_id != null) {
    currentCall.callId = r.call_id;
    detailCall = currentCall;
  }
  $("call-state").textContent = r.error
    ? ("Lỗi gọi: " + r.error)
    : "Đã gửi yêu cầu gọi. Bên kia đang đổ chuông — tiếng sẽ có khi engine giai đoạn 2 gắn vào.";
  await loadCalls();
}

async function endCall() {
  const cc = currentCall || detailCall;
  if (cc) {
    await api("/api/call/end", "POST",
      { uid_to: (cc.peer && cc.peer.id) || "", call_id: cc.callId || "" });
    currentCall = null;
    detailCall = null;
  }
  await loadCalls();
  loadMain();
}

// -- menu (phones/tablets) -------------------------------------------------
function closeMenu() {
  $("sidebar").classList.remove("open");
  $("btn-menu").setAttribute("aria-expanded", "false");
}

// -- wiring ---------------------------------------------------------------
$("btn-qr").onclick = startQr;
$("btn-qr-again").onclick = startQr;
$("btn-logout").onclick = () => api("/api/logout", "POST").then(loadMain);
$("btn-end").onclick = endCall;
$("btn-back").onclick = loadMain;
$("btn-retry-contacts").onclick = loadMain;
$("search").oninput = () => { renderList(); renderCalls(); };
$("rail-view-all").onclick = () => { show("view-calls"); };
$("topbar-call").onclick = () => {
  if (callsData.active) showCallDetail(callsData.active);
  else show("view-calls");
};
$("nav-contacts").onclick = () => { show("view-main"); loadMain(); };
$("nav-calls").onclick = async () => { await loadCalls(); show("view-calls"); };
$("btn-menu").onclick = () => {
  const open = $("sidebar").classList.toggle("open");
  $("btn-menu").setAttribute("aria-expanded", String(open));
};
function setFilter(f) {
  currentFilter = f;
  ["all", "friends", "groups"].forEach((k) => {
    $("filter-" + k).className =
      "count-card" + (k === f ? " on" : "");
  });
  renderList();
}
$("filter-all").onclick = () => setFilter("all");
$("filter-friends").onclick = () => setFilter("friends");
$("filter-groups").onclick = () => setFilter("groups");

loadMain();
