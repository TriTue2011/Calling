// App UI logic: login view -> main view (contacts + calls rail) ->
// calls view (full history) -> call detail view -> services view.
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
let ending = false; // an End request is in flight — ignore taps.
let currentThread = null; // the thread open in the chat view
// ({id, name, type, members}); row click opens chat, the "Goi"
// button still starts a call (startCall, unchanged).
let mediaRecorder = null;
let recChunks = [];
let recTimer = null;
let lastTypingAt = 0;
let pollTimer = null;
let callsTimer = null;
let clockTimer = null;
let svcCatalog = null; // /api/svc/catalog, loaded on first open
let svcThread = null; // {id, type, name} — thread the service panel acts on

// Contacts cache/429 state (mirror of server CONTACTS_TTL_SECONDS):
// the server caches contacts for 120s and backs off 60s after a 429.
// The reload button stays disabled until contactsBackoffUntil, and
// the meta line under "Danh bạ" shows cache/429 state + countdown.
const CONTACTS_TTL_SECONDS = 120;
let contactsBackoffUntil = 0;
let lastContactsMeta = null;
// Stale-while-revalidate follow-up (sửa lỗi load chậm 2026-11-05):
// khi /api/contacts trả cache cũ (stale=true), UI hiện danh bạ
// cũ ngay rồi hẹn loadMain() lại sau 3 giây để lấy dữ liệu mới
// mà lần làm mới nền vừa ghi vào cache. Timer bị hủy mỗi lần
// loadMain() chạy lại / đăng xuất, để không load chồng nhau.
let staleRefreshTimer = null;
function clearStaleRefresh() {
  if (staleRefreshTimer) {
    clearTimeout(staleRefreshTimer);
    staleRefreshTimer = null;
  }
}
function scheduleStaleRefresh() {
  clearStaleRefresh();
  staleRefreshTimer = setTimeout(() => {
    staleRefreshTimer = null;
    loadMain();
  }, 3000);
}

// -- views ---------------------------------------------------------------
// View quyết định theo phiên, KHÔNG theo mặc định lúc tải trang:
// lúc tải chỉ có view-loading (trung tính) hiện; view-login chỉ
// hiện khi /api/status chứng minh là chưa đăng nhập, view-main
// chỉ hiện khi đã đăng nhập (xem loadMain). Trước sửa này,
// view-login hiện sẵn trong HTML rồi loadMain mới đổi view sau
// khi await /api/status — nên mỗi lần làm mới trang đều nháy
// trang QR dù phiên vẫn còn (lỗi 2026-11-05).
const VIEWS = ["view-loading", "view-login", "view-main", "view-calls", "view-call",
               "view-chat", "view-webhooks", "view-services"];
function show(view) {
  VIEWS.forEach((v) => { $(v).style.display = (v === view ? "" : "none"); });
  // No contacts to search before login — hide the search box there.
  $("search").style.display =
    (view === "view-login" || view === "view-loading" ? "none" : "");
  $("nav-contacts").className =
    "nav-item" + ((view === "view-main" || view === "view-call" || view === "view-chat") ? " on" : "");
  $("nav-calls").className =
    "nav-item" + (view === "view-calls" ? " on" : "");
  $("nav-webhooks").className =
    "nav-item" + (view === "view-webhooks" ? " on" : "");
  $("nav-services").className =
    "nav-item" + (view === "view-services" ? " on" : "");
  closeMenu();
}

