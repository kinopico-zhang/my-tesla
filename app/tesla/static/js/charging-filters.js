// charging-filters.js — 充电记录页 (3/6): 筛选交互 —— 快充/慢充下拉、费用记录
// 下拉、顶栏时间筛选 (快捷档 + 自定义日历, 连点两次选区间)、省市区级联
// 地点筛选 (与行程页同款) 与重试。
// 由 index.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 index.html
// 里的顺序加载, 跨模块引用走全局); 底座在 charging-page.js, 记录卡片在
// charging-cards.js, 详情弹层在 charging-detail.js, 导航选单在
// charging-nav.js, 费用编辑在 charging-cost.js。
/* global $, esc, getJSON, pad, state, TIME_RANGES, syncURL, refetch */
"use strict";
const TYPE_LABELS = { all: "类型: 全部", fast: "类型: 快充", slow: "类型: 慢充" };
$("#type-opts").addEventListener("click", e => {   // 快充/慢充下拉 (与城市筛选同款, 替代占地方的分段钮)
  const b = e.target.closest("button"); if (!b || b.classList.contains("on")) return;
  $("#type-menu").removeAttribute("open");
  state.type = b.dataset.v;
  $("#type-opts .on").classList.remove("on"); b.classList.add("on");
  $("#type-lb").textContent = TYPE_LABELS[state.type];
  syncURL(); refetch();
});
const COST_LABELS = { all: "费用: 全部", recorded: "费用: 已记录", missing: "费用: 未记录" };
$("#cost-opts").addEventListener("click", e => {   // 费用记录下拉 (找没记费用的充电补录)
  const b = e.target.closest("button"); if (!b || b.classList.contains("on")) return;
  $("#cost-menu").removeAttribute("open");
  state.cost = b.dataset.v;
  $("#cost-opts .on").classList.remove("on"); b.classList.add("on");
  $("#cost-lb").textContent = COST_LABELS[state.cost];
  syncURL(); refetch();
});
function timeLabel() {
  if (state.range === "custom")   // 自定义显示紧凑区间, 如 01/01–03/31
    return `${state.cFrom.slice(5).replace("-", "/")}–${state.cTo.slice(5).replace("-", "/")}`;
  return TIME_RANGES.find(r => r.v === state.range).lb;
}
function setTimeRange(v, skipFetch) {
  state.range = v;
  $("#time-lb").textContent = timeLabel();
  document.querySelectorAll("#time-opts button[data-v]").forEach(b =>
    b.classList.toggle("on", b.dataset.v === v));
  if (v !== "custom") $("#tm-dates").hidden = true;   // 回到快捷档, 收起日历
  syncURL();
  if (!skipFetch) refetch();
}
/* ---------- 自定义日历: 同一个日历连点两次 —— 第一下起点, 第二下终点 ----------
   终点早于起点自动交换; 已有区间再点 = 重新开始选; 只点一下就确定 = 单日。 */
