// stats-chart-trend.js — 充电统计页 (2/4): 图表底座 (echarts 实例注册表/tooltip 样式) +
// 月度趋势 (上电量柱/下费用线, 联动) + 常去充电点 (横向条形, 前 7 + 其他) +
// 图表/表格切换与窗口变化重绘。
// 由 stats.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 stats.html
// 里的顺序加载, 跨模块引用走全局); 底座与统计卡片在 stats-page.js, 维度类图表在
// stats-chart-dimensions.js, 时间筛选与数据加载在 stats-time-filters.js。
/* global $, esc, num, money, moneyInt, hasEcharts */
/* exported monthlyData, locData, dimsData, chartText, tooltipStyle, mkChart,
           renderMonthly, renderLocations */
"use strict";
/* ============================ 图表 ============================ */
const chartText = { axis: "#898781", ink: "#c3c2b7" };
const tooltipStyle = {
  backgroundColor: "rgba(28,28,30,.95)", borderWidth: 0, padding: [7, 10],
  textStyle: { color: "#f5f5f7", fontSize: 12 },
};
let monthlyData = [], locData = [], dimsData = null;
const CHART_ELS = { monthlyKw: "#chart-monthly-kwh", monthlyCost: "#chart-monthly-cost",
                    loc: "#chart-loc", fastslow: "#chart-fastslow", hour: "#chart-hour",
                    soc: "#chart-socdist", power: "#chart-powerdist", city: "#chart-city" };
const charts = {};   // 名字 → echarts 实例 (ResizeObserver 统一 resize)

function shortMonth(ym) { return ym.slice(2).replace("-", "/"); }
function truncateName(s, n) { return s.length > n ? s.slice(0, n) + "…" : s; }
function mkChart(name) {
  if (!charts[name]) charts[name] = echarts.init($(CHART_ELS[name]));
  return charts[name];
}

/* ---------- 月度趋势: 上充电量柱 / 下费用线 (联动) ---------- */
function renderMonthly() {
  if (!monthlyData.length) return;
  const months = monthlyData.map(d => d.month);
  const kw = monthlyData.map(d => Math.round((d.energy_used || 0) * 10) / 10);
  const cost = monthlyData.map(d => d.cost == null ? 0 : d.cost);
  const total = monthlyData.reduce((a, d) => a + (d.cost || 0), 0);
  $("#monthly-sub").textContent = `共 ${months.length} 个月 · 合计 ${moneyInt(total)}`;
  $("#table-monthly").innerHTML = `<table>
    <thead><tr><th>月份</th><th>kWh</th><th>费用</th><th>次数</th></tr></thead>
    <tbody>${monthlyData.map(d => `<tr>
      <td>${esc(d.month)}</td><td>${num(d.energy_used)}</td>
      <td>${money(d.cost)}</td><td>${d.sessions}</td></tr>`).join("")}</tbody></table>`;
  if (!hasEcharts) return;
  if (!charts.monthlyKw) {
    echarts.connect([mkChart("monthlyKw"), mkChart("monthlyCost")]);
  }
  const xBase = {
    type: "category", data: months,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: "#383835" } },
  };
  charts.monthlyKw.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 10, bottom: 2, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { ...xBase, axisLabel: { show: false } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", name: "充电量", data: kw, barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] } }],
  });
  charts.monthlyCost.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis",
               axisPointer: { type: "line", lineStyle: { color: "#898781" } } },
    xAxis: { ...xBase, axisLabel: { color: chartText.axis, fontSize: 10,
              interval: months.length > 14 ? 1 : 0, formatter: shortMonth } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10,
                          formatter: v => v >= 1000 ? (v / 1000) + "k" : v } },
    series: [{ type: "line", name: "费用", data: cost, showSymbol: false,
               lineStyle: { color: "#c98500", width: 2 },
               itemStyle: { color: "#c98500" } }],
  });
}

