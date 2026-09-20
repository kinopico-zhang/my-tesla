// view/charging-detail.js — 充电记录视图 (壳版 4/6): 详情底部弹层 —— 开合/
// 下滑关闭/Escape 分层关闭 + 详情渲染 (统计格/SOC 曲线/充电曲线三档切换)。
// 壳版差异: 元素 id 与导出名加 chg- 前缀 (壳里多视图并存, #sheet/#backdrop
// 留给行程页, closeSheet 在充电地图/足迹地图也各有一份); chartText/tooltipStyle
// 同理 (充电统计页也有一份); echarts 按需注入 (loadEcharts, 壳不默认拖图表库)。
/* global $, esc, num, money, fmtCardDate, fmtDur, fmtMinAxis, getJSON,
          detailCache, loadEcharts, chgCloseNavChooser, chgCloseAlert */
/* exported chgOpenSheet, chgSheetBody, chgAlertBd, chgAlInput, chgNavBd,
            chgSheetOpen, chgCurrentDetailId, chgChartText, chgTooltipStyle */
"use strict";
/* ============================ 详情图表样式 (统计图表卡在充电统计页) ============================ */
const chgChartText = { axis: "#898781", ink: "#c3c2b7" };
const chgTooltipStyle = {
  backgroundColor: "rgba(28,28,30,.95)", borderWidth: 0, padding: [7, 10],
  textStyle: { color: "#f5f5f7", fontSize: 12 },
};

/* ============================ 详情 Sheet ============================ */
const chgSheet = $("#chg-sheet"), chgBackdrop = $("#chg-backdrop"), chgSheetBody = $("#chg-sheet-body");
const chgAlertBd = $("#chg-alert-bd"), chgAlInput = $("#chg-al-input"), chgNavBd = $("#chg-nav-bd");
let chSoc, chPw, pwMode = "kw", chgSheetOpen = false, chgCurrentDetailId = null;
const PW_SERIES = {
  kw:       { name: "功率", color: "#3987e5", unit: "kW", key: "kw" },
  voltage:  { name: "电压", color: "#9085e9", unit: "V",  key: "voltage" },
  current:  { name: "电流", color: "#d95926", unit: "A",  key: "current" },
};

function chgOpenSheet(id) {
  chgSheetOpen = true;
  chgSheet.classList.add("on"); chgBackdrop.classList.add("on");
  chgSheetBody.innerHTML = `<div class="spin"></div>`;
  loadDetail(id);
}
function chgCloseSheet() {
  chgSheetOpen = false; chgCurrentDetailId = null;
  chgSheet.classList.remove("on"); chgBackdrop.classList.remove("on");
  [chSoc, chPw].forEach(c => { c && c.dispose(); }); chSoc = chPw = null;
}
chgBackdrop.addEventListener("click", chgCloseSheet);
$("#chg-sheet-close").addEventListener("click", chgCloseSheet);
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if (!chgNavBd.hidden) chgCloseNavChooser();
  else if (!chgAlertBd.hidden) chgCloseAlert();
  else if (chgSheetOpen) chgCloseSheet();
});

/* 下滑关闭 (pointer: 触摸/鼠标/笔统一, 拖着跟手, 松手回弹)。
   不用 setPointerCapture: iOS Safari 对 touch 指针 capture 会当场
   pointercancel (手指一动事件就被系统收走, 2026-09-13 用户实测拉不动),
   move/up 挂 window 级 —— 不捕获手指出界照样收, 各端行为一致。 */
(() => {
  const zone = $("#chg-grab-zone");
  let y0 = null, dy = 0;
  const move = e => {
    dy = Math.max(0, e.clientY - y0);      // 只往下拖有效, 往上顶不抬层
    chgSheet.style.transition = "none";
    chgSheet.style.transform = `translateY(${dy}px)`;
  };
  const release = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", release);
    window.removeEventListener("pointercancel", release);
    if (y0 == null) return;
    chgSheet.style.transition = ""; chgSheet.style.transform = "";
    if (dy > 90) chgCloseSheet();          // 拉过 90px = 明确想关; 否则弹回
    y0 = null;
  };
  zone.addEventListener("pointerdown", e => {
    y0 = e.clientY; dy = 0;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
  });
  // 点一下也关 (trips 手柄同款): 拖过 8px 不算点击, 否则回弹动画结束瞬间
  // 跟着来的 click 会把刚弹回的弹层又关掉
  zone.addEventListener("click", () => {
    if (dy > 8) { dy = 0; return; }
    chgCloseSheet();
  });
})();

