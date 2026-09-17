// charging-cards.js — 充电记录页 (2/6): 瀑布流记录卡片 (SOC 轴/费用胶囊/断档
// 标签) + 分页加载 (触底预载 + 首屏不满时链式续载) + 卡片点击分发 (详情/
// 补费用) + 顶栏刷新/退出与车辆胶囊、首屏拉取。
// 由 index.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 index.html
// 里的顺序加载, 跨模块引用走全局); 底座在 charging-page.js, 筛选交互在
// charging-filters.js, 详情弹层在 charging-detail.js, 导航选单在
// charging-nav.js, 费用编辑在 charging-cost.js。
/* global $, esc, num, money, fmtCardDate, fmtDur, getJSON, PAGE, state,
          sessionParams, editCost, openSheet */
/* exported masonryEl, itemsById, renderCard, refetch */
"use strict";
/* ============================ 瀑布流 ============================ */
const masonryEl = $("#masonry");
const itemsById = new Map();

function clearCards() { masonryEl.innerHTML = ""; itemsById.clear(); }

function renderCard(it) {
  const el = document.createElement("article");
  el.className = "card-s"; el.dataset.id = it.id;
  const costLine = it.cost != null
    ? `<button class="cs-cost" data-cost>${money(it.cost)}${it.price_per_kwh != null
        ? `<span class="pp">¥${it.price_per_kwh.toFixed(2)}/kWh</span>` : ""}<span class="edit-ic">✎</span></button>`
    : `<button class="cs-cost none" data-cost>＋ 添加费用</button>`;
  /* 短充电 (起止差 < 15%) 两个标签钉在真实百分比会叠字: 并成一个 "起 → 终"
     标签居中钉在轨迹中点 (中点钳 15~85%, 标签再宽也不出卡) */
  const wide = it.end_soc - it.start_soc >= 15;
  const mid = Math.min(Math.max((it.start_soc + it.end_soc) / 2, 15), 85);
  const socLabels = wide
    ? `<span class="sa-lb" style="left:${Math.min(it.start_soc, 93)}%">${it.start_soc}%</span>` +
      `<span class="sa-lb" style="right:${100 - it.end_soc}%">${it.end_soc}%</span>`
    : `<span class="sa-lb" style="left:${mid}%;transform:translateX(-50%)">` +
      `${it.start_soc} → ${it.end_soc}%</span>`;
  el.innerHTML = `
    <div class="cs-top">
      <span class="cs-date">${esc(fmtCardDate(it.start))}</span>
      <span class="tag ${it.is_fast ? "tag-fast" : "tag-slow"}">${it.is_fast ? "⚡ 快充" : "🔌 慢充"}</span>
    </div>
    <h3 class="cs-loc">${esc(it.location)}</h3>
    <div class="soc-axis">
      ${socLabels}
      <span class="trk"><i style="left:${it.start_soc}%;width:${Math.max(it.end_soc - it.start_soc, 2)}%"></i></span>
    </div>
    <div class="cs-main">
      <div class="cs-energy">${num(it.energy_added ?? it.energy_used)}<small>kWh</small></div>
      ${costLine}
    </div>
    <div class="cs-sub">${fmtDur(it.duration_min)} · 峰值 ${it.power_max ?? "—"} kW${it.outside_temp != null ? ` · ${num(it.outside_temp, 0)}°C` : ""}</div>`;
  return el;
}

const tailEl = $("#tail");
function setTail() {
  tailEl.hidden = state.total === 0 && !state.loading && state.done;
  $("#loader-spin").hidden = !state.loading;
  $("#endnote").hidden = !(state.done && state.total > 0);
  $("#empty").hidden = !(state.done && state.total === 0 && !state.err);
  $("#errbox").hidden = !state.err;
  $("#count-badge").textContent = state.total ? `共 ${state.total} 次` : "";
}

const PRELOAD_PX = 800;   // 触底前多远开始预加载 (IO rootMargin 与链式续载共用)

async function loadMore(reset) {
  if (state.loading || (state.done && !reset)) return;
  state.loading = true; state.err = null; setTail();
  try {
    const d = await getJSON("/tesla/charging/api/sessions?" + sessionParams({ offset: state.offset, limit: PAGE }));
    if (reset) clearCards();
    state.total = d.total; state.offset += d.items.length;
    if (state.offset >= d.total) state.done = true;
    d.items.forEach(it => {
      itemsById.set(it.id, it);
      masonryEl.appendChild(renderCard(it));
    });
  } catch (e) {
    state.err = "数据加载失败: " + e.message;
  }
  state.loading = false; setTail();
  /* 首页填不满"视口+预载区"时, tail 一直留在交叉区里, IntersectionObserver
     只在进出过渡时回调, 不会再触发 —— 主动续载直到 tail 滚出预载区。
     (Chrome 桌面端宽屏下 24 张卡不足一屏, 曾因此永远卡在第一页。) */
  if (!state.done && !state.err &&
      tailEl.getBoundingClientRect().top < window.innerHeight + PRELOAD_PX)
    loadMore(false);
}

/* 懒加载: 触底前 PRELOAD_PX 预加载下一页 */
new IntersectionObserver(es => {
  if (es[0].isIntersecting) loadMore(false);
}, { rootMargin: PRELOAD_PX + "px" }).observe(tailEl);

async function refetch() {
  state.offset = 0; state.total = 0; state.done = false; state.err = null;
  masonryEl.classList.add("dim");
  await loadMore(true);
  masonryEl.classList.remove("dim");
}

masonryEl.addEventListener("click", e => {
  const costBtn = e.target.closest("[data-cost]");
  if (costBtn) {
    editCost(itemsById.get(+costBtn.closest(".card-s").dataset.id));
    return;
  }
  const card = e.target.closest(".card-s");
  if (card) openSheet(+card.dataset.id);
});

/* 顶栏刷新: 重拉当前页数据 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await refetch();
  window.scrollTo({ top: 0 });
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
  location.href = "/login";
});
(async () => {
  try {
    const cars = await getJSON("/tesla/charging/api/car");
    if (cars[0]) $("#car-pill").textContent = `${cars[0].model} · ${cars[0].name}`;
  } catch (e) { /* 车辆信息失败不阻塞 */ }
  await refetch();
})();
