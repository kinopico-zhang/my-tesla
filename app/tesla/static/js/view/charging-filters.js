// view/charging-filters.js — 充电记录视图 (壳版 3/6): 屏底筛选条的三枚
// chips —— 类型/费用/地点 (省市区级联, 旧页同款树与交互, 渲染目标从悬浮
// 下拉换成 #fb-pop 弹层)。时间筛选 3.3.0 下线 (全时段), 条里再无全局 chip。
/* global esc, getJSON, chgState, chgSaveFilters, chgRefetch, shellState,
          onCarChange, registerChips, refreshBarChips, closeFbPop */
/* exported chgFetchRegions */
"use strict";
const TYPE_LABELS = { all: "类型: 全部", fast: "类型: 快充", slow: "类型: 慢充" };
const COST_LABELS = { all: "费用: 全部", recorded: "费用: 已记录", missing: "费用: 未记录" };

/* 地点树 (次数降序, 按当前车过滤); 拉不到就只有"全部" */
let REGIONS = [];
function chgFetchRegions() {
  const q = shellState.carId != null ? `?car_id=${shellState.carId}` : "";
  getJSON("/tesla/charging/api/regions" + q)
    .then(r => { REGIONS = r; })
    .catch(() => { /* keep 全部 */ });
}
onCarChange(chgFetchRegions);   // 换车: 地点树按新车重拉

/* ---------- 通用 chip 弹层: 选完即收, 刷新 chips 文案再重拉列表 ---------- */
function buildOptsPop(pop, opts, cur, onPick) {
  pop.innerHTML = `<div class="fb-scroll">${opts.map(o =>
    `<button type="button" data-v="${o.v}"${o.v === cur ? ' class="on"' : ""}>${o.lb}</button>`).join("")}</div>`;
  pop.onclick = e => {
    const b = e.target.closest("button[data-v]");
    if (!b) return;
    closeFbPop();
    if (b.dataset.v !== cur) onPick(b.dataset.v);   // 点当前项 = 只收弹层
  };
}

/* ---------- 类型 / 费用 ---------- */
function buildTypePop(pop) {
  buildOptsPop(pop,
    [{ v: "all", lb: "全部" }, { v: "fast", lb: "快充" }, { v: "slow", lb: "慢充" }],
    chgState.type, v => {
      chgState.type = v;
      chgSaveFilters(); refreshBarChips(); chgRefetch();
    });
}
function buildCostPop(pop) {
  buildOptsPop(pop,
    [{ v: "all", lb: "全部" }, { v: "recorded", lb: "已记录费用" }, { v: "missing", lb: "未记录费用" }],
    chgState.cost, v => {
      chgState.cost = v;
      chgSaveFilters(); refreshBarChips(); chgRefetch();
    });
}

/* ---------- 地点: 省市区级联 (行程页同款) ----------
   树来自 /charging/api/regions。点层级行钻下一级, 顶部 "全部X" 行选中当前层
   (省/市/区县任一级都能作为筛选条件), 叶子直接选中。弹层每次打开都从
   当前所选的父层起钻 (旧版靠菜单 toggle 事件重置, 弹层没有 toggle)。 */
function buildLocPop(pop) {
  let stack = chgState.region ? chgState.region.split("/").slice(0, -1) : [];
  const setLoc = v => {
    chgState.region = v;
    chgSaveFilters();
  };
  const nodesAt = () => {   // stack 对应的节点层
    let nodes = REGIONS;
    for (const seg of stack) {
      const n = nodes.find(x => x.name === seg);
      nodes = n ? n.children : [];
    }
    return nodes;
  };
  const render = () => {
    const sel = chgState.region, cur = stack.join("/");
    const rows = nodesAt().map(n => {
      const path = (cur ? cur + "/" : "") + n.name;
      return `<button type="button" class="loc-row${path === sel ? " on" : ""}" data-n="${esc(n.name)}">` +
        `<span class="nm">${esc(n.name)}</span>` +
        `<span class="cnt">${n.count}${n.children.length ? " ›" : ""}</span></button>`;
    }).join("");
    pop.innerHTML = `<div class="fb-scroll">` +
      (stack.length ? `<button type="button" class="loc-back" data-b="1">‹ 返回</button>` +
        `<div class="loc-crumb">${esc(stack.join(" · "))}</div>` : "") +
      `<button type="button" data-a="${esc(cur)}"${sel === cur ? ' class="on"' : ""}>` +
      `${cur ? "全部" + esc(stack[stack.length - 1]) : "全部"}</button>` + rows + `</div>`;
  };
  pop.onclick = e => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.b) { stack.pop(); return render(); }   // ‹ 返回
    if (b.dataset.a !== undefined) {                     // "全部X" = 选中当前层
      setLoc(b.dataset.a);
      closeFbPop(); refreshBarChips(); chgRefetch();
      return;
    }
    const node = nodesAt().find(n => n.name === b.dataset.n);
    if (!node) return;
    if (node.children.length) { stack.push(node.name); return render(); }   // 钻下一级
    setLoc([...stack, node.name].join("/"));             // 叶子 (区县) 直接选中
    closeFbPop(); refreshBarChips(); chgRefetch();
  };
  render();
}

registerChips("charging", [
  { id: "type", label: () => TYPE_LABELS[chgState.type],
    isOn: () => chgState.type !== "all", build: buildTypePop },
  { id: "loc", label: () => "地点: " + (chgState.region ? chgState.region.split("/").pop() : "全部"),
    isOn: () => !!chgState.region, build: buildLocPop },
  { id: "cost", label: () => COST_LABELS[chgState.cost],
    isOn: () => chgState.cost !== "all", build: buildCostPop },
]);
