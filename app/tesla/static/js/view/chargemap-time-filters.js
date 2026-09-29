// view/chargemap-time-filters.js — 充电地图视图 (壳版 3/3): 三视角度量
// (地图脚下 pills 行, 2026-09-27 用户点名从屏底筛选条 chip 搬进页内 ——
// 与图例同一水平线, 只换热力度量, 不重新请求数据) + 弹层/缩放/重试收尾 +
// 视图生命周期 (registerView: 首进才起地图, AMap 实例保留秒开)。
// 旧版 (js/chargemap-time-filters.js) 的顶栏时间筛选/日历/URL 同步/刷新/
// 登出全删 (时间筛选 3.3.0 整个下线, 账号卡住设置页); 文件名沿用旧名
// (basename 折叠)。
/* global $, registerView, bindGestures, bindSheetDrag, bindSheetSettle,
          cmMode: writable, cmMap: writable, heatmap: writable,
          pickMark: writable, locations, renderHeatmap, cmCloseSheet,
          cmRefresh, cmBoot, cmSaveFilters */
/* exported heatmap, pickMark */   // 只写不读 (换度量清旧实例), exported 豁免
"use strict";

/* 度量档 (三视角): 地图脚下 pills (mini-seg, 与充电曲线档位条同款)。
   初始档来自深链/存档 (chargemap-page 抬出 cmMode), 这里只管切换 ——
   地图没起来时记着状态, boot 后首渲染 */
function cmSyncViews() {
  document.querySelectorAll("#cm-views button[data-v]").forEach(b =>
    b.classList.toggle("on", b.dataset.v === cmMode));
}
$("#cm-views").addEventListener("click", e => {
  const b = e.target.closest("button[data-v]");
  if (!b || b.dataset.v === cmMode) return;   // 点当前档 = 只亮着不动
  cmMode = b.dataset.v;
  cmSaveFilters();
  cmSyncViews();
  if (cmMap && locations.length) renderHeatmap();
});
cmSyncViews();

/* ---------- 收尾: 重试/重检/弹层/Esc/缩放 ---------- */
$("#cm-retry").addEventListener("click", () => cmRefresh(false));
$("#cm-recheck").addEventListener("click", () => location.reload());
$("#cm-backdrop").addEventListener("click", cmCloseSheet);
/* 下滑收起 (tesla-sheet-drag 壳级): 明细整张都是信息区, 拖下就收
   (以前只有点旁边蒙层一条路); 点一下不关 */
bindSheetDrag($("#cm-sheet"), $("#cm-sheet"), cmCloseSheet, false);
bindSheetSettle($("#cm-sheet"), "show");   // 视口折腾后强制废弃旧栅格 (7556 同保险)
/* Esc 链最上环 (视图脚本加载期挂, 先于筛选条): 自己有弹层就关掉并
   拦断, 没有则放行给下面两层 */
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !$("#cm-sheet").classList.contains("show")) return;
  cmCloseSheet();
  e.stopImmediatePropagation();
});
$("#cm-zin").addEventListener("click", () => cmMap && cmMap.zoomIn());
$("#cm-zout").addEventListener("click", () => cmMap && cmMap.zoomOut());

/* 手势面: 顶部摘要条在顶下拉刷新; 画布本体 touch-action:none 全给地图
   引擎, 左缘 24px 条单独供右划开抽屉 */
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
  refresh: () => cmRefresh(false),   // 下拉刷新/换车
});

/* 地图配置换了 (设置页保存后发 maplib:swap): 常驻实例作废, 下次进视图
   cmBoot 重建 (热力层/挑站标记随地图去; locations 是数据缓存, 重拉重画) */
addEventListener("maplib:swap", () => {
  if (!cmBooted) return;
  cmBooted = false;
  if (cmMap) { try { cmMap.destroy(); } catch { /* 实例已不在 */ } cmMap = null; }
  heatmap = null; pickMark = null;
});
