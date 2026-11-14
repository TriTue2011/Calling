// Cửa sổ cuộc gọi TÁCH RỜI (/call): video đối tác + nút điều khiển, tự xếp lại theo kích cỡ cửa sổ (xem call.css). Chạy độc lập với trang chính:
// tự hỏi /api/calls, dùng cùng các API điều khiển (/api/call/media, /api/call/end ...) nên hai nơi luôn thấy cùng một cuộc gọi.
"use strict";
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const ICONS = {
    mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3"/>',
    speaker: '<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5zM15.5 9a4 4 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
    cam: '<rect x="3.5" y="6.5" width="12" height="11" rx="2.2"/><path d="m15.5 11 5-3v8l-5-3z"/>',
    hang: '<path d="M3 14c4.5-4 13.5-4 18 0l-1.5 3-4-1.2v-2.3a10 10 0 0 0-7 0v2.3L4.5 17z"/>',
    phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
  };
  const $ = (id) => document.getElementById(id);
  const svg = (n) => { const s = document.createElementNS(NS, "svg"); s.setAttribute("class", "i"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "1.7"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round"); s.innerHTML = ICONS[n] || ""; return s; };
  const h = (tag, props, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) { if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v); else if (v === true) el.setAttribute(k, ""); else if (v !== false && v != null) el.setAttribute(k, v); }
    for (const k of kids.flat()) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(String(k)));
    return el;
  };
  try { const t = localStorage.getItem("zalo-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* riêng tư */ }

  const S = { call: null, cm: { mic: false, speaker: false, video: false, busy: "", gain: { mic: 100, speaker: 100 } }, vid: null, closing: false };
  const MEDIA_ERR = { chua_co_camera: "chưa có camera — quy tắc (automation) của người này chưa chọn camera", chua_co_speaker_url: "chưa có loa — quy tắc (automation) của người này chưa chọn loa", no_live_transport: "cuộc gọi chưa sẵn sàng", no_live_call: "không có cuộc gọi đang diễn ra" };
  const mediaErr = (e) => MEDIA_ERR[e] || e || "lỗi";
  let toastT = null;
  function toast(msg, ms) { const t = $("cw-toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, ms || 4000); }
  async function api(path, method, body) {
    const r = await fetch(path, method === "POST" ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}), credentials: "same-origin" } : { credentials: "same-origin" });
    if (r.status === 401) { location.href = (window.__zIng || "") + "/login"; return { error: "chua_dang_nhap" }; }
    try { return await r.json(); } catch (e) { return { error: "HTTP " + r.status }; }
  }
  const fmtDur = (s) => { s = Math.max(0, Math.floor(s)); const m = Math.floor(s / 60); return String(m).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };
  const peerName = (a) => a.peer || a.name || String(a.thread_id || "");

  // ---- hình đối tác: luồng liên tục, tự chuyển sang ảnh mới nhất nếu luồng không lên (proxy/tunnel gom bộ đệm) ----
  function startVideo(a) {
    const id = String(a.call_id);
    if (S.vid && S.vid.id === id) return;
    if (S.vid) { clearTimeout(S.vid.timer); S.vid.dead = true; }
    const el = $("cw-vview"), box = $("cw-vbox"), enc = encodeURIComponent(a.call_id);
    const vv = S.vid = { id, mode: "stream", errors: 0, timer: null, dead: false };
    box.classList.remove("on"); el.hidden = false;
    const live = () => S.vid === vv && !vv.dead;
    const snapLoop = () => {
      if (!live() || vv.mode !== "snap") return;
      const img = new Image();
      img.onload = () => { if (!live()) return; el.src = img.src; box.classList.add("on"); vv.timer = setTimeout(snapLoop, 250); };
      img.onerror = () => { if (!live()) return; vv.timer = setTimeout(snapLoop, 700); };
      img.src = "/api/call/video/snapshot?call_id=" + enc + "&t=" + Date.now();
    };
    vv.fallback = () => { if (!live() || vv.mode === "snap") return; vv.mode = "snap"; clearTimeout(vv.timer); snapLoop(); };
    el.onload = () => { if (vv.mode === "stream") { clearTimeout(vv.timer); box.classList.add("on"); } };
    el.onerror = () => {
      if (vv.mode !== "stream") return;
      box.classList.remove("on"); vv.errors++;
      if (vv.errors >= 2) return vv.fallback();
      setTimeout(() => { if (live() && vv.mode === "stream") el.src = "/api/call/video/view?call_id=" + enc + "&t=" + Date.now(); }, 3000);
    };
    el.src = "/api/call/video/view?call_id=" + enc + "&t=" + Date.now();
    vv.timer = setTimeout(() => { if (live() && !box.classList.contains("on")) vv.fallback(); }, 6000);
  }
  function stopVideo() { if (S.vid) { clearTimeout(S.vid.timer); S.vid.dead = true; S.vid = null; } const el = $("cw-vview"); el.hidden = true; el.removeAttribute("src"); $("cw-vbox").classList.remove("on"); }

  // ---- điều khiển ----
  async function refreshMedia() {
    const a = S.call; if (!a || S.cm.busy) return;
    try { const r = await api("/api/call/media", "POST", { call_id: a.call_id, action: "status" }); if (!r.error && r.ok !== false) applyCm(r); } catch (e) { /* mạng: lần sau */ }
  }
  function applyCm(r) {
    const on = (x) => !!x && x.alive !== false && !x.idle;      // bộ gửi im lặng chỉ giữ luồng, không phải mic đang bật
    S.cm = Object.assign(S.cm, { mic: on(r.mic), speaker: on(r.speaker), video: on(r.video) });
    if (r.gain && typeof r.gain === "object") S.cm.gain = { mic: Number(r.gain.mic) || 0, speaker: Number(r.gain.speaker) || 0 };
    renderPanel();
  }
  async function toggleMedia(target) {
    const a = S.call; if (!a || S.cm.busy) return;
    const turnOn = !S.cm[target];
    S.cm.busy = target; renderPanel();
    try {
      const upgrade = target === "video" && turnOn && a.type !== "video";      // cuộc THOẠI mà bật camera = xin chuyển sang video
      const r = await api(upgrade ? "/api/call/upgrade_video" : target === "video" ? "/api/call/video" : "/api/call/media", "POST", upgrade ? { call_id: a.call_id } : { call_id: a.call_id, action: turnOn ? "start" : "stop", target });
      if (r.error || r.ok === false) toast((turnOn ? "Không bật được " : "Không tắt được ") + ({ mic: "mic", speaker: "loa", video: "camera" })[target] + ": " + mediaErr(r.error), 6000);
      S.cm.busy = ""; if (!r.error && r.ok !== false) applyCm(r); else { renderPanel(); refreshMedia(); }
    } catch (e) { S.cm.busy = ""; toast("Lỗi mạng khi điều khiển cuộc gọi", 4000); renderPanel(); }
  }
  async function changeGain(target, step) {
    const a = S.call; if (!a) return;
    try {
      const r = await api("/api/call/media", "POST", { call_id: a.call_id, action: "gain", target, step });
      if (r.error || r.ok === false) return toast("Không chỉnh được âm lượng " + (target === "mic" ? "mic" : "loa") + ": " + mediaErr(r.error), 4000);
      S.cm.gain = Object.assign({}, S.cm.gain, r.gain || {}); renderPanel();
    } catch (e) { toast("Lỗi mạng khi chỉnh âm lượng", 4000); }
  }
  async function endCall() { const a = S.call; if (!a) return; const r = await api("/api/call/end", "POST", { call_id: a.call_id }); if (r.error) toast("Lỗi kết thúc cuộc gọi: " + r.error, 5000); await loadCalls(); }
  async function answerCall() { const a = S.call; if (!a) return; const r = await api("/api/call/answer", "POST", { call_id: a.call_id }); if (r.error || r.ok === false) toast("Không nghe máy được: " + (r.error || r.detail || "không rõ"), 6000); await loadCalls(); }
  async function rejectCall() { const a = S.call; if (!a) return; const r = await api("/api/call/reject", "POST", { call_id: a.call_id }); if (r.error || r.ok === false) toast("Không từ chối được: " + (r.error || r.detail || "không rõ"), 6000); await loadCalls(); }

  // ---- vẽ ----
  function renderPanel() {
    const a = S.call, answered = !!a && (a.status === "answered" || !!a.answered_at);
    const tg = $("cw-toggles"), gn = $("cw-gains"), acts = $("cw-acts");
    if (!a) { tg.replaceChildren(); gn.replaceChildren(); acts.replaceChildren(); return; }
    const incoming = a.direction === "in" && a.status === "incoming" && !a.answered_at;
    tg.replaceChildren(...(answered ? [["mic", "mic", "Mic"], ["speaker", "speaker", "Loa"], ["video", "cam", "Camera"]].map(([key, icon, label]) =>
      h("button", { class: "cw-tg" + (S.cm[key] ? " on" : ""), type: "button", "aria-pressed": S.cm[key] ? "true" : "false", disabled: !!S.cm.busy, title: label + (S.cm[key] ? " đang bật, bấm để tắt" : " đang tắt, bấm để bật"), onclick: () => toggleMedia(key) }, svg(icon), h("span", {}, label + (S.cm[key] ? " bật" : " tắt")))) : []));
    gn.replaceChildren(...(answered ? [["mic", "Mic"], ["speaker", "Loa"]].map(([key, label]) => {
      const g = (S.cm.gain && S.cm.gain[key]) ?? 100;
      return h("div", { class: "cw-gn" },
        h("button", { type: "button", "aria-label": "Giảm âm lượng " + label.toLowerCase(), disabled: g <= 0, onclick: () => changeGain(key, -10) }, "−"),
        h("span", { class: "gv" }, label + " " + g + "%"),
        h("button", { type: "button", "aria-label": "Tăng âm lượng " + label.toLowerCase(), disabled: g >= 300, onclick: () => changeGain(key, 10) }, "+"));
    }) : []));
    acts.replaceChildren(...(incoming
      ? [h("button", { class: "cw-btn end", type: "button", onclick: rejectCall }, svg("hang"), h("span", {}, "Từ chối")), h("button", { class: "cw-btn ok", type: "button", onclick: answerCall }, svg("phone"), h("span", {}, "Nghe"))]
      : [h("button", { class: "cw-btn end", type: "button", onclick: endCall }, svg("hang"), h("span", {}, "Kết thúc"))]));
  }
  function render() {
    const a = S.call, cw = $("cw");
    if (!a) {
      cw.dataset.state = "end"; $("cw-st").textContent = "Cuộc gọi đã kết thúc"; $("cw-tm").textContent = ""; stopVideo(); renderPanel();
      if (!S.closing) { S.closing = true; setTimeout(() => { try { window.close(); } catch (e) { /* không đóng được: để người dùng đóng */ } }, 2500); }
      return;
    }
    S.closing = false;
    const answered = a.status === "answered" || !!a.answered_at, incoming = a.direction === "in" && a.status === "incoming" && !a.answered_at;
    cw.dataset.state = incoming ? "incoming" : answered ? "live" : "ringing";
    $("cw-nm").textContent = (a.type === "video" ? "Video · " : "") + peerName(a); document.title = peerName(a) + " — Zalo";
    $("cw-st").textContent = incoming ? (a.type === "video" ? "Cuộc gọi video đến…" : "Cuộc gọi đến…") : answered ? "Đang trong cuộc gọi" : "Đang đổ chuông…";
    const mc = a.media && a.media.counters;
    if (answered && (a.type === "video" || (mc && mc.video_rx > 0))) startVideo(a); else if (!answered) stopVideo();
    $("cw-wait").textContent = answered ? "Đang chờ hình…" : incoming ? "Có cuộc gọi đến" : "Đang đổ chuông…";
    if (!S.cm.id || S.cm.id !== String(a.call_id)) { S.cm.id = String(a.call_id); S.cm.mic = S.cm.speaker = S.cm.video = false; if (answered) refreshMedia(); }
    renderPanel();
  }
  async function loadCalls() {
    try { const d = await api("/api/calls", "GET"); if (d.error) return; S.call = d.active || null; render(); } catch (e) { /* mạng: lần sau */ }
  }
  $("cw-vbox").addEventListener("click", () => $("cw-vbox").classList.toggle("fill"));
  setInterval(() => { const a = S.call; if (a) { const since = (a.answered_at || a.started_at); $("cw-tm").textContent = (a.status === "answered" || a.answered_at) ? fmtDur(Date.now() / 1000 - since) : ""; } }, 1000);
  setInterval(loadCalls, 1500);
  setInterval(() => { const a = S.call; if (a && (a.status === "answered" || a.answered_at)) refreshMedia(); }, 3000);
  loadCalls();
  if (typeof window.__CALL_TEST_HOOK__ === "function") window.__CALL_TEST_HOOK__({ S, render, loadCalls, toggleMedia, changeGain, endCall, answerCall, rejectCall, startVideo, applyCm });   // chỉ để kiểm thử giao diện (jsdom)
})();
