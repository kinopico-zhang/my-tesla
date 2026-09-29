// view/trips-list-page.js — 行程列表视图 (壳版 1/6): 底座 —— 筛选状态
// (state, 偏好持久化进 shellState.filters.trips; 时间档是筛选条全局 chip) +
// 行程卡片渲染与尾部状态 + 视图生命周期 (registerView: 首进才拉列表/
// 起终点树/预载地图引擎, 离开时收弹层/掐在途打开/退多选)。
// 旧版 (js/trips-list-page.js) 的 $/esc/格式化解构/getJSON/toast 全部上移
// 壳公共件; TIME_RANGES/日历/URL 解析删 (tesla-shell; 时间档模块 3.3.0 已随筛选下线);
// 文件名沿用旧名 (命名普查按 basename 折叠, 旧页与壳版同名不同目录)。
/* global $, esc, num, fmtCardDate, fmtDur, shellState, saveShell,
          registerView, bindGestures, loadMore, pickCard, openTrip, openDrvPick,
          PRELOAD_PX, exitSelect, closeTrip, hideSheet, curKey, rec,
          sheetFrom: writable, stopRecExport, ensureAMap, trFetchRegions,
          bumpOpenSeq */
/* exported postJSON, TR_PAGE, KM_BUCKETS, state, trackCache, driversCache,
            items, listEl, tailEl, renderCard, marqueeCards, setTail,
            refreshList, trSaveFilters, sheetFrom */   // sheetFrom 只写不清 (离开视图清宿主), exported 豁免
"use strict";

/* postJSON: 驾驶员标注等写操作用 (trips-sheet-driver.js); tesla-common 只
   收了读路径, 写路径留在这 (旧页同款) */
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
  return r.json();
}

const TR_PAGE = 24;   // 每页条数 (旧名 PAGE 与充电视图撞, 壳内改 TR_PAGE)

/* 里程档位: 筛选条 chip 用, 请求时换算成 km_min/km_max */
const KM_BUCKETS = [
  { v: "all", lb: "全部", min: null, max: null },
  { v: "0-20", lb: "20km 内", min: 0, max: 20 },
  { v: "20-100", lb: "20–100km", min: 20, max: 100 },
  { v: "100-300", lb: "100–300km", min: 100, max: 300 },
  { v: "300+", lb: "300km 以上", min: 300, max: null },
];

/* 筛选偏好: 上次用过的住 localStorage (时间筛选 3.3.0 下线, 不在筛选之列) */
const savedTr = shellState.filters.trips || {};
const state = {
  fromLoc: typeof savedTr.fromLoc === "string" ? savedTr.fromLoc : "",
  toLoc: typeof savedTr.toLoc === "string" ? savedTr.toLoc : "",
  km: KM_BUCKETS.some(b => b.v === savedTr.km) ? savedTr.km : "all",
  drvId: Number.isInteger(savedTr.drvId) ? savedTr.drvId : null,
  offset: 0, total: 0, loading: false, done: false, err: null,
};
function trSaveFilters() {
  shellState.filters.trips =
    { fromLoc: state.fromLoc, toLoc: state.toLoc, km: state.km, drvId: state.drvId };
  saveShell();
}

const trackCache = new Map();       // id → {pts, ts} 全精度轨迹
let driversCache;   // 驾驶员表 (undefined=还没拉过, null=失败, 数组=结果), 筛选条与弹层共用
const items = [];                   // 已加载卡片数据 (与 #list 子元素一一对应, 多选用)

const listEl = $("#list");

/* ============================ 行程列表 (单列) ============================ */
/* 起终点短地名 (用户点名改口径): 只看省市区链, 取「城市 + 最小行政级」
   —— 链是 [省, 市, 区] 取后两段 (市 · 区), [省, 市] 取市, 地名 (POI) 不再
   混进来; 解析不出链 (如直辖市旧数据) 退回整链 (from/to 是洗过的)。
   充电列表的 fmtPlaceShort 是另一套 (区 · 地名), 互不相扰 */
function shortPlace(region, full) {
  const seg = (region || "").split(" · ").filter(Boolean);
  const pp = seg.length >= 3 ? seg.slice(-2) : seg.slice(-1);
  return pp.length ? pp.join(" · ") : full;
}

