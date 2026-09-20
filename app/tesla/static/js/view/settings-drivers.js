// view/settings-drivers.js — 驾驶员视图 (P6, 旧设置页的驾驶员卡原样搬):
// 列表 (增/删/设默认, 重渲染时旧节点脱链防误触)。删除确认弃旧页的原生
// 对话框, 改壳内同款二次确认 (3s 内再点才删, 分组视图同款); 旧版底座
// ($/esc/toast/api) 在 settings-connections.js, 壳版由 tesla-common 接管。
/* global $, esc, toast, getJSON, sendJSON, bindGestures, registerView */
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
  drivers = await getJSON("/tesla/api/drivers");
  renderDrivers();
}

$("#drv-add").addEventListener("click", async () => {
  const name = $("#drv-name").value.trim();
  if (!name) return;
  try {
    await sendJSON("/tesla/api/drivers", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    $("#drv-name").value = "";
    await loadDrivers();
  } catch (err) {
    toast(`添加失败: ${err.message}`);
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
      await sendJSON(`/tesla/api/drivers/${id}`, Object.assign(opts,
        { body: JSON.stringify({ is_default: true }) }));
      await loadDrivers();
    } else if (t.closest(".del")) {
      /* 二次确认: 一次点把钮武装成「确认删除」, 3s 内再点才真删 */
      if (t.textContent !== "确认删除") {
        t.textContent = "确认删除";
        setTimeout(() => { if (t.isConnected) t.textContent = "删除"; }, 3000);
        return;
      }
      await sendJSON(`/tesla/api/drivers/${id}`, { method: "DELETE" });
      await loadDrivers();
    }
  } catch (err) {
    toast(`操作失败: ${err.message}`);
  }
});

bindGestures($("#drset-scroll"), { drawer: true, ptr: true, onRefresh: loadDrivers });
registerView("settings-drivers", {
  title: "驾驶员",
  el: $("#view-settings-drivers"),
  show: loadDrivers,   // 每次进来都拉 (行程弹层里就能改驾驶员标注)
  refresh: loadDrivers,
});
