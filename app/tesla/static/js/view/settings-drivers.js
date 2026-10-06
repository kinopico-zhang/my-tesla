// view/settings-drivers.js — 驾驶员视图 (P6, 旧设置页的驾驶员卡原样搬):
// 列表 (增/删/设默认/改名)。行上常显钮 2026-10-04 用户点名退役「去掉按
// 钮, 改成左滑显示: 设为默认, 改名和删除」—— 左滑露出操作面板: 设为默认
// (默认驾驶员那行没有这枚) + 改名 + 删除; 删除二次确认弃武装式 (钮上变
// 「确认删除」3s, 地点页实踩没被看见), 换原生 confirm 对话框同款。改名是
// 新增能力: 行内编辑 (groups 页同款 —— 输入框 + 确定/取消, 回车存 Esc 弃)。
// 重渲染时旧节点脱链防误触。旧版底座 ($/esc/toast/api) 在
// settings-connections.js, 壳版由 tesla-common 接管。
/* global $, esc, toast, getJSON, sendJSON, bindGestures, registerView,
           bindSwipeDelete */
"use strict";
let drivers = [];

function renderDrivers() {
  $("#drv-empty").hidden = drivers.length > 0;
  $("#drv-list").innerHTML = drivers.map(d =>
    `<div class="drv-item">` +
    `<div class="swipe-wrap drv-g${d.is_default ? " w2" : " w3"}" data-id="${d.id}">` +
    `<div class="drv-row">` +
    `<div class="drv-name">${esc(d.name)}${d.is_default ? '<span class="drv-badge">默认</span>' : ""}</div>` +
    `</div>` +
    `<div class="swipe-actions">` +
    (d.is_default ? "" : `<button type="button" class="swipe-edit set-def">设为默认</button>`) +
    `<button type="button" class="swipe-edit ren">改名</button>` +
    `<button type="button" class="swipe-del del">删除</button>` +
    `</div></div></div>`).join("");
}

async function loadDrivers() {
  try {
    drivers = await getJSON("/tesla/api/drivers");
    renderDrivers();
  } catch (err) {
    // 拉挂了别装成空列表 (2026-10-05 服务重启窗口实踩: 静默空白被当成
    // 没驾驶员) —— 地点视图同款 toast, 旧数据留着, 重进视图/下拉即重试
    toast(`驾驶员加载失败: ${err.message}`);
  }
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

// 行内改名 (面板「改名」开): 确定存 / 取消弃 —— 输入框和这两枚钮住行体
// 里, 左滑件的捕获层不认它们, 冒泡到这; Enter 存 / Esc 弃 (groups 同款)
$("#drv-list").addEventListener("click", async e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;   // 重渲染脱链防误触
  const wrap = t.closest(".drv-g");
  if (!wrap) return;
  const d = drivers.find(x => x.id === +wrap.dataset.id);
  if (!d) return;
  try {
    if (t.closest(".drv-ok")) {
      const name = wrap.querySelector(".drv-input").value.trim();
      if (!name) { toast("名字不能为空"); return; }
      await sendJSON(`/tesla/api/drivers/${d.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      await loadDrivers();
    } else if (t.closest(".drv-no")) {
      renderDrivers();
    }
  } catch (err) {
    toast(`操作失败: ${err.message}`);
  }
});

$("#drv-list").addEventListener("keydown", e => {
  if (!(e.target instanceof Element)) return;
  if (e.key === "Enter" && e.target.classList.contains("drv-input")) {
    e.preventDefault();
    e.target.closest(".swipe-wrap").querySelector(".drv-ok").click();
  } else if (e.key === "Escape") {
    renderDrivers();          // 行内改名的输入框: Esc 放弃
  }
});

// 左滑操作面板 (2026-10-04): 「设为默认」/「改名」是编辑类 (v4 起模块把
// 被点的钮也递进来, 这里按钮分派), 「删除」走 confirm
bindSwipeDelete($("#drv-list"),
  async wrap => {
    const d = drivers.find(x => x.id === +wrap.dataset.id);
    if (!d) return;
    if (!window.confirm(`删除驾驶员「${d.name}」?`)) return;
    try {
      await sendJSON(`/tesla/api/drivers/${d.id}`, { method: "DELETE" });
    } catch (err) {
      toast(`删除失败: ${err.message}`);
    }
    await loadDrivers();
  },
  async (wrap, act) => {
    const d = drivers.find(x => x.id === +wrap.dataset.id);
    if (!d) return;
    try {
      if (act.classList.contains("set-def")) {
        await sendJSON(`/tesla/api/drivers/${d.id}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_default: true }),
        });
        await loadDrivers();
        return;
      }
      const row = wrap.querySelector(".drv-row");
      row.innerHTML = `<input class="drv-input" value="${esc(d.name)}" maxlength="30">` +
        `<button type="button" class="drv-act drv-ok">确定</button>` +
        `<button type="button" class="drv-act drv-no">取消</button>`;
      const inp = row.querySelector(".drv-input");
      inp.focus(); inp.select();
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
