// charging-nav.js — 充电记录页 (5/6): 导航到充电站 —— 先弹选单挑地图 App, 点
// 一个只拉一个; 没装的长按隐藏 (localStorage 记住), ＋ 胶囊恢复。
// 由 index.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 index.html
// 里的顺序加载, 跨模块引用走全局); 底座在 charging-page.js, 记录卡片在
// charging-cards.js, 筛选交互在 charging-filters.js, 详情弹层在
// charging-detail.js, 费用编辑在 charging-cost.js。
/* global $, GCJ02, navBd */
/* exported openNavChooser, closeNavChooser */
"use strict";
/* ---------- 导航到充电站 ----------
   先弹选单让用户挑地图 App, 点一个只拉一个。试过自动探测 (逐个拉
   scheme, 按页面切没切后台判断装没装) —— iOS 拉 scheme 前先弹「在 xx
   中打开」确认框, 用户按确认前页面不切后台, 探测窗口一过就当没装接着
   拉下一个, 高德百度被连环拉起 (2026-09-13 用户实测), 弃。各图商都用
   国测局 GCJ-02 坐标, TeslaMate 存的是 WGS-84, 直接用会偏几百米。 */
/* 选单里的 App 列表: 网页枚举不了手机装了哪些地图 (这正是弃自动探测的原因),
   所以四个都列, 没装的 (如腾讯) 长按一行隐藏掉, 记在 localStorage。 */
const NAV_APPS = [
  { app: "amap", label: "高德地图" },
  { app: "baidu", label: "百度地图" },
  { app: "tencent", label: "腾讯地图" },
  { app: "apple", label: "苹果地图" },
];
const navHidden = new Set(JSON.parse(localStorage.getItem("navHiddenApps") || "[]")
  .filter(x => NAV_APPS.some(a => a.app === x)));
let navLongFired = false;   // 长按已处理, 跟着的 click 要吞掉

function renderNavApps() {   // 在用的行 + 隐藏过的 (＋ 恢复胶囊)
  const appsEl = $("#nav-apps");
  appsEl.innerHTML = NAV_APPS.filter(a => !navHidden.has(a.app))
    .map(a => `<button data-app="${a.app}">${a.label}</button>`).join("");
  const hidden = NAV_APPS.filter(a => navHidden.has(a.app));
  if (hidden.length) {
    const box = document.createElement("div");
    box.className = "nav-restore";
    box.innerHTML = hidden.map(a =>
      `<button data-restore="${a.app}">＋ ${a.label}</button>`).join("");
    appsEl.appendChild(box);
  }
}
renderNavApps();

let navTarget = null;

function navAppUrl(app, d) {
  const [lng, lat] = GCJ02.wgs84ToGcj02(d.lng, d.lat);
  const name = encodeURIComponent(d.location);
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (app === "amap")                        // 高德 (dev=0: 坐标已是 GCJ-02)
    return (ios ? "iosamap://navi?sourceApplication=mytesla&backScheme=mytesla"
                : "androidamap://navi?sourceApplication=mytesla")
           + `&poiname=${name}&lat=${lat}&lon=${lng}&dev=0&style=0`;
  if (app === "baidu")                       // 百度 (coord_type=gcj02: 免转 BD-09)
    return `${ios ? "baidumap" : "bdapp"}://map/direction`
           + `?origin=${encodeURIComponent("我的位置")}&destination=${name}|${lat},${lng}`
           + `&coord_type=gcj02&mode=driving&src=mytesla`;
  if (app === "tencent")                     // 腾讯 (fromcoord=CurrentLocation: 出发点用当前定位)
    return `qqmap://map/routeplan?type=drive&from=${encodeURIComponent("我的位置")}`
           + `&fromcoord=CurrentLocation&to=${name}&tocoord=${lat},${lng}&policy=1&referer=mytesla`;
  return `https://maps.apple.com/?daddr=${lat},${lng}&q=${name}&dirflg=d`;
}

function openNavChooser(d) {
  navTarget = d;
  navBd.hidden = false;
  requestAnimationFrame(() => navBd.classList.add("on"));
}

function closeNavChooser() {
  navTarget = null;
  navBd.classList.remove("on");
  setTimeout(() => { navBd.hidden = true; }, 230);
}

(() => {   // 长按 480ms 隐藏一行 (移动 >10px 取消), contextmenu 拦下防 iOS 掐触摸
  const appsEl = $("#nav-apps");
  let timer = 0, sx = 0, sy = 0;
  appsEl.addEventListener("pointerdown", e => {
    navLongFired = false;   // 任何新按压都解除吞 click 旗标 (含 ＋ 恢复胶囊)
    const b = e.target.closest("button[data-app]");
    if (!b) return;
    sx = e.clientX; sy = e.clientY;
    timer = setTimeout(() => {
      navLongFired = true;
      const app = b.dataset.app;
      navHidden.add(app);
      localStorage.setItem("navHiddenApps", JSON.stringify([...navHidden]));
      renderNavApps();                       // 行就地消失, ＋ 恢复胶囊随即出现
    }, 480);
  });
  const cancel = e => {
    if (!timer) return;
    if (e.type === "pointermove" &&
        Math.hypot(e.clientX - sx, e.clientY - sy) <= 10) return;
    clearTimeout(timer); timer = 0;
  };
  appsEl.addEventListener("pointermove", cancel);
  appsEl.addEventListener("pointerup", cancel);
  appsEl.addEventListener("pointercancel", cancel);
  appsEl.addEventListener("contextmenu", e => e.preventDefault());
})();
$("#nav-apps").addEventListener("click", e => {
  if (navLongFired) { navLongFired = false; return; }   // 长按隐藏后的 click 吞掉
  const r = e.target.closest("button[data-restore]");   // ＋ 恢复胶囊
  if (r) {
    navHidden.delete(r.dataset.restore);
    localStorage.setItem("navHiddenApps", JSON.stringify([...navHidden]));
    renderNavApps();
    return;
  }
  const b = e.target.closest("button[data-app]");
  if (!b || !navTarget) return;
  const url = navAppUrl(b.dataset.app, navTarget);
  closeNavChooser();
  location.href = url;                       // 只拉这一个, 不探测不连环
});
$("#nav-cancel").addEventListener("click", closeNavChooser);
navBd.addEventListener("click", e => { if (e.target === navBd) closeNavChooser(); });
