// view/trips-sheet-page.js — 轨迹弹层 (壳版 1/13): 底座 —— 弹层会话状态
// (openSeq 连点只认最后一次 / curKey 深链键 / sheetTrip 驾驶员标注 /
// mergedCache 合并整包缓存), 多选合并入口 openMerged, 地图引擎装载
// (mapLib 统一收口, 服务商可切; WebGL 保留缓冲补丁在适配层页面加载即装)
// 与弹层加载提示 tripMsg。旧版 (js/trips-sheet-page.js) 只删了 parseLocal
// 的本地解构 —— 壳里 tesla-common 已占这个名字 (const 重声明 =
// SyntaxError), 弹层/播放脚本沿用的裸名直接走 tesla-common 的;
// fmtTime/fmtDurLive 仍在这解构 (壳公共件没收)。文件名沿用旧名
// (命名普查按 basename 折叠)。
/* global $, FormatUtil, mapLib, openTrip */
/* exported fmtTime, fmtFullDate, fmtFullStamp, shiftStamp, fmtDurLive,
   openMerged, ensureAMap, tripMsg, tripMap, openSeq, curKey, sheetTrip,
   sheetFrom, mergedCache, bumpOpenSeq */
"use strict";
const { fmtTime, fmtFullDate, fmtFullStamp, shiftStamp, fmtDurLive } = FormatUtil;

/* ============================ 轨迹弹层 ============================ */
let amapLoading = null;             // Promise<true>: 地图引擎就绪
let tripMap = null;                 // 弹层内地图实例, 复用不销毁
let openSeq = 0;                    // 连续点开多条时, 只认最后一次
let curKey = null;                  // 弹层当前行程 key (单条 "2200" / 合并 "1836-1839"), 地址栏镜像用
let sheetTrip = null;               // 弹层当前单条行程条目 (标驾驶员用; 合并 = null)
/* 合并弹层的来源视图 (groups 页打开时置 "groups"): 关弹层要跳回去 —— 壳是
   零历史路由, 没有物理后退可走, 不记的话关掉就落在行程列表 (2026-09-22
   用户实报)。主动离开行程视图 (底栈换页) 时由 trips 的 hide() 清掉, 不拽人。 */
let sheetFrom = null;
const mergedCache = new Map();      // "首-尾" → 合并轨迹整包 (流式下完后存, 重开秒开)

/* 多选的连续行程 → 一条轨迹。ids 为多选数组 (必连续 → 只记头尾 id) 或
   深链原始串 ("首-尾" / 旧版逗号); info 带汇总字段 (分组页传分组条目,
   多选传本地聚合, 2026-09-23 用户点名「平均电耗空着, 加载完地图才显
   示」) —— 弹层数字带一开就填数, 不等流式汇总头; 深链重开没有 info,
   照旧占位。弹层立即打开阻断其他操作, 轨迹数据走流式接口边下边播
   (见 loadMergedStream); 整包缓存命中则直接播。 */
function openMerged(ids, fromUrl, info) {
  const key = typeof ids === "string" ? ids
    : `${Math.min(...ids)}-${Math.max(...ids)}`;
  const extra = info && info.km != null ? {         // 有汇总才带 (字段名与
    n: info.n, start: info.start, end: info.end, km: info.km,  // 汇总头一致)
    min: info.min, speed_max: info.speed_max,
    kwh: info.kwh, wh_per_km: info.wh_per_km } : {};
  return openTrip(Object.assign({ id: "m:" + key, merged: true, mergeKey: key,
    gname: info && info.name || null }, extra),
    fromUrl);   // promise 传回 (深链失败抹参靠它)
}

/* 地图引擎只装载一次 (弹层打开与后台预载共用入口; 失败可重试) */
function ensureAMap() {
  if (!amapLoading) {
    amapLoading = mapLib.ready().then(() => true);
    amapLoading.catch(() => { amapLoading = null; });
  }
  return amapLoading;
}

/* 地图配置换了 (设置页保存后发 maplib:swap): 弹层地图实例作废, 下次打开
   重建 —— 点击跳播/变焦接管这些监听都在建图时重挂 (实时页本来就每次进
   视图重建, 不用管) */
addEventListener("maplib:swap", () => {
  if (!tripMap) return;
  try { tripMap.destroy(); } catch { /* 实例已不在 */ }
  tripMap = null;
});

/* 离开行程视图时掐掉所有在途打开: openTrip/流式下载的 seq 检查全部失效
   (视图底座 hide() 先调这个, 之后再停录制/关弹层/退多选) */
function bumpOpenSeq() { openSeq++; }

function tripMsg(text, spin) {
  $("#trip-msg").hidden = !text && !spin;
  $("#trip-msg-text").textContent = text || "";
  $("#trip-spin").hidden = !spin;
}
