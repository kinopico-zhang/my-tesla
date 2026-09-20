// view/map-page.js — 足迹地图视图 (壳版 1/5): 底座 —— 诊断探针回传 +
// 驾驶员筛选状态 (?driver_id= 深链加载期抠出, 偏好持久化进
// shellState.filters.map; 时间档上移抽屉全局) + 轨迹库状态族 (清单 /
// 全精度内存库 / 本地 IndexedDB 句柄) + 本地筛选 (清单行 t/c/d × 时间/
// 车/驾驶员, v4 起不再按筛选请求服务端) + 取数参数拼装 (汇总用) +
// 加载/错误/下载进度占位 + 汇总行。
// 旧版 (js/map-page.js) 的菜单收起/$/getJSON/esc/pad/TIME_RANGES/日历/
// URL 同步全删 (壳公共件与 tesla-time-range 接管); 高德脚本加载器也撤了
// (tesla-map-adapter 的 mapLib 统一装引擎, 服务商可切); 文件名沿用旧名
// (命名普查按 basename 折叠, 旧页与壳版同名不同目录)。
/* global $, shellState, saveShell, timeRangeParams */
/* exported PAGE_V, FP_FMT_V, diag, drvId, fpDefaultDrv, map, overlays, selected,
           selectedId, mapReady, manifest, manifestIdx, allById, localDb,
           tracks, tracksById, coarseById, detailLines, detailBand, detailTier,
           renderGen, refineTimer, fullIds, fpRowVisible, fpVisibleTracks,
           trackParams, showLoading, showError, showProgress, renderStats,
           fpSaveFilters */
"use strict";
const PAGE_V = "v13";   // 页面版本: 诊断时确认浏览器是否在跑最新代码
const FP_FMT_V = 5;     // 轨迹格式版本 (= 服务端 CACHE_VERSION, 不符清本地库重下)

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

/* ---------- 轨迹库状态族: 清单驱动, 全精度本体在内存 + 本地库 ---------- */
let manifest = null;          // 全量清单 {v, tracks: [{id, n, d, c, t}]}
let manifestIdx = new Map();  // id → 清单行
let allById = new Map();      // id → 全精度轨迹 (下载一条进一条; 本地库镜像)
let localDb;                  // undefined=还没开过, null=不可用(内存模式), IDB=就绪

let tracks = [];              // 当前筛选后的轨迹对象 (渲染集)
let tracksById = new Map();   // id → 轨迹对象 (点击信息用)
let coarseById = new Map();   // id → 概览线 Polyline (~40 点/条)
let detailLines = new Map();  // id → 细化线 Polyline (替换概览线)
let detailBand = null;        // 当前细化档位: null / 13 / 14 / 15
let detailTier = new Map();   // id → 该轨迹已画到哪档 (per 值; 换档按它增量升/降)
let renderGen = 0;            // 渲染代号: 切换筛选时作废进行中的批次
let refineTimer = null;
let fullIds = new Set();      // 选中过的轨迹 (已按全精度画), 永不降级

function fpRowVisible(row) {   // 清单行 × 当前筛选 (纯本地判断, 不发请求)
  if (shellState.carId != null && row.c !== shellState.carId) return false;
  const p = timeRangeParams();
  if (p.from && row.t < p.from) return false;
  if (p.to && row.t > p.to) return false;
  if (drvId != null && !(row.d === drvId || (fpDefaultDrv && row.d == null))) return false;
  return true;
}

function fpVisibleTracks() {   // 清单序 (日期升序) 里筛出且已下载的轨迹
  if (!manifest) return [];
  const out = [];
  for (const row of manifest.tracks)
    if (fpRowVisible(row)) {
      const t = allById.get(row.id);
      if (t) out.push(t);
    }
  return out;
}

function trackParams() {   // 时间档 (抽屉全局) + 车 + 驾驶员 (汇总端点同口径)
  const p = new URLSearchParams(timeRangeParams());
  if (shellState.carId != null) p.set("car_id", String(shellState.carId));
  if (drvId != null) p.set("driver_id", String(drvId));
  return "?" + p;
}

function showLoading(on, text) {
  $("#fp-loading").hidden = !on;
  if (on) $("#fp-prog").style.width = "0%";   // 进度条每轮从零起
  if (text) $("#fp-loading-text").textContent = text;
}
function showProgress(done, total) {   // 下载进度条 (加载层内, 确定值)
  $("#fp-prog").style.width = (total ? Math.round(done * 100 / total) : 100) + "%";
  $("#fp-loading-text").textContent = "正在下载轨迹 " + done + " / " + total + "…";
}
function showError(msg) {
  $("#fp-error").hidden = false;
  $("#fp-error-text").textContent = msg || "加载失败";
}

function renderStats(s) {
  $("#fp-stats").hidden = false;
  $("#st-drives").textContent = Number(s.drives).toLocaleString();
  $("#st-km").innerHTML = Number(s.distance_km).toLocaleString() + "<small>km</small>";
  $("#st-hours").innerHTML = (s.duration_min / 60).toFixed(1) + "<small>小时</small>";
}
