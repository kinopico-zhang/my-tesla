// view/stats-chart-dimensions.js — 充电统计视图 (壳版 3/3): 维度类图表 ——
// 充电开始时段 (12 档柱状, 每 2 小时一组) + 起充 SOC / 峰值功率 / 单价 /
// 充电时长 (十档柱状, 颜色随档位渐进) + 城市分布 (竖排柱状, 双击城市柱
// 下钻区/县/镇二级, 再双击柱返回)。
// 十档与下钻都是 2026-09-27 用户点名 (「起充电量 10 个 bar / 功率每 20 一档 /
// 单价时长也一样」「城市双击展开二级地区」); 轴标用档位起点数字 (与开始
// 时段图同款), 完整区间落在副题和气泡里。
// 2026-09-28 城市分布 (含区县下钻层) 横向条形改竖排柱状 (用户点名「统计的
// 柱状图竖着放吧，下面的文字竖着排列」), 城名/区县名竖排铺柱底。
// 依赖壳公共件: pad/num/money 走 format, 图表底座在 view/stats-chart-trend.js。
/* global $, esc, num, money, pad, hasEcharts, summaryData, chartText,
          tooltipStyle, mkChart, dimsData, getJSON, statsParams, stackLabel */
/* exported renderHour, renderSoc, renderPower, renderPrice, renderDuration,
            renderCity, renderDimBins */
"use strict";
/* ---------- 充电开始时段: 12 档柱状 (每 2 小时一组) ---------- */
function renderHour() {
  if (!dimsData) return;
  const hours = dimsData.by_hour;
  const total = hours.reduce((a, b) => a + b, 0);
  const peak = hours.indexOf(Math.max(...hours));
  $("#hour-sub").textContent = total
    ? `最常 ${pad(peak * 2)}-${pad(peak * 2 + 2)} 点开始 · 共 ${total} 次` : "暂无数据";
  if (!hasEcharts || !total) return;
  mkChart("hour").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 14, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               // 组内下标 b → 起止小时 (b*2 – b*2+2)
               formatter: ps => `${pad(ps[0].dataIndex * 2)}:00 – ` +
                                `${pad(ps[0].dataIndex * 2 + 2)}:00 · <b>${ps[0].value} 次</b>` },
    xAxis: { type: "category", data: hours.map((_, i) => String(i * 2)),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.axis, fontSize: 10, interval: 0 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: hours, barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] } }],
  });
}

/* ---------- 四张十档柱状: 起充 SOC / 峰值功率 / 单价 / 充电时长 ----------
   LB = 完整区间文案 (副题/气泡), AX = 轴标 (档位起点), COLORS 随档渐进 */
const SOC_LB = ["0-10%", "10-20%", "20-30%", "30-40%", "40-50%", "50-60%",
                "60-70%", "70-80%", "80-90%", "90-100%"];
const SOC_AX = ["0", "10", "20", "30", "40", "50", "60", "70", "80", "90"];
const SOC_COLORS = ["#e5484d", "#e0683c", "#e08a3c", "#d9a13c", "#d9b13c",
                    "#c2b145", "#a3b34e", "#7fb257", "#4fae52", "#1fa349"];
const POWER_LB = ["<20", "20-40", "40-60", "60-80", "80-100", "100-120",
                  "120-140", "140-160", "160-180", "≥180"];
const POWER_AX = ["<20", "20", "40", "60", "80", "100", "120", "140", "160", "180"];
const POWER_COLORS = ["#636366", "#74809a", "#879dbf", "#7ba2d2", "#679fd9",
                      "#5c9dd9", "#4a94e2", "#3987e5", "#2d7ce0", "#1f6fd8"];
const PRICE_LB = ["<0.25", "0.25-0.5", "0.5-0.75", "0.75-1", "1-1.25", "1.25-1.5",
                  "1.5-1.75", "1.75-2", "2-2.25", "≥2.25"];