async function loadDetail(id) {
  let d;
  try {
    d = detailCache.get(id) || await getJSON(`/tesla/charging/api/sessions/${id}`);
    detailCache.set(id, d);
  } catch (e) {
    chgSheetBody.innerHTML = `<div class="err-box"><p>加载失败: ${esc(e.message)}</p></div>`;
    return;
  }
  if (!chgSheetOpen) return;
  chgCurrentDetailId = id;
  const rangeGain = d.end_rated_range != null && d.start_rated_range != null
    ? d.end_rated_range - d.start_rated_range : null;
  $("#chg-sh-date").textContent = fmtCardDate(d.start);
  $("#chg-sh-loc").textContent = d.city ? `${d.location} · ${d.city}` : d.location;
  $("#chg-sh-row").innerHTML = `
    <span class="tag ${d.is_fast ? "tag-fast" : "tag-slow"}">${d.is_fast ? "⚡ 快充" : "🔌 慢充"}</span>
    ${d.cable ? `<span class="tag tag-slow" style="color:var(--ink-2);background:var(--surface-2)">${esc(d.cable)}</span>` : ""}
    ${d.charger_type ? `<span class="tag tag-slow" style="color:var(--ink-2);background:var(--surface-2)">${esc(d.charger_type)}</span>` : ""}`;
  chgSheetBody.innerHTML = `
    ${d.lat != null && d.lng != null
      ? `<button class="nav-go" id="nav-go">🧭 导航到充电站</button>` : ""}
    <div class="st-grid">
      <div class="st"><div class="lb">充入电量</div><div class="val">${num(d.energy_added)}<small> kWh</small></div></div>
      <div class="st"><div class="lb">表计电量</div><div class="val">${num(d.energy_used)}<small> kWh</small></div></div>
      <div class="st st-cost" id="st-cost-tile"><div class="lb">费用</div><div class="val${d.cost == null ? " red" : ""}" id="st-cost-val">${d.cost != null ? money(d.cost) : "未记费用"}</div></div>
      <div class="st"><div class="lb">电价</div><div class="val" id="st-price-val">${d.price_per_kwh != null ? "¥" + d.price_per_kwh.toFixed(3) + "<small>/kWh</small>" : "—"}</div></div>
      <div class="st"><div class="lb">时长</div><div class="val">${fmtDur(d.duration_min)}</div></div>
      <div class="st"><div class="lb">电量变化</div><div class="val">${d.start_soc}<small>%</small> → ${d.end_soc}<small>%</small></div></div>
      <div class="st"><div class="lb">峰值功率</div><div class="val">${d.power_max ?? "—"}<small> kW</small></div></div>
      <div class="st"><div class="lb">续航增加</div><div class="val">${rangeGain != null ? "+" + num(rangeGain, 0) : "—"}<small> km</small></div></div>
    </div>
    <div class="sh-chart-title">电量 %</div>
    <div id="chart-soc"></div>
    <div class="sh-chart-title">
      <span>充电曲线</span>
      <div class="mini-seg" id="pw-seg">
        <button data-v="kw" class="on">功率</button>
        <button data-v="voltage">电压</button>
        <button data-v="current">电流</button>
      </div>
    </div>
    <div id="chart-pw"></div>
    <div class="sh-addr">${esc(d.address || "")}${d.outside_temp != null ? ` · 平均气温 ${num(d.outside_temp, 0)}°C` : ""}</div>`;

  $("#pw-seg").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    $("#pw-seg .on").classList.remove("on"); b.classList.add("on");
    pwMode = b.dataset.v; renderPwChart(d);
  });

  requestAnimationFrame(async () => {
    let ec;
    try { ec = await loadEcharts(); }             // 按需注入; 弹层已关就不画了
    catch (_e) { return; }
    if (!chgSheetOpen) return;
    chSoc = ec.init($("#chart-soc"));
    chPw = ec.init($("#chart-pw"));
    ec.connect([chSoc, chPw]);
    const cv = d.curve, xBase = {
      type: "value", min: 0,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: chgChartText.axis, fontSize: 10, formatter: fmtMinAxis },
      splitLine: { lineStyle: { color: "#2c2c2a" } },
    };
    chSoc.setOption({
      animationDuration: 250,
      grid: { left: 6, right: 8, top: 10, bottom: 0, containLabel: true },
      tooltip: { ...chgTooltipStyle, trigger: "axis",
                 axisPointer: { type: "cross", lineStyle: { color: "#898781" },
                                crossStyle: { color: "#5a5a5e" } },
                 formatter: ps => `${fmtMinAxis(ps[0].axisValue)} · 电量 <b>${ps[0].value}%</b>` },
      xAxis: xBase,
      yAxis: { type: "value", min: 0, max: 100,
               splitLine: { lineStyle: { color: "#2c2c2a" } },
               axisLabel: { color: chgChartText.axis, fontSize: 10, formatter: "{value}%" } },
      series: [{ type: "line", data: cv.minutes.map((t, i) => [t, cv.soc[i]]),
                 showSymbol: false, sampling: "lttb",
                 lineStyle: { color: "#1fa349", width: 2 },
                 itemStyle: { color: "#1fa349" },
                 areaStyle: { color: "rgba(31,163,73,.10)" } }],
    });
    renderPwChart(d);
  });
}

function renderPwChart(d) {
  if (!chPw) return;
  const s = PW_SERIES[pwMode], cv = d.curve, vals = cv[s.key];
  const yMax = Math.max(...vals, 1);
  chPw.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 10, bottom: 0, containLabel: true },
    tooltip: { ...chgTooltipStyle, trigger: "axis",
               axisPointer: { type: "cross", lineStyle: { color: "#898781" },
                              crossStyle: { color: "#5a5a5e" } },
               formatter: ps => {
                 const i = ps[0].dataIndex;
                 return `${fmtMinAxis(ps[0].axisValue)} · ${s.name} <b>${ps[0].value} ${s.unit}</b>` +
                        (cv.energy[i] != null ? `<br/>累计 ${num(cv.energy[i])} kWh` : "");
               } },
    xAxis: { type: "value", min: 0,
             axisLine: { show: false }, axisTick: { show: false },
             axisLabel: { color: chgChartText.axis, fontSize: 10, formatter: fmtMinAxis },
             splitLine: { lineStyle: { color: "#2c2c2a" } } },
    yAxis: { type: "value", min: 0, max: Math.ceil(yMax * 1.08),
             splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chgChartText.axis, fontSize: 10 } },
    series: [{ type: "line", data: cv.minutes.map((t, i) => [t, vals[i]]),
               showSymbol: false, sampling: "lttb",
               lineStyle: { color: s.color, width: 2 },
               itemStyle: { color: s.color },
               areaStyle: { color: s.color + "1a" } }],
  }, { replaceMerge: ["series"] });
}
