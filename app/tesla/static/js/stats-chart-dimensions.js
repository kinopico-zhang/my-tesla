// stats-chart-dimensions.js — 充电统计页 (3/4): 维度类图表 —— 快慢充占比 (环形) +
// 充电时段 (24 档柱状) + 起充 SOC / 峰值功率 (五档柱状, 颜色随档位渐进) +
// 城市分布 (横向条形)。
// 由 stats.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 stats.html
// 里的顺序加载, 跨模块引用走全局); 底座与统计卡片在 stats-page.js, 总量类图表在
// stats-chart-trend.js, 时间筛选与数据加载在 stats-time-filters.js。
/* global $, esc, num, money, pad, hasEcharts, summaryData, chartText,
          tooltipStyle, mkChart, dimsData */
/* exported renderFastSlow, renderHour, renderSoc, renderPower, renderCity */
"use strict";
/* ---------- 快慢充占比: 环形 ---------- */
function renderFastSlow() {
  if (!dimsData) return;
  const d = dimsData, total = d.fast_sessions + d.slow_sessions;
  $("#fastslow-sub").textContent = total
    ? `快充 ${Math.round(d.fast_sessions / total * 100)}% · 慢充 ${total - d.fast_sessions} 次` : "暂无数据";
  const pct = v => total ? Math.round(v / total * 100) + "%" : "—";
  $("#table-fastslow").innerHTML = `<table>
    <thead><tr><th>类型</th><th>次数</th><th>占比</th></tr></thead>
    <tbody>
      <tr><td>快充</td><td>${d.fast_sessions}</td><td>${pct(d.fast_sessions)}</td></tr>
      <tr><td>慢充</td><td>${d.slow_sessions}</td><td>${pct(d.slow_sessions)}</td></tr>
      <tr><td>合计</td><td>${total}</td><td>100%</td></tr>
    </tbody></table>`;
  if (!hasEcharts || !total) return;
  mkChart("fastslow").setOption({
    animationDuration: 250,
    tooltip: { ...tooltipStyle, trigger: "item", formatter: "{b}: {c} 次 ({d}%)" },
    legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8, itemGap: 18,
              textStyle: { color: chartText.ink, fontSize: 11 } },
    series: [{ type: "pie", radius: ["50%", "70%"], center: ["50%", "42%"],
               avoidLabelOverlap: true,
               itemStyle: { borderColor: "#1c1c1e", borderWidth: 2 },
               label: { show: false },
               data: [
                 { name: "快充", value: d.fast_sessions, itemStyle: { color: "#f0b13d" } },
                 { name: "慢充", value: d.slow_sessions, itemStyle: { color: "#7db3f0" } },
               ] }],
  });
}

/* ---------- 充电时段: 24 档柱状 ---------- */
function renderHour() {
  if (!dimsData) return;
  const hours = dimsData.by_hour;
  const total = hours.reduce((a, b) => a + b, 0);
  const peak = hours.indexOf(Math.max(...hours));
  $("#hour-sub").textContent = total ? `最常 ${pad(peak)} 点前后开始 · 共 ${total} 次` : "暂无数据";
  $("#table-hour").innerHTML = `<table>
    <thead><tr><th>时段</th><th>次数</th></tr></thead>
    <tbody>${hours.map((v, i) => `<tr>
      <td>${pad(i)}:00 – ${pad((i + 1) % 24)}:00</td><td>${v}</td></tr>`).join("")}</tbody></table>`;
  if (!hasEcharts || !total) return;
  mkChart("hour").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 14, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => `${pad(ps[0].dataIndex)}:00 – ${pad((ps[0].dataIndex + 1) % 24)}:00 · <b>${ps[0].value} 次</b>` },
    xAxis: { type: "category", data: hours.map((_, i) => pad(i)),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.axis, fontSize: 10, interval: 2 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: hours, barMaxWidth: 12,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] } }],
  });
}

/* ---------- 起充 SOC / 峰值功率: 五档柱状 (颜色随档位渐进, 低档偏暖) ---------- */
const SOC_LB = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"];
const SOC_COLORS = ["#e5484d", "#e08a3c", "#d9b13c", "#7db3f0", "#1fa349"];
const POWER_LB = ["<60", "60-100", "100-150", "150-200", "≥200"];
const POWER_COLORS = ["#636366", "#7d8ba3", "#5c9dd9", "#3987e5", "#1f6fd8"];