const PRICE_AX = ["0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "1.75", "2", "2.25"];
const PRICE_COLORS = ["#6e5c2e", "#7d672d", "#8f742c", "#a07c28", "#b08425",
                      "#c08a12", "#c98500", "#d38f13", "#d9951f", "#e09a2b"];
const DUR_LB = ["<30分", "30-60分", "1-1.5时", "1.5-2时", "2-3时", "3-4时",
                "4-5时", "5-6时", "6-8时", "≥8时"];
const DUR_AX = ["0", "0.5", "1", "1.5", "2", "3", "4", "5", "6", "8"];   // 小时
const DUR_COLORS = ["#a9c4e9", "#93b7e4", "#7dabde", "#6aa5da", "#589cd6",
                    "#4794e2", "#3a8ce4", "#2f83df", "#2878d9", "#1f6fd8"];

/* 十档柱状公共底座: 副题文本/气泡文案各图自带 (LB 闭包在调用方)。
   2026-09-27 行程统计的分布图也走这里: 图表库有没有直接问 echarts 本尊
   (不读充电视图的 hasEcharts 旗号 —— 两视图各自注入各自重试, 旗号独立) */
function renderDimBins(key, subSel, bins, ax, colors, subText, tipText) {
  const total = bins.reduce((a, b) => a + b, 0);
  $(subSel).textContent = total ? subText : "暂无数据";
  if (typeof echarts === "undefined" || !total) return;
  mkChart(key).setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 14, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => tipText(ps[0].dataIndex) },
    xAxis: { type: "category", data: ax,
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.axis, fontSize: 10, interval: 0 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: bins.map((v, i) => ({ value: v,
               itemStyle: { color: colors[i] } })),
               barMaxWidth: 16, itemStyle: { borderRadius: [4, 4, 0, 0] } }],
  });
}

function renderSoc() {
  if (!dimsData) return;
  const bins = dimsData.by_soc;
  const total = bins.reduce((a, b) => a + b, 0);
  const maxI = bins.indexOf(Math.max(...bins));
  const unknown = summaryData ? summaryData.sessions - total : 0;
  renderDimBins("soc", "#soc-sub", bins, SOC_AX, SOC_COLORS,
    `最常 ${SOC_LB[maxI]} 起充${unknown > 0 ? ` · ${unknown} 次未知` : ""}`,
    i => `${SOC_LB[i]} 起充 · <b>${bins[i]} 次</b>`);
}

function renderPower() {
  if (!dimsData) return;
  const bins = dimsData.by_power;
  const total = bins.reduce((a, b) => a + b, 0);
  const over100 = bins.slice(5).reduce((a, b) => a + b, 0);
  const unknown = summaryData ? summaryData.sessions - total : 0;
  renderDimBins("power", "#power-sub", bins, POWER_AX, POWER_COLORS,
    `≥100 kW 共 ${over100} 次${unknown > 0 ? ` · ${unknown} 次未知` : ""}`,
    i => `${POWER_LB[i]} kW · <b>${bins[i]} 次</b>`);
}

function renderPrice() {
  if (!dimsData) return;
  const bins = dimsData.by_price;
  const total = bins.reduce((a, b) => a + b, 0);
  const maxI = bins.indexOf(Math.max(...bins));
  const unknown = summaryData ? summaryData.sessions - total : 0;
  renderDimBins("price", "#price-sub", bins, PRICE_AX, PRICE_COLORS,
    `最常 ${PRICE_LB[maxI]} ¥/kWh${unknown > 0 ? ` · ${unknown} 次未记费用` : ""}`,
    i => `${PRICE_LB[i]} ¥/kWh · <b>${bins[i]} 次</b>`);
}

