// view/charging-cards.js — 充电记录视图 (壳版 2/6): 瀑布流卡片 + 按月分组
// + 分页 (makePager 骨架) + registerView("charging") 生命周期 (首次进视图才
// chgBoot, 藏起停 IO) + 手势绑定 (在顶下拉刷新) + 卡片点击分发。
// 旧版顶栏刷新/登出/车辆胶囊归筛选条全局 chip 与账号卡; 分页细节收进 tesla-paged-list.js。
/* global $, esc, num, money, fmtCardDate, fmtPlaceShort, getJSON, PAGE,
          sessionParams, editCost, chgOpenSheet, registerView, bindGestures,
          makePager, chgFetchRegions, TESLA_MARK */
/* exported chgMasonry, chgItemsById, chgRenderCard, chgRefetch, chgBoot */
"use strict";
/* ============================ 瀑布流 ============================ */
const chgMasonry = $("#chg-masonry");
const chgItemsById = new Map();

function chgRenderCard(it) {
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
  /* 地点只留最小两段 (用户点名; 整链在详情底部地址): 前段 (区/市) 弱色
     同字号前缀 + 地名, 解析不出省市区时退化到市级, 再退化到光地名 */
  const pp = fmtPlaceShort(it), pre = pp.length > 1 ? pp[0] : "";
  /* 角标: 快充 (琥珀) / 慢充 (蓝) 照旧打 (2026-09-27 用户点名「该是快充和
     慢充还是要打对应的 tag」); 特斯拉官方桩 (采样里有 Tesla+Gb) 的 Tesla
     文字标 (TESLA_MARK, 用户点名附加标 + 白字不套底) —— 同日用户再点名
     「换个位置, 快慢充一直在右上角」: pill 常驻卡右上角 (组内最右), 字标
     立到它左边 */
  const tagCls = it.is_fast ? "tag-fast" : "tag-slow";
  const tagLb = it.is_fast ? "快充" : "慢充";
  el.innerHTML = `
    <div class="cs-top">
      <span class="cs-date">${esc(fmtCardDate(it.start))}</span>
      <span class="cs-tags">${it.tesla_supercharger ? `<span class="tesla-mark" aria-label="Tesla 超充">${TESLA_MARK}</span>` : ""}<span class="tag ${tagCls}">${tagLb}</span></span>
    </div>
    <h3 class="cs-loc">${pre ? `<span class="cs-region">${esc(pre)} · </span>` : ""}${esc(pp[pp.length - 1])}</h3>
    <div class="soc-axis">
      ${socLabels}
      <span class="trk"><i style="left:${it.start_soc}%;width:${Math.max(it.end_soc - it.start_soc, 2)}%"></i></span>
    </div>
    <div class="cs-main">
      <div class="cs-energy">${num(it.energy_added ?? it.energy_used)}<small>kWh</small></div>
      ${costLine}
    </div>`;
  return el;
}

/* 按月分组 (用户点名): 列表按日期倒序, 跨月处插一行月份小标; 同月不重插,
   解析不出的日期不立头也不记账 (免得带崩后续同月的账) */
let chgLastMonth = "";
function chgMonthHead(it) {
  const m = /^(\d{4})-(\d{2})/.exec(it.start || "");
  if (!m) return null;
  const key = m[1] + m[2];
  if (key === chgLastMonth) return null;
  chgLastMonth = key;
  const h = document.createElement("div");
  h.className = "month-head";
  h.textContent = `${+m[1]}年${+m[2]}月`;
  return h;
}

/* ============================ 分页 (骨架在 tesla-paged-list) ============================ */
function chgSetTail(st) {
  $("#chg-tail").hidden = st.total === 0 && !st.loading && st.done;
  $("#chg-loader-spin").hidden = !st.loading;
  $("#chg-endnote").hidden = !(st.done && st.total > 0);
  $("#chg-empty").hidden = !(st.done && st.total === 0 && !st.err);
  $("#chg-errbox").hidden = !st.err;
  $("#chg-count-badge").textContent = st.total ? `共 ${st.total} 次` : "";
}
const chgPager = makePager({
  sentinel: $("#chg-tail"),
  container: chgMasonry,
  limit: PAGE,
  fetchPage: (offset, limit) =>
    getJSON("/tesla/charging/api/sessions?" + sessionParams({ offset, limit })),
  renderItem: it => {
    chgItemsById.set(it.id, it);
    const card = chgRenderCard(it), head = chgMonthHead(it);
    if (!head) return card;
    const frag = document.createDocumentFragment();   // 月头带首卡一起进栏
    frag.append(head, card);
    return frag;
  },
  paint: chgSetTail,
});
async function chgRefetch() {
  chgItemsById.clear();                 // reset 重灌前的配套清账 (骨架只清容器)
  chgLastMonth = "";                    // 月账归零, 头从新月数起
  await chgPager.refetch();
}

/* ============================ 首启与生命周期 ============================ */
let chgBooted = false;
function chgBoot() {   // 首次进视图: 地点树异步拉 (失败不阻塞) + 首屏列表
  chgBooted = true;
  chgFetchRegions();
  chgRefetch();
}

/* 手势一次绑定 (元素静态常驻; 重进视图不重复挂) */
const chgScroll = $("#chg-scroll");
bindGestures(chgScroll, { drawer: true, ptr: true, onRefresh: chgRefetch });

registerView("charging", {
  title: "充电记录",
  el: $("#view-charging"),
  show() {
    if (!chgBooted) chgBoot();
    chgPager.start();
  },
  hide() { chgPager.stop(); },
  refresh: chgRefetch,
});

chgMasonry.addEventListener("click", e => {
  const costBtn = e.target.closest("[data-cost]");
  if (costBtn) {
    editCost(chgItemsById.get(+costBtn.closest(".card-s").dataset.id));
    return;
  }
  const card = e.target.closest(".card-s");
  if (card) chgOpenSheet(+card.dataset.id);
});
$("#chg-retry").addEventListener("click", () => {
  chgPager.st.err = null;
  chgRefetch();
});
