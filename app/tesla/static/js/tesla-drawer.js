// tesla-drawer — 左抽屉 (3.3.0 定稿: 纯导航 · 窄版树状): 开合 (任意页右划
// / 地图页画布左缘条 + 右划/点蒙版) + 拖拽跟手 (视图右划开 · 抽屉身上左划
// 收, 收 side 用指针捕获 —— music-pane-swipe 验证过的路线; 触摸滚动期间
// iOS pointercancel 不可靠, 那条走 tesla-gesture) + 树状导航 (用户点名:
// 一级分组行点开展开二级页面, 手风琴口径一次只开一组; 当前视图所在组自动
// 展开, 单页组直接叶行)。菜单圆键 2026-09-27 退役 (用户点名「所有的页面
// 都是边缘呼出设置, 设置按钮就不需要了」)。图标取 Lucide 开源线性图标集
// (iconfont 同款风格, ISC 许可), path 数据原样内联。车辆选择住抽屉顶
// (drw-cars, 3.3.0 全局生效), 时间筛选已下线 (所有视图全时段), 账号卡住
// 账号设置独立页 (2026-09-27 拆页, 设置组首位) —— 抽屉本体只管导航。
"use strict";
/* global $, layerMotion, VIEWS, navigate, closeFbPop, bindSheetSettle,
          GESTURE_SLOP */
/* exported openDrawer, closeDrawer, drawerDragMove, drawerDragEnd,
            syncDrawerNav, bootDrawer */

/* ---------- 导航分组 (顺序按用户原话: 状态/行程/充电/设置) ----------
   ic = 分组行图标; 单页组 (状态) 不需要 —— 直接渲染成叶行 */
