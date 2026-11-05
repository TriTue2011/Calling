// App UI logic: login view -> main view -> call view.
// The page never sees session secrets; it only gets states + rows.
const $ = (id) => document.getElementById(id);
let contacts = { friends: [], groups: [] };
let currentTab = "friends";
let currentCall = null;
let pollTimer = null;

function show(view) {
  ["view-login", "view-main", "view-call"].forEach(
    (v) => $(v).style.display = (v === view ? "" : "none"));
}

async function api(path, method, body) {
  const r = await fetch(path, {
    method: method || "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}

function renderList() {
  const fRows = contacts.friends.rows || [];
  const gRows = contacts.groups.rows || [];
  // Counts on the tabs (totals, not the filtered view): "Bạn bè (0)"
  // / "Nhóm (0)" means the account really has none, while a non-zero
  // count with no names would mean a parsing bug — the two cases
  // looked identical before (both showed empty tabs).
  $("tab-friends").textContent = "Bạn bè (" + fRows.length + ")";
  $("tab-groups").textContent = "Nhóm (" + gRows.length + ")";
  const rows = currentTab === "friends" ? fRows : gRows;
  const q = $("search").value.trim().toLowerCase();
  const ul = $("list");
  ul.innerHTML = "";
  rows.filter((r) => !q || (r.name || "").toLowerCase().includes(q))
    .forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r.name || r.id;
      li.onclick = () => startCall(r);
      ul.appendChild(li);
    });
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
  if (!st.login) { show("view-login"); return; }
  const data = await api("/api/contacts");
  if (data.error) { $("engine-note").textContent = "Lỗi tải danh bạ: " + data.error; }
  else { contacts = data; }
  renderList();
  show("view-main");
}

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

async function startCall(peer) {
  const callId = String(Date.now());
  currentCall = { peer, callId };
  $("call-peer").textContent = "Gọi tới: " + (peer.name || peer.id);
  $("call-state").textContent = "Đang gửi yêu cầu gọi...";
  show("view-call");
  const r = await api("/api/call/request", "POST",
    { callee_id: peer.id, call_id: callId, type_request: 0 });
  $("call-state").textContent = r.error
    ? ("Lỗi gọi: " + r.error)
    : "Đã gửi yêu cầu gọi. Tiếng sẽ có khi engine giai đoạn 2 gắn vào.";
}

async function endCall() {
  if (currentCall) {
    await api("/api/call/end", "POST",
      { uid_to: currentCall.peer.id, call_id: currentCall.callId });
    currentCall = null;
  }
  loadMain();
}

$("btn-qr").onclick = startQr;
$("btn-qr-again").onclick = startQr;
$("btn-logout").onclick = () => api("/api/logout", "POST").then(loadMain);
$("btn-end").onclick = endCall;
$("btn-back").onclick = loadMain;
$("search").oninput = renderList;
$("tab-friends").onclick = () => {
  currentTab = "friends";
  $("tab-friends").className = "on"; $("tab-groups").className = "";
  renderList();
};
$("tab-groups").onclick = () => {
  currentTab = "groups";
  $("tab-groups").className = "on"; $("tab-friends").className = "";
  renderList();
};

loadMain();