async function api(path, method, body) {
  const r = await fetch(path, {
    method: method || "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  // Het phien dang nhap app (hoac chua dang nhap): ve trang dang nhap.
  // Trang /login la cong ngoai; QR Zalo nam sau no.
  if (r.status === 401) {
    window.location.href = "/login";
    throw new Error("chua_dang_nhap_app");
  }
  return r.json();
}

// POST multipart (file/photo/voice): FormData, no JSON header.
// Timeout bat buoc: fetch mac dinh KHONG co timeout — neu may chu
// treo (khong tra loi), UI ket o "Dang gui..." mai ma khong bao
// loi (loi cam 07/11). Mac dinh 90 giay > timeout Zalo 60 giay
// cua server + du phong; voice duoc goi voi timeout dai hon vi
// server doi sang AAC truoc khi gui.
let API_FORM_TIMEOUT_MS = 90000;
async function apiForm(path, form, timeoutMs = API_FORM_TIMEOUT_MS) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(path, { method: "POST", body: form, signal: ctrl.signal });
    return r.json();
  } catch (e) {
    if (e && e.name === "AbortError") {
      throw new Error("hết thời gian chờ " + Math.round(timeoutMs / 1000)
        + " giây — máy chủ không trả lời, file chưa chắc đã gửi");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

// Giai ma anh de lay width/height co gioi han thoi gian: neu
// trinh duyet kẹt khong goi onload/onerror, promise cu treo mai
// (loi cam 07/11) — qua 5 giay thi gui voi 0x0 thay vi ket o
// "Dang gui..." khong bao loi.
let IMAGE_DIMS_TIMEOUT_MS = 5000;

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
function statusPill(status, requestSent) {
  // "sent" means step 1 (11300) went out, NOT that the peer is
  // ringing: the peer only rings once step 2 (11301) is sent,
  // and request_sent records exactly that. Showing "Đang đổ
  // chuông" for a call whose step 2 never left lied to the
  // user (live 07/11: step 2 stuck, chip still said ringing).
  // requestSent === true -> ringing; === false -> step 2 failed
  // (the call is still live until ended, but the attempt failed);
  // null/undefined -> step 2 not attempted yet.
  if (status === "sent") {
    if (requestSent === true) return ["pill pill-accent", "Đang đổ chuông"];
    if (requestSent === false) return ["pill pill-negative", "Lỗi"];
    return ["pill pill-neutral", "Đang gọi"];
  }
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
    li.dataset.threadId = r.id;
    li.dataset.threadType = r.type;
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
    if (r.type === "group") {
      // Số thành viên HIỂN THỊ lấy từ r.member_count (totalMember /
      // memberIds / currentMems phía server) — KHÔNG đếm
      // r.members.length: members chỉ là topMember (danh sách hiển
      // thị, có thể rỗng dù nhóm đông) và chỉ dùng cho partners khi
      // gọi nhóm. Trước sửa này mọi nhóm đều hiện "0 thành viên".
      const n = (typeof r.member_count === "number")
        ? r.member_count : (r.members ? r.members.length : 0);
      sub.appendChild(document.createTextNode(" · " + n + " thành viên"));
    }
    main.appendChild(name);
    main.appendChild(sub);
    // Tin den tu kenh sync: xem truoc tin moi nhat + huy hieu so
    // tin chua doc (xem refreshInboxSummary). Khong co tin den thi
    // hang trong nhu cu.
    const info = inboxSummary[r.id + "|" + r.type];
    if (info && info.last && info.last.text) {
      const last = document.createElement("div");
      last.className = "row-last";
      const who = info.last.sender_name || info.last.sender_id || "";
      last.textContent = (who ? who + ": " : "")
        + info.last.text
        + (info.last.time ? " · " + fmtTime(info.last.time) : "");
      main.appendChild(last);
    }
    let badgeEl = null;
    if (info && info.unread > 0) {
      badgeEl = document.createElement("span");
      badgeEl.className = "unread-badge";
      badgeEl.textContent = info.unread > 99 ? "99+" : String(info.unread);
      badgeEl.title = info.unread + " tin chưa đọc";
    }
    const pill = document.createElement("span");
    pill.className = "pill " + (r.type === "group" ? "pill-accent" : "pill-neutral");
    pill.textContent = typePill(r.type);
    const call = document.createElement("button");
    call.type = "button";
    call.className = "btn btn-secondary row-call";
    call.textContent = "Gọi";
    call.onclick = (e) => { e.stopPropagation(); startCall(r); };
    const svc = document.createElement("button");
    svc.type = "button";
    svc.className = "btn btn-text row-svc";
    svc.textContent = "Dịch vụ";
    svc.title = "Mở panel Dịch vụ cho thread này";
    svc.onclick = (e) => { e.stopPropagation(); openServices(r); };
    li.appendChild(av);
    li.appendChild(main);
    if (badgeEl) li.appendChild(badgeEl);
    li.appendChild(pill);
    li.appendChild(svc);
    li.appendChild(call);
    // Row tap opens the thread's chat (Zalo PC style); the "Goi"
    // button beside it still starts a call by threadID.
    li.onclick = () => openThread(r);
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

// -- tin den (kenh sync) ------------------------------------------------
// Map "threadId|type" -> {unread, last} tu /api/inbox/summary; renderList
// dung de gan huy hieu + xem truoc tin moi nhat o thread list. Chi
// goi API nay (khong goi Zalo): tin den do server day vao Inbox qua
// kenh sync long-poll 99100 (xem sync_poll.py). Timer 15 giay, chi
// ve lai list khi summary that su doi (tranh nhap nhay khi cuon/tim).
let inboxSummary = {};
let inboxSummaryJson = "";
let inboxTimer = null;
async function refreshInboxSummary() {
  try {
    const data = await api("/api/inbox/summary");
    const map = {};
    (data.threads || []).forEach((t) => {
      map[t.thread_id + "|" + t.type] = t;
    });
    const json = JSON.stringify(map);
    if (json === inboxSummaryJson) return;
    inboxSummary = map;
    inboxSummaryJson = json;
    renderList();
  } catch (e) { /* lan sau thu lai; list cu van dung duoc */ }
}
function startInboxTimer() {
  if (!inboxTimer) {
    inboxTimer = setInterval(refreshInboxSummary, 15000);
    refreshInboxSummary();
  }
}

// -- trang thai kenh sync o chan khung chat ---------------------------
// Truoc day dong chu o chan khung chat la text tinh trong app.html
// ("kenh nhan tin (sync) chua co") — hien mai du poller co dang
// chay that hay khong, vi khong co dong JS nao doc st.sync tu
// /api/status. Tu nay updateSyncNote() ve lai dong chu theo dung
// trang thai that tra ve tu server (xem AppState.sync_status):
// chi "no_endpoints" that (server khong cap endpoint) moi bao
// quet QR lai; "refresh_failed" thi bao thu ket noi lai truoc.
function syncNoteText(sync) {
  if (sync === "running") {
    return { text: "Tin nhắn đến tự cập nhật qua kênh sync (đang chạy) — tin mới sẽ tự hiện trong khung chat.",
             showRetry: false };
  }
  if (sync === "no_endpoints") {
    return { text: "Tin nhắn đến chưa tự cập nhật — máy chủ chưa cấp kênh nhận tin (sync) cho phiên này. Bấm “Thử kết nối lại” để lấy lại kênh; nếu vẫn không được, đăng xuất rồi quét QR lại một lần.",
             showRetry: true };
  }
  if (sync === "refresh_failed") {
    return { text: "Tin nhắn đến chưa tự cập nhật — không lấy được kênh sync từ Zalo (lỗi làm mới phiên). Bấm “Thử kết nối lại”; nếu vẫn không được, đăng xuất rồi quét QR lại một lần.",
             showRetry: true };
  }
  if (sync === "kicked_out") {
    return { text: "Kênh nhận tin (sync) đã bị Zalo dừng — cần đăng nhập lại (quét QR) để nhận tin đến.",
             showRetry: false };
  }
  if (sync === "stopped") {
    return { text: "Kênh nhận tin (sync) đang dừng — bấm “Thử kết nối lại” để mở lại.",
             showRetry: true };
  }
  if (sync === "logged_out") {
    return { text: "Chưa đăng nhập nên chưa có kênh nhận tin.",
             showRetry: false };
  }
  return { text: "Chưa rõ trạng thái kênh nhận tin — bấm “Tải lại lịch sử” để xem lịch sử nhóm mới nhất.",
           showRetry: false };
}
function updateSyncNote(sync) {
  const note = syncNoteText(sync);
  const el = $("chat-sync-note");
  if (el) el.textContent = note.text;
  const btn = $("btn-sync-retry");
  if (btn) btn.hidden = !note.showRetry;
}
let syncRetrying = false;
async function retrySync() {
  if (syncRetrying) return;
  syncRetrying = true;
  const btn = $("btn-sync-retry");
  if (btn) btn.disabled = true;
  try {
    const r = await api("/api/sync/retry", "POST", {});
    updateSyncNote(r.sync);
    if (!r.ok && r.retry_after_seconds) {
      const n = $("chat-notice");
      n.hidden = false;
      n.textContent = "Vừa thử kết nối lại — thử lại sau "
        + r.retry_after_seconds + " giây.";
    }
  } catch (e) {
    const n = $("chat-notice");
    n.hidden = false;
    n.textContent = "Không kết nối lại được: lỗi mạng.";
  }
  if (btn) btn.disabled = false;
  syncRetrying = false;
}

function fmtClock(epochSec) {
  return new Date(epochSec * 1000).toLocaleTimeString("vi-VN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}
// How many seconds of server backoff are left (0 when none).
function backoffLeft() {
  return Math.max(0, Math.ceil((contactsBackoffUntil - Date.now()) / 1000));
}
function setContactsBackoff(seconds) {
  if (seconds > 0) {
    contactsBackoffUntil = Date.now() + seconds * 1000;
  }
  updateReloadButton();
}
// The reload button respects the server backoff: while it lasts the
// button is disabled and counts down — tapping it again would only
// hammer Zalo harder (that is how the 7x burst happened). The retry
// button in the error box follows the same rule.
function updateReloadButton() {
  const left = backoffLeft();
  const reload = $("btn-reload-contacts");
  if (reload) {
    reload.disabled = left > 0;
    reload.textContent = left > 0 ? ("Tải lại (" + left + " giây)") : "Tải lại";
  }
  const retry = $("btn-retry-contacts");
  if (retry) {
    retry.disabled = left > 0;
    retry.textContent = left > 0 ? ("Tải lại (" + left + " giây)") : "Tải lại";
  }
}
// Meta line under "Danh bạ": fresh / cached / 429 state, in plain
// Vietnamese. The 429 countdown ticks via the 1s clock timer.
function updateContactsMeta(data) {
  if (data) lastContactsMeta = data;
  const el = $("contacts-meta");
  if (!el) return;
  const d = lastContactsMeta;
  if (!d || d.fetched_at === undefined) { el.textContent = ""; el.className = "contacts-meta"; return; }
  const when = fmtClock(d.fetched_at);
  const left = backoffLeft();
  // rate_limited alone is stale history once the wait has passed —
  // only a live countdown (left > 0) keeps the warning up.
  if (left > 0) {
    el.textContent = "Zalo đang giới hạn (429) — đang hiển thị danh bạ đã lưu lúc "
      + when + ", thử lại sau " + Math.max(left, d.retry_after_seconds || 0) + " giây.";
    el.className = "contacts-meta warn";
    return;
  }
  if (d.source === "cache-after-429") {
    el.textContent = "Danh bạ đã lưu lúc " + when + " (Zalo vừa giới hạn, đã qua cơn).";
    el.className = "contacts-meta";
    return;
  }
  if (d.stale) {
    // Cache cũ đã hết TTL, vừa trả ngay trong lúc chờ làm mới nền:
    // hiện rõ là đang tải bản mới (loadMain sẽ tự tải lại sau
    // 3 giây để lấy dữ liệu mới).
    el.textContent = "Danh bạ đã lưu lúc " + when + " — đang tải bản mới…";
    el.className = "contacts-meta";
    return;
  }
  if (d.source === "cache") {
    const freshIn = Math.max(0, CONTACTS_TTL_SECONDS - (d.age_seconds || 0));
    el.textContent = "Danh bạ đã lưu lúc " + when + " — sẽ tải mới sau "
      + freshIn + " giây (bấm “Tải lại” để lấy mới ngay).";
    el.className = "contacts-meta";
    return;
  }
  el.textContent = "Vừa cập nhật lúc " + when + ".";
  el.className = "contacts-meta";
}

async function loadMain(force) {
  clearStaleRefresh();
  // Quyết định view theo phiên TRƯỚC khi vẽ view chính: chỉ khi
  // /api/status trả về mới biết đã đăng nhập hay chưa. Trong lúc
  // chờ, view-loading (trung tính) vẫn hiện — tuyệt đối không vẽ
  // trang QR khi chưa chứng minh được là chưa đăng nhập (lỗi nháy
  // QR 2026-11-05). Nếu không kết nối được máy chủ thì ở lại màn
  // hình chờ với câu báo lỗi, cũng không hiện trang QR.
  let st;
  try {
    st = await api("/api/status");
  } catch (e) {
    $("loading-text").textContent =
      "Không kết nối được máy chủ. Thử tải lại trang.";
    show("view-loading");
    stopCallsTimers();
    return;
  }
  $("who").textContent = st.login
    ? ("Đã đăng nhập: " + (st.phonenum || st.uid)) : "Chưa đăng nhập";
  // Chan khung chat phan anh dung trang thai sync that tu /api/status
  // (st.sync) — khong de text tinh "chua co" cu hien mai.
  updateSyncNote(st.sync);
  // Version marker: shows which image/commit the server is really
  // running, so a redeploy can be verified at a glance.
  if (st.version) $("app-version").textContent = "Phiên bản: " + st.version;
  $("engine-note").textContent = st.engine && st.engine.detail
    ? ("Tiếng: " + st.engine.detail) : "";
  if (!st.login) { show("view-login"); stopCallsTimers(); return; }
  // force=true only from an intentional "Tải lại" tap: the server
  // skips the TTL then, but still honours the 429 backoff. Every
  // other loadMain() call (tab switch, back from a call, end call)
  // is a plain load and is served from the server cache in TTL.
  const data = await api("/api/contacts" + (force ? "?force=1" : ""));
  const err = $("contacts-error");
  if (data.error) {
    // 429 with no cache to serve: a dry error, but with the wait
    // stated and the reload button locked until it passes.
    if (data.retry_after_seconds) setContactsBackoff(data.retry_after_seconds);
    err.hidden = false;
    $("contacts-error-text").textContent = "Lỗi tải danh bạ: " + data.error;
    updateContactsMeta(null);
  } else {
    // A 429 WITH cache still returns rows (source cache-after-429):
    // show the list, not an error — plus the wait, in the meta line.
    if (data.rate_limited && data.retry_after_seconds) {
      setContactsBackoff(data.retry_after_seconds);
    }
    err.hidden = true;
    contacts = data;
    updateContactsMeta(data);
    // Stale-while-revalidate: danh bạ cũ vừa hiện ngay; hẹn tải
    // lại sau 3 giây để lấy bản mới mà lần làm mới nền vừa ghi
    // vào cache (xem scheduleStaleRefresh). Không hẹn khi dữ liệu
    // đã tươi / còn trong TTL — chỉ khi stale mới cần lần tải nữa.
    if (data.stale) scheduleStaleRefresh();
  }
  updateReloadButton();
  renderList();
  renderSvcThreadOptions();
  await loadCalls();
  startCallsTimers();
  startInboxTimer();
  show("view-main");
}

// -- services: the 96 addon services, grouped, acting on the
// selected thread. Supported ops get a real form + Run button;
// anything else shows its status + reason and NO fake button.
const SVC_STATUS_LABEL = {
  supported: "Thao tác được",
  chat: "Thuộc khung chat",
  zalobot: "Thuộc máy chủ zalobot",
  view: "Đã xem được",
  unsupported: "Chưa hỗ trợ",
};
const SVC_STATUS_PILL = {
  supported: "pill pill-positive",
  chat: "pill pill-neutral",
  zalobot: "pill pill-neutral",
  view: "pill pill-accent",
  unsupported: "pill pill-negative",
};

function svcCurrentThread() {
  const typed = $("svc-thread-id").value.trim();
  if (typed) {
    return { id: typed, type: $("svc-thread-type").value,
             name: svcThread && svcThread.id === typed
               ? svcThread.name : "" };
  }
  if (svcThread) return svcThread;
  const sel = $("svc-thread");
  if (sel && sel.value) {
    const opt = sel.options[sel.selectedIndex];
    return { id: sel.value, type: opt.dataset.type || "user",
             name: opt.textContent.split(" · ")[0] };
  }
  return null;
}

function renderSvcThreadOptions() {
  const sel = $("svc-thread");
  if (!sel) return;
  const keep = svcThread ? svcThread.id : sel.value;
  sel.innerHTML = "";
  const { f, g, all } = allRows();
  all.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.id;
    o.dataset.type = r.type;
    o.textContent = (r.name || r.id) + " · " + r.id;
    sel.appendChild(o);
  });
  if (keep) sel.value = keep;
  if (sel.value && !svcThread) {
    const opt = sel.options[sel.selectedIndex];
    svcThread = { id: sel.value, type: opt.dataset.type || "user",
                  name: (opt.textContent || "").split(" · ")[0] };
  }
  syncSvcThreadBox();
}

function syncSvcThreadBox() {
  const t = svcCurrentThread();
  const name = $("svc-thread-name");
  if (!t) { name.textContent = "Chưa chọn thread nào."; return; }
  $("svc-thread-type").value = t.type;
  name.textContent = (t.name ? t.name + " · " : "")
    + t.id + " · " + typePill(t.type);
}

function openServices(row) {
  svcThread = { id: row.id, type: row.type, name: row.name || row.id };
  $("svc-thread-id").value = "";
  renderSvcThreadOptions();
  if ($("svc-thread")) $("svc-thread").value = row.id;
  syncSvcThreadBox();
  loadServices().then(() => show("view-services"));
}

async function loadServices() {
  if (!svcCatalog) {
    try {
      svcCatalog = await api("/api/svc/catalog");
    } catch (e) {
      $("svc-counts").textContent =
        "Không tải được danh mục dịch vụ: " + e;
      return;
    }
  }
  renderServices();
}

function renderServices() {
  const cat = svcCatalog;
  if (!cat || !cat.services) return;
  const c = cat.counts || {};
  const done = (c.supported || 0) + (c.view || 0);
  $("svc-counts").textContent =
    done + "/96 thao tác được trên UI (trong đó "
    + (c.supported || 0) + " qua panel Dịch vụ, "
    + (c.view || 0) + " đã xem được ở Danh bạ) · "
    + (c.chat || 0) + " thuộc khung chat · "
    + (c.zalobot || 0) + " thuộc máy chủ zalobot · "
    + (c.unsupported || 0) + " chưa hỗ trợ (chưa có đường PC).";
  const box = $("svc-groups");
  box.innerHTML = "";
  (cat.groups || []).forEach((g) => {
    const items = cat.services.filter((s) => s.group === g.id);
    if (!items.length) return;
    const sec = document.createElement("section");
    sec.className = "svc-group";
    const h = document.createElement("h2");
    h.className = "svc-group-title";
    h.textContent = g.label;
    sec.appendChild(h);
    const ul = document.createElement("ul");
    ul.className = "svc-list";
    items.forEach((s) => ul.appendChild(svcRow(s)));
    sec.appendChild(ul);
    box.appendChild(sec);
  });
  syncSvcThreadBox();
}

function svcRow(s) {
  const li = document.createElement("li");
  li.className = "svc-row" + (s.danger ? " svc-danger" : "");
  const main = document.createElement("div");
  main.className = "svc-main";
  const name = document.createElement("div");
  name.className = "svc-name";
  name.textContent = s.label;
  const sub = document.createElement("div");
  sub.className = "row-sub";
  sub.textContent = s.addon + (s.pc ? " · " + s.pc : "");
  main.appendChild(name);
  main.appendChild(sub);
  if (s.desc) {
    const d = document.createElement("div");
    d.className = "svc-desc";
    d.textContent = s.desc;
    main.appendChild(d);
  }
  if (s.status === "supported" && s.body_unverified) {
    const w = document.createElement("div");
    w.className = "svc-warn";
    w.textContent = "Body chưa xác minh thật — path và mã có trong "
      + "bundle, body dùng tham số addon.";
    main.appendChild(w);
  }
  if (s.status !== "supported" && s.reason) {
    const r = document.createElement("div");
    r.className = "svc-reason";
    r.textContent = s.reason;
    main.appendChild(r);
  }
  const pill = document.createElement("span");
  pill.className = SVC_STATUS_PILL[s.status] || "pill pill-neutral";
  pill.textContent = SVC_STATUS_LABEL[s.status] || s.status;
  li.appendChild(main);
  li.appendChild(pill);
  if (s.status === "supported" && s.action) {
    const form = document.createElement("div");
    form.className = "svc-form";
    const inputs = {};
    (s.fields || []).forEach((f) => {
      const lab = document.createElement("label");
      lab.className = "svc-field";
      const cap = document.createElement("span");
      cap.textContent = f.label + (f.required ? " *" : "");
      const inp = document.createElement("input");
      inp.type = "text";
      inp.placeholder = f.label;
      inp.setAttribute("aria-label", f.label);
      lab.appendChild(cap);
      lab.appendChild(inp);
      form.appendChild(lab);
      inputs[f.key] = inp;
    });
    const run = document.createElement("button");
    run.type = "button";
    run.className = "btn " + (s.danger ? "btn-danger-outline svc-run"
      : "btn-secondary svc-run");
    run.textContent = "Chạy";
    run.onclick = () => runSvc(s, inputs, run);
    form.appendChild(run);
    li.appendChild(form);
  }
  return li;
}

function svcResult(text, ok) {
  const box = $("svc-result");
  box.hidden = false;
  box.className = "svc-result" + (ok ? " svc-ok" : " svc-err");
  box.textContent = text;
}

async function runSvc(s, inputs, btn) {
  const t = svcCurrentThread();
  if (s.thread !== "none" && !t) {
    svcResult("Chọn một thread trước (ở ô Thread thao tác).", false);
    return;
  }
  if (s.danger && !window.confirm(
      "Thao tác “" + s.label + "” không hoàn tác được. Chạy tiếp?")) {
    return;
  }
  const body = {};
  if (t) { body.thread_id = t.id; body.type = t.type; }
  let missing = null;
  (s.fields || []).forEach((f) => {
    const v = inputs[f.key] ? inputs[f.key].value.trim() : "";
    if (v) body[f.key] = v;
    else if (f.required) missing = f.label;
  });
  if (missing) {
    svcResult("Thiếu: " + missing + ".", false);
    return;
  }
  btn.disabled = true;
  svcResult("Đang chạy “" + s.label + "”…", true);
  try {
    const r = await api("/api/svc/" + s.action, "POST", body);
    if (r.ok) {
      svcResult("Xong “" + s.label + "”: "
        + JSON.stringify(r.data), true);
    } else {
      svcResult("Lỗi “" + s.label + "”: "
        + (r.error || JSON.stringify(r)), false);
    }
  } catch (e) {
    svcResult("Lỗi mạng khi chạy “" + s.label + "”: " + e, false);
  } finally {
    btn.disabled = false;
  }
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
    // Only "ringing" once step 2 (11301) is actually sent:
    // request_sent is the only honest signal; before that the
    // call is still being placed and the peer may not be
    // ringing at all (live 07/11: step 2 stuck, chip lied).
    pill.textContent = (active.request_sent === true
      ? "Đang đổ chuông: "
      : "Đang gọi: ") + (active.peer || active.thread_id);
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
  const [cls, label] = statusPill(c.status, c.request_sent);
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
  // Rail tracking must show the thread ID (same as the active card
  // and the history table): the rail is the view the user watches
  // while a call is live, and feed rows previously showed only the
  // name + time/type, so a call could not be matched to its thread.
  const tid = document.createElement("div");
  tid.className = "feed-tid mono";
  tid.textContent = c.thread_id;
  const sub = document.createElement("div");
  sub.className = "feed-sub";
  sub.textContent = fmtTime(c.started_at) + " · " + typePill(c.type);
  main.appendChild(name);
  main.appendChild(tid);
  main.appendChild(sub);
  const pill = document.createElement("span");
  const [cls, label] = statusPill(c.status, c.request_sent);
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
  const [cls, label] = statusPill(c.status, c.request_sent);
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
      // 1s tick for the contacts reload countdown + 429 meta line.
      if (contactsBackoffUntil) {
        updateReloadButton();
        if (lastContactsMeta) updateContactsMeta();
        if (backoffLeft() === 0) contactsBackoffUntil = 0;
      }
    }, 1000);
  }
}
function stopCallsTimers() {
  if (callsTimer) { clearInterval(callsTimer); callsTimer = null; }
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null; }
}

