// tesla-gesture — 手势仲裁 (全壳唯一 arbiter): 每个视图滚动器绑一个
// bindGestures。8px slop 内不定轴, 过了定一次轴, 本次触摸不再改判:
//   横向右划        → 抽屉拖拽 (drawer 支线, 3.3.0 定稿回归; body pan-y
//                    下横划本就无原生行为, 不需要 preventDefault)
//   竖向下拉且在顶  → 下拉刷新 (ptr 支线; preventDefault 掐掉原生滚动/
//                    回弹, 只有指示器跟手)。判定要明确向下 (dy > 2|dx|)
//                    —— 2026-09-27 用户点名「左右滑会被判定下滑」, 45°
//                    斜角就认下拉太灵敏, 斜向一律交还系统
//   其余            → 交还系统 (原生滚动, 后续 move 不再看)
// 触摸事件而非指针事件: iOS Safari 触摸滚动期间 pointercancel 不可靠
// (trips-sheet-close.js 记录过); 抽屉自己身上的关闭拖拽另用指针捕获
// (music-pane-swipe 验证过的路线)。
// 2026-10-04 手势自愈: 一次触摸的 end/cancel 被系统吞掉 (边缘手势抢走/
// 打断) 时, 旧逻辑 tid 永占 —— 该元素的手势哑火到整页重载 (jsdom 复现
// 实锤)。新触摸起手时对账 e.touches: 被跟的那根已不在 (手指早离屏) 就
// 清场认新触摸 (半开的抽屉/下拉先收拾干净)。
// 2026-10-04 ptrMove 透传: 下拉的位移挂载元素 (宿主下面有兄弟画布的舞台
// 视图传整舞台, 位移不沉底 —— 见 tesla-pull-refresh 头注)。
"use strict";
/* global drawerDragMove, drawerDragEnd, ptrPull, ptrRelease, bindPTR */
/* exported bindGestures, GESTURE_SLOP */

const GESTURE_SLOP = 8;

function bindGestures(el, cfg) {
  // cfg: {drawer: 是否允许右划开抽屉, ptr: 是否支持在顶下拉刷新,
  //        onRefresh: 下拉松手的刷新回调, ptrMove: 下拉位移挂哪 (默认自己)}
  // ptr 面顺手在这里注册回调 (bindPTR 只管登记): 视图只调一次 bindGestures,
  // 忘了给 bindPTR 传回调的话指示器会空转不拉数 (P5 前踩过)
  if (cfg.ptr) bindPTR(el, cfg.onRefresh, cfg.ptrMove);
  let tid = -1, mode = "", sx = 0, sy = 0;
  el.addEventListener("touchstart", e => {
    if (tid !== -1) {                                 // 上一根还占着?
      let gone = true;                                // 还在 e.touches 里 = 真多指
      for (let i = 0; i < e.touches.length; i++)
        if (e.touches.item(i).identifier === tid) { gone = false; break; }
      if (!gone) return;                              // 只认第一根手指
      if (mode === "drawer") drawerDragEnd();         // 收拾半开的抽屉
      else if (mode === "ptr") ptrRelease(el, true);  // 半拉的指示器弹回 (按取消)
      tid = -1; mode = "";                            // 被吞掉的那根清场认新的
    }
    // 滑块控件起手不仲裁: 拖 range 的手势归控件自己 (统计页月度时间窗滑块),
    // 抽屉/下拉别来抢 —— tp-pager 对 .pb-seek 同款规矩
    if (e.target.closest('input[type="range"]')) return;
    const t = e.changedTouches[0];
    tid = t.identifier; sx = t.clientX; sy = t.clientY; mode = "";
  }, { passive: true });
  el.addEventListener("touchmove", e => {
    if (tid === -1 || mode === "done") return;
    let t = null;
    for (let i = 0; i < e.changedTouches.length; i++)
      if (e.changedTouches.item(i).identifier === tid) { t = e.changedTouches.item(i); break; }
    if (!t) return;
    const dx = t.clientX - sx, dy = t.clientY - sy;
    if (!mode) {                                     // slop 内不定轴
      if (Math.abs(dx) < GESTURE_SLOP && Math.abs(dy) < GESTURE_SLOP) return;
      if (cfg.drawer && dx > 0 && Math.abs(dx) > Math.abs(dy)) mode = "drawer";
      else if (cfg.ptr && dy > Math.abs(dx) * 2 && el.scrollTop <= 0) mode = "ptr";
      else mode = "done";                            // 原生滚动/左划: 交还系统
    }
    if (mode === "drawer") drawerDragMove(dx);
    else if (mode === "ptr") { e.preventDefault(); ptrPull(el, dy); }
  }, { passive: false });
  const end = e => {
    let hit = false;
    for (let i = 0; i < e.changedTouches.length; i++)
      if (e.changedTouches.item(i).identifier === tid) { hit = true; break; }
    if (!hit) return;
    if (mode === "drawer") drawerDragEnd();
    else if (mode === "ptr") ptrRelease(el, e.type === "touchcancel");
    tid = -1; mode = "";
  };
  el.addEventListener("touchend", end);
  el.addEventListener("touchcancel", end);
}
