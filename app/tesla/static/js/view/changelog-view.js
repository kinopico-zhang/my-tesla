// view/changelog-view.js — 更新日志视图 (壳版): 版本块渲染 + 失败重试。
// 旧版 (/static/changelog-page.js, My Tesla / My Music 共用的页骨架) 自带
// $/esc/getJSON/页签菜单/顶栏刷新/登出并自执行 load() —— 壳里不能直接复用
// (全局 load() 会撞行程分组视图, D2 定案), 按视图生命周期重写; 数据仍走
// /tesla/changelog/api/entries, 标记与样式沿用 tesla-changelog.css。
/* global $, esc, getJSON, registerView, bindGestures */
/* exported clLoad */
"use strict";

const API_URL = "/tesla/changelog/api/entries";
const KIND_CLS = { "新增": "add", "改进": "imp", "修复": "fix" };

function clRender(list) {   // 行写进内层 #cl-list, 加载/错误节点不被顶掉
  $("#cl-list").innerHTML = list.map(v => `
    <div class="ver">
      <div class="v-head">
        <span class="v-badge">${esc(v.version)}</span>
        <span class="v-date">${esc(v.date)}</span>
      </div>
      <ul class="v-items">${v.items.map(it => `
        <li><span class="k k-${KIND_CLS[it.kind] || "imp"}">${esc(it.kind)}</span><span class="t">${esc(it.text)}</span></li>`).join("")}
      </ul>
    </div>`).join("");
}

function clShowError(msg) {
  $("#error-text").textContent = msg || "加载失败";
  $("#error").hidden = false;
}

async function clLoad() {
  $("#error").hidden = true;
  $("#loading").hidden = false;
  try {
    const list = await getJSON(API_URL);
    if (list.length) clRender(list);
    else clShowError("还没有版本记录");
  } catch (e) {
    clShowError(e.message);
  }
  $("#loading").hidden = true;
}

$("#cl-retry").addEventListener("click", clLoad);

/* 手势: 滚动器右划开抽屉 / 在顶下拉刷新 */
const clScroll = $("#cl-scroll");
bindGestures(clScroll, { drawer: true, ptr: true, onRefresh: clLoad });

let clBooted = false;
registerView("changelog", {
  title: "更新日志",
  el: $("#view-changelog"),
  show() { if (!clBooted) { clBooted = true; clLoad(); } },
  refresh: clLoad,
});