// -- chat theo thread -------------------------------------------------
function chatThreadParam() {
  return "?type=" + (currentThread.type === "group" ? "group" : "user");
}

function openThread(row) {
  currentThread = row;
  const av = $("chat-avatar");
  av.className = "avatar " + tintFor(row.id);
  av.textContent = initials(row.name, row.id);
  $("chat-name").textContent = row.name || row.id;
  $("chat-type").textContent = typePill(row.type || "user");
  $("chat-thread").textContent = row.id;
  // Member count: only show when known (>0). The group rows' member
  // list can be empty while the real count is not (topMember is
  // partial) — showing "0 thanh vien" would be wrong.
  $("chat-members").textContent =
    (row.type === "group" && row.members && row.members.length > 0)
      ? (" · " + row.members.length + " thành viên") : "";
  $("chat-input").value = "";
  chatLastTime = 0;
  show("view-chat");
  loadThreadHistory();
  startChatPoll();
}

// -- tin den tu hien trong thread dang mo ---------------------------------
// UI hoi /api/thread/<id>/updates moi 5 giay (chi doc Inbox o RAM,
// khong goi Zalo — tranh 429 khi tai lai lich su lien tuc). Tin moi
// duoc noi vao list da ve, dedup theo id. Roi khoi view-chat thi
// tick tu dung (khong can hook them vao nav).
let chatPollTimer = null;
let chatLastTime = 0;
function stopChatPoll() {
  if (chatPollTimer) { clearInterval(chatPollTimer); chatPollTimer = null; }
}
function startChatPoll() {
  stopChatPoll();
  chatPollTimer = setInterval(async () => {
    if (!currentThread || $("view-chat").style.display === "none") {
      stopChatPoll();
      return;
    }
    try {
      // after = moc moi nhat - 1 giay: tin den cung giay voi tin
      // moi nhat da ve van khong lot (dedup theo id o duoi lo
      // trung lap).
      const data = await api("/api/thread/" + encodeURIComponent(currentThread.id)
        + "/updates" + chatThreadParam() + "&after=" + Math.max(0, chatLastTime - 1));
      if (data.error || !data.messages || !data.messages.length) return;
      const cur = chatRenderedMessages();
      const seen = new Set(cur.map((m) => String(m.id || m.client_id || "")));
      const fresh = data.messages.filter(
        (m) => !seen.has(String(m.id || m.client_id || "")));
      if (fresh.length) renderMessages([...cur, ...fresh]);
    } catch (e) { /* tick sau thu lai; khong bao gio pha khung chat */ }
  }, 5000);
}

