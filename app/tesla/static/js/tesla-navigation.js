// tesla-navigation — 内存路由 (music-navigation 同思路): VIEWS 注册表 +
// navigate/refreshCurrent。永不 pushState —— 壳内零历史条目, iOS 屏幕边缘
// 后退无处可退 (跟 music 一样禁掉边缘返回); 视图切换各自保留滚动位置
// (藏起前记住 .view-scroll 的 scrollTop, 回来时还原 —— display:none 会丢)。
"use strict";
/* global setBarView, syncDrawerNav, layerMotion, saveLastView */
/* exported VIEWS, registerView, navigate, currentView, refreshCurrent */

const VIEWS = {};            // key → {title, group, icon, el, show(), hide(), refresh()}
const VIEW_SCROLLS = {};     // key → 藏起前的 scrollTop
let currentKey = "";

function registerView(key, def) { VIEWS[key] = def; }

function viewScroller(key) {
  const def = VIEWS[key];
  return def && def.el ? def.el.querySelector(".view-scroll") : null;
}

function navigate(key) {
  const next = VIEWS[key];
  if (!next || !next.el) return;
  if (key === currentKey) { refreshCurrent(); return; }   // 点当前项 = 刷新
  if (currentKey && VIEWS[currentKey]) {
    const prev = VIEWS[currentKey];
    const sc = viewScroller(currentKey);
    if (sc) VIEW_SCROLLS[currentKey] = sc.scrollTop;
    if (prev.hide) prev.hide();
    prev.el.hidden = true;
  }
  currentKey = key;
  next.el.hidden = false;
  const sc = viewScroller(key);
  if (sc && VIEW_SCROLLS[key] != null) sc.scrollTop = VIEW_SCROLLS[key];
  setBarView(key);       // 屏底筛选条换当前视图的 chips
  syncDrawerNav(key);    // 抽屉导航高亮跟随
  layerMotion();         // 切换瞬间撤磨砂防重影 (400ms 自愈)
  if (next.show) next.show();
  saveLastView(key);
}

function currentView() { return VIEWS[currentKey] || null; }

function refreshCurrent() {
  const cur = currentView();
  if (cur && cur.refresh) return cur.refresh();
  return null;
}
