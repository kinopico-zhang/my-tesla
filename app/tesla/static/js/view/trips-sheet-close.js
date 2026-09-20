// view/trips-sheet-close.js — 轨迹弹层 (壳版 13/13): 收尾 —— 关弹层
// (hideSheet/closeTrip), 深链入口 openByKey (壳冷启把 ?id=/?ids= 消费后由
// tesla-app-boot 调), 弹层下拉拖拽关闭。
// 旧版 (js/trips-sheet-close.js) 的 popstate 同步 / history.back /
// cameFromGroups 全删 —— 壳是零历史条目内存路由, 没有"后退回分组页"可走
// (分组视图改 navigate 内存跳转); 启动预载与深链直开归 tesla-app-boot。
// 文件名沿用旧名 (命名普查按 basename 折叠)。
/* global $, getJSON, openMerged, openTrip, stopAnim, curSess: writable,
   sheetTrip: writable, curKey: writable */
/* exported hideSheet, openByKey, sheetTrip */
"use strict";
/* ---------- 深链入口: 壳冷启消费 ?id=/?ids= 后调用 (分享链接直开) ---------- */
async function openByKey(key) {
  /* 手里没有卡片数据, 单条走单条接口, 合并走合并接口 (失败 → 洗掉参数)。
     合并键两种形式: "首-尾" (现行) / 逗号 (旧链) */
  try {
    if (/[-,]/.test(key)) await openMerged(key, true);   // 必须 await: 流式失败要
    else openTrip(await getJSON(`/tesla/trips/api/sessions/${key}`), true);  // rethrow 到这抹参
  } catch (_e) {
    hideSheet();
    history.replaceState(null, "", "/tesla");   // 坏链接 → 洗掉行程参数
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

/* 零历史条目: 关弹层只把地址栏镜像回裸壳地址 (打开时 replaceState 过
   /tesla?view=trips&id=); 不动历史栈。 */
function closeTrip() {
  const key = curKey;
  hideSheet();
  curKey = null;
  if (key != null) history.replaceState(null, "", "/tesla");
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