function bubbleText(m) {
  if (m.kind === "file") return "Đã gửi file: " + (m.file_name || m.text || "");
  if (m.kind === "photo") return "Đã gửi ảnh" + (m.file_name ? ": " + m.file_name : "");
  if (m.kind === "voice") return "Đã gửi tin nhắn thoại" + (m.file_name ? ": " + m.file_name : "") + " (thu tại trình duyệt)";
  return m.text || "";
}

function renderMessages(messages) {
  const box = $("chat-history");
  box.innerHTML = "";
  (messages || []).forEach((m) => {
    const out = m.direction === "out" || m.sender_id === "me";
    const div = document.createElement("div");
    div.className = "bubble " + (out ? "bubble-out" : "bubble-in");
    if (!out && currentThread.type === "group" && (m.sender_name || m.sender_id)) {
      const who = document.createElement("div");
      who.className = "bubble-who";
      who.textContent = m.sender_name || m.sender_id;
      div.appendChild(who);
    }
    const text = document.createElement("div");
    text.className = "bubble-text";
    text.textContent = bubbleText(m);
    div.appendChild(text);
    if (m.time) {
      const meta = document.createElement("div");
      meta.className = "bubble-meta";
      meta.textContent = fmtTime(m.time);
      div.appendChild(meta);
    }
    box.appendChild(div);
  });
  box.scrollTop = box.scrollHeight;
  const empty = $("chat-empty");
  if (!messages || messages.length === 0) {
    empty.hidden = false;
    empty.textContent = currentThread.type === "group"
      ? "Chưa có tin nhắn nào trong nhóm này."
      : "Chưa có tin nhắn nào trong phiên này. Lịch sử 1-1 cũ chưa lấy được qua HTTPS — tin nhắn mới đến sẽ tự hiện khi có.";
  } else {
    empty.hidden = true;
  }
}

