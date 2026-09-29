// trips-list-select.js — 行程页 (5/6): 多选连续行程 —— 长按卡片进入 (触屏/
// 桌面按住 480ms), 两段式点选定范围, 底栏全选 (没装够先补载) / 合并播放
// (openMerged 在后加载的 trips-sheet-page.js, 点击时才解析)。
// 由 trips-list.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// trips.html 里的顺序加载, 跨模块引用走全局); 底座在 trips-list-page.js。
/* global $, num, items, listEl, state, loadMore, openMerged */
/* exported pickCard, exitSelect, selRange */
"use strict";
/* ============================ 多选: 连续行程拼成一条轨迹 ============================ */
/* 一次最多 100 段的上限 2026-09-25 用户点名撤掉 (前端封顶/上限提示/后端
   校验/schema max_length 一并退役) —— 大列表全选补载到底, 播放走逐段流式 */
let selAnchor = -1;                 // 范围锚点 (点选的第一张卡)
let selRange = [-1, -1];            // 当前选中范围 [from, to] (闭区间, 必连续)

function applyPick() {
  const [a, b] = selRange, on = a >= 0;
  [...listEl.children].forEach((el, i) => el.classList.toggle("picked", on && i >= a && i <= b));
  const n = on ? b - a + 1 : 0;
  const km = on ? items.slice(a, b + 1).reduce((s, it) => s + (it.km || 0), 0) : 0;
  $("#sel-count").textContent = n;
  $("#sel-km").textContent = num(km);
  $("#sel-go").disabled = n < 2;
  $("#gp-btn").disabled = n < 2;            // 存分组与合并播放同一口径 (≥2)
  $("#sel-all").textContent =             // 已选全部 → 再点一次变清空
    on && a === 0 && b === items.length - 1 ? "清空" : "全选";
}

/* 两段式点选: 点第一张卡定锚, 点另一张 → 锚点到该处的连续范围; 再点锚点清空重来 */
function pickCard(el) {
  const i = [...listEl.children].indexOf(el);
  if (i < 0) return;
  if (selAnchor < 0) { selAnchor = i; selRange = [i, i]; }
  else if (i === selAnchor) { selAnchor = -1; selRange = [-1, -1]; }
  else selRange = [Math.min(selAnchor, i), Math.max(selAnchor, i)];
  applyPick();
}

function enterSelect() {
  document.body.classList.add("selecting");
  $("#selbar").hidden = false;
  selAnchor = -1; selRange = [-1, -1];
  applyPick();
}
function exitSelect() {
  document.body.classList.remove("selecting");
  $("#selbar").hidden = true;
  $("#selbar").classList.remove("naming");
  selAnchor = -1; selRange = [-1, -1];
  applyPick();
}
/* 长按卡片进多选 (多选按钮已撤, 这是唯一入口); 触屏长按 / 桌面按住 480ms
   → 进多选并选中这张卡。移动超 10px (滚动/下拉) 即取消; 长按后紧跟的
   click 吞掉, 别又把弹层打开。 */
(function setupLongPress() {
  const HOLD_MS = 480;
  let timer = null, card = null, x0 = 0, y0 = 0, fired = false, suppress = false;
  const clear = () => {
    if (timer) clearTimeout(timer);
    timer = null; card = null; fired = false;
  };
  const start = (x, y, target) => {
    suppress = false;
    if (document.body.classList.contains("selecting")) return;
    card = target.closest(".card-t");
    if (!card) return;
    x0 = x; y0 = y;
    timer = setTimeout(() => {
      timer = null; fired = true; suppress = true;
      enterSelect(); pickCard(card);
    }, HOLD_MS);
  };
  const move = (x, y) => {
    if (timer != null && Math.hypot(x - x0, y - y0) > 10) clear();
  };
  listEl.addEventListener("touchstart", e => {
    if (e.touches.length !== 1) { clear(); return; }
    start(e.touches[0].clientX, e.touches[0].clientY, e.target);
  }, { passive: true });
  listEl.addEventListener("touchmove",
    e => move(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
  listEl.addEventListener("touchend", e => {
    if (fired) { e.preventDefault(); suppress = false; }   // click 不会再产生
    clear();
  }, { passive: false });
  listEl.addEventListener("touchcancel", clear, { passive: true });
  listEl.addEventListener("mousedown", e => {   // 桌面: 按住不放同样进多选
    if (e.button === 0) start(e.clientX, e.clientY, e.target);
  });
  window.addEventListener("mousemove", e => move(e.clientX, e.clientY));
  window.addEventListener("mouseup", clear);
  listEl.addEventListener("click", e => {       // 长按紧随的 click 不开弹层
    if (suppress) { suppress = false; e.stopPropagation(); e.preventDefault(); }
  }, true);
  listEl.addEventListener("contextmenu", e => {  // iOS 长按呼系统菜单会掐掉触摸
    if (e.target.closest(".card-t")) e.preventDefault();
  });
})();
$("#sel-cancel").addEventListener("click", exitSelect);
/* 全选: 选中当前筛选下的全部行程, 没装够的页先补载到底 (100 段封顶
   2026-09-25 用户点名撤掉)。已选全部时按钮变"清空", 再点一次取消选择。 */
$("#sel-all").addEventListener("click", async () => {
  const isAll = selRange[0] === 0 && selRange[1] === items.length - 1;
  if (!isAll) {
    const btn = $("#sel-all");
    btn.disabled = true;
    try {
      const target = state.total || items.length;
      while (!state.done && !state.err && items.length < target) await loadMore();
    } finally { btn.disabled = false; }
    if (state.err) return;        // 补载失败: 列表区已有重试入口, 不动现有选择
  }
  selAnchor = -1;
  selRange = isAll || items.length < 2 ? [-1, -1] : [0, items.length - 1];
  applyPick();
});
$("#sel-go").addEventListener("click", () => {
  const picked = items.slice(selRange[0], selRange[1] + 1);   // 新→旧排序
  const ids = picked.map(it => it.id);
  /* 多选聚合 (2026-09-23 用户点名弹层一开就显数, 不等地图): 列表新→旧,
     时间上首段在末尾; 电耗 ΣkWh÷Σkm 与合并汇总头同口径, 没电耗数据的
     段不计入, 全都没数据就留空 (弹层显 —) */
  const km = picked.reduce((a, it) => a + (it.km || 0), 0);
  const kws = picked.map(it => it.kwh).filter(v => v != null);
  const kwh = kws.length ? kws.reduce((a, b) => a + b, 0) : null;
  exitSelect();
  openMerged(ids, null, {
    n: picked.length,
    start: picked[picked.length - 1].start, end: picked[0].end,
    km: Math.round(km * 10) / 10,
    min: picked.reduce((a, it) => a + (it.min || 0), 0),
    speed_max: Math.max(...picked.map(it => it.speed_max || 0)) || null,
    kwh: kwh == null ? null : Math.round(kwh * 10) / 10,
    wh_per_km: kwh != null && km >= 1 ? Math.round(kwh / km * 1000) : null,
  });
});
