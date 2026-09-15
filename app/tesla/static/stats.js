// stats.js — 充电统计页: 统计卡片 + 各维度图表 (记录列表在充电记录页, 此页只看汇总)
"use strict";
/* 页签菜单: 点空白处收起。
   注意: 日历点选会在点击处理器里 innerHTML 重渲染, 事件目标被脱链
   (closest() 找不到菜单祖先) —— 脱链的点击一定发生在某个菜单里, 不能当"点外面"关闭。 */
document.addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});
/* ============================ 工具 ============================ */
const $ = (s, el) => (el || document).querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* 页面共用格式化 (format.js 先加载): 顶部解构, 下文沿用裸名 */
const { pad, parseLocal, num } = FormatUtil;

const money = v => v == null ? "—" : "¥" + Number(v).toFixed(2).replace(/\.?0+$/, "");
const moneyInt = v => v == null ? "—" : "¥" + Math.round(v).toLocaleString("zh-CN");
const thousands = v => Math.round(v).toLocaleString("zh-CN");

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/* ============================ 状态 ============================ */
/* ---------- 顶栏时间筛选: 快捷档位下拉, 编码进 ?range= (分享/刷新保留) ---------- */
const TIME_RANGES = [
  { v: "24h", days: 1, lb: "24小时" },
  { v: "7d", days: 7, lb: "近一周" },
  { v: "30d", days: 30, lb: "近一月" },
  { v: "180d", days: 180, lb: "近半年" },
  { v: "1y", days: 365, lb: "近一年" },
  { v: "all", days: 0, lb: "全部" },
];
function timeFrom(v) {   // 档位 → from 本地日期 (含今天共 N 天; 24h 即"昨天起")
  const r = TIME_RANGES.find(x => x.v === v);
  if (!r || !r.days) return null;
  const d = new Date(); d.setDate(d.getDate() - (r.days - 1));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
// URL → 初始筛选: ?range= 快捷档; ?from=&to= 自定义区间
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const state = { range: range0, cFrom: cFrom0, cTo: cTo0 };
const hasEcharts = typeof echarts !== "undefined";

function rangeParams() {
  if (state.range === "custom") {   // 自定义起止 (日历)
    const p = {};
    if (state.cFrom) p.from = state.cFrom;
    if (state.cTo) p.to = state.cTo;
    return p;
  }
  const from = timeFrom(state.range);
  return from ? { from } : {};
}
function statsParams() { return new URLSearchParams(rangeParams()).toString(); }
function syncURL() {   // 筛选写进地址栏 (默认值不写, 链接保持干净)
  const u = new URL(location.href);
  if (state.range === "custom") {
    u.searchParams.delete("range");
    u.searchParams.set("from", state.cFrom); u.searchParams.set("to", state.cTo);
  } else {
    u.searchParams.delete("from"); u.searchParams.delete("to");
    if (state.range === "all") u.searchParams.delete("range");
    else u.searchParams.set("range", state.range);
  }
  history.replaceState(null, "", u);
}

/* ============================ 统计卡片 ============================ */
let summaryData = null;   // 起充 SOC / 峰值功率图要算"未知"次数 (总次数 - 进档次数)

function renderSummary(s) {
  summaryData = s;
  const months = s.first_date && s.last_date ?
    (parseLocal(s.last_date + " 00:00").getFullYear() * 12 + parseLocal(s.last_date + " 00:00").getMonth()) -
    (parseLocal(s.first_date + " 00:00").getFullYear() * 12 + parseLocal(s.first_date + " 00:00").getMonth()) + 1 : 1;
  const fastPct = s.sessions ? Math.round(s.fast_sessions / s.sessions * 100) : 0;
  const cards = [
    { lb: "充电次数", val: thousands(s.sessions), sub: months > 1 ? `月均 ${Math.round(s.sessions / months)} 次` : "" },
    { lb: "总充电量", val: thousands(s.energy_used || s.energy_added), unit: "kWh", sub: `表计口径` },
    { lb: "总费用", val: moneyInt(s.cost), sub: s.first_date ? `${s.first_date.replace(/-/g, "/")} 起` : "" },
    { lb: "平均电价", val: s.price_per_kwh == null ? "—" : "¥" + s.price_per_kwh.toFixed(3), unit: "/kWh", sub: "按表计电量" },
    { lb: "快充占比", val: fastPct + "%", sub: `快充 ${s.fast_sessions} 次` },
    { lb: "充电时长", val: num(s.duration_min / 60, 1), unit: "小时", sub: s.range_gain ? `≈ ${thousands(s.range_gain)} km 续航` : "" },
  ];
  $("#stats-row").innerHTML = cards.map(c => `
    <div class="stat">
      <div class="lb">${esc(c.lb)}</div>
      <div class="val">${c.val}${c.unit ? `<small>${c.unit}</small>` : ""}</div>
      ${c.sub ? `<div class="sub">${esc(c.sub)}</div>` : ""}
    </div>`).join("");
}

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

/* ============================ 加载 ============================ */
async function loadAll() {
  $("#charts-grid").classList.add("dim");
  $("#loader-spin").hidden = false;
  $("#errbox").hidden = true;
  try {
    const [summary, monthly, locations, dims] = await Promise.all([
      getJSON("/tesla/charging/api/summary?" + statsParams()),
      getJSON("/tesla/charging/api/monthly?" + statsParams()),
      getJSON("/tesla/charging/api/locations?" + statsParams()),
      getJSON("/tesla/charging/api/dimensions?" + statsParams()),
    ]);
    renderSummary(summary);
    monthlyData = monthly; locData = locations; dimsData = dims;
    renderMonthly(); renderLocations(); renderFastSlow();
    renderHour(); renderSoc(); renderPower(); renderCity();
  } catch (e) {
    $("#errmsg").textContent = "数据加载失败: " + e.message;
    $("#errbox").hidden = false;
  }
  $("#loader-spin").hidden = true;
  $("#charts-grid").classList.remove("dim");
}

async function refetch() { await loadAll(); }

/* ============================ 时间筛选 ============================ */
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
$("#retry").addEventListener("click", () => { $("#errbox").hidden = true; refetch(); });

/* 顶栏刷新: 重拉当前页数据 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await refetch();
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
  location.href = "/login";
});

setTimeRange(state.range, true);
refetch();
