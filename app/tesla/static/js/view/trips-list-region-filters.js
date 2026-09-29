// view/trips-list-region-filters.js — 行程列表视图 (壳版 4/6): 屏底筛选条
// chips —— 起点/终点 (省市区三级级联, 树来自 /trips/api/regions, 按当前车
// 过滤) / 里程档 / 驾驶员 (设置页驾驶员表, 没配过驾驶员整枚 chip 不出现)。
// 旧版 (js/trips-list-region-filters.js) 是头部 .filters 下拉菜单族 + 懒
// 加载观察器/重试/登出 —— 后三者已归 view 底座与壳件; 级联弹层交互照
// 充电视图 buildLocPop 同款 (fb-pop 没有 toggle 事件, 每次打开从当前所
// 选的父层起钻)。文件名沿用旧名 (命名普查按 basename 折叠)。
/* global esc, getJSON, KM_BUCKETS, state, driversCache: writable,
          trSaveFilters, resetList, shellState, onCarChange, registerChips,
          refreshBarChips, closeFbPop, buildOptsPop */
/* exported trFetchRegions */
"use strict";

/* 起终点省市区树 (次数降序, 按当前车过滤); 拉不到就只有"全部" */
const TR_REGIONS = { start: [], end: [] };
function trFetchRegions() {
  const q = shellState.carId != null ? `?car_id=${shellState.carId}` : "";
  getJSON("/tesla/trips/api/regions" + q)
    .then(r => { TR_REGIONS.start = r.start || []; TR_REGIONS.end = r.end || []; })
    .catch(() => { /* keep 全部 */ });
}
onCarChange(trFetchRegions);   // 换车: 起终点树按新车重拉

/* ---------- 起点 / 终点: 省市区级联弹层 ----------
   点层级行钻下一级, 顶部 "全部X" 行选中当前层 (省/市/区县任一级都能作为
   筛选条件), 叶子直接选中; key 是 state 字段 (fromLoc/toLoc)。 */
function buildTrLocPop(pop, key, treeKey) {
  let stack = state[key] ? state[key].split("/").slice(0, -1) : [];
  const setLoc = v => {
    state[key] = v;
    trSaveFilters();
  };
  const nodesAt = () => {   // stack 对应的节点层
    let nodes = TR_REGIONS[treeKey];
    for (const seg of stack) {
      const n = nodes.find(x => x.name === seg);
      nodes = n ? n.children : [];
    }
    return nodes;
  };
  const render = () => {
    const sel = state[key], cur = stack.join("/");
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
      closeFbPop(); refreshBarChips(); resetList();
      return;
    }
    const node = nodesAt().find(n => n.name === b.dataset.n);
    if (!node) return;
    if (node.children.length) { stack.push(node.name); return render(); }   // 钻下一级
    setLoc([...stack, node.name].join("/"));             // 叶子 (区县) 直接选中
    closeFbPop(); refreshBarChips(); resetList();
  };
  render();
}

const locLabel = (key, prefix) =>
  prefix + (state[key] ? state[key].split("/").pop() : "全部");

/* ---------- 里程 / 驾驶员: 通用选项弹层 (charging-filters 同款) ---------- */
function buildKmPop(pop) {
  buildOptsPop(pop, KM_BUCKETS.map(b => ({ v: b.v, lb: b.lb })), state.km, v => {
    state.km = v;
    trSaveFilters(); refreshBarChips(); resetList();
  });
}
function buildDrvPop(pop) {
  const drivers = driversCache || [];
  buildOptsPop(pop,
    [{ v: "", lb: "全部" }].concat(
      drivers.map(d => ({ v: String(d.id), lb: d.name }))),
    state.drvId == null ? "" : String(state.drvId), v => {
      state.drvId = v === "" ? null : +v;
      trSaveFilters(); refreshBarChips(); resetList();
    });
}
function drvLabel() {
  const d = (driversCache || []).find(x => x.id === state.drvId);
  return "驾驶员: " + (d ? d.name : "全部");
}

/* chips: 先注册起终点/里程三枚; 驾驶员表拉回来且有人才补第四枚
   (没配驾驶员的部署不该出现空 chip) */
function trChips() {
  const chips = [
    { id: "from", label: () => locLabel("fromLoc", "起点: "),
      isOn: () => !!state.fromLoc, build: p => buildTrLocPop(p, "fromLoc", "start") },
    { id: "to", label: () => locLabel("toLoc", "终点: "),
      isOn: () => !!state.toLoc, build: p => buildTrLocPop(p, "toLoc", "end") },
    { id: "km", label: () => "里程: " + KM_BUCKETS.find(b => b.v === state.km).lb,
      isOn: () => state.km !== "all", build: buildKmPop },
  ];
  if ((driversCache || []).length)
    chips.push({ id: "drv", label: drvLabel,
                 isOn: () => state.drvId != null, build: buildDrvPop });
  return chips;
}
registerChips("trips", trChips());

/* 驾驶员筛选: 选项来自设置页的驾驶员表 (筛选条与弹层标注共用 driversCache);
   筛选口径与卡片一致 —— 选默认驾驶员 = 标注它的 + 未标注的 (后端合并处理) */
(async () => {
  if (driversCache === undefined) {
    try { driversCache = await getJSON("/tesla/api/drivers"); }
    catch { driversCache = null; }
  }
  const drivers = driversCache || [];
  if (!drivers.length) return;
  if (state.drvId != null) {   // 上次存的选择要还在表里才算数 (驾驶员可能已删)
    if (!drivers.some(d => d.id === state.drvId)) {
      state.drvId = null;
      trSaveFilters();
    }
  }
  registerChips("trips", trChips());
  refreshBarChips();
})();
