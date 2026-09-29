// view/chargemap-page.js — 充电地图视图 (壳版 1/3): 底座 —— 三视图 (热力
// 权重度量) 与热力梯度定义 + 度量偏好 (?metric= 深链加载期抠出, 持久化进
// shellState.filters.chargemap; 时间筛选 3.3.0 下线, 全时段) + 加载/错误占位。
// 旧版 (js/chargemap-page.js) 的菜单收起/$/getJSON/TIME_RANGES/日历/URL
// 同步全删; 高德脚本加载器 (带 HeatMap 插件) 也撤了 —— tesla-map-adapter
// 的 mapLib 统一装引擎 (插件随主脚本带), 服务商可切; 壳内撞名的全局全带
// cm 前缀 (VIEWS→cmViews 撞导航注册表, view→cmMode, map→cmMap, loadAMap/
// showLoading/showError/renderStats/closeSheet/refresh 撞足迹视图的裸名)。
// 旧页度量参数叫 ?view=, 3.0 的 ?view= 让给视图选择 —— 旧页路由 302 时
// 换名成 ?metric= (pages.py), 这里只认新名。
/* global $, shellState, saveShell */
/* exported cmViews, GRADIENT, PICK_PX, cmMode, cmMap, heatmap, pickMark,
           locations, cmShowLoading, cmShowError, cmSaveFilters */
"use strict";

/* ---------- 三视图: 热力权重度量 ---------- */
const cmViews = {
  energy:   { lb: "充电电量", fmt: v => Math.round(v) + " kWh" },
  sessions: { lb: "充电次数", fmt: v => v + " 次" },
  cost:     { lb: "充电费用", fmt: v => "¥" + Math.round(v) },
};
/* 热力梯度: 蓝 → 绿 → 黄 → 橙 → 红 (值越高越红), 图例梯度条用同一组色 */
const GRADIENT = { 0.2: "#3987e5", 0.45: "#1fa349", 0.65: "#d9b13c", 0.82: "#e08a3c", 1: "#e5484d" };
const PICK_PX = 36;    // 点击就近取点半径 (像素)

/* 度量档 (三视图): URL 深链优先 (加载期抠出, app-boot 洗参前), 否则上次
   存的偏好 */
const cmQs0 = new URLSearchParams(location.search);
const savedCm = shellState.filters.chargemap || {};
let cmMode = cmViews[cmQs0.get("metric")] ? cmQs0.get("metric")
  : cmViews[savedCm.view] ? savedCm.view : "energy";
function cmSaveFilters() {
  shellState.filters.chargemap = { view: cmMode };
  saveShell();
}

let cmMap = null, heatmap = null, pickMark = null, locations = [];

function cmShowLoading(on, text) {
  $("#cm-loading").hidden = !on;
  if (text) $("#cm-loading-text").textContent = text;
}
function cmShowError(msg) {
  $("#cm-error").hidden = false;
  $("#cm-error-text").textContent = msg || "加载失败";
}
