// view/trips-list-groups.js — 行程列表视图 (壳版 6/6): 多选存为轨迹分组
// (命名模式, 预填日期跨度)。旧版 (js/trips-list-groups.js) 自带的顶部
// toast 删了 —— 壳里 tesla-common 统一管屏底 toast; 其余逐字节同源。
// 文件名沿用旧名 (命名普查按 basename 折叠)。
/* global $, toast, items, selRange, exitSelect */
"use strict";
/* ============================ 轨迹分组 ============================ */
/* 逻辑分组存自有库 (api/groups), 行程原数据不动; 管理 (打开/改名/删除) 在
   独立的分组视图, 本视图只留创建入口 (多选 → 存为分组)。打开分组 =
   navigate("trips") + openMerged 内存跳转 (groups-page.js)。 */
let gpIds = [];         // 进入命名模式时快照的选中 ids (之后划选变动不影响本次保存)

// ---- 多选栏: 存为分组 (命名模式, 预填日期跨度) ----
$("#gp-btn").addEventListener("click", () => {
  gpIds = items.slice(selRange[0], selRange[1] + 1).map(it => it.id);
  const dNew = items[selRange[0]].date.slice(5).replace(/-/g, "/");   // 列表时间倒序: [0] 最新 [末] 最旧
  const dOld = items[selRange[1]].date.slice(5).replace(/-/g, "/");  // 斜杠写法与分组卡跨度同款 (2026-09-25)
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