async function loadThreadHistory() {
  if (!currentThread) return;
  const notice = $("chat-notice");
  // Mo thread: lay lai trang thai sync that de chan khung chat
  // khong giu cau cu tu luc load trang (kenh co the vua mo
  // duoc nho vong retry nen / nut "Thu ket noi lai").
  try {
    const st = await api("/api/status");
    updateSyncNote(st.sync);
  } catch (e) { /* giu cau hien tai; lich su van tai ben duoi */ }
  try {
    const data = await api("/api/thread/" + encodeURIComponent(currentThread.id)
      + "/history" + chatThreadParam() + "&count=50");
    if (data.error) {
      notice.hidden = false;
      notice.textContent = "Lỗi tải lịch sử: " + data.error;
      renderMessages([]);
      return;
    }
    if (_lastSendError && currentThread
        && String(_lastSendError.threadId) === String(currentThread.id)) {
      // Loi gui vua hien o chinh thread nay thang thong bao lich
      // su: mo lai thread khong duoc xoa banner loi (loi cam
      // 07/11 — user gui anh loi, mo lai doan chat de goi thi
      // banner bien mat, tuong la khong co loi gi).
      notice.hidden = false;
      notice.textContent = _lastSendError.text;
    } else if (data.notice) {
      notice.hidden = false;
      notice.textContent = data.notice;
    } else {
      notice.hidden = true;
    }
    renderMessages(data.messages || []);
    // Mo thread = da doc: server da xoa unread; cap nhat lai huy
    // hieu o thread list (khong doi lan refresh 15 giay).
    refreshInboxSummary();
    // Mark read (best effort): only ids we actually saw, never "me".
    const ids = (data.messages || [])
      .map((m) => m.id).filter((id) => id && id !== "me");
    if (ids.length) {
      api("/api/thread/" + encodeURIComponent(currentThread.id) + "/seen",
        "POST", { type: currentThread.type === "group" ? "group" : "user", msg_ids: ids })
        .catch(() => {});
    }
  } catch (e) {
    notice.hidden = false;
    notice.textContent = "Lỗi tải lịch sử: " + (e && e.message ? e.message : e);
    renderMessages([]);
  }
}

async function sendChatText() {
  if (!currentThread) return;
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  const r = await api("/api/thread/" + encodeURIComponent(currentThread.id) + "/send",
    "POST", { type: currentThread.type === "group" ? "group" : "user", message: text });
  if (r.error) {
    $("chat-notice").hidden = false;
    $("chat-notice").textContent = "Lỗi gửi tin: " + r.error;
    _setSendError("Lỗi gửi tin: " + r.error);
    input.value = text;
    return;
  }
  // The message just sent shows at once (local echo from the server).
  if (r.message) {
    _setSendError(null);
    const box = $("chat-history");
    const cur = Array.from(box.querySelectorAll(".bubble")).length;
    if (cur === 0) $("chat-empty").hidden = true;
    renderMessages([...chatRenderedMessages(), r.message]);
  }
}

let _rendered = [];
function chatRenderedMessages() { return _rendered; }
// Keep the rendered list so a just-sent message can be appended
// without refetching history (refetching group history on every
// send would cost a Zalo call each time). Also tracks the newest
// rendered timestamp — the /updates poll asks only for newer.
const _renderMessagesOrig = renderMessages;
renderMessages = function (messages) {
  _rendered = messages || [];
  for (const m of _rendered) {
    if (m.time && m.time > chatLastTime) chatLastTime = m.time;
  }
  _renderMessagesOrig(messages);
};