function renderDuration() {
  if (!dimsData) return;
  const bins = dimsData.by_duration;
  const total = bins.reduce((a, b) => a + b, 0);
  const maxI = bins.indexOf(Math.max(...bins));
  const unknown = summaryData ? summaryData.sessions - total : 0;
  renderDimBins("dur", "#dur-sub", bins, DUR_AX, DUR_COLORS,
    `最常 ${DUR_LB[maxI]}${unknown > 0 ? ` · ${unknown} 次未知` : ""}`,
    i => `${DUR_LB[i]} · <b>${bins[i]} 次</b>`);
}

/* ---------- 城市分布: 竖排柱状; 双击城市柱下钻区/县/镇, 再双击柱返回 ---------- */
let cityDrill = null;                   // 下钻中的城市名 (null = 城市层)
let lastCityTap = { name: "", t: 0 };   // 双击判定: 同一根柱两击且间隔 < 350ms
let cityTapBound = false;

/* 双击 = click 双连 (桌面双击/手机双击轻点都发 click); 不绑 echarts 的
   dblclick —— click 时序已捕捉, dblclick 再来会双触发 */
function bindCityTap(chart) {
  if (cityTapBound) return;
  cityTapBound = true;
  chart.on("click", e => {
    if (e.componentType !== "series") return;
    const now = Date.now();
    const dbl = lastCityTap.name === e.name && now - lastCityTap.t < 350;
    lastCityTap = { name: e.name, t: now };
    if (!dbl) return;
    cityDrill = cityDrill ? null : e.name;   // 已在下钻层: 双击任一柱返回
    renderCity();
  });
}

async function renderCity() {
  if (!dimsData) return;
  if (cityDrill) { await renderDistricts(); return; }
  const rows = dimsData.by_city;
  const total = rows.reduce((a, c) => a + c.sessions, 0);
  $("#city-sub").textContent = total ? `共 ${rows.length} 城 · 双击柱看区县` : "暂无数据";
  if (!hasEcharts || !total) return;
  const chart = mkChart("city");
  bindCityTap(chart);
  chart.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 16, top: 16, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => {
                 const c = rows[ps[0].dataIndex];
                 return `<b>${esc(c.city)}</b><br/>${c.sessions} 次` +
                        `<br/>电量 ${num(c.energy)} kWh<br/>费用 ${money(c.cost)}`;
               } },
    xAxis: { type: "category", interval: 0, data: rows.map(c => stackLabel(c.city)),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.ink, fontSize: 10.5, lineHeight: 12 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: rows.map(c => c.sessions), barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] },
               label: { show: true, position: "top", color: chartText.ink,
                        fontSize: 10.5, formatter: "{c} 次" } }],
  });
}

/* 下钻层: 某市的区/县/镇竖排柱状 (深一档的蓝区分层级); 拉失败/空表退回城市层 */
async function renderDistricts() {
  const city = cityDrill;
  let rows = [];
  try {
    const q = statsParams();
    rows = await getJSON("/tesla/charging/api/districts?city=" +
                         encodeURIComponent(city) + (q ? "&" + q : ""));
  } catch (_e) { /* 下钻拉失败: 下面退回城市层 */ }
  if (cityDrill !== city) return;             // 期间层被切走 (双击返回抢先)
  if (!rows.length) { cityDrill = null; renderCity(); return; }
  $("#city-sub").textContent = `${city} · 双击柱返回`;
  const chart = mkChart("city");
  bindCityTap(chart);
  chart.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 16, top: 16, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => {
                 const d = rows[ps[0].dataIndex];
                 return `<b>${esc(d.district)}</b><br/>${d.sessions} 次` +
                        `<br/>电量 ${num(d.energy)} kWh<br/>费用 ${money(d.cost)}`;
               } },
    xAxis: { type: "category", interval: 0, data: rows.map(d => stackLabel(d.district)),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.ink, fontSize: 10.5, lineHeight: 12 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: rows.map(d => d.sessions), barMaxWidth: 16,
               itemStyle: { color: "#1f6fd8", borderRadius: [4, 4, 0, 0] },
               label: { show: true, position: "top", color: chartText.ink,
                        fontSize: 10.5, formatter: "{c} 次" } }],
  });
}
