// chargemap-page.js — 充电地图页 (1/3): 页面底座 (菜单收起/$/getJSON) +
// 三视图与热力梯度定义 + URL 初始筛选状态 (?range=/?from=&to=/?view=) +
// 高德脚本加载器与加载/错误占位。
// 由 chargemap.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// chargemap.html 里的顺序加载, 跨模块引用走全局); 热力渲染在
// chargemap-heatmap.js, 时间筛选/日历/收尾在 chargemap-time-filters.js。
/* exported $, VIEWS, GRADIENT, PICK_PX, TIME_RANGES, pad, timeSel, view,
           map, heatmap, pickMark, locations, getJSON, rangeParams, loadAMap,
           showLoading, showError */
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

/* ---------- 三视图: 热力权重度量 ---------- */
const VIEWS = {
  energy:   { lb: "充电电量", fmt: v => Math.round(v) + " kWh" },
  sessions: { lb: "充电次数", fmt: v => v + " 次" },
  cost:     { lb: "充电费用", fmt: v => "¥" + Math.round(v) },
};
/* 热力梯度: 蓝 → 绿 → 黄 → 橙 → 红 (值越高越红), 图例梯度条用同一组色 */
const GRADIENT = { 0.2: "#3987e5", 0.45: "#1fa349", 0.65: "#d9b13c", 0.82: "#e08a3c", 1: "#e5484d" };
const PICK_PX = 36;    // 点击就近取点半径 (像素)

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
// URL → 初始状态: ?range= 快捷档; ?from=&to= 自定义区间; ?view= 三视图
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const timeSel = { v: range0, from: cFrom0, to: cTo0 };
let view = VIEWS[qs0.get("view")] ? qs0.get("view") : "energy";

let map = null, heatmap = null, pickMark = null, locations = [];

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

function loadAMap(key, securityCode) {
  return new Promise((resolve, reject) => {
    if (securityCode) window._AMapSecurityConfig = { securityJsCode: securityCode };
    const s = document.createElement("script");
    s.src = "https://webapi.amap.com/maps?v=2.0&plugin=AMap.HeatMap&key=" + encodeURIComponent(key);
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("高德地图脚本加载失败, 请检查网络"));
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
