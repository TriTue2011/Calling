// Đo bố cục WebUI ở khổ điện thoại bằng Chrome thật (CDP, WebSocket có sẵn của Node 22). In JSON: {"<màn>@<rộng>": {...số đo...}}.
// Dùng: node phone_layout_cdp.js <baseUrl> <cookie> [rộng,rộng...]   (do tests/test_phone_layout.py gọi)
const { spawn } = require("child_process"); const fs = require("fs"); const http = require("http");
const [base, cookie, widths] = [process.argv[2], process.argv[3], (process.argv[4] || "390,320").split(",").map(Number)];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const getJson = (u) => new Promise((res, rej) => http.get(u, (r) => { let d = ""; r.on("data", (c) => d += c); r.on("end", () => res(JSON.parse(d))); }).on("error", rej));
const click = (sel, txt) => `(()=>{const l=[...document.querySelectorAll(${JSON.stringify(sel)})];const e=${txt ? `l.find(x=>x.textContent.trim()===${JSON.stringify(txt)})` : "l[0]"};if(!e)return ${JSON.stringify("THIẾU " + sel)};(e.closest("button")||e).click();return "ok"})()`;
const SCREENS = {
  list: [], chat: [click("#list .row-name", "BenBap")], info: [click("#list .row-name", "BenBap"), click("#btn-info")],
  call_incoming: [], call_voice: [], call_video: [],
  watch: [click('.rail-btn[data-tab="watch"]')],
  svc_chip: [click('.rail-btn[data-tab="services"]'), `(()=>{const l=[...document.querySelectorAll("#svc-page .chip")];const e=l[l.length-1];e.scrollIntoView({inline:"end"});e.click();return "ok"})()`],
  contacts: [click('.rail-btn[data-tab="contacts"]')], calls: [click('.rail-btn[data-tab="calls"]')], services: [click('.rail-btn[data-tab="services"]')],
};
const MEASURE = `(()=>{const q=(s)=>document.querySelector(s), r=(s)=>{const e=q(s);if(!e)return null;const b=e.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height,disp:getComputedStyle(e).display}};
  const root=document.documentElement, app=q("#app");
  return JSON.stringify({bp:root.dataset.bp, pane:app.dataset.pane, tab:app.dataset.tab, info:app.dataset.info, sw:root.scrollWidth, cw:root.clientWidth,
   head:q(".pane.on .head,#pane-chat .head")?getComputedStyle(q(".pane.on .head")||q("#pane-chat .head")).backgroundImage:"", listHead:getComputedStyle(q(".list-head")).backgroundImage,
   rail:r("#rail"), railLabels:[...document.querySelectorAll(".rail-btn")].map(b=>getComputedStyle(b,"::after").content.replace(/"/g,"")),
   input:r("#msg-in"), more:r("#btn-more"), emoji:r("#btn-emoji"), img:r("#btn-img"), rec:r("#btn-rec"), attach:r("#btn-attach"), like:r("#btn-like"),
   infoBox:r("#info"), infoPos:getComputedStyle(q("#info")).position, back:r("#info .back"), btnInfo:r("#btn-info"),
   tblRowDisp:q(".tbl tr")?getComputedStyle(q(".tbl tr")).display:"", tblHeadDisp:q(".tbl thead")?getComputedStyle(q(".tbl thead")).display:"",
   chips:(()=>{const c=q("#svc-page .chips");if(!c)return null;const sel=c.querySelector('[aria-pressed="true"]');const b=c.getBoundingClientRect(), sb=sel?sel.getBoundingClientRect():null;return {scrollLeft:c.scrollLeft, box:{x:b.x,w:b.width}, sel:sb?{x:sb.x,w:sb.width}:null}})(),
   noticeHidden:(()=>{const n=q("#chat-notice");return !n||n.hidden||!n.textContent.trim()})(),
   cc:r("#callcard"), ccState:q("#callcard").dataset.state||"", ccVideo:q("#callcard").dataset.video||"", ccPe:getComputedStyle(q("#callcard")).pointerEvents, end:r("#callcard .end"), ok:r("#callcard .ok"), mt:r("#callcard .mt"), vid:r("#vidwin"), popout:r("#callcard .popout-row"),
   icWide:r(".ic-wide"), icPhone:r(".ic-phone"), clipped:[...document.querySelectorAll(".pane.on *, .listcol *")].filter(e=>{const b=e.getBoundingClientRect();if(!(b.width>0&&b.right>innerWidth+1&&getComputedStyle(e).position!=="fixed"))return false;for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){if(/auto|scroll/.test(getComputedStyle(p).overflowX))return false}return true}).slice(0,8).map(e=>e.tagName+"."+e.className+"@"+Math.round(e.getBoundingClientRect().right))});})()`;
