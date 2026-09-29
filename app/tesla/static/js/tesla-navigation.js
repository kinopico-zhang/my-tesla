// tesla-navigation — 内存路由 (music-navigation 同思路): VIEWS 注册表 +
// navigate/refreshCurrent。永不 pushState —— 壳内零历史条目, iOS 屏幕边缘
// 后退无处可退 (跟 music 一样禁掉边缘返回); 视图切换各自保留滚动位置
// (藏起前记住 .view-scroll 的 scrollTop, 回来时还原 —— display:none 会丢)。
// 3.3.0 定稿回到抽屉导航: 页面各自 hidden 切换 (tab-group 整编/pager 横滑
// 已撤, 用户点名二级页直挂抽屉菜单), navigate 是唯一通路。
"use strict";
/* global setBarView, syncDrawerNav, layerMotion, saveLastView */
/* exported VIEWS, registerView, navigate, currentView, refreshCurrent */

const VIEWS = {};            // key → {title, el, show(), hide(), refresh()}
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
  } else {
    /* 冷启首跳没有「上一视图」可藏, 但 HTML 里默认亮着状态页 —— 恢复上次
       视图/深链直跳别页时它不会被藏掉, 绝对定位叠放 = 两页内容叠影
       (P2 用户实报)。把其余视图全扫一遍藏净, 只留本次的目标页 */
    document.querySelectorAll("main > .view").forEach(v => { v.hidden = true; });
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