// -- dinh kem file/anh: phan loai + gioi han theo Node.js (zalobot) --
// Chi jpg/jpeg/png/webp moi gui duong anh (EXT_ALBUM cua
// utils/sendImages.js); gif/heic/bmp/svg/... gui dang tep dinh kem
// (zca-js xep ext la vao "others"). Zalo khong nhan file rong —
// case live 23:00 +07 (iptv-udpxy.m3u, 0 byte) truoc day gui thang
// 0 byte sang Zalo roi khong co phan hoi hien ra.
const PHOTO_EXTS = ["jpg", "jpeg", "png", "webp"];
const MAX_FILE_BYTES = 100 * 1024 * 1024; // gioi han server hien tai
const MAX_PHOTO_BYTES = 25 * 1024 * 1024; // cap saveImage cua Node.js
function attachExt(name) {
  const n = String(name || "");
  const i = n.lastIndexOf(".");
  if (i < 0) return "";
  return n.slice(i + 1).toLowerCase();
}
function isPhotoFile(file) {
  const ext = attachExt(file.name);
  if (ext) return PHOTO_EXTS.indexOf(ext) !== -1;
  return ["image/jpeg", "image/png", "image/webp"].indexOf(
    (file.type || "").toLowerCase()) !== -1;
}
function attachNotice(msg) {
  const el = $("chat-notice");
  el.hidden = false;
  el.textContent = msg;
}
// Loi gui gan nhat theo thread — loadThreadHistory khong duoc xoa
// banner loi khi mo lai thread (loi cam 07/11: banner hien roi
// bien mat khi user mo lai doan chat de goi). Luu kem thread id de
// loi cua thread nay khong hien sang thread khac; xoa khi gui
// thanh cong o chinh thread do.
let _lastSendError = null; // { threadId, text } | null
function _setSendError(text) {
  _lastSendError = text
    ? { threadId: currentThread && currentThread.id, text }
    : null;
}
// Kiem tra truoc khi gui: tra ve loi tieng Viet cu the, "" neu dat.
function attachCheck(file) {
  if (!file) return "Chưa chọn file để gửi.";
  if (!file.name) return "File không có tên — hãy chọn file khác.";
  if (!file.size) {
    return "File “" + file.name + "” rỗng (0 byte) — Zalo không nhận "
      + "file rỗng, hãy chọn file khác.";
  }
  if (isPhotoFile(file) && file.size > MAX_PHOTO_BYTES) {
    return "Ảnh “" + file.name + "” quá lớn ("
      + (file.size / 1048576).toFixed(1)
      + " MB > 25 MB) — hãy nén nhỏ ảnh trước khi gửi.";
  }
  if (!isPhotoFile(file) && file.size > MAX_FILE_BYTES) {
    return "File “" + file.name + "” quá lớn ("
      + (file.size / 1048576).toFixed(1)
      + " MB > 100 MB).";
  }
  return "";
}

async function sendChatFile(file) {
  // Tra ve {ok, error} de luong gui nhieu file (sendChatFiles) tong
  // hop duoc; hanh vi hien thi (notice) giu nguyen nhu cu.
  if (!currentThread) {
    attachNotice("Chưa mở đoạn chat nào — hãy chọn một cuộc trò chuyện rồi gửi file.");
    return { ok: false, error: "Chưa mở đoạn chat nào." };
  }
  const bad = attachCheck(file);
  if (bad) { attachNotice(bad); return { ok: false, error: bad }; }
  const btn = $("btn-chat-attach");
  btn.disabled = true;
  attachNotice("Đang gửi file “" + file.name + "”…");
  try {
    const form = new FormData();
    form.append("type", currentThread.type === "group" ? "group" : "user");
    const isPhoto = isPhotoFile(file);
    form.append("kind", isPhoto ? "photo" : "file");
    if (isPhoto) {
      // Real photo send carries width/height (11152/11164 params).
      const dims = await new Promise((resolve) => {
        const img = new Image();
        let done = false;
        const finish = (d) => { if (!done) { done = true; resolve(d); } };
        img.onload = () => finish({ w: img.naturalWidth, h: img.naturalHeight });
        img.onerror = () => finish({ w: 0, h: 0 });
        img.src = URL.createObjectURL(file);
        setTimeout(() => finish({ w: 0, h: 0 }), IMAGE_DIMS_TIMEOUT_MS);
      });
      form.append("width", String(dims.w));
      form.append("height", String(dims.h));
    }
    form.append("file", file, file.name);
    const r = await apiForm("/api/thread/" + encodeURIComponent(currentThread.id) + "/sendfile", form);
    if (r && r.error) {
      attachNotice("Lỗi gửi file: " + r.error);
      _setSendError("Lỗi gửi file: " + r.error);
      return { ok: false, error: r.error };
    }
    if (r && r.message) {
      $("chat-notice").hidden = true;
      _setSendError(null);
      renderMessages([...chatRenderedMessages(), r.message]);
      return { ok: true };
    }
    attachNotice("Máy chủ trả về không rõ kết quả gửi file — hãy mở lại đoạn chat để kiểm tra.");
    _setSendError("Máy chủ trả về không rõ kết quả gửi file — hãy mở lại đoạn chat để kiểm tra.");
    return { ok: false, error: "Máy chủ trả về không rõ kết quả." };
  } catch (e) {
    // fetch bi tu choi (mat mang / server khong tra loi) hoac tra ve
    // khong phai JSON: truoc day promise reject im lang (onchange
    // khong catch), nguoi dung khong thay gi — gio luon hien loi
    // cu the (loi live 23:00 +07).
    const errText = e && e.message ? e.message : String(e);
    attachNotice("Lỗi gửi file: " + errText
      + " — hãy kiểm tra mạng rồi gửi lại.");
    _setSendError("Lỗi gửi file: " + errText
      + " — hãy kiểm tra mạng rồi gửi lại.");
    return { ok: false, error: errText };
  } finally {
    btn.disabled = false;
  }
}

// -- gui nhieu file mot luc: client PC that gui moi anh/file bang
// mot message rieng (bundle _sendPhoto chi nhan mot fileContent,
// backend send_photo tao clientId moi moi call — khong co endpoint
// gop). Gui lan luot tung file, moi file mot POST sendfile rieng;
// mot file loi khong chan cac file con lai; cuoi cung bao tong ket
// so file da gui + ten file loi.
async function sendChatFiles(files) {
  const list = Array.prototype.slice.call(files || []);
  if (!list.length) return;
  if (list.length === 1) { await sendChatFile(list[0]); return; }
  if (!currentThread) {
    attachNotice("Chưa mở đoạn chat nào — hãy chọn một cuộc trò chuyện rồi gửi file.");
    return;
  }
  const btn = $("btn-chat-attach");
  btn.disabled = true;
  let okCount = 0;
  const failed = [];
  try {
    for (let i = 0; i < list.length; i++) {
      const file = list[i];
      attachNotice("Đang gửi " + (i + 1) + "/" + list.length + ": “" + file.name + "”…");
      const r = await sendChatFile(file);
      if (r && r.ok) okCount++;
      else failed.push({ name: file.name, error: (r && r.error) || "không rõ lỗi" });
    }
  } finally {
    btn.disabled = false;
  }
  const failedText = failed.map((f) => "“" + f.name + "” (" + f.error + ")").join(", ");
  if (failed.length === 0) {
    attachNotice("Đã gửi " + okCount + "/" + list.length + " file.");
    _setSendError(null);
  } else if (okCount === 0) {
    attachNotice("Không gửi được file nào (0/" + list.length + "): " + failedText + ".");
    _setSendError("Không gửi được file nào (0/" + list.length + "): " + failedText + ".");
  } else {
    attachNotice("Đã gửi " + okCount + "/" + list.length + " file. Lỗi: " + failedText + ".");
    _setSendError("Đã gửi " + okCount + "/" + list.length + " file. Lỗi: " + failedText + ".");
  }
}

