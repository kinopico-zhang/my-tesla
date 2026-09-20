// tesla-drawer — 左抽屉: 开合 (菜单圆键/右划/点蒙版) + 拖拽跟手 (视图右划
// 开 · 抽屉身上左划收, 收 side 用指针捕获 —— music-pane-swipe 验证过的
// 路线; 触摸滚动期间 iOS pointercancel 不可靠, 那条走 tesla-gesture) +
// 导航分组 (每个子类带图标) + 顶部时间菜单/车辆行 + 底部账号行/登出。
// 用户点名: 右划拉出; 抽屉加宽 (min(400px, 92vw)), 子项图标瓦片每行 4 个,
// 压缩纵向空间。
"use strict";
/* global $, layerMotion, VIEWS, navigate,
          closeFbPop, GESTURE_SLOP */
/* exported openDrawer, closeDrawer, drawerDragMove, drawerDragEnd,
            syncDrawerNav, bootDrawer */

/* ---------- 导航分组 (设置按用户原话 = 四个子视图) ---------- */
const NAV_GROUPS = [
  { lb: "充电", items: [
    { key: "charging", lb: "充电记录" },
    { key: "stats", lb: "充电统计" },
    { key: "chargemap", lb: "充电地图" },
  ] },
  { lb: "行程", items: [
    { key: "trips", lb: "行程列表" },
    { key: "groups", lb: "行程分组" },
    { key: "map", lb: "足迹地图" },
  ] },
  { lb: "驾驶", items: [{ key: "live", lb: "驾驶" }] },
  { lb: "设置", items: [
    { key: "settings-db", lb: "数据来源" },
    { key: "settings-map", lb: "地图设置" },
    { key: "settings-drivers", lb: "驾驶员" },
    { key: "changelog", lb: "更新日志" },
  ] },
];
/* 每个子类一枚 20px 线性图标 (stroke 跟文字色, 选中态提亮) */
const drwIcon = p => `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const DRW_ICONS = {
  charging: drwIcon('<path d="M13 2.5 4.5 13.5H11l-1 8 8.5-11H12l1-8z"/>'),
  stats: drwIcon('<path d="M5 20v-6M12 20V4.5M19 20v-9"/>'),
  chargemap: drwIcon('<path d="M12 21.5s-6.8-5.6-6.8-10.6a6.8 6.8 0 1 1 13.6 0c0 5-6.8 10.6-6.8 10.6z"/><circle cx="12" cy="10.5" r="2.4"/>'),
  trips: drwIcon('<circle cx="6" cy="18" r="2.1"/><circle cx="18" cy="6" r="2.1"/><path d="M7.5 16.5 16.5 7.5"/>'),
  groups: drwIcon('<path d="M12 3.5 3.5 8l8.5 4.5L20.5 8 12 3.5z"/><path d="M3.5 12.5 12 17l8.5-4.5"/><path d="M3.5 17 12 21.5 20.5 17"/>'),
  map: drwIcon('<path d="M9 4.5 3.5 6.5v13L9 17.5l6 2 5.5-2v-13l-5.5 2-6-2z"/><path d="M9 4.5v13M15 6.5v13"/>'),
  live: drwIcon('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="2.6"/><path d="M12 14.6v5.9M9.7 10.8 3.6 9.9M14.3 10.8l6.1-.9"/>'),
  "settings-db": drwIcon('<ellipse cx="12" cy="5.5" rx="7" ry="2.7"/><path d="M5 5.5v13c0 1.5 3.1 2.7 7 2.7s7-1.2 7-2.7v-13"/><path d="M5 12c0 1.5 3.1 2.7 7 2.7s7-1.2 7-2.7"/>'),
  "settings-map": drwIcon('<path d="M4 6.5h8.5M17.5 6.5H20M4 12h2.5M11.5 12H20M4 17.5h11.5"/><circle cx="15" cy="6.5" r="2"/><circle cx="8.5" cy="12" r="2"/><circle cx="18" cy="17.5" r="2"/>'),
  "settings-drivers": drwIcon('<circle cx="12" cy="7.5" r="3.6"/><path d="M5 20.5a7 7 0 0 1 14 0"/>'),
  changelog: drwIcon('<path d="M14 3.5H6.5A1.5 1.5 0 0 0 5 5v14a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19V8.5l-5-5z"/><path d="M14 3.5v5h5M8.5 13h7M8.5 16.5h4.5"/>'),
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

/* ---------- 导航 (只渲染已注册的视图; 后续阶段逐个点亮) ---------- */
function buildNav() {
  const nav = $("#drw-nav");
  nav.innerHTML = NAV_GROUPS.map(g => {
    const items = g.items.filter(it => VIEWS[it.key]);
    if (!items.length) return "";
    /* 子项 = 图标瓦片, 每组一张网格 (每行 4 个, 用户点名压纵向空间) */
    return `<div class="drw-group-lb">${g.lb}</div>` +
      `<div class="drw-grid">` +
      items.map(it => `<button type="button" class="drw-item" data-nav="${it.key}">` +
        `${DRW_ICONS[it.key] || ""}<span>${it.lb}</span></button>`).join("") +
      `</div>`;
  }).join("");
  nav.addEventListener("click", e => {
    const b = e.target.closest("button.drw-item");
    if (!b) return;
    closeDrawer();
    navigate(b.dataset.nav);
  });
}
function syncDrawerNav(key) {
  document.querySelectorAll("#drw-nav .drw-item").forEach(b =>
    b.classList.toggle("on", b.dataset.nav === key));
}

/* ---------- 接线 (app-boot 调; 那时视图都已注册) ---------- */
function bootDrawer() {
  $("#menu-key").addEventListener("click", openDrawer);
  $("#drawer-mask").addEventListener("click", closeDrawer);
  /* 刷新按钮已按用户要求撤掉: 每个视图都能下拉刷新 (tesla-pull-refresh),
     车辆/时间档切换也会整页重拉 (app-boot 接的 refreshCurrent)。 */
  $("#logout").addEventListener("click", async () => {
    try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
    location.href = "/login";
  });
  /* Esc 剥层: 本模块先于 tesla-filter-bar/视图脚本挂上, 关了抽屉就拦住
     事件往下传 (stopImmediatePropagation), 一层 Esc 只关一层 */
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape" || !drawerShown) return;
    closeDrawer();
    e.stopImmediatePropagation();
  });
  /* 抽屉里点开另一份 details 菜单 (时间), 点别处收起旧的那份 */
  document.addEventListener("click", e => {
    const t = e.target;
    if (!(t instanceof Element) || !t.isConnected) return;
    const inside = t.closest("details.drw-menu");
    document.querySelectorAll("details.drw-menu[open]").forEach(m => {
      if (m !== inside) m.removeAttribute("open");
    });
  });
  buildNav();
  bindDrawerDrag();
  /* 账号行 (/api/me; 名字走 DOM, 不进 innerHTML) */
  fetch("/api/me").then(r => (r.ok ? r.json() : null)).then(me => {
    const row = $("#acct-row");
    if (!row || !me || !me.name) return;
    $("#acct-name").textContent = me.name;
    if (me.is_admin) $("#acct-badge").hidden = false;
    row.hidden = false;
  }).catch(() => { /* 会话过期/断网: 行不亮而已 */ });
}