function renderSoc() {
  if (!dimsData) return;
  const bins = dimsData.by_soc;
  const total = bins.reduce((a, b) => a + b, 0);
  const maxI = bins.indexOf(Math.max(...bins));
  const unknown = summaryData ? summaryData.sessions - total : 0;
  $("#soc-sub").textContent = total
    ? `最常 ${SOC_LB[maxI]} 起充${unknown > 0 ? ` · ${unknown} 次未知` : ""}` : "暂无数据";
  $("#table-socdist").innerHTML = `<table>
    <thead><tr><th>起充 SOC</th><th>次数</th></tr></thead>
    <tbody>${bins.map((v, i) => `<tr><td>${SOC_LB[i]}</td><td>${v}</td></tr>`).join("")}
      ${unknown > 0 ? `<tr><td>未知</td><td>${unknown}</td></tr>` : ""}</tbody></table>`;
  if (!hasEcharts || !total) return;
  mkChart("soc").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 14, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => `${ps[0].name} 起充 · <b>${ps[0].value} 次</b>` },
    xAxis: { type: "category", data: SOC_LB,
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: bins.map((v, i) => ({ value: v,
               itemStyle: { color: SOC_COLORS[i] } })),
               barMaxWidth: 30, itemStyle: { borderRadius: [4, 4, 0, 0] } }],
  });
}

function renderPower() {
  if (!dimsData) return;
  const bins = dimsData.by_power;
  const total = bins.reduce((a, b) => a + b, 0);
  const over100 = bins[2] + bins[3] + bins[4];
  const unknown = summaryData ? summaryData.sessions - total : 0;
  $("#power-sub").textContent = total
    ? `≥100 kW 共 ${over100} 次${unknown > 0 ? ` · ${unknown} 次未知` : ""}` : "暂无数据";
  $("#table-powerdist").innerHTML = `<table>
    <thead><tr><th>峰值功率 kW</th><th>次数</th></tr></thead>
    <tbody>${bins.map((v, i) => `<tr><td>${POWER_LB[i]}</td><td>${v}</td></tr>`).join("")}
      ${unknown > 0 ? `<tr><td>未知</td><td>${unknown}</td></tr>` : ""}</tbody></table>`;
  if (!hasEcharts || !total) return;
  mkChart("power").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 14, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => `${ps[0].name} kW · <b>${ps[0].value} 次</b>` },
    xAxis: { type: "category", data: POWER_LB,
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: bins.map((v, i) => ({ value: v,
               itemStyle: { color: POWER_COLORS[i] } })),
               barMaxWidth: 30, itemStyle: { borderRadius: [4, 4, 0, 0] } }],
  });
}

/* ---------- 城市分布: 横向条形 (服务端已按次数降序, 最多 10 城) ---------- */
function renderCity() {
  if (!dimsData) return;
  const rows = dimsData.by_city;
  const total = rows.reduce((a, c) => a + c.sessions, 0);
  $("#city-sub").textContent = total ? `共 ${rows.length} 城` : "暂无数据";
  $("#table-city").innerHTML = `<table>
    <thead><tr><th>城市</th><th>次数</th><th>kWh</th><th>费用</th></tr></thead>
    <tbody>${rows.map(c => `<tr>
      <td>${esc(c.city)}</td><td>${c.sessions}</td>
      <td>${num(c.energy)}</td><td>${money(c.cost)}</td></tr>`).join("")}</tbody></table>`;
  if (!hasEcharts || !total) return;
  mkChart("city").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 44, top: 6, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => {
                 const c = rows[ps[0].dataIndex];
                 return `<b>${esc(c.city)}</b><br/>${c.sessions} 次` +
                        `<br/>电量 ${num(c.energy)} kWh<br/>费用 ${money(c.cost)}`;
               } },
    xAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    yAxis: { type: "category", inverse: true, data: rows.map(c => c.city),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.ink, fontSize: 10.5, width: 96,
                          overflow: "truncate" } },
    series: [{ type: "bar", data: rows.map(c => c.sessions), barMaxWidth: 14,
               itemStyle: { color: "#3987e5", borderRadius: [0, 4, 4, 0] },
               label: { show: true, position: "right", color: chartText.ink,
                        fontSize: 10.5, formatter: "{c} 次" } }],
  });
}
