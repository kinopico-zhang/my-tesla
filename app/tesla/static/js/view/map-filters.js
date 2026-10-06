// view/map-filters.js — 足迹地图视图 (壳版 5/5): 驾驶员筛选 (2026-10-02
// 用户点名「进度条短一点, 把驾驶员筛选放到一行」—— 从屏底悬浮条并进
// 播放条行尾 #fp-drv 裸文字 chip, 这页 chips 退役) + 重试/缩放收尾 +
// 视图生命周期 (registerView: 首进才起地图拉驾驶员表; 地图实例保留,
// 回视图秒开; 切走视图收掉时间回放 —— 2026-10-02 用户报「打开足迹地图
// 就自动开始播放」, 回放不该跨视图活着)。点路不弹详情卡 (2026-09-29
// 用户点名「点击路不要弹窗」, 详情层/蒙版/Esc/拖拽收尾整链随退役)。
// v4 起换筛选/下拉刷新都走 fpSync (清单现拉 + 本地渲染, 驾驶员
// 标注在清单 d 字段里, 标/清完回视图一刷就新鲜)。
// v17 (2026-10-04): ptrMove 挂整视图 —— 下拉位移原来只挂头部自己, 会沉进
// 画布后面 (状态页用户点名「图标数字和地图要一个整体」, 三舞台图同修)。
// 2026-10-04 用户报「右划返回失效」: 左缘取证补盲 —— 10-01 的边条/画布
// 探针从没响过, 因为缝条 (0-40px) 盖在边条 (卡内 16-56px) 头上, 左缘
// 触摸全落缝条这个无探针面; 补缝条起手/收手/被抢 (cancel) 三探针 +
// 版本信标 + 抽屉开张信标, 下次复现翻日志就能定罪到具体一环。
// 旧版 (js/map-filters.js) 的顶栏时间筛选/日历/URL 同步/刷新/登出全删
// (时间筛选 3.3.0 下线, 账号卡住设置页); 驾驶员筛选从下拉菜单改屏底 chip。
/* global $, getJSON, diag, registerView, buildOptsPop, bindGestures,
          closeFbPop, anchorPop, openDrawer: writable, PAGE_V,
          drvId: writable, fpDefaultDrv: writable, map: writable,
          mapReady: writable, fpViewOn: writable, fpBoot, fpSync,
          fpPlaying, fpPlayExit, fpPlayAuto, fpPlayArm,
          fpSaveFilters */
/* exported fpFetchDrivers, mapReady, fpViewOn */   // 后两个只写不读 (清态/前台旗), exported 豁免
"use strict";

/* 驾驶员筛选 chip: 口径与行程页一致 —— 选默认驾驶员 = 标注它的 + 未标注的
   (清单行 d 字段本地判断); 没配驾驶员 chip 不出现。换选置 fpPlayArm 点名
   重播 (2026-10-02 用户点名「任何时候, 切换驾驶员都重播」) */
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
      fpPlayArm();   // 换驾驶员点名重播 (任何时候都重播): 同步收尾从头播新清单
      fpSaveFilters(); fpDrvChipSync(); fpSync();
    });
}
function fpDrvChipSync() {   // 播放条行尾的驾驶员筛选: 文案/选中态/显隐
  const btn = $("#fp-drv");
  btn.hidden = !(fpDrivers || []).length;   // 没配驾驶员整颗藏
  btn.textContent = fpDrvLabel();
  btn.classList.toggle("on", drvId != null);
}
$("#fp-drv").addEventListener("click", () => {   // 开/收选项弹层 (全局 #fb-pop
  const pop = $("#fb-pop");                       // 锚 chip 上方; 再点同 chip 收)
  const open = pop.classList.contains("on") && pop.dataset.chip === "fpdrv";
  closeFbPop();
  if (open) return;
  pop.dataset.chip = "fpdrv";
  pop.innerHTML = "";
  buildFpDrvPop(pop);
  pop.classList.add("on");
  anchorPop(pop, $("#fp-drv"));
});
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
  fpDrvChipSync();
  if (drvId != null) fpSync();   // 首开与拉表并发: 默认驾驶员口径要补一轮重筛
}

/* ---------- 收尾: 重试/重检 (缩放钮 2026-10-01 随播放条重做退役 —— 双指
   捏合本来就有, 用户点名去掉按钮) ---------- */
$("#fp-retry").addEventListener("click", () => fpSync());
$("#fp-recheck").addEventListener("click", () => location.reload());

/* 手势面: 顶部摘要条在顶下拉刷新; 画布本体 touch-action:none 全给地图
   引擎, 左缘两条供右划开抽屉 —— 卡内 40px 边条 (#fp-edge) + 视图层 16px
   缝条 (#fp-gutter, 2026-10-01 补: 卡片两侧有 16px 出血边距, 手指中心
   落在卡外的缝里时卡内条接不到, 两条接力覆盖到物理屏缘) */
const fpHead = $("#fp-map-head");
bindGestures(fpHead, { drawer: true, ptr: true, onRefresh: () => fpSync(),
                       ptrMove: $("#view-map") });
