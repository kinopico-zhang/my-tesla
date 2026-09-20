// tesla-filter-bar — 屏底悬浮筛选条: 菜单圆键 (开抽屉, 在 tesla-drawer 绑)
// + 当前视图的筛选 chips (横滑, 放不下左右滚)。视图经 registerChips(key,
// chips) 注册; chip = {id, label(), isOn()?, build(pop)} —— label 每次渲染
// 刷 (选中态文案), build 往 #fb-pop 填交互 (选完视图自己 closeFbPop +
// refreshBarChips)。弹层 fixed 锚在被点 chip 上方, 不放进横滚条 (防裁剪)。
"use strict";
/* global $, esc */
/* exported registerChips, setBarView, refreshBarChips, closeFbPop, bindFilterBar */

const BAR_CHIPS = {};   // 视图键 → chip 定义数组
let barViewKey = "";

function registerChips(viewKey, chips) { BAR_CHIPS[viewKey] = chips; }

function closeFbPop() {
  const pop = $("#fb-pop");
  if (pop) { pop.classList.remove("on"); delete pop.dataset.chip; }
}

/* 重渲染当前视图的 chips (筛选变了刷 label/高亮; 视图切换时 setBarView 调) */
function refreshBarChips() {
  const bar = $("#filter-bar");
  if (!bar) return;
  const chips = BAR_CHIPS[barViewKey] || [];
  bar.classList.toggle("no-chips", !chips.length);
  bar.innerHTML = chips.map((c, i) =>
    `<button type="button" class="fchip${c.isOn && c.isOn() ? " on" : ""}" data-i="${i}">${esc(c.label())}</button>`).join("");
}

function setBarView(viewKey) {
  barViewKey = viewKey;
  closeFbPop();
  refreshBarChips();
}

/* 弹层锚定: chip 上方 10px, 左右夹在屏内; 实在放不下兜底到 chip 下方 */
function anchorPop(pop, btn) {
  const r = btn.getBoundingClientRect();
  pop.style.left = "0px"; pop.style.top = "0px";   // 先归位再量自身宽高
  const pw = pop.offsetWidth, ph = pop.offsetHeight;
  let x = r.left + r.width / 2 - pw / 2;
  x = Math.min(Math.max(x, 10), window.innerWidth - pw - 10);
  let y = r.top - ph - 10;
  if (y < 10) y = r.bottom + 10;
  pop.style.left = x + "px";
  pop.style.top = y + "px";
}

function bindFilterBar() {
  const bar = $("#filter-bar");
  if (!bar) return;
  bar.addEventListener("click", e => {
    const btn = e.target.closest("button.fchip");
    if (!btn) return;
    const chips = BAR_CHIPS[barViewKey] || [];
    const chip = chips[+btn.dataset.i];
    if (!chip) return;
    const pop = $("#fb-pop");
    const reopen = pop && pop.dataset.chip !== btn.dataset.i;   // 换 chip / 首开
    closeFbPop();
    if (!reopen) return;                                       // 再点同一 chip = 收起
    pop.dataset.chip = btn.dataset.i;
    pop.innerHTML = "";
    chip.build(pop);
    pop.classList.add("on");
    anchorPop(pop, btn);
  });
  /* 点弹层/chips 以外任意处 → 收弹层 (chips 自己走上面的 toggle) */
  document.addEventListener("click", e => {
    const pop = $("#fb-pop");
    if (!pop || !pop.classList.contains("on")) return;
    if (pop.contains(e.target) || e.target.closest("#filter-bar")) return;
    closeFbPop();
  }, true);
  document.addEventListener("keydown", e => {   // Esc: 收弹层 (行程详情那条 Esc 链的头一环)
    if (e.key === "Escape") closeFbPop();
  });
}
