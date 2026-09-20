// view/map-filters.js — 足迹地图视图 (壳版 5/5): 驾驶员筛选 (屏底筛选条
// chip, 选项来自设置页的驾驶员表, 没配整颗藏掉) + 弹层/缩放/重试收尾 +
// 视图生命周期 (registerView: 首进才起地图拉驾驶员表, 离开收弹层/掐细化
// 防抖 —— 地图实例保留, 回视图秒开)。
// v4 起换筛选/下拉刷新/抽屉刷新都走 fpSync (清单现拉 + 本地渲染, 驾驶员
// 标注在清单 d 字段里, 标/清完回视图一刷就新鲜)。
// 旧版 (js/map-filters.js) 的顶栏时间筛选/日历/URL 同步/刷新/登出全删
// (抽屉与 tesla-time-range 接管); 驾驶员筛选从下拉菜单改屏底 chip。
/* global $, getJSON, registerView, registerChips, refreshBarChips,
          buildOptsPop, bindGestures, drvId: writable, fpDefaultDrv: writable,
          map, fpBoot, fpSync, fpSaveFilters, closeSheet, refineTimer: writable */
/* exported fpFetchDrivers */
"use strict";

/* 驾驶员筛选 chip: 口径与行程页一致 —— 选默认驾驶员 = 标注它的 + 未标注的
   (清单行 d 字段本地判断); 没配驾驶员 chip 不出现 */
let fpDrivers;   // undefined=还没拉过, null=失败, 数组=结果
function fpDrvLabel() {
  const d = (fpDrivers || []).find(x => x.id === drvId);
  return d ? "驾驶员: " + d.name : "驾驶员: 全部";
}
function fpDrvPicked() {   // 换选择后同步默认驾驶员标记 (未标注轨迹的归属)
  fpDefaultDrv = (fpDrivers || []).some(d => d.id === drvId && d.is_default);
  return fpDefaultDrv;
}
function buildFpDrvPop(pop) {
  buildOptsPop(pop,
    [{ v: "", lb: "全部" }].concat(
      (fpDrivers || []).map(d => ({ v: String(d.id), lb: d.name }))),
    drvId == null ? "" : String(drvId), v => {
      drvId = v === "" ? null : +v;
      fpDrvPicked();
      fpSaveFilters(); refreshBarChips(); fpSync();
    });
}
function fpChips() {
  const chips = [];
  if ((fpDrivers || []).length)
    chips.push({ id: "drv", label: fpDrvLabel,
                 isOn: () => drvId != null, build: buildFpDrvPop });
  return chips;
}
registerChips("map", fpChips());
async function fpFetchDrivers() {
  if (fpDrivers === undefined) {
    try { fpDrivers = await getJSON("/tesla/api/drivers"); }
    catch { fpDrivers = null; }
  }
  const drivers = fpDrivers || [];
  if (!drivers.length) return;               // 没配驾驶员, 筛选不出现
  if (drvId != null) {                       // 存的/深链带的选择要还在表里才算数
    if (!drivers.some(d => d.id === drvId)) {
      drvId = null;
      fpSaveFilters();
    }
  }
  fpDrvPicked();
  registerChips("map", fpChips());
  refreshBarChips();
  if (drvId != null) fpSync();   // 首开与拉表并发: 默认驾驶员口径要补一轮重筛
}

/* ---------- 收尾: 重试/重检/弹层/Esc/缩放 ---------- */
$("#fp-retry").addEventListener("click", () => fpSync());
$("#fp-recheck").addEventListener("click", () => location.reload());
$("#fp-backdrop").addEventListener("click", closeSheet);
/* Esc 链最上环 (视图脚本加载期挂, 先于抽屉/筛选条): 自己有弹层就关掉并
   拦断, 没有则放行给下面两层 */
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !$("#fp-sheet").classList.contains("show")) return;
  closeSheet();
  e.stopImmediatePropagation();
});
$("#fp-zin").addEventListener("click", () => map && map.zoomIn());
$("#fp-zout").addEventListener("click", () => map && map.zoomOut());

/* 手势面: 顶部摘要条右划开抽屉/在顶下拉刷新; 画布本体 touch-action:none
   全给地图引擎, 左缘 24px 条单独供右划开抽屉 */
const fpHead = $("#fp-map-head");
bindGestures(fpHead, { drawer: true, ptr: true, onRefresh: () => fpSync() });
bindGestures($("#fp-edge"), { drawer: true });

/* ============================ 生命周期 ============================ */
let fpBooted = false;
registerView("map", {
  title: "足迹地图",
  el: $("#view-map"),
  show() {                      // 首次进视图: 起地图同步轨迹, 驾驶员表异步拉
    if (fpBooted) return;
    fpBooted = true;
    fpBoot();
    fpFetchDrivers();
  },
  /* 离开视图: 掐在途的细化防抖 (放行会换线), 收弹层。
     地图实例保留 (回视图秒开, 轨迹线还在) */
  hide() {
    clearTimeout(refineTimer);
    if ($("#fp-sheet").classList.contains("show")) closeSheet();
  },
  refresh: () => fpSync(),   // 抽屉刷新/换时间档/换车 (清单现拉 + 本地渲染)
});