(async () => {
  const chrome = spawn("google-chrome", ["--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--remote-debugging-port=0", "--user-data-dir=" + fs.mkdtempSync("/tmp/phone-prof-"), "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
  const port = await new Promise((res) => { let b = ""; chrome.stderr.on("data", (d) => { b += d; const m = /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/.exec(b); if (m) res(m[1]); }); });
  const tab = (await getJson(`http://127.0.0.1:${port}/json`)).find((t) => t.type === "page");
  const ws = new WebSocket(tab.webSocketDebuggerUrl); await new Promise((r) => { ws.onopen = r; });
  let id = 0; const pend = new Map(); const logs = [];
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
    if (d.method === "Runtime.exceptionThrown") logs.push((d.params.exceptionDetails.exception || {}).description || "exception"); };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (js) => { const r = await send("Runtime.evaluate", { expression: js, awaitPromise: true, returnByValue: true }); if (r.result.exceptionDetails) throw new Error("JS: " + r.result.exceptionDetails.exception.description.slice(0, 300) + " | " + js.slice(0, 60)); return r.result.result.value; };
  await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable");
  const host = new URL(base).hostname;
  await send("Network.setCookie", { name: cookie.split("=")[0], value: cookie.split("=")[1], domain: host, path: "/" });
  const out = { exceptions: logs };
  for (const w of widths) {
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: 844, deviceScaleFactor: 1, mobile: true });
    await send("Emulation.setTouchEmulationEnabled", { enabled: true });
    for (const [name, steps] of Object.entries(SCREENS)) {
      await send("Page.navigate", { url: base }); await sleep(600);
      await ev(`fetch("/__call?mode=${name.startsWith("call_") ? name.slice(5) : "none"}")`); await sleep(200);     // máy chủ giả: đổi cuộc gọi đang diễn ra
      await send("Page.navigate", { url: base }); await sleep(1800);
      const res = []; for (const js of steps) { res.push(await ev(js)); await sleep(700); }
      let m; try { m = JSON.parse(await ev(MEASURE)); } catch (e) { throw new Error(name + "@" + w + ": " + e.message + " url=" + (await ev("location.href"))); } m.steps = res;
      m.endVis = await ev(`getComputedStyle(document.querySelector("#callcard .end")||document.body).visibility`); m.topVis = await ev(`getComputedStyle(document.querySelector("#callcard .top")||document.body).visibility`);
      if (name === "call_video") {
        await ev(`document.querySelector("#vidwin .vvbox").click()`); await sleep(500);
        m.tapped = JSON.parse(await ev(`JSON.stringify({ui:document.getElementById("callcard").dataset.ui, end:getComputedStyle(document.querySelector("#callcard .end")).visibility, top:getComputedStyle(document.querySelector("#callcard .top")).visibility, endPe:getComputedStyle(document.querySelector("#callcard .end")).pointerEvents})`));
        await ev(`document.querySelector("#vidwin .vvbox").click()`); await sleep(500);
        m.tappedAgain = await ev(`getComputedStyle(document.querySelector("#callcard .end")).visibility`);
        await ev(`document.querySelector("#vidwin .vvbox").click()`); await sleep(5600);
        m.autoHide = await ev(`getComputedStyle(document.querySelector("#callcard .end")).visibility`);
      }
      if (name === "info") { m.afterBack = await ev(`(()=>{document.querySelector("#info .back").click();return document.getElementById("app").dataset.info})()`); }
      if (name === "chat") { await ev(`document.getElementById("btn-more").click()`); await sleep(300);
        m.moreMenu = await ev(`[...document.querySelectorAll(".pop button")].map(b=>b.textContent.trim())`); await ev(`document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}))`); await ev(`document.getElementById("msg-in").value="xin chào";document.getElementById("msg-in").dispatchEvent(new Event("input",{bubbles:true}))`); await sleep(300);
        m.typing = JSON.parse(await ev(`JSON.stringify({send:getComputedStyle(document.getElementById("btn-send")).display, tools:getComputedStyle(document.querySelector(".ctools")).display})`)); }
      out[name + "@" + w] = m;
    }
  }
  console.log(JSON.stringify(out)); ws.close(); chrome.kill(); process.exit(0);
})();
