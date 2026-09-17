// charging-cost.js — 充电记录页 (6/6): 费用编辑 —— 卡片胶囊与详情格都能补录
// (iOS alert 风格弹窗), 保存后卡片/详情就地更新。
// 由 index.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 index.html
// 里的顺序加载, 跨模块引用走全局); 底座在 charging-page.js, 记录卡片在
// charging-cards.js, 筛选交互在 charging-filters.js, 详情弹层在
// charging-detail.js, 导航选单在 charging-nav.js。
/* global $, money, itemsById, masonryEl, renderCard, detailCache, sheetOpen,
          currentDetailId, alertBd, alInput, sheetBody, openNavChooser */
/* exported editCost */
"use strict";
/* ============================ 费用编辑 ============================ */
let editing = null, saving = false;

function editCost(it) {
  if (!it) return;
  editing = it;
  $("#al-msg").textContent = `${it.date} · ${it.location}`;
  $("#al-err").textContent = "";
  $("#al-clear").hidden = it.cost == null;
  alertBd.hidden = false;
  requestAnimationFrame(() => {
    alertBd.classList.add("on");
    alInput.value = it.cost != null ? it.cost : "";
    setTimeout(() => { alInput.focus(); alInput.select(); }, 80);
  });
}

function closeAlert() {
  alertBd.classList.remove("on");
  setTimeout(() => { alertBd.hidden = true; }, 230);
  editing = null; saving = false;
}

async function saveCost() {
  if (!editing || saving) return;
  const raw = alInput.value.trim().replace(/[¥￥,，\s]/g, "");
  let cost = null;
  if (raw !== "") {
    cost = parseFloat(raw);
    if (!isFinite(cost) || cost < 0 || cost > 100000) {
      $("#al-err").textContent = "请输入 0 ~ 100000 之间的金额";
      alInput.classList.remove("shake");
      void alInput.offsetWidth;
      alInput.classList.add("shake");
      return;
    }
  }
  saving = true;
  try {
    const r = await fetch(`/tesla/charging/api/sessions/${editing.id}/cost`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cost }),
    });
    if (r.status === 401) { location.replace("/login"); return; }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status);
    const d = await r.json();
    applyCostUpdate(editing.id, d.cost, d.price_per_kwh);
    closeAlert();
  } catch (e) {
    $("#al-err").textContent = "保存失败: " + e.message;
    saving = false;
  }
}

function applyCostUpdate(id, cost, ppk) {
  const it = itemsById.get(id);
  if (it) {
    it.cost = cost; it.price_per_kwh = ppk;
    const old = masonryEl.querySelector(`.card-s[data-id="${id}"]`);
    if (old) old.replaceWith(renderCard(it));
  }
  const det = detailCache.get(id);
  if (det) { det.cost = cost; det.price_per_kwh = ppk; }
  if (sheetOpen && currentDetailId === id) {
    const cv = $("#st-cost-val"), pv = $("#st-price-val");
    if (cv) {
      cv.textContent = cost != null ? money(cost) : "未记费用";
      cv.classList.toggle("red", cost == null);
    }
    if (pv) pv.textContent = ppk != null ? "¥" + ppk.toFixed(3) : "—";
  }
}

$("#al-cancel").addEventListener("click", closeAlert);
$("#al-save").addEventListener("click", saveCost);
$("#al-clear").addEventListener("click", () => { alInput.value = ""; saveCost(); });
alertBd.addEventListener("click", e => { if (e.target === alertBd) closeAlert(); });
alInput.addEventListener("keydown", e => {
  e.stopPropagation();
  if (e.key === "Enter") saveCost();
});

sheetBody.addEventListener("click", e => {
  if (e.target.closest("#st-cost-tile") && currentDetailId != null)
    editCost(detailCache.get(currentDetailId));
  if (e.target.closest("#nav-go") && currentDetailId != null)
    openNavChooser(detailCache.get(currentDetailId));
});