// -- ghi am: MediaRecorder cua trinh duyet (khong phai ghi am native
// cua Zalo PC) -> gui file da ghi qua duong hai buoc (upload chunked
// 12060/12063 + asyncfile/msg). Chrome thuong cho webm/opus —
// server DOI SANG AAC truoc khi gui (ffmpeg, mono 16 kHz 64 kbps
// ADTS, theo cach Node.js voiceAac.js lam).
// UI chi hien trang thai tung buoc; loi o buoc nao hien ro buoc do,
// khong lam rot ban ghi lang le.
async function toggleRecord() {
  const btn = $("btn-chat-record");
  const state = $("chat-rec-state");
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    state.hidden = false;
    state.textContent = "Trình duyệt này không hỗ trợ ghi âm (cần micro + HTTPS/localhost).";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : (MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "");
    mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size) recChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      clearInterval(recTimer);
      recTimer = null;
      stream.getTracks().forEach((t) => t.stop());
      btn.textContent = "● Ghi âm";
      state.hidden = true;
      const blob = new Blob(recChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      if (!blob.size) {
        state.hidden = false;
        state.textContent = "Ghi âm không thu được âm thanh nào — thử lại.";
        return;
      }
      const ext = (blob.type || "").includes("mp4") ? "mp4" : "webm";
      const file = new File([blob], "voice." + ext, { type: blob.type || "audio/webm" });
      const form = new FormData();
      form.append("type", currentThread.type === "group" ? "group" : "user");
      form.append("file", file, file.name);
      // Server doi sang AAC (ffmpeg) roi moi gui qua duong hai
      // buoc — buoc nay co the mat vai giay voi ban ghi dai.
      state.hidden = false;
      state.textContent = "Đang chuyển sang AAC rồi gửi…";
      let r;
      try {
        // 180 giay: server doi sang AAC truoc khi gui nen co the
        // lau hon gui file thuong (apiForm mac dinh 90 giay).
        r = await apiForm("/api/thread/" + encodeURIComponent(currentThread.id) + "/sendvoice", form, 180000);
      } catch (e) {
        state.textContent = "Lỗi gửi tin nhắn thoại: không tới được máy chủ (" + (e && e.message ? e.message : e) + "). Bản ghi vẫn ở trình duyệt — bấm ghi âm lại để gửi.";
        return;
      }
      state.hidden = true;
      if (r.error) {
        $("chat-notice").hidden = false;
        $("chat-notice").textContent = "Lỗi gửi tin nhắn thoại: " + r.error;
        _setSendError("Lỗi gửi tin nhắn thoại: " + r.error);
        return;
      }
      if (r.message) {
        _setSendError(null);
        renderMessages([...chatRenderedMessages(), r.message]);
      }
    };
    mediaRecorder.start();
    btn.textContent = "■ Dừng";
    state.hidden = false;
    const started = Date.now();
    state.textContent = "Đang ghi âm… 00:00";
    recTimer = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      state.textContent = "Đang ghi âm… " + String(Math.floor(s / 60)).padStart(2, "0")
        + ":" + String(s % 60).padStart(2, "0") + " — bấm “■ Dừng” để gửi.";
    }, 1000);
  } catch (e) {
    state.hidden = false;
    state.textContent = "Không mở được micro: " + (e && e.message ? e.message : e);
  }
}

function onChatInput() {
  // Typing event (11144/11196), throttled: at most once per 4 s
  // while typing, fire-and-forget.
  if (!currentThread) return;
  const now = Date.now();
  if (now - lastTypingAt < 4000) return;
  lastTypingAt = now;
  api("/api/thread/" + encodeURIComponent(currentThread.id) + "/typing",
    "POST", { type: currentThread.type === "group" ? "group" : "user" })
    .catch(() => {});
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
  // c is a call record ({peer, thread_id, type, started_at, call_id,
  // request_sent, request_detail}) or a contact row ({name, id, type}).
  const peer = c.peer || c.name || c.thread_id || c.id;
  const threadId = c.thread_id || c.id;
  const type = c.type || "user";
  $("call-peer").textContent = peer;
  $("call-type").textContent = typePill(type);
  $("call-thread").textContent = threadId;
  $("call-timer").textContent =
    fmtElapsed(c.started_at || (currentCall && currentCall.started_at) || Date.now() / 1000);
  detailCall = { peer: { id: threadId }, callId: c.call_id || (currentCall && currentCall.callId) || "",
                 started_at: c.started_at || (currentCall && currentCall.started_at),
                 type: type, requestSent: c.request_sent,
                 requestError: c.request_detail || "" };
  renderCallDetail();
  show("view-call");
}

function renderCallDetail() {
  // Fill the detail view's step-2 diagnostic (§7l, §7m) from the
  // freshest record we have: the /api/calls entry (request_sent /
  // request_detail live there), falling back to what startCall
  // stored on currentCall / what showCallDetail carried over. The
  // 18:09 live test needs this line: it says whether the server
  // accepted the follow-up `request` (11301/12434) carrying the
  // media endpoints — the detail view showed only a generic
  // sentence before, so a rejected step-2 was invisible.
  const cc = currentCall || detailCall;
  const el = $("call-request");
  if (!cc) { el.textContent = ""; return; }
  const id = String(cc.callId || cc.call_id || "");
  const rec = id ? callsData.calls.find((c) => String(c.call_id) === id) : null;
  const sent = rec ? rec.request_sent : cc.requestSent;
  const detail = rec ? (rec.request_detail || "") : (cc.requestError || "");
  if (sent === true) {
    el.textContent = "Bước 2 (11301): đã gửi — server đã nhận đủ lời mời gọi.";
  } else if (sent === false) {
    el.textContent = "Bước 2 (11301): KHÔNG gửi được"
      + (detail ? (" — " + detail) : "")
      + ". Máy bên kia có thể chưa đổ chuông.";
  } else {
    el.textContent = "Bước 2 (11301): chưa có thông tin.";
  }
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
  // Keep the step-2 outcome (§7l) on the call, so the detail view
  // can show it even before the first /api/calls poll returns it.
  currentCall.requestSent = r.request_sent;
  currentCall.requestError = r.request_error || "";
  // The state line must NOT claim "the other side is ringing"
  // when step 2 (11301) was not sent: the 22:58 live test showed
  // exactly that lie — requestcall (11300) accepted, request
  // (11301) failed on "relays: empty", and the state line still
  // said the far end was ringing. The detail view (renderCallDetail)
  // already shows the step-2 outcome; this line now agrees with it.
  $("call-state").textContent = r.error
    ? ("Lỗi gọi: " + r.error)
    : (r.request_sent === false
      ? ("Đã gửi yêu cầu gọi (bước 1), nhưng bước 2 (11301) KHÔNG gửi được"
         + (r.request_error ? (": " + r.request_error) : "")
         + ". Bên kia có thể chưa đổ chuông.")
      : "Đã gửi yêu cầu gọi. Bên kia đang đổ chuông — tiếng sẽ có khi engine giai đoạn 2 gắn vào.");
  await loadCalls();
  renderCallDetail();
}

