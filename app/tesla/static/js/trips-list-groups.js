// trips-list-groups.js — 行程页 (6/6): 多选存为轨迹分组 (命名模式, 预填日期
// 跨度) 与全页轻提示 toast (弹层标注/导出视频等后加载模块共用)。
// 由 trips-list.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// trips.html 里的顺序加载, 跨模块引用走全局); 底座在 trips-list-page.js,
// 多选在 trips-list-select.js。
/* global $, items, selRange, exitSelect */
/* exported toast */
"use strict";
/* ============================ 轨迹分组 ============================ */
/* 逻辑分组存自有库 (api/groups), 行程原数据不动; 管理 (打开/改名/删除) 在
   独立的分组页, 本页只留创建入口 (多选 → 存为分组)。打开分组 = 行程页
   ?ids= 深链合并播放, 关弹层自动回分组页 (见 closeTrip)。 */
let gpIds = [];         // 进入命名模式时快照的选中 ids (之后划选变动不影响本次保存)
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

// ---- 多选栏: 存为分组 (命名模式, 预填日期跨度) ----
$("#gp-btn").addEventListener("click", () => {
  gpIds = items.slice(selRange[0], selRange[1] + 1).map(it => it.id);
  const dNew = items[selRange[0]].date.slice(5);   // 列表时间倒序: [0] 最新 [末] 最旧
  const dOld = items[selRange[1]].date.slice(5);
  $("#gp-name").value = dNew === dOld ? dNew : `${dOld}~${dNew}`;   // 预填日期跨度, 可改
  $("#gp-save").disabled = false;
  $("#selbar").classList.add("naming");
  setTimeout(() => $("#gp-name").select(), 50);    // 等命名行布局稳定再全选
});

$("#gp-name-cancel").addEventListener("click", () =>
  $("#selbar").classList.remove("naming"));

$("#gp-name").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); $("#gp-save").click(); }
  else if (e.key === "Escape") { $("#selbar").classList.remove("naming"); }
});

$("#gp-save").addEventListener("click", async () => {
  const name = $("#gp-name").value.trim();
  if (!name) { toast("名字不能为空"); return; }
  const btn = $("#gp-save");
  btn.disabled = true;
  try {
    const r = await fetch("/tesla/trips/api/groups", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, ids: gpIds }),
    });
    if (r.status === 401) { location.replace("/login"); return; }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
    toast(`已存分组「${name}」`);
    exitSelect();
  } catch (err) {
    toast(`存分组失败: ${err.message}`);
    btn.disabled = false;
  }
});
