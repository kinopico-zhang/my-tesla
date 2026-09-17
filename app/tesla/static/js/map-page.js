// map-page.js — 足迹地图页 (1/5): 页面底座 (菜单收起/$/诊断探针回传) +
// 时间与驾驶员筛选状态 (?range=/?from=&to=/?driver_id= 初始解析) + 取数底座
// (getJSON/参数拼装/高德加载器/加载错误占位) + 汇总行。
// 由 map.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 map.html
// 里的顺序加载, 跨模块引用走全局); 轨迹绘制与选中在
// map-tracks-render.js, 缩放渐进细化在 map-tracks-refine.js, 数据刷新与地图启动在
// map-boot.js, 时间/驾驶员筛选 UI 与收尾在 map-filters.js。
/* exported $, PAGE_V, diag, TIME_RANGES, pad, timeSel, drvId, tracks, tracksById,
           coarseById, detailLines, detailBand, detailCache, renderGen,
           detailSeq, refineTimer, fullCache, map, overlays, selected,
           selectedId, mapReady, getJSON, rangeParams, trackParams, loadAMap,
           showLoading, showError, renderStats */
"use strict";
/* 页签菜单: 点空白处收起。
   注意: 日历点选会在点击处理器里 innerHTML 重渲染, 事件目标被脱链
   (closest() 找不到菜单祖先) —— 脱链的点击一定发生在某个菜单里, 不能当"点外面"关闭。 */
document.addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});
const $ = s => document.querySelector(s);
const PAGE_V = "v11";   // 页面版本: 诊断时确认浏览器是否在跑最新代码

/* ---------- 诊断探针: 浏览器端异常/高德请求失败自动回传服务端日志 ---------- */
let diagCount = 0;
function diag(stage, extra) {
  if (diagCount++ > 40) return;
  try {
    fetch("/tesla/map/api/diag", {
      method: "POST", headers: { "Content-Type": "application/json" },
      keepalive: true,
      body: JSON.stringify(Object.assign({ stage, ua: navigator.userAgent.slice(0, 100) }, extra)),
    }).catch(() => {});
  } catch (e) { /* 探针自身绝不能影响页面 */ }
}
window.addEventListener("error", e => diag("window_error",
  { msg: ((e.message || "") + " @" + (e.filename || "") + ":" + (e.lineno || 0)).slice(0, 300) }));
window.addEventListener("unhandledrejection", e => diag("promise_rejection",
  { msg: String((e.reason && e.reason.message) || e.reason || "").slice(0, 300) }));
(function patchConsole() {
  for (const lvl of ["error", "warn"]) {
    const orig = console[lvl].bind(console);
    console[lvl] = (...args) => {
      diag("console_" + lvl, { msg: args.map(a => String((a && a.message) || a)).join(" | ").slice(0, 400) });
      orig(...args);
    };
  }
})();
(function patchNetwork() {  // 捕获高德请求的真实失败 (状态码 + 响应体)
  const origFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    return origFetch(url, opts).then(r => {
      if (r.status >= 400 && String(url).includes("amap.com"))
        diag("amap_fetch_" + r.status, { url: String(url).slice(0, 250) });
      return r;
    }).catch(e => {
      if (String(url).includes("amap.com"))
        diag("amap_fetch_err", { url: String(url).slice(0, 250), err: String(e).slice(0, 150) });
      throw e;
    });
  };
  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.addEventListener("load", () => {
      if (this.status >= 400 && String(url).includes("amap.com"))
        diag("amap_xhr_" + this.status,
             { url: String(url).slice(0, 250), resp: String(this.responseText || "").slice(0, 250) });
    });
    return origOpen.call(this, method, url, ...rest);
  };
})();

let map = null, overlays = [], selected = null, selectedId = null, mapReady = false;
/* ---------- 顶栏时间筛选: 快捷档位下拉, 编码进 ?range= (分享/刷新保留) ---------- */
const TIME_RANGES = [
  { v: "24h", days: 1, lb: "24小时" },
  { v: "7d", days: 7, lb: "近一周" },
  { v: "30d", days: 30, lb: "近一月" },
  { v: "180d", days: 180, lb: "近半年" },
  { v: "1y", days: 365, lb: "近一年" },
  { v: "all", days: 0, lb: "全部" },
];
const pad = n => String(n).padStart(2, "0");
const fmtDate = d => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());

function timeFrom(v) {   // 档位 → from 本地日期 (含今天共 N 天; 24h 即"昨天起")
  const r = TIME_RANGES.find(x => x.v === v);
  if (!r || !r.days) return null;
  const d = new Date(); d.setDate(d.getDate() - (r.days - 1));
  return fmtDate(d);
}
// URL → 初始时间: ?range= 快捷档; ?from=&to= 自定义区间
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const timeSel = { v: range0, from: cFrom0, to: cTo0 };
let drvId = /^\d+$/.test(qs0.get("driver_id") || "") ? +qs0.get("driver_id") : null;
                                             // 驾驶员筛选 (null = 全部), URL 深链可带
let tracks = [];                  // 当前筛选后的粗轨迹对象
let tracksById = new Map();       // id → 粗轨迹对象 (点击信息用)
let coarseById = new Map();       // id → 粗线 Polyline
let detailLines = new Map();      // id → 细化线 Polyline (替换粗线)
let detailBand = null;            // 当前细化档位: null / 13 / 14 / 15
let detailCache = new Map();      // 档位 → Map(id → {box, pts})
let renderGen = 0;                // 渲染代号: 切换筛选时作废进行中的批次
let detailSeq = 0;                // 作废在途的细化请求
let refineTimer = null;
let fullCache = new Map();        // id → 全精度 pts (点过的轨迹单独全取, 永不降级)

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ("HTTP " + r.status));
  return r.json();
}

function rangeParams() {
  if (timeSel.v === "custom")   // 自定义起止 (日历)
    return `?from=${timeSel.from}&to=${timeSel.to}`;
  const from = timeFrom(timeSel.v);
  return from ? "?from=" + from : "";
}
function trackParams() {        // 时间 + 驾驶员一起拼 (tracks/summary 同口径)
  const p = rangeParams();
  return drvId == null ? p : p + (p ? "&" : "?") + "driver_id=" + drvId;
}

function loadAMap(key, securityCode) {
  return new Promise((resolve, reject) => {
    if (securityCode) window._AMapSecurityConfig = { securityJsCode: securityCode };
    const s = document.createElement("script");
    s.src = "https://webapi.amap.com/maps?v=2.0&key=" + encodeURIComponent(key);
    s.onload = () => resolve();
    s.onerror = () => { diag("amap_script_fail", { src: s.src.slice(0, 120) });
                        reject(new Error("高德地图脚本加载失败, 请检查网络")); };
    document.head.appendChild(s);
  });
}

function showLoading(on, text) {
  $("#loading").hidden = !on;
  if (text) $("#loading-text").textContent = text;
}
function showError(msg) {
  $("#error").hidden = false;
  $("#error-text").textContent = msg || "加载失败";
}

function renderStats(s) {
  $("#stats").hidden = false;
  $("#st-drives").textContent = Number(s.drives).toLocaleString();
  $("#st-km").innerHTML = Number(s.distance_km).toLocaleString() + "<small>km</small>";
  $("#st-hours").innerHTML = (s.duration_min / 60).toFixed(1) + "<small>小时</small>";
}
