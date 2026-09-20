// tesla-pull-refresh — 下拉刷新指示器 (手势仲裁的 ptr 支线): 在顶下拉跟手
// (阻尼 0.4, 封顶 110px), 过阈值 (~70px) 箭头翻上变"松手刷新"; 松手 →
// spinner 钉在顶部模糊带下沿, await onRefresh() 完成后弹回藏进模糊带。
"use strict";
/* exported bindPTR, ptrPull, ptrRelease */

const PTR_PULL_FNS = new Map();   // 滚动器 → 刷新回调 (bindPTR 注册)
const PTR_ARM_PX = 70;            // 松手即刷的拉动阈值 (阻尼后)
const PTR_HIDE_PX = -58;          // 藏进模糊带上沿的位移 (与 CSS 起始 transform 一致)

function bindPTR(el, onRefresh) { PTR_PULL_FNS.set(el, onRefresh); }

let ptrEl = null, ptrLb = null;
function ptrFind() {
  ptrEl = ptrEl || document.getElementById("ptr");
  ptrLb = ptrLb || (ptrEl ? ptrEl.querySelector(".ptr-lb") : null);
}

function ptrPull(el, dy) {
  if (!PTR_PULL_FNS.has(el)) return;
  ptrFind();
  if (!ptrEl) return;
  const off = Math.min(Math.max(dy, 0) * 0.4, 110);   // 阻尼 + 封顶
  ptrEl.classList.add("pulling");                     // 跟手: 松手才弹 (transition:none)
  ptrEl.style.transform = `translate(-50%, ${PTR_HIDE_PX + off}px)`;
  const armed = off >= PTR_ARM_PX;
  ptrEl.classList.toggle("armed", armed);
  if (ptrLb) ptrLb.textContent = armed ? "松手刷新" : "下拉刷新";
}

/* 松手 (cancelled: 系统打断的 touchcancel 只弹回不刷新) */
function ptrRelease(el, cancelled) {
  ptrFind();
  if (!ptrEl) return;
  const armed = ptrEl.classList.contains("armed");
  ptrEl.classList.remove("pulling", "armed");
  if (cancelled || !armed) { ptrEl.style.transform = ""; return; }   // 没过阈值: 弹回
  const onRefresh = PTR_PULL_FNS.get(el);
  ptrEl.classList.add("spin");
  ptrEl.style.transform = "translate(-50%, 0px)";    // 钉在模糊带下沿转
  if (ptrLb) ptrLb.textContent = "正在刷新";
  Promise.resolve(onRefresh ? onRefresh() : null)
    .catch(() => {})                                  // 刷新失败视图自己 toast
    .finally(() => {
      ptrEl.classList.remove("spin");
      ptrEl.style.transform = "";                     // transition 弹回
    });
}
