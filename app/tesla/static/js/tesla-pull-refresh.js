// tesla-pull-refresh — 下拉刷新 (手势仲裁的 ptr 支线, 橡皮筋款): 在顶
// 下拉 preventDefault 掐掉原生滚动, 绑定元素本身双曲阻尼跟手下移 (橡皮
// 筋, 渐近 110px 拉不到头), 过阈值 (~70px) 顶部浮出「松开刷新」提示;
// 松手 armed 才 await onRefresh(), 元素过渡弹回原位。
"use strict";
/* exported bindPTR, ptrPull, ptrRelease */

const PTR_PULL_FNS = new Map();   // 滚动器 → 刷新回调 (bindPTR 注册)
const PTR_ARM_PX = 70;            // 松手即刷的拉动阈值 (阻尼后)
const PTR_MAX_PX = 110;           // 橡皮筋渐近上限 (拉不到头)
const PTR_K = 100;                // 双曲阻尼系数 (拉过 100px 时到一半)
const PTR_ARMED = new WeakSet();  // 本次拉动是否过阈值 (ptrPull 记, ptrRelease 消费)

let ptrHint = null;
function ptrFind() { ptrHint = ptrHint || document.getElementById("ptr-hint"); }

function bindPTR(el, onRefresh) {
  PTR_PULL_FNS.set(el, onRefresh);
  el.classList.add("ptr-elastic");   // 松手弹回的过渡 (拉动中被 ptr-pulling 掐掉)
}

function ptrPull(el, dy) {
  if (!PTR_PULL_FNS.has(el)) return;
  ptrFind();
  dy = Math.max(dy, 0);
  const off = PTR_MAX_PX * dy / (dy + PTR_K);   // 橡皮筋: 越拉越紧
  el.classList.add("ptr-pulling");               // 跟手: 松手才弹 (transition:none)
  el.style.transform = `translateY(${off}px)`;
  const armed = off >= PTR_ARM_PX;
  if (armed) PTR_ARMED.add(el);
  if (ptrHint) ptrHint.classList.toggle("show", armed);
}

/* 松手 (cancelled: 系统打断的 touchcancel 只弹回不刷新) */
function ptrRelease(el, cancelled) {
  ptrFind();
  const armed = PTR_ARMED.delete(el);
  el.classList.remove("ptr-pulling");            // 弹回过渡接管
  el.style.transform = "";
  if (ptrHint) ptrHint.classList.remove("show");
  if (cancelled || !armed) return;               // 没过阈值: 只弹回
  const onRefresh = PTR_PULL_FNS.get(el);
  Promise.resolve(onRefresh ? onRefresh() : null)
    .catch(() => {});                            // 刷新失败视图自己 toast
}
