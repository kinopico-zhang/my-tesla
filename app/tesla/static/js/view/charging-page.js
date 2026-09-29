// view/charging-page.js — 充电记录视图 (壳版 1/6): 视图底座 —— 筛选状态
// (chgState, 偏好持久化进 shellState.filters.charging) + 查询参数拼装
// (车辆来自 shellState.carId; 时间筛选 3.3.0 下线, 全时段)。
// 旧版 (js/charging-page.js) 的 $/esc/getJSON/格式化解构/money/
// TIME_RANGES/日历/syncURL/URL 解析全部上移壳模块 (tesla-common) 或删除
// —— 壳内地址栏恒 /tesla, 状态住 localStorage。旧页继续用旧文件, P7 退役。
/* global shellState, saveShell */
/* exported PAGE, fmtMinAxis, detailCache, chgState, chgSaveFilters,
            sessionParams */
"use strict";
const PAGE = 24;

function fmtMinAxis(v) {
  if (v >= 60) { const h = Math.floor(v / 60), m = Math.round(v % 60); return m ? `${h}h${m}m` : `${h}h`; }
  return `${Math.round(v)}m`;
}

/* 筛选偏好: 上次用过的住 localStorage (壳冷启已把旧 URL 参数折进来) */
const savedF = shellState.filters.charging || {};
const chgState = {
  type: ["fast", "slow"].includes(savedF.type) ? savedF.type : "all",
  region: typeof savedF.region === "string" ? savedF.region : "",
  cost: ["recorded", "missing"].includes(savedF.cost) ? savedF.cost : "all",
};
function chgSaveFilters() {
  shellState.filters.charging =
    { type: chgState.type, region: chgState.region, cost: chgState.cost };
  saveShell();
}

const detailCache = new Map();

/* 筛选/车辆 → /sessions 查询参数 (offset/limit 由分页器 extra 传;
   时间不筛, 全时段) */
function sessionParams(extra) {
  const p = new URLSearchParams({ type: chgState.type, cost: chgState.cost,
                                  ...(extra || {}) });
  if (chgState.region) p.set("region", chgState.region);
  if (shellState.carId != null) p.set("car_id", String(shellState.carId));
  return p.toString();
}
