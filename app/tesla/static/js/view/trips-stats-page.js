// view/trips-stats-page.js — 行程统计视图 (壳版 1/2, 2026-09-27 新增, 用户点名
// 「加一个行程统计页面, 参考充电统计」): 视图底座 —— 统计卡片行 + 数据加载
// (汇总/月度/地点/司机/维度五路并发) + registerView 生命周期 (echarts 进视图
// 才按需注入, 注入失败亮错误盒) + 下拉刷新。与充电统计 (view/stats-page.js)
// 同构: 千分位/查询参数等格式化件复用那边的全局 (单壳跨视图共享), 数据位与
// 错误盒是 ts- 前缀自家一份。
/* global $, esc, getJSON, num, parseLocal, loadEcharts,
          registerView, bindGestures, thousands, statsParams, statsResize,
          tsRenderMonthly, tsRenderLocations, tsRenderDrivers, tsRenderHour,
          tsRenderDist, tsRenderDur, tsRenderSpd, tsRenderWh */
/* exported tsHasEcharts, tsEnsureEcharts, tSummaryData, tMonthlyData,
            tLocData, tDrvData, tDimsData, tsRenderSummary, loadTAll, tsRefetch */
"use strict";

/* echarts 注入器与充电统计共用同一个 loadEcharts (壳里只注入一次), 成功
   旗号各自记账 —— 两视图独立进页、独立亮错误盒 */
let tsHasEcharts = false;

async function tsEnsureEcharts() {
  if (tsHasEcharts) return;
  try {
    await loadEcharts();
    tsHasEcharts = true;
  } catch (_e) { /* 留给 loadTAll 收尾亮灯 */ }
}

/* ============================ 统计卡片 ============================ */
let tSummaryData = null;   // 平均电耗图要算"未定标"次数 (总次数 - 进档次数)
let tMonthlyData = [], tLocData = [], tDrvData = [], tDimsData = null;   // 图表数据 (渲染器共用)

function tsRenderSummary(s) {
  tSummaryData = s;
  const months = s.first_date && s.last_date ?
    (parseLocal(s.last_date + " 00:00").getFullYear() * 12 + parseLocal(s.last_date + " 00:00").getMonth()) -
    (parseLocal(s.first_date + " 00:00").getFullYear() * 12 + parseLocal(s.first_date + " 00:00").getMonth()) + 1 : 1;
  const avgKm = s.trips ? Math.round(s.km / s.trips) : 0;
  const avgSpd = s.duration_min ? Math.round(s.km / (s.duration_min / 60)) : null;
  const cards = [
    { lb: "行程次数", val: thousands(s.trips), sub: months > 1 ? `月均 ${Math.round(s.trips / months)} 次` : "" },
    { lb: "总里程", val: thousands(s.km), unit: "km", sub: s.trips ? `平均每次 ${avgKm} km` : "" },
    { lb: "行驶时长", val: num(s.duration_min / 60, 1), unit: "小时", sub: s.first_date ? `${s.first_date.replace(/-/g, "/")} 起` : "" },
    { lb: "总电耗", val: s.kwh == null ? "—" : num(s.kwh, 1), unit: "kWh", sub: "按额定续航差估算" },
    { lb: "平均电耗", val: s.wh_per_km == null ? "—" : String(s.wh_per_km), unit: "Wh/km",
      sub: s.wh_per_km == null ? "车辆未定标" : "" },
    { lb: "最快车速", val: s.speed_max == null ? "—" : String(s.speed_max), unit: "km/h",
      sub: avgSpd != null ? `平均 ${avgSpd} km/h` : "" },
  ];
  $("#ts-row").innerHTML = cards.map(c => `
    <div class="stat">
      <div class="lb">${esc(c.lb)}</div>
      <div class="val">${c.val}${c.unit ? `<small>${c.unit}</small>` : ""}</div>
      ${c.sub ? `<div class="sub">${esc(c.sub)}</div>` : ""}
    </div>`).join("");
}

/* ============================ 加载与生命周期 ============================ */
async function loadTAll() {
  $("#ts-grid").classList.add("dim");
  $("#ts-loader").hidden = false;
  $("#ts-errbox").hidden = true;
  let err = null;
  try {
    const [summary, monthly, locations, drivers, dims] = await Promise.all([
      getJSON("/tesla/trips/api/stats/summary?" + statsParams()),
      getJSON("/tesla/trips/api/stats/monthly?" + statsParams()),
      getJSON("/tesla/trips/api/stats/locations?" + statsParams()),
      getJSON("/tesla/trips/api/stats/drivers?" + statsParams()),
      getJSON("/tesla/trips/api/stats/dimensions?" + statsParams()),
    ]);
    tsRenderSummary(summary);
    tMonthlyData = monthly; tLocData = locations; tDrvData = drivers;
    tDimsData = dims;
    tsRenderMonthly(); tsRenderLocations(); tsRenderDrivers();
    tsRenderHour(); tsRenderDist(); tsRenderDur(); tsRenderSpd(); tsRenderWh();
  } catch (e) {
    err = e.message;
  }
  $("#ts-loader").hidden = true;
  $("#ts-grid").classList.remove("dim");
  if (err) {
    $("#ts-errmsg").textContent = "数据加载失败: " + err;
    $("#ts-errbox").hidden = false;
  } else if (!tsHasEcharts) {
    $("#ts-errmsg").textContent = "图表库加载失败";   // 图表全空, 如实亮灯等重试
    $("#ts-errbox").hidden = false;
  }
}

async function tsRefetch() { await loadTAll(); }

let tsBooted = false;
async function tsBoot() {               // 首次进视图: 注入 echarts 再拉数据
  tsBooted = true;
  await tsEnsureEcharts();
  await loadTAll();
}

/* 手势: 列表滚动器在顶下拉刷新 (与充电统计同款) */
const tsScroll = $("#ts-scroll");
bindGestures(tsScroll, { drawer: true, ptr: true, onRefresh: tsRefetch });

$("#ts-retry").addEventListener("click", async () => {
  $("#ts-errbox").hidden = true;
  await tsEnsureEcharts();              // 图表库失败过的连注入一起重试
  await loadTAll();
});

registerView("tripstats", {
  title: "行程统计",
  el: $("#view-tripstats"),
  async show() {
    if (!tsBooted) { tsBoot(); return; }
    statsResize();                      // 藏起期间网格可能变过列数, 回来先重排
  },
  refresh: tsRefetch,
});
