// trips-list-region-filters.js — 行程页 (4/6): 筛选行 —— 起终点省市区三级
// 级联 (树来自 /trips/api/regions) / 里程档 / 驾驶员菜单, 触底懒加载观察
// 器、重试与退出登录。
// 由 trips-list.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// trips.html 里的顺序加载, 跨模块引用走全局); 底座在 trips-list-page.js,
// 加载与地址栏在 trips-list-url.js。
/* global $, esc, getJSON, KM_BUCKETS, state, driversCache: writable, syncURL,
   resetList, loadMore, tailEl, PRELOAD_PX */
"use strict";
/* ---------- 筛选行: 起终点省市区级联 / 里程范围 ----------
   树来自 /trips/api/regions (省→市→区县, 次数降序)。点层级行钻下一级,
   顶部 "全部X" 行选中当前层 (省/市/区县任一级都能作为筛选条件), 叶子直接选中。 */
const REGIONS = { start: [], end: [] };
function bindLocMenu(menuId, optsId, key, lbId, prefix, treeKey) {
  const menuEl = $("#" + menuId), optsEl = $("#" + optsId), lbEl = $("#" + lbId);
  const stack = [];   // 当前钻取路径 (省名/市名), 空 = 省列表
  const setLoc = v => {
    state[key] = v;
    lbEl.textContent = prefix + (v ? v.split("/").pop() : "全部");   // 显示末级, title 全路径
    lbEl.parentElement.title = v;
  };
  const nodesAt = () => {   // stack 对应的节点层
    let nodes = REGIONS[treeKey];
    for (const s of stack) {
      const n = nodes.find(x => x.name === s);
      nodes = n ? n.children : [];
    }
    return nodes;
  };
  const render = () => {
    const sel = state[key], cur = stack.join("/");
    const rows = nodesAt().map(n => {
      const path = (cur ? cur + "/" : "") + n.name;
      return `<button class="loc-row${path === sel ? " on" : ""}" data-n="${esc(n.name)}">` +
        `<span class="nm">${esc(n.name)}</span>` +
        `<span class="cnt">${n.count}${n.children.length ? " ›" : ""}</span></button>`;
    }).join("");
    optsEl.innerHTML =
      (stack.length ? `<button class="loc-back" data-b="1">‹ 返回</button>` +
        `<div class="loc-crumb">${esc(stack.join(" · "))}</div>` : "") +
      `<button data-a="${esc(cur)}"${sel === cur ? ' class="on"' : ""}>` +
      `${cur ? "全部" + esc(stack[stack.length - 1]) : "全部"}</button>` + rows;
  };
  optsEl.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.b) { stack.pop(); return render(); }   // ‹ 返回
    if (b.dataset.a !== undefined) {                     // "全部X" = 选中当前层
      menuEl.removeAttribute("open");
      setLoc(b.dataset.a);
      syncURL(); resetList();
      return;
    }
    const node = nodesAt().find(n => n.name === b.dataset.n);
    if (!node) return;
    if (node.children.length) { stack.push(node.name); return render(); }   // 钻下一级
    menuEl.removeAttribute("open");                     // 叶子 (区县) 直接选中
    setLoc([...stack, node.name].join("/"));
    syncURL(); resetList();
  });
  menuEl.addEventListener("toggle", () => {   // 关闭时把视图重置到当前所选的父层,
    if (menuEl.open) return;                  // 下次打开即所见 (toggle 异步, 开时才渲会闪旧视图)
    stack.length = 0;
    if (state[key]) stack.push(...state[key].split("/").slice(0, -1));
    render();
  });
  setLoc(state[key]);   // URL 带筛选时同步标签
  if (state[key]) stack.push(...state[key].split("/").slice(0, -1));
  render();
  return render;
}
const renderLocStart = bindLocMenu("fc-menu", "fc-opts", "fromLoc", "fc-lb", "起点: ", "start");
const renderLocEnd = bindLocMenu("tc-menu", "tc-opts", "toLoc", "tc-lb", "终点: ", "end");
$("#km-opts").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b || b.dataset.k === state.km) return;
  $("#km-menu").removeAttribute("open");
  state.km = b.dataset.k;
  $("#km-opts .on").classList.remove("on"); b.classList.add("on");
  $("#km-lb").textContent = "里程: " + KM_BUCKETS.find(x => x.v === state.km).lb;
  syncURL(); resetList();
});
$("#km-lb").textContent = "里程: " + KM_BUCKETS.find(b => b.v === state.km).lb;
if (state.km !== "all") {
  $("#km-opts .on").classList.remove("on");
  $(`#km-opts button[data-k="${state.km}"]`).classList.add("on");
}
(async () => {   // 起终点省市区树 (次数降序); 拉不到就只有"全部"
  try {
    const rg = await getJSON("/tesla/trips/api/regions");
    REGIONS.start = rg.start || [];
    REGIONS.end = rg.end || [];
  } catch (_e) { /* keep empty */ }
  renderLocStart(); renderLocEnd();
})();

/* 驾驶员筛选: 选项来自设置页的驾驶员表 (没配驾驶员整颗筛选藏掉); 筛选口径与
   卡片一致 —— 选默认驾驶员 = 标注它的 + 未标注的 (后端合并处理) */
(async () => {
  if (driversCache === undefined) {
    try { driversCache = await getJSON("/tesla/api/drivers"); }
    catch { driversCache = null; }
  }
  const drivers = driversCache || [];
  if (!drivers.length) return;
  const opts = $("#drv-opts");
  opts.innerHTML = `<button data-id=""${state.drvId == null ? ' class="on"' : ""}>全部</button>` +
    drivers.map(d =>
      `<button data-id="${d.id}"${state.drvId === d.id ? ' class="on"' : ""}>${esc(d.name)}</button>`).join("");
  if (state.drvId != null) {               // URL 深链带入的驾驶员要存在才算数
    const hit = drivers.find(d => d.id === state.drvId);
    if (hit) $("#drv-lb").textContent = "驾驶员: " + hit.name;
    else {
      state.drvId = null;
      opts.querySelector(".on")?.classList.remove("on");
      opts.querySelector('button[data-id=""]').classList.add("on");
    }
  }
  $("#drv-menu").hidden = false;
})();
$("#drv-opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const v = b.dataset.id === "" ? null : +b.dataset.id;
  if (v === state.drvId) return;
  $("#drv-menu").removeAttribute("open");
  state.drvId = v;
  $("#drv-opts .on").classList.remove("on"); b.classList.add("on");
  $("#drv-lb").textContent = "驾驶员: " + b.textContent;
  syncURL(); resetList();
});

/* 懒加载: 触底前 PRELOAD_PX 预加载下一页 */
new IntersectionObserver(es => {
  if (es[0].isIntersecting) loadMore();
}, { rootMargin: PRELOAD_PX + "px" }).observe(tailEl);

$("#retry").addEventListener("click", () => { state.err = null; loadMore(); });
$("#logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.replace("/login");
});
