// tesla-filter-bar — 屏底悬浮条 (3.3.0 定稿; 菜单圆键 2026-09-27 退役后
// 只剩它自己住 #bar-row): 当前视图的筛选 chips (横滑, 放不下左右滚)。全局
// chips 已双双退役 —— 车辆选择住抽屉顶 (tesla-car-switcher), 时间筛选整个
// 下线 (所有视图全时段, 用户点名「时间筛选去掉, 所有的视图都是所有时间」)。
// 视图经 registerChips(key, chips) 注册; chip = {id, label(), isOn()?,
// build(pop)} —— label 每次渲染刷 (选中态文案), build 往 #fb-pop 填交互
// (选完视图自己 closeFbPop + refreshBarChips)。弹层 fixed 锚在被点 chip
// 上方, 不放进横滚条 (防裁剪)。
"use strict";
/* global $, esc */
/* exported registerChips, setBarView, refreshBarChips, closeFbPop, bindFilterBar,
            anchorPop */   // anchorPop: 足迹播放条行的驾驶员筛选 (#fp-drv) 借弹层借锚定

const BAR_CHIPS = {};   // 视图键 → chip 定义数组
let barViewKey = "";

function barChips() { return BAR_CHIPS[barViewKey] || []; }

function registerChips(viewKey, chips) { BAR_CHIPS[viewKey] = chips; }

function closeFbPop() {
  const pop = $("#fb-pop");
  if (pop) { pop.classList.remove("on"); delete pop.dataset.chip; }
}

/* 重渲染当前视图的 chips (筛选变了刷 label/高亮; 视图切换时 setBarView 调)。
   菜单圆键 2026-09-27 退役 (用户点名: 任意页右划都能呼出抽屉, 圆键冗余):
   没有任何 chip 的视图 (状态/分组/统计/设置组) 屏底什么也不剩 —— 整条
   #bar-row 收起, 底部让位高度 --bar-clear 也跟着收 (body.no-bar, 几何在
   tesla-base) */
function refreshBarChips() {
  const bar = $("#filter-bar");
  if (!bar) return;
  const chips = barChips();
  const noChips = !chips.length;
  $("#bar-row").classList.toggle("no-chips", noChips);
  document.body.classList.toggle("no-bar", noChips);
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
    const chip = barChips()[+btn.dataset.i];
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
  /* 点弹层/chips 以外任意处 → 收弹层 (chips 自己走上面的 toggle)。
     #fp-bar 也豁免: 足迹的驾驶员筛选住在播放条行里 (2026-10-02 并行),
     它自己的开/收在 map-filters 里 toggle, 这里的收会抢先一步把再点
     chip 变成「收了又开」。
     pointerdown 不是 click (2026-10-02 用户点名「从哪来回哪去」全弹窗
     审计): 充电/足迹视图里弹层底下是高德画布, 画布 preventDefault 触摸
     后不合成 click —— 靠 click 收, 点地图永远收不起; pointerdown 在触摸
     被吞之前就已派发, 点哪都灵 */
  document.addEventListener("pointerdown", e => {
    const pop = $("#fb-pop");
    if (!pop || !pop.classList.contains("on")) return;
    if (pop.contains(e.target) || e.target.closest("#filter-bar") ||
        e.target.closest("#fp-bar")) return;
    closeFbPop();
  }, true);
  document.addEventListener("keydown", e => {   // Esc: 收弹层 (行程详情那条 Esc 链的一环)
    if (e.key !== "Escape" || !$("#fb-pop").classList.contains("on")) return;
    closeFbPop();
    e.stopImmediatePropagation();   // 一层一关 (2026-10-02 全弹窗「从哪来回哪
                                    // 去」): 别再串关后注册的抽屉
  });
}
