// changelog-page.js — 更新日志页渲染器: 菜单收起 / 版本块渲染 / 顶栏刷新 /
// 失败重试 / 退出登录。数据源 (应用自己的条目接口) 由页面 body 的
// data-changelog-api 指定。
"use strict";
/* 页签菜单: 点空白处收起。 */
document.addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ("HTTP " + r.status));
  return r.json();
}

const API_URL = document.body.dataset.changelogApi;
const KIND_CLS = { "新增": "add", "改进": "imp", "修复": "fix" };

function render(list) {   // 行写进内层 #list, 加载/错误节点不被顶掉
  $("#list").innerHTML = list.map(v => `
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

async function load() {
  $("#error").hidden = true;
  $("#loading").hidden = false;
  try {
    const list = await getJSON(API_URL);
    if (list.length) render(list);
    else showError("还没有版本记录");
  } catch (e) {
    showError(e.message);
  }
  $("#loading").hidden = true;
}
function showError(msg) {
  $("#error-text").textContent = msg || "加载失败";
  $("#error").hidden = false;
}

$("#retry").addEventListener("click", load);
/* 顶栏刷新: 重拉当前页数据 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await load();
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
  location.href = "/login";
});

load();
