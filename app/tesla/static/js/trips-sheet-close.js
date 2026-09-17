// trips-sheet-close.js — 轨迹弹层 (13/13): 收尾 —— 关弹层 (hideSheet/
// closeTrip), 地址栏深链入口 (openByKey: 分享直开/后退再前进), 弹层下拉
// 拖拽关闭, popstate 同步, 启动时后台预载高德脚本与深链直开。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局); 本文件排在最后, 前面模块的事件回调
// 到这里都已就绪。
/* global $, getJSON, openMerged, openTrip, urlTripKey, listURL, loadMore,
   ensureAMap, stopAnim, curSess: writable, sheetTrip: writable,
   curKey: writable */
/* exported hideSheet, sheetTrip */
"use strict";
/* ---------- 地址栏深链: 打开变 /tesla/trips?id=X 或 ?ids=a,b, 方便分享/回退 ---------- */
async function openByKey(key) {
  /* 分享直开 / 后退再前进: 手里没有卡片数据, 单条走单条接口, 合并走合并
     接口 (404 → 抹掉参数)。合并键两种形式: "首-尾" (现行) / 逗号 (旧链) */
  try {
    if (/[-,]/.test(key)) await openMerged(key, true);   // 必须 await: 流式失败要
    else openTrip(await getJSON(`/tesla/trips/api/sessions/${key}`), true);  // rethrow 到这抹参
  } catch (e) {
    hideSheet();
    history.replaceState(null, "", listURL());   // 坏链接 → 抹掉行程参数, 保留筛选
  }
}

function hideSheet() {
  stopAnim();
  if (curSess) { curSess.alive = false; curSess = null; }
  $("#sheet").classList.remove("show");
  $("#backdrop").classList.remove("show");
  $("#sh-drv").hidden = true;
  sheetTrip = null;
}

/* 分组页跳来的深链 (?ids=): 关弹层要回分组页。referrer 是整页导航留下的,
   页内后续 push/replace 不影响它; 直开的分享链没有这个 referrer, 照旧抹参。 */
const cameFromGroups = document.referrer.endsWith("/tesla/groups");

function closeTrip() {
  const key = curKey;
  hideSheet();
  curKey = null;
  if (key == null) return;
  if (history.state && history.state.k === key)
    history.back();   // 弹层是本页推入的 → 回退 (popstate 会再走一遍 hideSheet, 无害)
  else if (urlTripKey() != null) {
    if (cameFromGroups) { history.back(); return; }    // 分组页跳来 → 回分组页
    history.replaceState(null, "", listURL());         // 分享直开 → 只抹行程参数
  }
}

$("#backdrop").addEventListener("click", closeTrip);
/* 手柄: 点一下关, 也能拖着往下拉关 (跟手 + 松手回弹; 拖过 8px 就不算点击,
   否则回弹动画结束瞬间跟着来的 click 会把刚弹回的弹层又关掉)。
   不用 setPointerCapture: iOS Safari 对 touch 指针 capture 会当场
   pointercancel (手指一动事件就被系统收走, 2026-09-13 用户实测充电详情
   拉不动), move/up 挂 window 级 —— 不捕获手指出界照样收, 各端行为一致。 */
(() => {
  const sheetEl = $("#sheet");
  let y0 = null, dy = 0;
  const grab = $("#grab");
  const move = e => {
    dy = Math.max(0, e.clientY - y0);      // 只往下拖有效, 往上顶不抬层
    sheetEl.style.transition = "none";
    sheetEl.style.transform = `translateY(${dy}px)`;
  };
  const release = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", release);
    window.removeEventListener("pointercancel", release);
    if (y0 == null) return;
    sheetEl.style.transition = ""; sheetEl.style.transform = "";
    if (dy > 90) closeTrip();              // 拉过 90px = 明确想关; 否则弹回
    y0 = null;
  };
  grab.addEventListener("pointerdown", e => {
    y0 = e.clientY; dy = 0;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
  });
  grab.addEventListener("click", e => {
    if (dy > 8) { e.stopImmediatePropagation(); dy = 0; return; }
    closeTrip();
  });
})();

/* 浏览器后退/前进: 只切界面不动历史, 与地址栏保持同步 */
addEventListener("popstate", () => {
  const key = urlTripKey();
  if (key == null) {
    if (curKey != null) { hideSheet(); curKey = null; }
  } else if (key !== curKey) {
    openByKey(key);
  }
});

/* 首页列表加载完后, 后台预载高德脚本 (首次点开更快); 分享链接 (?id=X) 直开弹层 */
loadMore().then(() => { ensureAMap().catch(() => {}); });
if (urlTripKey() != null) openByKey(urlTripKey());
