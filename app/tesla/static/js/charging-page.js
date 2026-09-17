// charging-page.js — 充电记录页 (1/6): 页面底座 (菜单收起/$/esc/getJSON/金额与
// 分钟轴格式化) + 筛选状态 (?type=/?region=/?cost=/?range=/?from=&to= 初始
// 解析) + 查询参数拼装与 URL 同步。
// 由 index.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 index.html
// 里的顺序加载, 跨模块引用走全局); 记录卡片与分页在 charging-cards.js,
// 筛选交互在 charging-filters.js, 详情弹层在 charging-detail.js, 导航选单在
// charging-nav.js, 费用编辑在 charging-cost.js。
/* global FormatUtil */
/* exported $, esc, pad, fmtCardDate, fmtDur, num, fmtMinAxis, money, getJSON, PAGE,
           TIME_RANGES, state, detailCache, hasEcharts, sessionParams, syncURL */
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
/* ============================ 工具 ============================ */
const $ = (s, el) => (el || document).querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* 页面共用格式化 (format.js 先加载): 顶部解构, 下文沿用裸名 */
const { pad, fmtCardDate, fmtDur, num } = FormatUtil;

function fmtMinAxis(v) {
  if (v >= 60) { const h = Math.floor(v / 60), m = Math.round(v % 60); return m ? `${h}h${m}m` : `${h}h`; }
  return `${Math.round(v)}m`;
}
const money = v => v == null ? "—" : "¥" + Number(v).toFixed(2).replace(/\.?0+$/, "");

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/* ============================ 状态 ============================ */
const PAGE = 24;
/* ---------- 顶栏时间筛选: 快捷档位下拉, 编码进 ?range= (分享/刷新保留) ---------- */
const TIME_RANGES = [
  { v: "24h", days: 1, lb: "24小时" },
  { v: "7d", days: 7, lb: "近一周" },
  { v: "30d", days: 30, lb: "近一月" },
  { v: "180d", days: 180, lb: "近半年" },
  { v: "1y", days: 365, lb: "近一年" },
  { v: "all", days: 0, lb: "全部" },
];
function timeFrom(v) {   // 档位 → from 本地日期 (含今天共 N 天; 24h 即"昨天起")
  const r = TIME_RANGES.find(x => x.v === v);
  if (!r || !r.days) return null;
  const d = new Date(); d.setDate(d.getDate() - (r.days - 1));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
// URL → 初始筛选: ?range= 快捷档; ?from=&to= 自定义区间; ?type= / ?region= 筛选行
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const locParam = () => {   // ?region=省/市/区 (1~3 段, 脏参数丢弃)
  const segs = (qs0.get("region") || "").split("/").map(x => x.trim()).filter(Boolean);
  return segs.length && segs.length <= 3 && segs.every(x => x.length <= 30) ? segs.join("/") : "";
};
const state = {
  type: ["fast", "slow"].includes(qs0.get("type")) ? qs0.get("type") : "all",
  region: locParam(),
  cost: ["recorded", "missing"].includes(qs0.get("cost")) ? qs0.get("cost") : "all",
  range: range0, cFrom: cFrom0, cTo: cTo0,
  offset: 0, total: 0, loading: false, done: false, err: null,
};
const detailCache = new Map();
const hasEcharts = typeof echarts !== "undefined";

function rangeParams() {
  if (state.range === "custom") {   // 自定义起止 (日历)
    const p = {};
    if (state.cFrom) p.from = state.cFrom;
    if (state.cTo) p.to = state.cTo;
    return p;
  }
  const from = timeFrom(state.range);
  return from ? { from } : {};
}
function sessionParams(extra) {
  const p = new URLSearchParams({ type: state.type, cost: state.cost,
                                  ...rangeParams(), ...(extra || {}) });
  if (state.region) p.set("region", state.region);
  return p.toString();
}
function syncURL() {   // 筛选写进地址栏 (默认值不写, 链接保持干净)
  const u = new URL(location.href);
  if (state.range === "custom") {
    u.searchParams.delete("range");
    u.searchParams.set("from", state.cFrom); u.searchParams.set("to", state.cTo);
  } else {
    u.searchParams.delete("from"); u.searchParams.delete("to");
    if (state.range === "all") u.searchParams.delete("range");
    else u.searchParams.set("range", state.range);
  }
  if (state.type === "all") u.searchParams.delete("type"); else u.searchParams.set("type", state.type);
  if (state.region) u.searchParams.set("region", state.region); else u.searchParams.delete("region");
  if (state.cost === "all") u.searchParams.delete("cost"); else u.searchParams.set("cost", state.cost);
  history.replaceState(null, "", u);
}
