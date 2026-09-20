// view/groups-page.js — 行程分组视图 (壳版): 分组存自有库 (trips 的
// api/groups), 打开 = 内存跳行程视图合并播放 (navigate + openMerged,
// 不再走旧行程页深链)。创建入口在行程列表 (长按多选 → 存为分组),
// 本视图只管浏览/打开/改名/删除。
// 旧版 (js/groups.js) 的 $/esc/toast/页签菜单/顶栏刷新/登出上移壳模块。
/* global $, esc, toast, registerView, bindGestures, navigate,
          openMerged */
/* exported gpLoad */
"use strict";

let groups = [];      // 列表当前数据 (渲染 + 委托处理器查用)

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
  $("#gp-count-badge").textContent = groups.length ? `${groups.length} 组` : "";
  $("#gp-list").innerHTML = groups.map(rowHTML).join("");
}

async function gpLoad() {
  $("#gp-errbox").hidden = true;
  $("#gp-spin").hidden = false;
  try {
    const r = await fetch("/tesla/trips/api/groups");
    if (r.status === 401) { location.replace("/login"); return; }
    if (!r.ok) throw new Error(`${r.status}`);
    groups = await r.json();
  } catch {
    groups = [];
    $("#gp-spin").hidden = true;
    $("#gp-errbox").hidden = false;
  }
  render();
}

/* 行点击委托: 点条目跳行程页合并播放 (?ids= 深链); 改名行内编辑;
   删除二次确认 (3s 内再点才删)。
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
    /* 内存跳转: 壳里行程视图与弹层都在 (零历史条目, 不走整页导航);
       裸逗号键 openMerged 自行识别 (旧版裸写, 编码成 %2C 会被截断) */
    navigate("trips");
    openMerged(item.dataset.ids);
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

$("#gp-retry").addEventListener("click", gpLoad);

/* 手势: 列表滚动器右划开抽屉 / 在顶下拉刷新 */
const gpScroll = $("#gp-scroll");
bindGestures(gpScroll, { drawer: true, ptr: true, onRefresh: gpLoad });

let gpBooted = false;
registerView("groups", {
  title: "行程分组",
  el: $("#view-groups"),
  show() { if (!gpBooted) { gpBooted = true; gpLoad(); } },
  refresh: gpLoad,
});