async function endCall() {
  if (ending) return; // ignore double taps while an End is in flight.
  // The target is the live call, from wherever it is known:
  // currentCall (started in this page session), detailCall (detail
  // view), or callsData.active (server state — the ONLY source after
  // a page reload, when both locals are null; the old code sent
  // nothing at all then, so the rail's End button was dead, §7m).
  const active = callsData.active;
  const cc = currentCall || detailCall;
  const rawId = (cc && (cc.callId || cc.call_id))
    || (active && active.call_id) || "";
  let callId = rawId;
  if (typeof rawId === "string" && /^\d+$/.test(rawId)) {
    callId = parseInt(rawId, 10); // the real server wants a uint32
    // JSON number, like requestcall (§7k) — a string callId can
    // draw inner 114 from endcall too.
  }
  const uidTo = (cc && cc.peer && cc.peer.id)
    || (active && active.thread_id) || "";
  const callType = (cc && (cc.type || (cc.peer && cc.peer.type)))
    || (active && active.type) || "user";
  ending = true;
  // Optimistic local clear (§7m): the call ends on screen at once.
  // The 18:06 bug also *looked* like "nothing happens" because the
  // UI waited for the whole endcall round-trip before re-rendering.
  // The POST + poll below reconcile with the server afterwards.
  currentCall = null;
  detailCall = null;
  if (active) {
    active.status = "ended";
    active.ended_at = Date.now() / 1000;
    callsData.active = null;
    const row = callsData.calls.find(
      (c) => String(c.call_id) === String(rawId));
    if (row) { row.status = "ended"; row.ended_at = active.ended_at; }
  }
  renderCalls();
  $("call-state").textContent = "Đã kết thúc cuộc gọi.";
  let endNote = "";
  try {
    const r = await api("/api/call/end", "POST",
      { uid_to: uidTo, call_id: callId, type: callType });
    if (r && r.zalo_endcall_ok === false) {
      endNote = "Đã kết thúc cuộc gọi. "
        + "(Máy chủ Zalo chưa xác nhận kết thúc: "
        + (r.zalo_error || "?") + ")";
    }
  } catch (e) { /* poll below reconciles; the call is ended locally */ }
  ending = false;
  await loadCalls();
  if (endNote) {
    // Stay on the detail view so the warning is visible.
    $("call-state").textContent = endNote;
    show("view-call");
  } else {
    show("view-main");
  }
}

// -- webhooks: settings -------------------------------------------------
// Four families, same names as the addon (set_account_webhook) plus
// the new call family. GET/POST /api/webhooks, POST /api/webhooks/test.
const WEBHOOK_KINDS = ["message", "group_event", "reaction", "call"];
function webhookForm() {
  const cfg = {};
  WEBHOOK_KINDS.forEach((k) => {
    cfg[k + "_webhook_url"] = $(`wh-${k}-url`).value.trim();
    cfg[k + "_enabled"] = $(`wh-${k}-enabled`).checked;
  });
  return cfg;
}
function fillWebhookForm(cfg) {
  WEBHOOK_KINDS.forEach((k) => {
    $(`wh-${k}-url`).value = cfg[k + "_webhook_url"] || "";
    $(`wh-${k}-enabled`).checked = cfg[k + "_enabled"] !== false;
    $(`wh-${k}-result`).textContent = "";
  });
  $("webhooks-error").hidden = true;
  $("webhooks-saved").hidden = true;
  $("wh-save-result").textContent = "";
}
async function loadWebhooks() {
  const cfg = await api("/api/webhooks");
  if (cfg.error) { show("view-login"); stopCallsTimers(); return; }
  fillWebhookForm(cfg);
  show("view-webhooks");
}
async function saveWebhooks(e) {
  if (e) e.preventDefault();
  $("webhooks-saved").hidden = true;
  const r = await api("/api/webhooks", "POST", webhookForm());
  const err = $("webhooks-error");
  if (r.error) {
    err.hidden = false;
    $("webhooks-error-text").textContent = "Không lưu được: " + r.error;
    return;
  }
  err.hidden = true;
  if (r.config) fillWebhookForm(r.config);
  $("webhooks-saved").hidden = false;
}
async function testWebhook(kind) {
  const out = $(`wh-${kind}-result`);
  const btn = $(`wh-${kind}-test`);
  btn.disabled = true;
  out.className = "test-result";
  out.textContent = "Đang gửi thử…";
  try {
    const r = await api("/api/webhooks/test", "POST", { kind });
    if (r.error) {
      out.className = "test-result bad";
      out.textContent = "Không gửi được: " + r.error;
    } else if (r.dispatched) {
      out.className = "test-result ok";
      out.textContent = "Đã gửi, bên nhận trả HTTP " + r.status + ".";
    } else if (r.reason === "no_url") {
      out.className = "test-result bad";
      out.textContent = "Chưa có địa chỉ cho loại này — dán URL rồi bấm Lưu trước.";
    } else if (r.reason === "disabled") {
      out.className = "test-result bad";
      out.textContent = "Loại này đang tắt — bật công tắc rồi bấm Lưu trước.";
    } else {
      out.className = "test-result bad";
      out.textContent = "Gửi thất bại" + (r.status ? (" (HTTP " + r.status + ")") : "") + ".";
    }
  } catch (e) {
    out.className = "test-result bad";
    out.textContent = "Không gửi được: lỗi mạng.";
  }
  btn.disabled = false;
}
// -- chat theo thread -------------------------------------------------
$("btn-back-chat").onclick = () => { show("view-main"); };
$("btn-chat-call").onclick = () => { if (currentThread) startCall(currentThread); };
$("btn-chat-refresh").onclick = loadThreadHistory;
$("btn-sync-retry").onclick = retrySync;
$("btn-chat-send").onclick = sendChatText;
$("chat-input").onkeydown = (e) => { if (e.key === "Enter") sendChatText(); };
$("chat-input").oninput = onChatInput;
$("btn-chat-attach").onclick = () => $("chat-file").click();
$("chat-file").onchange = (e) => {
  const files = e.target.files;
  e.target.value = "";
  if (files && files.length) sendChatFiles(files);
};
$("btn-chat-record").onclick = toggleRecord;

// -- menu (phones/tablets) -------------------------------------------------
function closeMenu() {
  $("sidebar").classList.remove("open");
  $("btn-menu").setAttribute("aria-expanded", "false");
}

// -- wiring ---------------------------------------------------------------
$("btn-qr").onclick = startQr;
$("btn-qr-again").onclick = startQr;
$("btn-logout").onclick = () =>
  api("/api/logout", "POST").then(() => { window.location.href = "/login"; })
    .catch(() => { window.location.href = "/login"; });
$("btn-end").onclick = endCall;
$("btn-back").onclick = () => loadMain();
$("btn-retry-contacts").onclick = () => {
  // Guard as well as disabled state: never fire during backoff.
  if (backoffLeft() > 0) return;
  loadMain(true);
};
$("btn-reload-contacts").onclick = () => {
  if (backoffLeft() > 0) return;
  loadMain(true);
};
$("search").oninput = () => { renderList(); renderCalls(); };
$("rail-view-all").onclick = () => { show("view-calls"); };
$("topbar-call").onclick = () => {
  if (callsData.active) showCallDetail(callsData.active);
  else show("view-calls");
};
$("nav-contacts").onclick = () => { show("view-main"); loadMain(); };
$("nav-calls").onclick = async () => { await loadCalls(); show("view-calls"); };
$("nav-webhooks").onclick = loadWebhooks;
$("webhooks-form").onsubmit = saveWebhooks;
WEBHOOK_KINDS.forEach((k) => {
  $(`wh-${k}-test`).onclick = () => testWebhook(k);
});
$("nav-services").onclick = async () => {
  renderSvcThreadOptions();
  await loadServices();
  show("view-services");
};
$("svc-thread").onchange = () => {
  const sel = $("svc-thread");
  const opt = sel.options[sel.selectedIndex];
  svcThread = { id: sel.value, type: opt.dataset.type || "user",
                name: (opt.textContent || "").split(" · ")[0] };
  $("svc-thread-id").value = "";
  syncSvcThreadBox();
};
$("svc-thread-id").oninput = () => syncSvcThreadBox();
$("svc-thread-type").onchange = () => syncSvcThreadBox();
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

// Khởi động: hiện màn hình chờ trung tính TRƯỚC khi biết phiên,
// rồi loadMain() mới quyết định view theo /api/status — trang QR
// chỉ hiện khi status chứng minh là chưa đăng nhập, không bao giờ
// là view mặc định lúc tải trang (lỗi nháy QR 2026-11-05).
show("view-loading");
loadMain();
