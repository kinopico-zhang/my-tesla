// menu-user.js — 品牌下拉菜单顶部显示当前登录的账号 (全站共用小件)。
// 挂在根 /static (账号层的静态目录), 应用页面都引这一个文件;
// 样式自带 (各应用配色略异, 用一套中性的深色指标), 找不到菜单就静默不装。
// 顺带管一件全站的事: 点在菜单外任意位置 → 收起所有展开的下拉。
"use strict";

(function () {
  /** 装进行: 人形图标 + 名字 (+ 管理员徽标); 纯展示, 不可点。 */
  function install(name, isAdmin) {
    const menu = document.querySelector(".brand-menu .menu");
    if (!menu || menu.querySelector(".menu-user")) return;
    if (!document.getElementById("menu-user-style")) {
      const style = document.createElement("style");
      style.id = "menu-user-style";
      style.textContent = [
        ".menu-user{display:flex;align-items:center;gap:10px;padding:9px 12px;",
        "margin:0 0 5px;border-bottom:1px solid rgba(255,255,255,.1);",
        "font-size:14px;color:rgba(235,235,245,.65);white-space:nowrap;",
        "-webkit-user-select:none;user-select:none;}",
        ".menu-user svg{flex-shrink:0;opacity:.7;}",
        ".menu-user span{overflow:hidden;text-overflow:ellipsis;}",
        ".menu-user em{font-style:normal;font-size:10px;color:#7db3f0;",
        "border:1px solid rgba(125,179,240,.5);border-radius:4px;",
        "padding:0 4px;margin-left:auto;flex-shrink:0;}",
      ].join("");
      document.head.appendChild(style);
    }
    const row = document.createElement("div");
    row.className = "menu-user";
    row.innerHTML =
      '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">'
      + '<path d="M12 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z'
      + 'M5.5 20a6.5 6.5 0 0 1 13 0" fill="none" stroke="currentColor"'
      + ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      + "<span></span>"
      + (isAdmin ? "<em>管理员</em>" : "");
    row.querySelector("span").textContent = name;   // 名字走 DOM, 不进 innerHTML
    menu.prepend(row);
  }

  fetch("/api/me")
    .then((response) => (response.ok ? response.json() : null))
    .then((me) => {
      if (me && me.name) install(me.name, !!me.is_admin);
    })
    .catch(() => { /* 会话过期/断网: 菜单照旧, 只是不显示名字 */ });

  // 菜单外任意点击 → 收起所有展开的下拉 (details.nav-menu, 各页通用)。
  // capture 阶段挂: 页面自己的 click 处理器就算 stopPropagation 也拦不住;
  // 点的是另一份菜单的 summary 时, 那份留给原生开关处理, 其余的收掉。
  document.addEventListener("click", (event) => {
    for (const menu of document.querySelectorAll("details.nav-menu[open]")) {
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    }
  }, true);
})();