let calYm = "", calA = null, calB = null;    // 显示月 / 草稿起止 (ISO 日期)
const calCn = iso => { const p = iso.split("-"); return `${+p[1]}月${+p[2]}日`; };
function calRender() {
  const [y, m] = calYm.split("-").map(Number);
  $("#tm-ym").textContent = `${y}年${m}月`;
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7;   // 周一开头
  const days = new Date(y, m, 0).getDate();
  const n = new Date();
  const today = `${n.getFullYear()}-${pad(n.getMonth() + 1)}-${pad(n.getDate())}`;
  $("#tm-next").disabled = calYm >= today.slice(0, 7);     // 未来月没有数据
  let h = "";
  for (let i = 0; i < lead; i++) h += "<i></i>";
  for (let d = 1; d <= days; d++) {
    const iso = `${calYm}-${pad(d)}`;
    const cls = iso === calA || iso === calB ? "on"
      : calA && calB && iso > calA && iso < calB ? "mid" : "";
    h += `<button class="${cls}${iso === today ? " today" : ""}"
            data-d="${iso}" aria-label="${iso}">${d}</button>`;
  }
  $("#tm-cal").innerHTML = h;   // 重渲染会脱链点击目标, "点空白处收起" 的守卫兜底
  $("#tm-sel").textContent = !calA ? "点选开始日期"
    : !calB ? `已选开始 ${calCn(calA)}, 再点结束日期`
    : `${calCn(calA)} – ${calCn(calB)}`;
}
function calShift(k) {
  const [y, m] = calYm.split("-").map(Number);
  const t = new Date(y, m - 1 + k, 1);
  calYm = `${t.getFullYear()}-${pad(t.getMonth() + 1)}`;
  calRender();
}
function calOpen() {   // 打开日历: 带出已应用的自定义区间, 没有则从当月起
  calA = state.cFrom; calB = state.cTo;
  calYm = (calA || `${new Date().getFullYear()}-${pad(new Date().getMonth() + 1)}`).slice(0, 7);
  calRender();
}
$("#tm-cal").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const d = b.dataset.d;
  if (!calA || calB) { calA = d; calB = null; }   // 新一轮: 重新选起点
  else if (d < calA) { calB = calA; calA = d; }   // 反着点: 自动交换
  else calB = d;                                  // 第二下 = 终点 (同一天 = 单日)
  calRender();
});
$("#tm-prev").addEventListener("click", () => calShift(-1));
$("#tm-next").addEventListener("click", () => calShift(1));
$("#time-opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || !b.dataset.v) return;   // 日历里的按钮 (日期/翻月/确定) 不走快捷档逻辑
  if (b.dataset.v === "custom") {   // 展开/收起日历, 连点两次选好再确定生效
    const box = $("#tm-dates");
    box.hidden = !box.hidden;
    if (!box.hidden) calOpen();
    return;
  }
  if (b.dataset.v === state.range) return;
  $("#time-menu").removeAttribute("open");
  setTimeRange(b.dataset.v);
});
$("#tm-apply").addEventListener("click", () => {
  if (!calA) return;                // 一下都没点不生效
  $("#time-menu").removeAttribute("open");
  state.cFrom = calA;               // 只点了起点 = 单日
  state.cTo = calB || calA;
  setTimeRange("custom");
});
$("#time-menu").addEventListener("toggle", () => {   // 重开菜单回到已应用区间
  if ($("#time-menu").open && !$("#tm-dates").hidden) calOpen();
});
setTimeRange(state.range, true);
$("#type-lb").textContent = TYPE_LABELS[state.type] || "类型: 全部";
if (state.type !== "all") {                   // URL 带类型/城市时同步选中态
  $("#type-opts .on").classList.remove("on");
  $(`#type-opts button[data-v="${state.type}"]`).classList.add("on");
}
if (state.cost !== "all") {                   // URL 带费用筛选时同步选中态
  $("#cost-lb").textContent = COST_LABELS[state.cost];
  $("#cost-opts .on").classList.remove("on");
  $(`#cost-opts button[data-v="${state.cost}"]`).classList.add("on");
}
/* ---------- 地点筛选: 省市区级联 (行程页同款) ----------
   树来自 /charging/api/regions (省→市→区县, 次数降序)。点层级行钻下一级,
   顶部 "全部X" 行选中当前层 (省/市/区县任一级都能作为筛选条件), 叶子直接选中。 */
let REGIONS = [];
function renderLocMenu() {
  const menuEl = $("#loc-menu"), optsEl = $("#loc-opts"), lbEl = $("#loc-lb");
  const stack = [];   // 当前钻取路径 (省名/市名), 空 = 省列表
  const setLoc = v => {
    state.region = v;
    lbEl.textContent = "地点: " + (v ? v.split("/").pop() : "全部");   // 显示末级, title 全路径
    lbEl.parentElement.title = v;
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
    const sel = state.region, cur = stack.join("/");
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
      syncURL(); refetch();
      return;
    }
    const node = nodesAt().find(n => n.name === b.dataset.n);
    if (!node) return;
    if (node.children.length) { stack.push(node.name); return render(); }   // 钻下一级
    menuEl.removeAttribute("open");                     // 叶子 (区县) 直接选中
    setLoc([...stack, node.name].join("/"));
    syncURL(); refetch();
  });
  menuEl.addEventListener("toggle", () => {   // 关闭时把视图重置到当前所选的父层,
    if (menuEl.open) return;                  // 下次打开即所见 (toggle 异步, 开时才渲会闪旧视图)
    stack.length = 0;
    if (state.region) stack.push(...state.region.split("/").slice(0, -1));
    render();
  });
  setLoc(state.region);   // URL 带筛选时同步标签
  if (state.region) stack.push(...state.region.split("/").slice(0, -1));
  render();
  return render;
}
const rerenderLoc = renderLocMenu();
(async () => {   // 地点树 (次数降序); 拉不到就只有"全部"
  try { REGIONS = await getJSON("/tesla/charging/api/regions"); }
  catch (_e) { /* keep 全部 */ }
  rerenderLoc();
})();
$("#retry").addEventListener("click", () => { state.err = null; $("#errbox").hidden = true; refetch(); });
