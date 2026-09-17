// stats-page.js — 充电统计页 (1/4): 页面底座 (菜单收起/$/esc/getJSON) + 金额与千分位格式化 +
// 时间筛选状态 (?range=/?from=&to= 初始解析, URL 同步) + 统计卡片行。
// 由 stats.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 stats.html
// 里的顺序加载, 跨模块引用走全局); 底座与总量类图表在 stats-chart-trend.js, 维度类图表在
// stats-chart-dimensions.js, 时间筛选 UI 与数据加载在 stats-time-filters.js。
/* global FormatUtil */
/* exported $, esc, pad, num, money, moneyInt, thousands, getJSON, TIME_RANGES,
           state, hasEcharts, statsParams, syncURL, summaryData, renderSummary */
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
const { pad, parseLocal, num } = FormatUtil;

const money = v => v == null ? "—" : "¥" + Number(v).toFixed(2).replace(/\.?0+$/, "");
const moneyInt = v => v == null ? "—" : "¥" + Math.round(v).toLocaleString("zh-CN");
const thousands = v => Math.round(v).toLocaleString("zh-CN");

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/* ============================ 状态 ============================ */
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
// URL → 初始筛选: ?range= 快捷档; ?from=&to= 自定义区间
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const state = { range: range0, cFrom: cFrom0, cTo: cTo0 };
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
function statsParams() { return new URLSearchParams(rangeParams()).toString(); }
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
  history.replaceState(null, "", u);
}

/* ============================ 统计卡片 ============================ */
let summaryData = null;   // 起充 SOC / 峰值功率图要算"未知"次数 (总次数 - 进档次数)

function renderSummary(s) {
  summaryData = s;
  const months = s.first_date && s.last_date ?
    (parseLocal(s.last_date + " 00:00").getFullYear() * 12 + parseLocal(s.last_date + " 00:00").getMonth()) -
    (parseLocal(s.first_date + " 00:00").getFullYear() * 12 + parseLocal(s.first_date + " 00:00").getMonth()) + 1 : 1;
  const fastPct = s.sessions ? Math.round(s.fast_sessions / s.sessions * 100) : 0;
  const cards = [
    { lb: "充电次数", val: thousands(s.sessions), sub: months > 1 ? `月均 ${Math.round(s.sessions / months)} 次` : "" },
    { lb: "总充电量", val: thousands(s.energy_used || s.energy_added), unit: "kWh", sub: `表计口径` },
    { lb: "总费用", val: moneyInt(s.cost), sub: s.first_date ? `${s.first_date.replace(/-/g, "/")} 起` : "" },
    { lb: "平均电价", val: s.price_per_kwh == null ? "—" : "¥" + s.price_per_kwh.toFixed(3), unit: "/kWh", sub: "按表计电量" },
    { lb: "快充占比", val: fastPct + "%", sub: `快充 ${s.fast_sessions} 次` },
    { lb: "充电时长", val: num(s.duration_min / 60, 1), unit: "小时", sub: s.range_gain ? `≈ ${thousands(s.range_gain)} km 续航` : "" },
  ];
  $("#stats-row").innerHTML = cards.map(c => `
    <div class="stat">
      <div class="lb">${esc(c.lb)}</div>
      <div class="val">${c.val}${c.unit ? `<small>${c.unit}</small>` : ""}</div>
      ${c.sub ? `<div class="sub">${esc(c.sub)}</div>` : ""}
    </div>`).join("");
}