const NAV_GROUPS = [
  { lb: "状态", items: [{ key: "live", lb: "状态" }] },
  { ic: "grp-trips", lb: "行程", items: [
    { key: "trips", lb: "行程列表" },
    { key: "tripstats", lb: "行程统计" },
    { key: "groups", lb: "行程分组" },
    { key: "map", lb: "足迹地图" },
  ] },
  { ic: "grp-charging", lb: "充电", items: [
    { key: "charging", lb: "充电记录" },
    { key: "stats", lb: "充电统计" },
    { key: "battery", lb: "电池健康" },
    { key: "chargemap", lb: "充电地图" },
  ] },
  { ic: "grp-settings", lb: "设置", items: [
    { key: "settings-account", lb: "账号设置" },
    { key: "settings-db", lb: "数据来源" },
    { key: "settings-map", lb: "地图设置" },
    { key: "settings-drivers", lb: "驾驶员" },
    { key: "settings-places", lb: "常用地点" },
    { key: "changelog", lb: "更新日志" },
  ] },
];
/* Lucide 线性图标 (24px 网格, stroke 跟文字色; 值 = svg 内部元素串) */
const drwIcon = (p, cls) =>
  `<svg${cls ? ` class="${cls}"` : ""} viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const DRW_ICONS = {
  live: "<path d='m12 14 4-4' /><path d='M3.34 19a10 10 0 1 1 17.32 0' />",
  trips: "<path d='M3 12h.01' /><path d='M3 18h.01' /><path d='M3 6h.01' /><path d='M8 12h13' /><path d='M8 18h13' /><path d='M8 6h13' />",
  tripstats: "<path d='M22 12h-4l-3 9L9 3l-3 9H2' />",
  groups: "<path d='m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z' /><path d='m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65' /><path d='m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65' />",
  map: "<path d='M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z' /><path d='M15 5.764v15' /><path d='M9 3.236v15' />",
  charging: "<path d='M15 7h1a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-2' /><path d='M6 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h1' /><path d='m11 7-3 5h4l-3 5' /><line x1='22' x2='22' y1='11' y2='13' />",
  stats: "<path d='M3 3v16a2 2 0 0 0 2 2h16' /><path d='M18 17V9' /><path d='M13 17V5' /><path d='M8 17v-3' />",
  battery: "<rect width='16' height='10' x='2' y='8' rx='2' ry='2' /><line x1='22' x2='22' y1='11' y2='13' /><line x1='6' x2='6' y1='12' y2='12' /><line x1='10' x2='10' y1='12' y2='12' /><line x1='14' x2='14' y1='12' y2='12' />",
  chargemap: "<path d='M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0' /><circle cx='12' cy='10' r='3' />",
  "settings-account": "<circle cx='12' cy='12' r='10' /><circle cx='12' cy='10' r='3' /><path d='M7 20.245a7 7 0 0 1 10 0' />",
  "settings-db": "<ellipse cx='12' cy='5' rx='9' ry='3' /><path d='M3 5V19A9 3 0 0 0 21 19V5' /><path d='M3 12A9 3 0 0 0 21 12' />",
  "settings-map": "<line x1='21' x2='14' y1='4' y2='4' /><line x1='10' x2='3' y1='4' y2='4' /><line x1='21' x2='12' y1='12' y2='12' /><line x1='8' x2='3' y1='12' y2='12' /><line x1='21' x2='16' y1='20' y2='20' /><line x1='12' x2='3' y1='20' y2='20' /><line x1='14' x2='14' y1='2' y2='6' /><line x1='8' x2='8' y1='10' y2='14' /><line x1='16' x2='16' y1='18' y2='22' />",
  "settings-drivers": "<circle cx='12' cy='8' r='5' /><path d='M20 21a8 8 0 0 0-16 0' />",
  "settings-places": "<path d='M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z' /><circle cx='7.5' cy='7.5' r='.5' fill='currentColor' />",
  changelog: "<path d='M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' /><path d='M14 2v4a2 2 0 0 0 2 2h4' /><path d='M10 9H8' /><path d='M16 13H8' /><path d='M16 17H8' />",
  "grp-trips": "<circle cx='6' cy='19' r='3' /><path d='M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15' /><circle cx='18' cy='5' r='3' />",
  "grp-charging": "<path d='M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z' />",
  "grp-settings": "<path d='M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z' /><circle cx='12' cy='12' r='3' />",
  chev: "<path d='m6 9 6 6 6-6' />",
};

/* ---------- 开合 ---------- */
let drawerShown = false;
function openDrawer() {
  drawerShown = true;
  closeFbPop();                                  // 弹层在抽屉底下, 一起收
  const d = $("#drawer"), mask = $("#drawer-mask");
  d.style.transform = "";                        // 清拖拽残留, 交给 class 过渡
  d.classList.remove("dragging");
  d.classList.add("on");
  mask.style.transition = ""; mask.style.opacity = "";
  mask.classList.add("on");
  layerMotion();
}
function closeDrawer() {
  drawerShown = false;
  const d = $("#drawer"), mask = $("#drawer-mask");
  d.style.transform = "";
  d.classList.remove("dragging");
  d.classList.remove("on");
  mask.style.transition = ""; mask.style.opacity = "";
  mask.classList.remove("on");
  layerMotion();
}

/* ---------- 视图右划开抽屉 (手势仲裁转来; dx = 自定轴起的横向位移) ---------- */
let dragDx = 0, dragVx = 0, dragT = 0;
function drawerDragMove(dx) {
  const d = $("#drawer"), mask = $("#drawer-mask");
  const w = d.offsetWidth || 1;
  const x = Math.min(Math.max(dx, 0), w);        // 只往右拉开
  const now = performance.now();
  dragVx = (dx - dragDx) / Math.max(now - dragT, 1);
  dragDx = dx; dragT = now;
  d.classList.add("dragging");                   // 拖拽期不过渡, 跟手
  d.style.transform = `translateX(${x - w}px)`;
  mask.style.transition = "none";
  mask.style.opacity = String(0.5 * (x / w));    // 蒙版浓度跟手
  mask.classList.add("on");
}
function drawerDragEnd() {
  const d = $("#drawer");
  const w = d.offsetWidth || 1;
  const x = Math.min(Math.max(dragDx, 0), w);
  const flick = dragVx > 0.5;                    // 快速右甩也算开
  if (x > w / 3 || (flick && x > 20)) openDrawer();
  else closeDrawer();
}

/* ---------- 抽屉身上左划收 (指针捕获; 竖滚导航时系统会 pointercancel, 放弃) ---------- */
function bindDrawerDrag() {
  const d = $("#drawer");
  let pid = -1, sx = 0, sy = 0, dragging = false, lastX = 0, lastT = 0, vx = 0;
  d.addEventListener("pointerdown", e => {
    if (!drawerShown || pid !== -1) return;
    pid = e.pointerId; sx = e.clientX; sy = e.clientY;
    dragging = false; lastX = e.clientX; lastT = performance.now(); vx = 0;
  });
  d.addEventListener("pointermove", e => {
    if (e.pointerId !== pid) return;
    const dx = e.clientX - sx, dy = e.clientY - sy;
    if (!dragging) {
      if (Math.abs(dx) < GESTURE_SLOP && Math.abs(dy) < GESTURE_SLOP) return;
      if (Math.abs(dx) <= Math.abs(dy)) { pid = -1; return; }   // 竖滚: 放弃
      dragging = true;
      try { d.setPointerCapture(pid); } catch (_err) { /* 老版本 iOS 不支持 */ }
      d.classList.add("dragging");
    }
    const now = performance.now();
    vx = (e.clientX - lastX) / Math.max(now - lastT, 1);
    lastX = e.clientX; lastT = now;
    const w = d.offsetWidth || 1;
    d.style.transform = `translateX(${Math.max(dx, -w)}px)`;    // 左收: dx 负
    const mask = $("#drawer-mask");
    mask.style.transition = "none";
    mask.style.opacity = String(0.5 * Math.max(0, 1 + dx / w));
  });
  const finish = e => {
    if (e.pointerId !== pid) return;
    pid = -1;
    if (!dragging) return;
    dragging = false;
    const w = d.offsetWidth || 1;
    const dx = lastX - sx;
    if (dx < -w / 3 || (vx < -0.5 && dx < -20)) closeDrawer();
    else openDrawer();                            // 没拉够: 弹回开着
  };
  d.addEventListener("pointerup", finish);
  d.addEventListener("pointercancel", () => {     // 系统打断 (来电/通知): 弹回开着
    if (!dragging) return;
    pid = -1; dragging = false;
    openDrawer();
  });
}

/* ---------- 树状导航 (只渲染已注册的视图) ----------
   多页组 = 分组行 (图标 + 组名 + chevron) 点开手风琴展开二级;
   单页组直接一张卡一枚叶行 (没有展开语义) */
const leafRow = it => `<button type="button" class="drw-leaf" data-nav="${it.key}">` +
  `${drwIcon(DRW_ICONS[it.key])}<span>${it.lb}</span></button>`;

function buildNav() {
  const nav = $("#drw-nav");
  nav.innerHTML = NAV_GROUPS.map(g => {
    const items = g.items.filter(it => VIEWS[it.key]);
    if (!items.length) return "";
    if (items.length === 1)                       // 单页组: 直接叶行卡
      return `<div class="drw-card">${leafRow(items[0])}</div>`;
    return `<div class="drw-card drw-grp">` +
      `<button type="button" class="drw-grp-row">${drwIcon(DRW_ICONS[g.ic])}` +
      `<span>${g.lb}</span>${drwIcon(DRW_ICONS.chev, "chev")}</button>` +
      `<div class="drw-sub"><div class="drw-sub-in">` +
      items.map(leafRow).join("") +
      `</div></div></div>`;
  }).join("");
  nav.addEventListener("click", e => {
    const leaf = e.target.closest("button.drw-leaf");
    if (leaf) { closeDrawer(); navigate(leaf.dataset.nav); return; }
    const grp = e.target.closest("button.drw-grp-row");
    if (!grp) return;
    /* 手风琴: 一次只开一组, 再点同一组收起 */
    const card = grp.closest(".drw-grp");
    const wasOpen = card.classList.contains("open");
    document.querySelectorAll("#drw-nav .drw-grp.open")
      .forEach(c => c.classList.remove("open"));
    if (!wasOpen) card.classList.add("open");
  });
}
function syncDrawerNav(key) {
  document.querySelectorAll("#drw-nav .drw-leaf").forEach(b =>
    b.classList.toggle("on", b.dataset.nav === key));
  /* 当前视图所在组自动展开, 其余收起 (跟手风琴同一口径) */
  document.querySelectorAll("#drw-nav .drw-grp").forEach(c =>
    c.classList.toggle("open", !!c.querySelector(`.drw-leaf[data-nav="${key}"]`)));
}

/* ---------- 接线 (app-boot 调; 那时视图都已注册) ---------- */
function bootDrawer() {
  /* 开合入口只剩蒙版点击 + 右划/左划拖拽 —— 菜单圆键退役 (2026-09-27
     用户点名: 任意页右划/地图左缘条都能呼出抽屉, 圆键是冗余入口) */
  $("#drawer-mask").addEventListener("click", closeDrawer);
  /* Esc 剥层: 本模块先于 tesla-filter-bar/视图脚本挂上, 关了抽屉就拦住
     事件往下传 (stopImmediatePropagation), 一层 Esc 只关一层 */
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape" || !drawerShown) return;
    closeDrawer();
    e.stopImmediatePropagation();
  });
  buildNav();
  bindDrawerDrag();
  /* 抽屉也是 fixed + 磨砂 + transform 的层: 视口折腾 (键盘/回前台) 后旧栅格
     保险同五张弹层 (7556 第五道保险), 复用 bindSheetSettle 的微变换收净 */
  bindSheetSettle($("#drawer"), "on");
}
