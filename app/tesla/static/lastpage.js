/* 上次停留页 —— 桌面全屏 App 冷启动直接回到上次的页面。
   iOS 主屏图标每次都从固定的 start_url 启动 (添加图标那一刻就定格了),
   不记得上次停在哪页。这里用 localStorage 记住最后停留的 URL, 冷启动
   (新会话) 时 replace 过去。

   - 只在 standalone (主屏全屏 App) 里跳: Safari 书签/链接进来只记录不跳;
   - 会话标记放 sessionStorage: 一次 App 会话内的正常换页不跳, 杀掉重开
     才跳。标记写不进去 (隐私模式) 就整段放弃, 否则每次换页都跳会来回弹;
   - 记录 path+search: 行程弹层深链 (?id=X) / 筛选参数原样回来; 换页时
     立即记一次, 切后台 (visibilitychange) 再记一次 —— trips 弹层开合只动
     URL 不重载, 靠后台那次捕捉最终停留的地址;
   - 只认业务页 (login / 静态资源不记), 跳转目标过白名单, 不可能跳去
     站外。主屏全屏 App 的存储与 Safari 相互独立, 两边各自记各自的。 */
(function () {
  "use strict";
  var PAGES = ["/tesla/charging", "/tesla/stats", "/tesla/chargemap", "/tesla/map", "/tesla/trips",
               "/tesla/groups", "/tesla/live", "/tesla/settings", "/tesla/changelog"];
  var path = location.pathname;
  if (PAGES.indexOf(path) === -1) return;
  var KEY = "mytesla-last-page", LAUNCH = "mytesla-launch-marked";
  var cold = false;
  try { cold = !sessionStorage.getItem(LAUNCH); sessionStorage.setItem(LAUNCH, "1"); }
  catch (e) { return; }        // 会话标记存不下: 宁可不记不跳, 防回弹循环

  function record() {
    try { localStorage.setItem(KEY, location.pathname + location.search); } catch (e) {}
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  record();
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) record();
  });
  if (!cold) return;           // 同一次会话里的正常换页: 记录但不跳
  var standalone = navigator.standalone === true
    || matchMedia("(display-mode: standalone)").matches;
  if (standalone && saved && saved !== location.pathname + location.search
      && PAGES.indexOf(saved.split("?")[0]) !== -1)
    location.replace(saved);
})();