/* ---------- 常去充电点: 横向条形 (前 7 + 其他) ---------- */
function renderLocations() {
  if (!locData.length) return;
  const top = locData.slice(0, 7);
  const rest = locData.slice(7);
  const rows = rest.length
    ? [...top, { location: "其他", sessions: rest.reduce((a, d) => a + d.sessions, 0),
                 energy_used: rest.reduce((a, d) => a + (d.energy_used || 0), 0),
                 cost: rest.reduce((a, d) => a + (d.cost || 0), 0),
                 fast_sessions: rest.reduce((a, d) => a + d.fast_sessions, 0) }] : top;
  $("#loc-sub").textContent = `共 ${locData.length} 个充电点`;
  $("#table-loc").innerHTML = `<table>
    <thead><tr><th>地点</th><th>次数</th><th>kWh</th><th>费用</th></tr></thead>
    <tbody>${locData.map(d => `<tr>
      <td>${esc(truncateName(d.location, 10))}</td><td>${d.sessions}</td>
      <td>${num(d.energy_used)}</td><td>${money(d.cost)}</td></tr>`).join("")}</tbody></table>`;
  if (!hasEcharts) return;
  mkChart("loc").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 44, top: 6, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: (ps) => {
        const d = locData.find(x => x.location === ps[0].name) ||
                  rows.find(x => x.location === ps[0].name);
        return `<b>${esc(ps[0].name)}</b><br/>次数 ${d.sessions} · 快充 ${d.fast_sessions}` +
               `<br/>电量 ${num(d.energy_used)} kWh<br/>费用 ${money(d.cost)}`;
      } },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    yAxis: { type: "category", inverse: true,
             data: rows.map(d => truncateName(d.location, 7)),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.ink, fontSize: 10.5, width: 76,
                          overflow: "truncate" } },
    series: [{ type: "bar", data: rows.map(d => d.sessions), barMaxWidth: 14,
               itemStyle: { color: "#3987e5", borderRadius: [0, 4, 4, 0] },
               label: { show: true, position: "right", color: chartText.ink,
                        fontSize: 10.5, formatter: "{c} 次" } }],
  });
}

/* 图表/表格切换 */
function bindViewToggle(segId, chartEls, tableEl) {
  $(segId).addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    $(segId + " .on").classList.remove("on"); b.classList.add("on");
    const table = b.dataset.v === "table";
    chartEls.forEach(el => el.hidden = table);
    tableEl.hidden = !table;
    if (!table) chartEls.forEach(el => { const c = echarts.getInstanceByDom(el); c && c.resize(); });
  });
}
bindViewToggle("#monthly-view", [$(CHART_ELS.monthlyKw), $(CHART_ELS.monthlyCost)], $("#table-monthly"));
bindViewToggle("#fastslow-view", [$(CHART_ELS.fastslow)], $("#table-fastslow"));
bindViewToggle("#hour-view", [$(CHART_ELS.hour)], $("#table-hour"));
bindViewToggle("#loc-view", [$(CHART_ELS.loc)], $("#table-loc"));
bindViewToggle("#soc-view", [$(CHART_ELS.soc)], $("#table-socdist"));
bindViewToggle("#power-view", [$(CHART_ELS.power)], $("#table-powerdist"));
bindViewToggle("#city-view", [$(CHART_ELS.city)], $("#table-city"));

/* 无 echarts (脚本加载失败) → 全部卡片直接落表格视图, 不留白框 */
if (!hasEcharts) document.querySelectorAll(".chart-card").forEach(card => {
  card.querySelectorAll(".chart-box").forEach(el => { el.hidden = true; });
  const t = card.querySelector(".chart-table"); if (t) t.hidden = false;
  const seg = card.querySelector(".mini-seg");
  if (seg) {
    seg.querySelector('[data-v="chart"]').classList.remove("on");
    seg.querySelector('[data-v="table"]').classList.add("on");
  }
});

/* 窗口尺寸变化: 图表重绘 (网格 1↔2 列切换时宽度变了) */
let resizeTimer;
new ResizeObserver(() => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    Object.values(charts).forEach(c => c && c.resize());
  }, 120);
}).observe(document.body);