bindGestures($("#fp-edge"), { drawer: true });
bindGestures($("#fp-gutter"), { drawer: true });

/* 左缘右划取证 (2026-10-01 用户报「左边缘右划无法呼出菜单」, 40px/z40 版
   线上仍复现): 边条与画布各挂 touchstart 探针 (各前 10 次回传坐标), 事后
   翻服务日志定罪 —— 零 fp_edge_touch = 触摸根本没到边条 (缝里/系统吞),
   到了但 fp_edge_end 的 dx 不成形 = 手势轨迹问题; fp_map_touch_lowx =
   该到边条的触摸落进了画布 (命中测试被谁压住)。 */
const fpEdgeProbe = new Map();   // touch 识别号 → 起点坐标
let fpEdgeN = 0, fpMapN = 0;
$("#fp-edge").addEventListener("touchstart", e => {
  const t = e.changedTouches[0];
  fpEdgeProbe.set(t.identifier, [t.clientX, t.clientY]);
  if (fpEdgeN++ < 10)
    diag("fp_edge_touch", { x: Math.round(t.clientX), y: Math.round(t.clientY) });
}, { passive: true });
$("#fp-edge").addEventListener("touchend", e => {
  for (const t of e.changedTouches) {
    const s = fpEdgeProbe.get(t.identifier);
    fpEdgeProbe.delete(t.identifier);
    if (s && fpEdgeN++ < 10)
      diag("fp_edge_end", { dx: Math.round(t.clientX - s[0]), dy: Math.round(t.clientY - s[1]) });
  }
}, { passive: true });
$("#fp-map").addEventListener("touchstart", e => {
  const t = e.changedTouches[0];
  if (t.clientX > 90 || fpMapN++ >= 10) return;   // 只关心左缘落进画布的
  diag("fp_map_touch_lowx", { x: Math.round(t.clientX), y: Math.round(t.clientY) });
}, { passive: true, capture: true });

/* 缝条探针 (2026-10-04 补盲, 用户报「右划返回失效」): 缝条 (0-40px) 盖在
   边条 (卡内 16-56px) 头上, 左缘起手全落缝条 —— 10-01 的两路探针因此从没
   响过, 证据一直真空。三笔定罪: fp_gutter_touch (起手到了没) /
   fp_gutter_end (收手 dx 成不成形) / fp_gutter_cancel (系统把手势抢走了:
   边缘返回/通知横幅都会这么干 —— 抢走的触摸没有 end, 仲裁器会哑火到重载,
   手势自愈在 tesla-gesture v7 对账清场)。 */
const fpGutProbe = new Map();
let fpGutN = 0;
$("#fp-gutter").addEventListener("touchstart", e => {
  const t = e.changedTouches[0];
  fpGutProbe.set(t.identifier, [t.clientX, t.clientY]);
  if (fpGutN++ < 10)
    diag("fp_gutter_touch", { x: Math.round(t.clientX), y: Math.round(t.clientY) });
}, { passive: true });
$("#fp-gutter").addEventListener("touchend", e => {
  for (const t of e.changedTouches) {
    const s = fpGutProbe.get(t.identifier);
    fpGutProbe.delete(t.identifier);
    if (s && fpGutN++ < 10)
      diag("fp_gutter_end", { dx: Math.round(t.clientX - s[0]), dy: Math.round(t.clientY - s[1]) });
  }
}, { passive: true });
$("#fp-gutter").addEventListener("touchcancel", e => {
  for (const t of e.changedTouches) {
    if (fpGutProbe.delete(t.identifier) && fpGutN++ < 10)
      diag("fp_gutter_cancel", { x: Math.round(t.clientX), y: Math.round(t.clientY) });
  }
}, { passive: true });

/* 抽屉开张信标: 手势链最后一环 —— 前面探针都响了这个没响, 问题在仲裁/
   抽屉侧; 全响了 = 抽屉真开了。openDrawer 是 tesla-drawer 的函数声明
   (全局可重绑), 包一层记账, 行为不动。 */
const fpOrigOpenDrawer = openDrawer;
openDrawer = function () { diag("fp_drawer_open", {}); return fpOrigOpenDrawer(); };

/* ============================ 生命周期 ============================ */
let fpBooted = false;
registerView("map", {
  title: "足迹地图",
  el: $("#view-map"),
  show() {                      // 首次进视图: 起地图同步轨迹, 驾驶员表异步拉
    fpViewOn = true;            // 在前台 (自动开播只趁人在看时起)
    if (fpBooted) { fpPlayAuto(); return; }   // 回视图: 数据就绪补一轮自动开播
    fpBooted = true;
    diag("fp_boot", { pv: PAGE_V, mf: "v16" });   // 版本信标: 确认手机真跑上 v16 (排查旧缓存混跑)
    fpBoot();
    fpFetchDrivers();
  },
  hide() {                      // 切走视图: 记下不在前台 + 回放整场收掉 —
    fpViewOn = false;           // 回来是静止热力图 (自动开播只此一回不再自来)
    if (fpPlaying) fpPlayExit(true);
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
