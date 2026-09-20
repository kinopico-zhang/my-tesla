// view/chargemap-time-filters.js — 充电地图视图 (壳版 3/3): 三视图度量
// (屏底筛选条的 chip, 只换热力度量, 不重新请求数据) + 弹层/缩放/重试收尾 +
// 视图生命周期 (registerView: 首进才起地图, AMap 实例保留秒开)。
// 旧版 (js/chargemap-time-filters.js) 的顶栏时间筛选/日历/URL 同步/刷新/
// 登出全删 (抽屉与 tesla-time-range 接管); 文件名沿用旧名 (basename 折叠)。
/* global $, registerView, bindGestures, registerChips, refreshBarChips,
          closeFbPop, cmViews, cmMode: writable, cmMap, locations,
          renderHeatmap, cmCloseSheet, cmRefresh, cmBoot, cmSaveFilters */
"use strict";

/* 度量档 (三视图): 屏底筛选条 chip, 弹层三选一。初始档来自深链/存档
   (chargemap-page 抬出 cmMode), 这里只管切换 —— 地图没起来时记着状态,
   boot 后首渲染 */
registerChips("chargemap", [{
  id: "metric",
  label: () => "视角: " + cmViews[cmMode].lb,
  isOn: () => cmMode !== "energy",
  build(pop) {
    pop.innerHTML = `<div class="fb-scroll">` + Object.entries(cmViews).map(([k, v]) =>
      `<button type="button" data-v="${k}"${k === cmMode ? ' class="on"' : ""}>${v.lb}</button>`).join("") +
      `</div>`;
    pop.onclick = e => {
      const b = e.target.closest("button[data-v]");
      if (!b) return;
      closeFbPop();
      if (b.dataset.v === cmMode) return;   // 点当前项 = 只收弹层
      cmMode = b.dataset.v;
      cmSaveFilters();
      if (cmMap && locations.length) renderHeatmap();
      refreshBarChips();
    };
  },
}]);

/* ---------- 收尾: 重试/重检/弹层/Esc/缩放 ---------- */
$("#cm-retry").addEventListener("click", () => cmRefresh(false));
$("#cm-recheck").addEventListener("click", () => location.reload());
$("#cm-backdrop").addEventListener("click", cmCloseSheet);
/* Esc 链最上环 (视图脚本加载期挂, 先于抽屉/筛选条): 自己有弹层就关掉并
   拦断, 没有则放行给下面两层 */
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !$("#cm-sheet").classList.contains("show")) return;
  cmCloseSheet();
  e.stopImmediatePropagation();
});
$("#cm-zin").addEventListener("click", () => cmMap && cmMap.zoomIn());
$("#cm-zout").addEventListener("click", () => cmMap && cmMap.zoomOut());

/* 手势面: 顶部摘要条右划开抽屉/在顶下拉刷新; 画布本体 touch-action:none
   全给地图引擎, 左缘 24px 条单独供右划开抽屉 */
const cmHead = $("#cm-map-head");
bindGestures(cmHead, { drawer: true, ptr: true, onRefresh: () => cmRefresh(false) });
bindGestures($("#cm-edge"), { drawer: true });

/* ============================ 生命周期 ============================ */
let cmBooted = false;
registerView("chargemap", {
  title: "充电地图",
  el: $("#view-chargemap"),
  show() {                      // 首次进视图才起地图
    if (cmBooted) return;
    cmBooted = true;
    cmBoot();
  },
  /* 离开视图: 收弹层。AMap 实例保留 (回视图秒开, 热力层还在) */
  hide() {
    if ($("#cm-sheet").classList.contains("show")) cmCloseSheet();
  },
  refresh: () => cmRefresh(false),   // 抽屉刷新/换时间档/换车
});
