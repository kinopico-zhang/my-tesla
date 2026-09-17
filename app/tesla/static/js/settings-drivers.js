// settings-drivers.js — 软件设置页 (2/3): 驾驶员列表 (增/删/设默认,
// 重渲染时旧节点脱链防误触)。
// 由 settings.js 按域拆出 (结构化重构, 声明顺序与语义不变); 底座
// ($/esc/toast/api) 在 settings-connections.js。
/* global $, esc, toast, api */
/* exported loadDrivers */
"use strict";
let drivers = [];

function renderDrivers() {
  $("#drv-empty").hidden = drivers.length > 0;
  $("#drv-list").innerHTML = drivers.map(d =>
    `<div class="drv-row" data-id="${d.id}">` +
    `<div class="drv-name">${esc(d.name)}${d.is_default ? '<span class="drv-badge">默认</span>' : ""}</div>` +
    (d.is_default ? "" : `<button class="drv-act set-def">设为默认</button>`) +
    `<button class="drv-act del">删除</button></div>`).join("");
}

async function loadDrivers() {
  drivers = await api("/tesla/api/drivers");
  renderDrivers();
}

$("#drv-add").addEventListener("click", async () => {
  const name = $("#drv-name").value.trim();
  if (!name) return;
  try {
    await api("/tesla/api/drivers", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    $("#drv-name").value = "";
    await loadDrivers();
  } catch (err) {
    toast(`添加失败: ${err.message}`, true);
  }
});

$("#drv-name").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); $("#drv-add").click(); }
});

$("#drv-list").addEventListener("click", async e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;   // 重渲染脱链防误触
  const row = t.closest(".drv-row");
  if (!row) return;
  const id = +row.dataset.id;
  const opts = {
    method: "PATCH", headers: { "Content-Type": "application/json" },
  };
  try {
    if (t.closest(".set-def")) {
      await api(`/tesla/api/drivers/${id}`, Object.assign(opts,
        { body: JSON.stringify({ is_default: true }) }));
      await loadDrivers();
    } else if (t.closest(".del")) {
      if (!confirm("删除这个驾驶员?")) return;
      await api(`/tesla/api/drivers/${id}`, { method: "DELETE" });
      await loadDrivers();
    }
  } catch (err) {
    toast(`操作失败: ${err.message}`, true);
  }
});
