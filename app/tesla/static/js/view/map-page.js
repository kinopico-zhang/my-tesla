// view/map-page.js — 足迹地图视图 (壳版 1/5): 底座 —— 诊断探针回传 +
// 驾驶员筛选状态 (?driver_id= 深链加载期抠出, 偏好持久化进
// shellState.filters.map) + 道路层状态族 (清单 / 拟合行 / 格计数 /
// 本地 IndexedDB 句柄) + 本地筛选 (清单行 c/d × 车/驾驶员, 不再按筛选
// 请求服务端; 时间筛选 3.3.0 下线, 全时段) + 取数参数拼装 (汇总用) +
// 错误占位 + 汇总行 (加载/下载进度条 2026-09-29 拆: 与图例重叠, 边下边
// 画本就增量展示, 不需要进度反馈)。
// 2026-09-29 起只画「走过的路」: 原始轨迹层退役 (全精度内存库/本地轨迹
// 仓/抽稀细化档整链拆净), 清单里没拟合到的程等 worker 拟合好再出现。
// 旧版 (js/map-page.js) 的菜单收起/$/getJSON/esc/pad/TIME_RANGES/日历/
// URL 同步全删 (壳公共件接管); 高德脚本加载器也撤了
// (tesla-map-adapter 的 mapLib 统一装引擎, 服务商可切); 文件名沿用旧名
// (命名普查按 basename 折叠, 旧页与壳版同名不同目录)。
/* global $, shellState, saveShell */
/* exported PAGE_V, ROAD_FMT_V, diag, drvId, fpDefaultDrv, map, overlays,
           mapReady, manifest, manifestIdx, localDb,
           tracks, tracksById, linesById, renderGen,
           roadsById, roadCellsById, roadCells, roadMax,
           fpRowVisible, fpVisibleTracks, fpPlaying, fpViewOn,
           trackParams, showError, renderStats, writeStats, fpRestoreStats,
           fpSaveFilters */
"use strict";
const PAGE_V = "v19";     // 页面版本: 诊断时确认浏览器是否在跑最新代码
const ROAD_FMT_V = 3;     // 道路算法版本 (= 服务端 ROAD_FIT_V; v3=原始轨迹桥接, 不符清 fp_roads 重下)

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

let map = null, overlays = [], mapReady = false;
/* 驾驶员筛选 (null = 全部): URL 深链优先 (加载期抠出, app-boot 洗参前),
   否则上次存的偏好; 表里已删的驾驶员首进时还会再校验一道 */
const fpQs0 = new URLSearchParams(location.search);
const savedFp = shellState.filters.map || {};
let drvId = /^\d+$/.test(fpQs0.get("driver_id") || "") ? +fpQs0.get("driver_id")
  : Number.isInteger(savedFp.drvId) ? savedFp.drvId : null;
let fpDefaultDrv = false;   // 当前筛选是否默认驾驶员 (未标注的轨迹也算 TA 的)
function fpSaveFilters() {
  shellState.filters.map = { drvId: drvId };
  saveShell();
}

/* ---------- 道路层状态族: 清单驱动, 拟合行在内存 + 本地库 ---------- */
let manifest = null;          // 全量清单 {v, tracks: [{id, n, d, c, t}]}
let manifestIdx = new Map();  // id → 清单行
let localDb;                  // undefined=还没开过, null=不可用(内存模式), IDB=就绪

let tracks = [];              // 当前筛选后的道路对象 (渲染集)
let tracksById = new Map();   // id → 道路对象 (点击信息/换画遍历用)
let linesById = new Map();    // id → 当前的折线组 (跨 15 级换画时逐程替换)
let renderGen = 0;            // 渲染代号: 切换筛选时作废进行中的批次
let fpPlaying = false;        // 时间回放中 (2026-10-01 播放钮, map-roads-playback):
                              // 正常渲染整链让路 (renderTracks 出口钩否决回放 /
                              // appendIfVisible 照画但藏起 / redrawRoads /
                              // roadsViewportSync 跳过), 收场由回放层 show()
                              // 瞬时亮回正常层 (整版重建只在进场时渲染在途)
let fpViewOn = false;         // 足迹地图视图当前在前台 (map-filters 的 show/hide
                              // 维护): 首次同步收尾的自动开播只趁人在看时起 —
                              // 回放兼作加载动画 (2026-10-02 用户点名「打开行程
                              // 地图…自动播放的时候可以用来加载数据」)

/* 格计数 (渲染上热力色阶的底): roadsById 本地就绪的拟合行 (补上 date/min
   后即渲染层对象); roadCellsById 每程的格键序列 (下载一条建一条); roadCells
   当前筛选的合并计数 (格键 → packStat, 换筛选只重算合并不再请求); roadMax
   其中最重的格计数 —— 连续色阶的上限 (图例右端, 对数刻度的 1 端)。 */
let roadsById = new Map();      // id → 拟合道路行 (pts, km, date, min)
let roadCellsById = new Map();  // id → 该程格键序列 (有序连续去重)
let roadCells = new Map();      // 格键 → packStat (次数×16384 + 天序)
let roadMax = 0;                // 当前筛选最重格计数 (色阶上限)

function fpRowVisible(row) {   // 清单行 × 当前筛选 (纯本地判断, 不发请求)
  if (shellState.carId != null && row.c !== shellState.carId) return false;
  if (drvId != null && !(row.d === drvId || (fpDefaultDrv && row.d == null))) return false;
  return true;
}

function fpVisibleTracks() {   // 清单序 (日期升序) 里筛出且已就绪的路
  if (!manifest) return [];
  const out = [];
  for (const row of manifest.tracks)
    if (fpRowVisible(row)) {
      const t = roadsById.get(row.id);
      if (t) out.push(t);
    }
  return out;
}

function trackParams() {   // 车 + 驾驶员 (汇总端点同口径; 时间不筛, 全时段)
  const p = new URLSearchParams();
  if (shellState.carId != null) p.set("car_id", String(shellState.carId));
  if (drvId != null) p.set("driver_id", String(drvId));
  return "?" + p;
}

function showError(msg) {
  $("#fp-error").hidden = false;
  $("#fp-error-text").textContent = msg || "加载失败";
}

let fpStatsLast = null;   // 最近一次服务端汇总 (回放收场还原两格用)
function writeStats(s) {  // 两格写数 (renderStats 与回放联动共用同一排版)
  $("#st-km").innerHTML = Number(s.distance_km).toLocaleString() + "<small>km</small>";
  $("#st-hours").innerHTML = (s.duration_min / 60).toFixed(1) + "<small>小时</small>";
}

function renderStats(s) {
  /* 两格 (2026-09-29 用户点名「不需要显示行程数量, 就显示里程和时长就行
     了」—— 原三格并排太挤, 里程/时长的数字溢出格子) */
  fpStatsLast = s;             // 存档: 回放联动改写两格, 收场从这里还原
  $("#fp-stats").hidden = false;
  writeStats(s);
}

function fpRestoreStats() {   // 回放收场: 两格还原服务端汇总口径 (联动只借不改)
  if (fpStatsLast) writeStats(fpStatsLast);
}

/* 汇总两数走 summary 端点的筛选口径 (fpSync 每轮现拉): 平移/缩放不动
   它 —— 2026-09-29 用户点名「足迹地图和充电地图的逻辑是不一样的,
   不用联动」(此前照充电地图抄了视野内口径, 平移缩放数字跟着跳)。 */
