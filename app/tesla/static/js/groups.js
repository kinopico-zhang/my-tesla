// groups.js — 行程分组页: 分组存自有库 (trips 的 api/groups), 打开 = 跳行程页
// 合并播放 (?ids= 深链, 播完关弹层自动回本页)。创建入口在行程列表
// (长按多选 → 存为分组), 本页只管浏览/打开/改名/删除。
"use strict";

document.addEventListener("click", e => {   // 页签菜单点空白处收起
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

let groups = [];      // 列表当前数据 (渲染 + 委托处理器查用)
let toastTimer = null;

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  requestAnimationFrame(() => el.classList.add("on"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove("on");
    setTimeout(() => { el.hidden = true; }, 250);
  }, 1800);
}

function rowHTML(g) {
  return `<div class="gp-item" data-gid="${g.id}" data-ids="${g.ids.join(",")}">` +
    `<button class="gp-main"><div class="gp-name">${esc(g.name)}</div>` +
    `<div class="gp-meta">${g.n} 段 · ${g.km} km` +
    (g.span ? ` · ${esc(g.span)}` : "") + `</div></button>` +
    `<button class="gp-act gp-rename">改名</button>` +
    `<button class="gp-act gp-del">删除</button></div>`;
}

function render() {
  $("#gp-spin").hidden = true;
  $("#gp-empty").hidden = groups.length > 0;
  $("#count-badge").textContent = groups.length ? `${groups.length} 组` : "";
  $("#gp-list").innerHTML = groups.map(rowHTML).join("");
}

async function load() {
  $("#errbox").hidden = true;
  $("#gp-spin").hidden = false;
  try {
    const r = await fetch("/tesla/trips/api/groups");
    if (r.status === 401) { location.replace("/login"); return; }
    if (!r.ok) throw new Error(`${r.status}`);
    groups = await r.json();
  } catch {
    groups = [];
    $("#gp-spin").hidden = true;
    $("#errbox").hidden = false;
  }
  render();
}

/* 行点击委托: 点条目跳行程页合并播放 (?ids= 深链, 关弹层自动回本页);
   改名行内编辑; 删除二次确认 (3s 内再点才删)。
   行内重渲染会脱链事件目标 —— 委托先判 isConnected (与行程页同一坑)。 */
$("#gp-list").addEventListener("click", async e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const item = t.closest(".gp-item");
  if (!item) return;
  const gid = +item.dataset.gid;
  const group = groups.find(g => g.id === gid);
  if (t.closest(".gp-del")) {
    const btn = t.closest(".gp-del");
    if (!btn.classList.contains("arm")) {          // 第一次点: 挂起 3s
      btn.classList.add("arm"); btn.textContent = "确认删除";
      setTimeout(() => { btn.classList.remove("arm"); btn.textContent = "删除"; }, 3000);
      return;
    }
    try {
      const r = await fetch(`/tesla/trips/api/groups/${gid}`, { method: "DELETE" });
      if (r.status === 401) { location.replace("/login"); return; }
      if (!r.ok) throw new Error(`${r.status}`);
      groups = groups.filter(g => g.id !== gid);
      render();
      toast("已删除分组");
    } catch { toast("删除失败"); }
  } else if (t.closest(".gp-rename")) {
    item.innerHTML =
      `<input class="gp-input" value="${esc(group.name)}" maxlength="30">` +
      `<button class="gp-act gp-ok">确定</button>` +
      `<button class="gp-act gp-no">取消</button>`;
    const inp = item.querySelector(".gp-input");
    inp.focus(); inp.select();
  } else if (t.closest(".gp-ok")) {
    const name = item.querySelector(".gp-input").value.trim();
    if (!name) { toast("名字不能为空"); return; }
    try {
      const r = await fetch(`/tesla/trips/api/groups/${gid}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (r.status === 401) { location.replace("/login"); return; }
      if (!r.ok) throw new Error(`${r.status}`);
      group.name = name;
      render();
    } catch { toast("改名失败"); }
  } else if (t.closest(".gp-no")) {
    render();
  } else if (t.closest(".gp-main")) {
    location.href = "/tesla/trips?ids=" + item.dataset.ids;   // 裸逗号: 行程页深链本就裸写, 编码成 %2C 会被截断
  }
});

$("#gp-list").addEventListener("keydown", e => {
  if (!(e.target instanceof Element)) return;
  if (e.key === "Enter" && e.target.classList.contains("gp-input")) {
    e.preventDefault();
    e.target.closest(".gp-item").querySelector(".gp-ok").click();
  } else if (e.key === "Escape") {
    render();            // 行内改名的输入框: Esc 放弃
  }
});

$("#retry").addEventListener("click", load);
/* 顶栏刷新: 重拉当前页数据 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await load();
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.replace("/login");
});

load();
