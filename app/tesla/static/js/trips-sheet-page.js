// trips-sheet-page.js — 轨迹弹层 (1/13): 底座 —— 弹层会话状态 (openSeq 连点
// 只认最后一次 / curKey 深链键 / sheetTrip 驾驶员标注 / mergedCache 合并整包
// 缓存), 多选合并入口 openMerged, 高德脚本装载 (WebGL 保留缓冲补丁, 导出
// 视频要 drawImage 地图画布) 与弹层加载提示 tripMsg。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局); 播放会话状态在 trips-playback-bar.js,
// 关弹层与地址栏深链在 trips-sheet-close.js。
/* global $, getJSON, FormatUtil, openTrip */
/* exported parseLocal, fmtTime, fmtDurLive, openMerged, ensureAMap, tripMsg,
   tripMap, amapStyle, openSeq, curKey, sheetTrip, mergedCache */
"use strict";
const { parseLocal, fmtTime, fmtDurLive } = FormatUtil;
/* fmtCardDate/fmtDur/num 由 trips-list-page.js 解构声明, 弹层/播放沿用 */

/* ============================ 轨迹弹层 ============================ */
let amapLoading = null;             // Promise<true>: 高德脚本就绪
let amapStyle = "amap://styles/dark";   // 地图样式 (config 下发, 设置页可换)
let tripMap = null;                 // 弹层内地图实例, 复用不销毁
let openSeq = 0;                    // 连续点开多条时, 只认最后一次
let curKey = null;                  // 弹层当前行程 key (单条 "2200" / 合并 "1836-1839"), 地址栏同步用
let sheetTrip = null;               // 弹层当前单条行程条目 (标驾驶员用; 合并 = null)
const mergedCache = new Map();      // "首-尾" → 合并轨迹整包 (流式下完后存, 重开秒开)

/* 多选的连续行程 → 一条轨迹。ids 为多选数组 (必连续 → 只记头尾 id) 或
   深链原始串 ("首-尾" / 旧版逗号)。弹层立即打开阻断其他操作, 轨迹数据
   走流式接口边下边播 (见 loadMergedStream); 整包缓存命中则直接播。 */
function openMerged(ids, fromUrl) {
  const key = typeof ids === "string" ? ids
    : `${Math.min(...ids)}-${Math.max(...ids)}`;
  return openTrip({ id: "m:" + key, merged: true, mergeKey: key }, fromUrl);   // promise 传回 (深链失败抹参靠它)
}

/* WebGL 保留绘图缓冲: 导出视频要 drawImage 地图画布拿内容, 高德默认建的
   上下文没开 preserveDrawingBuffer —— 合成器取走画面后缓冲即清空,
   drawImage 只能拿到黑帧 (dbg90 实测: 无补丁全画布直画 0 像素, 有补丁
   有内容)。上下文属性建时即定, 必须在高德脚本加载前装好。 */
function patchGLKeepBuffer() {
  if (patchGLKeepBuffer.done) return;
  patchGLKeepBuffer.done = true;
  const orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, attrs) {
    if (type === "webgl" || type === "webgl2" || type === "experimental-webgl")
      attrs = Object.assign({ antialias: true }, attrs, { preserveDrawingBuffer: true });
    return orig.call(this, type, attrs);
  };
}

function loadAMapScript(key, securityCode) {
  return new Promise((resolve, reject) => {
    patchGLKeepBuffer();
    if (securityCode) window._AMapSecurityConfig = { securityJsCode: securityCode };
    const s = document.createElement("script");
    s.src = "https://webapi.amap.com/maps?v=2.0&key=" + encodeURIComponent(key);
    s.onload = () => resolve(true);
    s.onerror = () => reject(new Error("高德地图脚本加载失败, 请检查网络"));
    document.head.appendChild(s);
  });
}

/* 高德脚本只加载一次 (弹层打开与后台预载共用入口; 失败可重试) */
function ensureAMap() {
  if (!amapLoading) {
    amapLoading = (async () => {
      const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
      if (!cfg.amap_key) throw new Error("未配置高德地图 Key (.env 里设置 AMAP_KEY)");
      if (cfg.style) amapStyle = cfg.style;
      await loadAMapScript(cfg.amap_key, cfg.security_code);
      return true;
    })();
    amapLoading.catch(() => { amapLoading = null; });
  }
  return amapLoading;
}

function tripMsg(text, spin) {
  $("#trip-msg").hidden = !text && !spin;
  $("#trip-msg-text").textContent = text || "";
  $("#trip-spin").hidden = !spin;
}