function renderCard(it) {
  const el = document.createElement("article");
  el.className = "card-t"; el.dataset.id = it.id;
  const fromP = shortPlace(it.from_region, it.from);
  const toP = shortPlace(it.to_region, it.to);
  el.innerHTML = `
    <div class="ct-top">
      <span class="ct-date">${esc(fmtCardDate(it.start))}</span>
      ${it.driver ?   /* 驾驶员 pill 点一下直选标注 (用户点名, 不用进详情) */
        `<span class="ct-drv${it.driver_id != null ? "" : " def"}">${esc(it.driver)}</span>` : ""}
      <span class="pick" aria-hidden="true"></span>
    </div>
    <div class="ct-cells">
      <div class="ct-cell"><div class="lb">里程</div>
        <div class="val">${it.km != null ? num(it.km) + "<small>km</small>" : "—"}</div></div>
      <div class="ct-cell"><div class="lb">时长</div><div class="val">${fmtDur(it.min)}</div></div>
      ${it.kwh != null ? `<div class="ct-cell"><div class="lb">总电耗</div>
        <div class="val">${num(it.kwh)}<small>kWh</small></div></div>` : ""}
    </div>
    <div class="ct-addr mq-line"><span class="mq-run"><i class="dot f"></i>${esc(fromP)}<span class="arr">→</span><i class="dot t"></i>${esc(toP)}</span></div>`;
  el.addEventListener("click", e => {
    if (e.target.closest(".ct-drv")) { openDrvPick(it); return; }   // 驾驶员直选
    if (document.body.classList.contains("selecting")) pickCard(el);
    else openTrip(it);
  });
  return el;
}

/* 起终点一行 (用户点名): 放得下静止, 放不下挂 .marquee 来回滚 —— 音乐
   迷你条同款, 两端各停一拍 (10% 行程) 再往回走。卡片进 DOM 后量宽;
   转屏/改窗口行宽变了要重量 (防抖)。列表没显示时量不出宽, 跳过不挂。 */
function marqueeCards() {
  for (const line of listEl.querySelectorAll(".mq-line")) {
    const run = line.querySelector(".mq-run");
    run.classList.remove("marquee");
    if (!line.clientWidth) continue;         // 视图藏着 (display:none): 量不出
    const over = run.scrollWidth - line.clientWidth;
    if (over <= 2) continue;                 // 放得下: 不滚
    run.style.setProperty("--mq-dx", `${-over}px`);
    run.style.setProperty("--mq-dur", `${Math.max(8, over / 18)}s`);
    run.classList.add("marquee");
  }
}
let mqTimer = 0;
addEventListener("resize", () => {
  clearTimeout(mqTimer);
  mqTimer = setTimeout(marqueeCards, 200);
});

/* 尾部 id 加 tr- 前缀: 壳里统计视图已占了 errbox/errmsg/retry/loader-spin
   (P3 先到先得), 行程这边的同名者让路 */
const tailEl = $("#tr-tail");
function setTail() {
  tailEl.hidden = state.total === 0 && !state.loading && state.done && !state.err;
  $("#tr-loader-spin").hidden = !state.loading;
  $("#tr-endnote").hidden = !(state.done && state.total > 0);
  $("#tr-empty").hidden = !(state.done && state.total === 0 && !state.err);
  $("#tr-errbox").hidden = !state.err;
  $("#count-badge").textContent = state.total ? `共 ${state.total} 次` : "";
}

const trScroll = $("#tr-scroll");

/* ---------- 整页刷新 (下拉刷新/换车/换时间档都走这) ---------- */
async function refreshList() {
  if (state.loading) return;
  items.length = 0;
  listEl.innerHTML = "";
  state.offset = 0; state.total = 0; state.done = false; state.err = null;
  await loadMore();
  trScroll.scrollTo({ top: 0 });
}

/* 懒加载: 触底前 PRELOAD_PX 预加载下一页 (壳公共件 tesla-paged-list 的
   常量, 值同款 800px; 视图藏起时 display:none 不相交, 观察器常驻无害) */
new IntersectionObserver(es => {
  if (es[0].isIntersecting) loadMore();
}, { rootMargin: PRELOAD_PX + "px" }).observe(tailEl);

$("#tr-retry").addEventListener("click", () => { state.err = null; loadMore(); });

/* 手势: 列表滚动器在顶下拉刷新 */
bindGestures(trScroll, { drawer: true, ptr: true, onRefresh: refreshList });

/* ============================ 生命周期 ============================ */
let trBooted = false;
function trBoot() {          // 首次进视图: 拉首页列表, 起终点树异步拉 (失败
  trBooted = true;           // 不阻塞), 后台预载地图引擎脚本
  trFetchRegions();
  loadMore().then(() => { ensureAMap().catch(() => {}); });
}

registerView("trips", {
  title: "行程轨迹",
  el: $("#view-trips"),
  show() { if (!trBooted) trBoot(); },
  /* 离开视图要收干净: 掐在途的打开与流式下载 (bumpOpenSeq 让所有 seq
     检查失效) / 导出录制 / 弹层 (含地址栏镜像) / 多选态 */
  hide() {
    bumpOpenSeq();
    sheetFrom = null;   // 主动离开行程视图 (底栈换页等): 关弹层不再拽回分组页
    if (rec) stopRecExport(true);
    if (curKey != null) closeTrip();
    else if ($("#sheet").classList.contains("show")) hideSheet();
    if (document.body.classList.contains("selecting")) exitSelect();
  },
  refresh: refreshList,
});
