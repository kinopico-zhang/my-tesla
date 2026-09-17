// trips-list-page.js — 行程页 (1/6): 底座 —— 页签菜单点空白收起 / $ / esc /
// getJSON / postJSON, 筛选状态初始解析 (?range= / ?from=&to= / ?from_loc= /
// ?to_loc= / ?km= / ?driver_id= → state), 行程卡片渲染与整页刷新。
// 由 trips-list.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// trips.html 里的顺序加载, 跨模块引用走全局); 续载与地址栏在
// trips-list-url.js, 时间日历在 trips-list-time-filters.js, 筛选行在
// trips-list-region-filters.js, 多选在 trips-list-select.js, 分组在
// trips-list-groups.js, 弹层/播放在 trips-sheet-*.js / trips-playback-*.js
// (后加载, 事件回调里引用这里的函数与状态)。
/* global FormatUtil, openTrip, pickCard, loadMore */
/* exported $, esc, pad, fmtCardDate, fmtDur, num, getJSON, postJSON, PAGE,
   TIME_RANGES, timeFrom, KM_BUCKETS, state, trackCache, driversCache, items,
   listEl, tailEl, renderCard, setTail */
"use strict";
/* 页签菜单: 点空白处收起。
   注意: 级联菜单钻取会在点击处理器里 innerHTML 重渲染, 事件目标被脱链
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
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* 页面共用格式化 (format.js 先加载): 顶部解构, 下文沿用裸名。
   postJSON/trackCache 本页不用, 供后加载的弹层/播放模块 (trips-sheet-*.js / trips-playback-*.js) 引用。 */
const { pad, fmtCardDate, fmtDur, num } = FormatUtil;

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
  return r.json();
}

/* ============================ 行程列表 (单列) ============================ */
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
const KM_BUCKETS = [   // 里程档位: URL 里存档位码, 请求时换算成 km_min/km_max
  { v: "all", lb: "全部", min: null, max: null },
  { v: "0-20", lb: "20km 内", min: 0, max: 20 },
  { v: "20-100", lb: "20–100km", min: 20, max: 100 },
  { v: "100-300", lb: "100–300km", min: 100, max: 300 },
  { v: "300+", lb: "300km 以上", min: 300, max: null },
];
// URL → 初始筛选: ?range= 快捷档; ?from=&to= 自定义区间; ?from_loc=/?to_loc=/?km= 筛选行
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const locParam = k => {   // ?from_loc=省/市/区 (1~3 段, 脏参数丢弃)
  const segs = (qs0.get(k) || "").split("/").map(s => s.trim()).filter(Boolean);
  return segs.length && segs.length <= 3 && segs.every(s => s.length <= 30) ? segs.join("/") : "";
};
const state = { range: range0, cFrom: cFrom0, cTo: cTo0,
                fromLoc: locParam("from_loc"), toLoc: locParam("to_loc"),
                km: KM_BUCKETS.some(b => b.v === qs0.get("km")) ? qs0.get("km") : "all",
                drvId: /^\d+$/.test(qs0.get("driver_id") || "") ? +qs0.get("driver_id") : null,
                offset: 0, total: 0, loading: false, done: false, err: null };
const trackCache = new Map();       // id → {pts, ts} 全精度轨迹
let driversCache;   // 设置页驾驶员表 (undefined=还没拉过, null=失败, 数组=结果), 筛选行与弹层共用
const items = [];                   // 已加载卡片数据 (与 #list 子元素一一对应, 多选用)

const listEl = $("#list");

function renderCard(it) {
  const el = document.createElement("article");
  el.className = "card-t"; el.dataset.id = it.id;
  const avg = it.km != null && it.min ? Math.round(it.km / (it.min / 60)) : null;
  el.innerHTML = `
    <div class="ct-top">
      <span class="ct-date">${esc(fmtCardDate(it.start))}</span>
      ${it.driver ?   /* 有驾驶员就上卡: 显式标注正常亮, 默认兜底弱化 .def */
        `<span class="ct-drv${it.driver_id != null ? "" : " def"}">${esc(it.driver)}</span>` : ""}
      <span class="ct-arrow">→ 查看轨迹</span>
      <span class="pick" aria-hidden="true"></span>
    </div>
    <div class="ct-cells">
      <div class="ct-cell"><div class="lb">里程</div>
        <div class="val">${it.km != null ? num(it.km) + "<small>km</small>" : "—"}</div></div>
      <div class="ct-cell"><div class="lb">时长</div><div class="val">${fmtDur(it.min)}</div></div>
      ${it.kwh != null ? `<div class="ct-cell"><div class="lb">总电耗</div>
        <div class="val">${num(it.kwh)}<small>kWh</small></div></div>` : ""}
    </div>
    <div class="ct-addr">
      <div class="line from"><i class="dot"></i><span class="txt">${esc(it.from)}</span></div>
      <div class="line to"><i class="dot"></i><span class="txt">${esc(it.to)}</span></div>
    </div>
    <div class="ct-sub">${avg ? `均速 ${avg} km/h` : ""}${avg && it.wh_per_km != null ? " · " : ""}${it.wh_per_km != null ? `平均电耗 ${num(it.wh_per_km, 0)} Wh/km` : ""}</div>`;
  el.addEventListener("click", () => {
    if (document.body.classList.contains("selecting")) pickCard(el);
    else openTrip(it);
  });
  return el;
}

const tailEl = $("#tail");
function setTail() {
  tailEl.hidden = state.total === 0 && !state.loading && state.done && !state.err;
  $("#loader-spin").hidden = !state.loading;
  $("#endnote").hidden = !(state.done && state.total > 0);
  $("#empty").hidden = !(state.done && state.total === 0 && !state.err);
  $("#errbox").hidden = !state.err;
  $("#count-badge").textContent = state.total ? `共 ${state.total} 次` : "";
}

/* ---------- 刷新: 顶栏按钮 (下拉手势已按需求撤掉) ---------- */
async function refreshList() {
  if (state.loading) return;
  items.length = 0;
  listEl.innerHTML = "";
  state.offset = 0; state.total = 0; state.done = false; state.err = null;
  await loadMore();
  window.scrollTo({ top: 0 });
}

$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await refreshList();
  btn.classList.remove("busy");
});
