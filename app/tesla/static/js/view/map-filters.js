// view/map-filters.js — 足迹地图视图 (壳版 5/5): 驾驶员筛选 (屏底筛选条
// chip, 选项来自设置页的驾驶员表, 没配整颗藏掉) + 重试/缩放收尾 +
// 视图生命周期 (registerView: 首进才起地图拉驾驶员表; 地图实例保留,
// 回视图秒开)。点路不弹详情卡 (2026-09-29 用户点名「点击路不要弹窗」,
// 详情层/蒙版/Esc/拖拽收尾整链随退役)。
// v4 起换筛选/下拉刷新都走 fpSync (清单现拉 + 本地渲染, 驾驶员
// 标注在清单 d 字段里, 标/清完回视图一刷就新鲜)。
// 旧版 (js/map-filters.js) 的顶栏时间筛选/日历/URL 同步/刷新/登出全删
// (时间筛选 3.3.0 下线, 账号卡住设置页); 驾驶员筛选从下拉菜单改屏底 chip。
/* global $, getJSON, registerView, registerChips, refreshBarChips,
          buildOptsPop, bindGestures,
          drvId: writable, fpDefaultDrv: writable, map: writable,
          mapReady: writable, fpBoot, fpSync,
          fpSaveFilters */
/* exported fpFetchDrivers, mapReady */   // 只写不读 (离开视图清态), exported 豁免
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

/* ---------- 收尾: 重试/重检/缩放 ---------- */
$("#fp-retry").addEventListener("click", () => fpSync());
$("#fp-recheck").addEventListener("click", () => location.reload());
$("#fp-zin").addEventListener("click", () => map && map.zoomIn());
$("#fp-zout").addEventListener("click", () => map && map.zoomOut());

/* 手势面: 顶部摘要条在顶下拉刷新; 画布本体 touch-action:none 全给地图
   引擎, 左缘 24px 条单独供右划开抽屉 */
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
  refresh: () => fpSync(),   // 下拉刷新/换时间档/换车 (清单现拉 + 本地渲染)
});

/* 地图配置换了 (设置页保存后发 maplib:swap): 常驻实例整个作废 —— 旧引擎
   销毁, 下次进视图 fpBoot 重建 + fpSync 全量重画 (覆盖物每次渲染整组
   重建, 见 map-tracks-render), 换服务商/样式不再要整页刷新 */
addEventListener("maplib:swap", () => {
  if (!fpBooted) return;
  fpBooted = false;
  if (map) { try { map.destroy(); } catch { /* 实例已不在 */ } map = null; }
  mapReady = false;
});
