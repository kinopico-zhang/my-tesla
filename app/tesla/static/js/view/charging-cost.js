// view/charging-cost.js — 充电记录视图 (壳版 6/6): 费用编辑 —— 卡片胶囊与
// 详情格都能补录 (iOS alert 风格弹窗), 保存后卡片/详情就地更新。
// 壳版差异: 元素/导出名加 chg- 前缀。
/* global $, money, chgItemsById, chgMasonry, chgRenderCard, detailCache,
          chgSheetOpen, chgCurrentDetailId, chgAlertBd, chgAlInput, chgSheetBody */
/* exported editCost, chgCloseAlert */
"use strict";
/* ============================ 费用编辑 ============================ */
let editing = null, saving = false;

function editCost(it) {
  if (!it) return;
  editing = it;
  $("#chg-al-msg").textContent = `${it.date} · ${it.location}`;
  $("#chg-al-err").textContent = "";
  $("#chg-al-clear").hidden = it.cost == null;
  chgAlertBd.hidden = false;
  requestAnimationFrame(() => {
    chgAlertBd.classList.add("on");
    chgAlInput.value = it.cost != null ? it.cost : "";
    setTimeout(() => { chgAlInput.focus(); chgAlInput.select(); }, 80);
  });
}

function chgCloseAlert() {
  chgAlertBd.classList.remove("on");
  setTimeout(() => { chgAlertBd.hidden = true; }, 230);
  editing = null; saving = false;
}

async function saveCost() {
  if (!editing || saving) return;
  const raw = chgAlInput.value.trim().replace(/[¥￥,，\s]/g, "");
  let cost = null;
  if (raw !== "") {
    cost = parseFloat(raw);
    if (!isFinite(cost) || cost < 0 || cost > 100000) {
      $("#chg-al-err").textContent = "请输入 0 ~ 100000 之间的金额";
      chgAlInput.classList.remove("shake");
      void chgAlInput.offsetWidth;
      chgAlInput.classList.add("shake");
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
    chgCloseAlert();
  } catch (e) {
    $("#chg-al-err").textContent = "保存失败: " + e.message;
    saving = false;
  }
}

function applyCostUpdate(id, cost, ppk) {
  const it = chgItemsById.get(id);
  if (it) {
    it.cost = cost; it.price_per_kwh = ppk;
    const old = chgMasonry.querySelector(`.card-s[data-id="${id}"]`);
    if (old) old.replaceWith(chgRenderCard(it));
  }
  const det = detailCache.get(id);
  if (det) { det.cost = cost; det.price_per_kwh = ppk; }
  if (chgSheetOpen && chgCurrentDetailId === id) {
    const cv = $("#st-cost-val"), pv = $("#st-price-val");   // 详情弹层运行时生成的格
    if (cv) {
      cv.textContent = cost != null ? money(cost) : "未记费用";
      cv.classList.toggle("red", cost == null);
    }
    if (pv) pv.textContent = ppk != null ? "¥" + ppk.toFixed(3) : "—";
  }
}

$("#chg-al-cancel").addEventListener("click", chgCloseAlert);
$("#chg-al-save").addEventListener("click", saveCost);
$("#chg-al-clear").addEventListener("click", () => { chgAlInput.value = ""; saveCost(); });
chgAlertBd.addEventListener("click", e => { if (e.target === chgAlertBd) chgCloseAlert(); });
chgAlInput.addEventListener("keydown", e => {
  e.stopPropagation();
  if (e.key === "Enter") saveCost();
});

chgSheetBody.addEventListener("click", e => {
  if (e.target.closest("#st-cost-tile") && chgCurrentDetailId != null)
    editCost(detailCache.get(chgCurrentDetailId));
});
