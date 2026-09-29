// view/battery-page.js — 电池健康视图 (2026-09-27 新增, 用户点名「充电菜单里
// 再加一个电池健康度的页面, 里面给一个电池健康度, 最大续航的曲线, 估计方法
// 你可以在网上找一下」): 估算口径照 TeslaMate Battery Health 仪表盘移植 ——
// 满电续航 = 额定续航 ÷ 可用电量 × 100, 只采充电结尾 100% 的过程 (同日用户
// 点名「满电续航你只能采集充电结尾是100%的样」: 部分充电外推有偏), 电池容量
// = 满电续航 × 充电定标系数 (与行程电耗同源), 健康度 = 当前 ÷ 峰值。
// 与充电统计 (view/stats-page.js) 同构: 统计卡行 + 图表底座/查询参数复用那边
// 的全局 (单壳跨视图共享), 数据位与错误盒是 bh- 前缀自家一份。
/* global $, esc, getJSON, num, loadEcharts, registerView, bindGestures,
          statsParams, statsResize, mkChart, chartText, tooltipStyle */
/* exported bhHasEcharts, bhEnsureEcharts, bhData, bhRenderCards,
            bhRenderCurve, bhLoad, bhRefetch, bhBoot */
"use strict";

/* echarts 注入器与充电/行程统计共用同一个 loadEcharts, 成功旗号各自记账 */
let bhHasEcharts = false;

async function bhEnsureEcharts() {
  if (bhHasEcharts) return;
  try {
    await loadEcharts();
    bhHasEcharts = true;
  } catch (_e) { /* 留给 bhLoad 收尾亮灯 */ }
}

/* ============================ 统计卡片 ============================ */
let bhData = null;

function bhRenderCards(h) {
  const eff100 = h.efficiency_kwh_per_km != null
    ? num(h.efficiency_kwh_per_km * 100, 1) : null;
  /* 峰值两张卡 2026-09-27 用户点名退役 (曲线里的峰值虚线留着), 页名/
     卡名同日从「电池健康度」改口「电池健康」 */
  const cards = [
    { lb: "电池健康", val: h.health_pct == null ? "—" : String(h.health_pct),
      unit: "%", sub: h.health_pct == null ? "" :
        `较峰值衰减 ${num(100 - h.health_pct, 1)}%` },
    { lb: "满电续航", val: h.current_range_km == null ? "—" : num(h.current_range_km, 0),
      unit: "km", sub: "最近 100 个满充采样均值" },
    { lb: "电池容量", val: h.current_capacity_kwh == null ? "—" : num(h.current_capacity_kwh, 1),
      unit: "kWh", sub: "满电续航 × 定标系数" },
    { lb: "充电定标", val: eff100 == null ? "—" : eff100, unit: "kWh/100km",
      sub: "额定续航 → 桩端电量" },
  ];
  $("#bh-row").innerHTML = cards.map(c => `
    <div class="stat">
      <div class="lb">${esc(c.lb)}</div>
      <div class="val">${c.val}${c.unit ? `<small>${c.unit}</small>` : ""}</div>
      ${c.sub ? `<div class="sub">${esc(c.sub)}</div>` : ""}
    </div>`).join("");
}

/* ============================ 满电续航曲线 ============================ */
function bhRenderCurve(h) {
  const sub = $("#bh-curve-sub");
  if (!h.series.length) {
    sub.textContent = "暂无充电采样";
    if (bhHasEcharts) mkChart("bhCurve").clear();
    return;
  }
  const first = h.series[0].day.replace(/-/g, "/"),
        last = h.series[h.series.length - 1].day.replace(/-/g, "/");
  sub.textContent = `${h.sample_days} 个满充日 · ${first} – ${last}`;
  if (!bhHasEcharts) return;
  mkChart("bhCurve").setOption({
    grid: { left: 6, right: 14, top: 30, bottom: 0, containLabel: true },
    tooltip: Object.assign({ trigger: "axis" }, tooltipStyle, {
      valueFormatter: v => num(v, 1) + " km",
    }),
    xAxis: {
      type: "time",
      axisLabel: { color: chartText.axis, fontSize: 10, hideOverlap: true },
      axisLine: { lineStyle: { color: "rgba(255,255,255,.14)" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value", scale: true,
      axisLabel: { color: chartText.axis, fontSize: 10, formatter: "{value} km" },
      splitLine: { lineStyle: { color: "rgba(255,255,255,.07)" } },
    },
    series: [{
      type: "line", smooth: true, showSymbol: false,
      data: h.series.map(p => [p.day, p.range_km]),
      lineStyle: { color: "#3987e5", width: 2 },
      itemStyle: { color: "#3987e5" },
      areaStyle: { color: "rgba(57,135,229,.16)" },
      markLine: {
        symbol: "none", silent: true,
        lineStyle: { color: "rgba(255,255,255,.25)", type: "dashed" },
        label: { formatter: `峰值 ${num(h.max_range_km, 0)} km`,
                 color: chartText.ink, fontSize: 10, position: "insideEndTop" },
        data: [{ yAxis: h.max_range_km }],
      },
    }],
  }, { notMerge: true });
}

/* ============================ 加载与生命周期 ============================ */
async function bhLoad() {
  $("#bh-grid").classList.add("dim");
  $("#bh-loader").hidden = false;
  $("#bh-errbox").hidden = true;
  let err = null;
  try {
    bhData = await getJSON("/tesla/charging/api/battery?" + statsParams());
    bhRenderCards(bhData);
    bhRenderCurve(bhData);
  } catch (e) {
    err = e.message;
  }
  $("#bh-loader").hidden = true;
  $("#bh-grid").classList.remove("dim");
  if (err) {
    $("#bh-errmsg").textContent = "数据加载失败: " + err;
    $("#bh-errbox").hidden = false;
  } else if (!bhHasEcharts) {
    $("#bh-errmsg").textContent = "图表库加载失败";   // 卡片有数, 图表空 —— 如实亮灯
    $("#bh-errbox").hidden = false;
  }
}

async function bhRefetch() { await bhLoad(); }

let bhBooted = false;
async function bhBoot() {               // 首次进视图: 注入 echarts 再拉数据
  bhBooted = true;
  await bhEnsureEcharts();
  await bhLoad();
}

/* 手势: 列表滚动器在顶下拉刷新 (与充电统计同款) */
const bhScroll = $("#bh-scroll");
bindGestures(bhScroll, { drawer: true, ptr: true, onRefresh: bhRefetch });

$("#bh-retry").addEventListener("click", async () => {
  $("#bh-errbox").hidden = true;
  await bhEnsureEcharts();              // 图表库失败过的连注入一起重试
  await bhLoad();
});

registerView("battery", {
  title: "电池健康",
  el: $("#view-battery"),
  async show() {
    if (!bhBooted) { bhBoot(); return; }
    statsResize();                      // 藏起期间网格可能变过列数, 回来先重排
  },
  refresh: bhRefetch,
});
