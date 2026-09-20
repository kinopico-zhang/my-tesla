// view/stats-page.js — 充电统计视图 (壳版 1/3): 视图底座 —— 金额千分位 +
// 统计卡片行 + 查询参数 (时间档来自全局抽屉, 车辆来自 shellState.carId) +
// 数据加载 (汇总/月度/地点/维度四路并发) + registerView 生命周期 (echarts
// 进视图才按需注入, 注入失败整页落表格视图)。
// 旧版 (js/stats-page.js / stats-time-filters.js) 的 $/esc/getJSON/格式化/
// TIME_RANGES/日历/syncURL/顶栏刷新/登出全部上移壳模块或删除; 时间筛选
// 档位改由抽屉里的 tesla-time-range 全局驱动 (换档 → refreshCurrent)。
/* global $, esc, getJSON, num, parseLocal, loadEcharts,
          timeRangeParams, shellState, registerView, bindGestures,
          renderMonthly, renderLocations, renderFastSlow, renderHour,
          renderSoc, renderPower, renderCity, statsResize, forceTableMode */
/* exported moneyInt, thousands, statsParams, summaryData, renderSummary,
            hasEcharts, monthlyData, locData, dimsData, loadAll, statsRefetch */
"use strict";

const moneyInt = v => v == null ? "—" : "¥" + Math.round(v).toLocaleString("zh-CN");
const thousands = v => Math.round(v).toLocaleString("zh-CN");

/* echarts 按需注入后置真; 注入失败 (网络) 整页落表格视图, 不留白框 */
let hasEcharts = false;

/* 时间档 (抽屉) + 车辆 (抽屉) → 四路统计接口的公共查询参数 */
function statsParams() {
  const p = new URLSearchParams(timeRangeParams());
  if (shellState.carId != null) p.set("car_id", String(shellState.carId));
  return p.toString();
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

/* ============================ 加载与生命周期 ============================ */
let monthlyData = [], locData = [], dimsData = null;   // 图表数据 (渲染器共用)

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

async function statsRefetch() { await loadAll(); }

let statsBooted = false;
async function statsBoot() {          // 首次进视图: 注入 echarts 再拉数据
  statsBooted = true;
  try {
    await loadEcharts();
    hasEcharts = true;
  } catch (_e) {
    forceTableMode();                 // 图表库拉不到: 全部卡片直接落表格
  }
  await loadAll();
}

/* 手势: 列表滚动器右划开抽屉 / 在顶下拉刷新 (与充电视图同款) */
const statsScroll = $("#stats-scroll");
bindGestures(statsScroll, { drawer: true, ptr: true, onRefresh: statsRefetch });

$("#retry").addEventListener("click", () => { $("#errbox").hidden = true; loadAll(); });

registerView("stats", {
  title: "充电统计",
  el: $("#view-stats"),
  async show() {
    if (!statsBooted) { statsBoot(); return; }
    statsResize();                    // 藏起期间网格可能变过列数, 回来先重排
  },
  refresh: statsRefetch,
});
