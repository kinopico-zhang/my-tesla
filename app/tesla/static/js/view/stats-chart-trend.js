// view/stats-chart-trend.js — 充电统计视图 (壳版 2/3): 图表底座 (echarts 实例
// 注册表/tooltip 样式) + 月度趋势 (充电量/充电费用两幅柱状, 共享一个 12 个月
// 时间窗滑块 —— 轨道是全部历史, 拖圆钮把窗口平移到任意 12 个月) + 常去充电点
// (竖排柱状, 前 7 + 其他) 与窗口变化重绘。
// 2026-09-27 用户点名「都不需要表格视图」: 表格/图表切换整链退役, echarts 注入
// 失败改由 stats-page 的错误盒亮灯 (不再有落表格兜底)。
// 2026-09-28 常去充电点横向条形改竖排柱状 (用户点名「统计的柱状图竖着放吧,
// 下面的文字竖着排列」), 名字竖排铺柱底 (stackLabel 每字一行, 两统计视图共用)。
// 同日行程统计视图入壳: 图表实例注册表 (CHART_ELS/mkChart/statsResize) 是
// 两统计视图共用的底座 —— 行程的 8 张图也登记在这里 (ts- 键), ResizeObserver
// 一份管全部; 窗口滑块状态各自独立 (行程那份在 trips-stats-charts.js)。
// v9 (2026-09-27): 司机里程分布图补登注册表 —— tsDrv 键漏了, mkChart 拿到
// undefined 选择器, echarts 在 null 上炸成一串「null is not an object」,
// 行程统计整页报数据加载失败 (对账钉在 test_tripstats_view)。
/* global $, esc, num, money, moneyInt, thousands, hasEcharts, monthlyData, locData */
/* exported chartText, tooltipStyle, mkChart, renderMonthly, renderLocations,
            statsResize, stackLabel */
"use strict";
/* ============================ 图表 ============================ */
const chartText = { axis: "#898781", ink: "#c3c2b7" };
const tooltipStyle = {
  backgroundColor: "rgba(28,28,30,.95)", borderWidth: 0, padding: [7, 10],
  textStyle: { color: "#f5f5f7", fontSize: 12 },
};
const CHART_ELS = { monthlyKw: "#chart-monthly-kwh", monthlyCost: "#chart-monthly-cost",
                    loc: "#chart-loc", hour: "#chart-hour",
                    soc: "#chart-socdist", power: "#chart-powerdist",
                    price: "#chart-price", dur: "#chart-dur", city: "#chart-city",
                    tsKm: "#chart-ts-km", tsKwh: "#chart-ts-kwh", tsLoc: "#chart-ts-loc",
                    tsDrv: "#chart-ts-drv", tsHour: "#chart-ts-hour",
                    tsDist: "#chart-ts-dist", tsDur: "#chart-ts-dur",
                    tsSpd: "#chart-ts-spd", tsWh: "#chart-ts-wh",
                    bhCurve: "#chart-bh-curve" };
const charts = {};   // 名字 → echarts 实例 (ResizeObserver 统一 resize)

function shortMonth(ym) { return ym.slice(2).replace("-", "/"); }
function truncateName(s, n) { return s.length > n ? s.slice(0, n) + "…" : s; }
/* 名字类轴标竖排 (2026-09-28 用户点名「下面的文字竖着排列」): 每字一行,
   中文直立着读, 比侧躺 90° 自然; 与 truncateName 组合用 */
function stackLabel(s) { return s.split("").join("\n"); }
function mkChart(name) {
  if (!charts[name]) charts[name] = echarts.init($(CHART_ELS[name]));
  return charts[name];
}

/* ---------- 月度趋势: 充电量/费用两幅柱状, 共享 12 个月时间窗 ---------- */
const MONTH_WINDOW = 12;    // 窗口宽 (月); 历史不足一年时整段全显、滑块藏起
let monthStart = 0;         // 当前窗口首月在 monthlyData 里的下标

function renderMonthly() {
  const n = monthlyData.length;
  const row = $("#monthly-slider-row");
  if (!n) {
    $("#monthly-sub").textContent = "暂无数据";
    $("#mkwh-total").textContent = "–";
    $("#mcost-total").textContent = "–";
    row.hidden = true;
    return;
  }
  monthStart = Math.max(0, n - MONTH_WINDOW);   // 默认落在最近 12 个月
  row.hidden = n <= MONTH_WINDOW;               // 一年都没满: 没得滑
  if (!row.hidden) {
    const slider = $("#monthly-window");
    slider.max = String(n - MONTH_WINDOW);
    slider.value = String(monthStart);
    slider.style.setProperty("--win", (MONTH_WINDOW / n * 100) + "%");
    $("#win-first").textContent = shortMonth(monthlyData[0].month);
    $("#win-last").textContent = shortMonth(monthlyData[n - 1].month);
  }
  drawMonthlyWindow();
}

/* 滑块平移窗口: 两幅柱状 + 副题/窗口合计一起跟着走 */
function drawMonthlyWindow() {
  const win = monthlyData.slice(monthStart, monthStart + MONTH_WINDOW);
  const months = win.map(d => d.month);
  const kw = win.map(d => Math.round((d.energy_used || 0) * 10) / 10);
  const cost = win.map(d => d.cost == null ? 0 : d.cost);
  $("#monthly-sub").textContent =
    shortMonth(months[0]) + " – " + shortMonth(months[months.length - 1]);
  $("#mkwh-total").textContent = thousands(kw.reduce((a, b) => a + b, 0)) + " kWh";
  $("#mcost-total").textContent = moneyInt(cost.reduce((a, b) => a + b, 0));
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
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: ps => { const d = win[ps[0].dataIndex];
        return `<b>${ps[0].name}</b><br/>充电量 ${num(d.energy_used)} kWh<br/>${d.sessions} 次`; } },
    xAxis: { ...xBase, axisLabel: { show: false } },   // 月份只在下面那幅标 (两图同轴联动)
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", name: "充电量", data: kw, barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] } }],
  });
  charts.monthlyCost.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 10, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: ps => { const d = win[ps[0].dataIndex];
        return `<b>${ps[0].name}</b><br/>费用 ${money(d.cost)}<br/>${d.sessions} 次`; } },
    xAxis: { ...xBase, axisLabel: { color: chartText.axis, fontSize: 10, interval: 0,
              // 月份轴防重叠 (2026-09-27 用户点名「日期重叠了」): 首格和每个
              // 一月带年份 "26/01", 其余只标月份数 —— 12 连月必含一个一月,
              // 年份上下文总在, 12 个标签在手机宽度也排得下
              formatter: (v, i) => i === 0 || v.endsWith("-01")
                ? shortMonth(v) : v.slice(5) } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10,
                          formatter: v => v >= 1000 ? (v / 1000) + "k" : v } },
    series: [{ type: "bar", name: "充电费用", data: cost, barMaxWidth: 16,
               itemStyle: { color: "#c98500", borderRadius: [4, 4, 0, 0] } }],
  });
}

/* ---------- 时间窗滑块: 宽钮 = 窗口本体 ---------- */
/* 钮宽定为 12/N 轨道宽时, 原生 range 的线性映射恰好让钮身 [左缘, 右缘]
   对准 [窗口首月, 末月] —— 滑块看起来就是那 12 个月本身 (轨道 = 全部
   历史)。原生拖拽会把钮心吸到手指 (宽钮 = 半个窗口的跳变), 指针改自己
   管: 按在窗口里抓住带着走 (抓点偏移全程保持), 点在窗口外先整窗跳过去;
   键盘方向键照走原生 input 事件。 */
const mSlider = $("#monthly-window");

function sliderGeom() {                 // 轨道左缘/宽、钮宽、可走步数
  const r = mSlider.getBoundingClientRect();
  const n = monthlyData.length;
  return { left: r.left, w: r.width, thumb: r.width * MONTH_WINDOW / n,
           span: n - MONTH_WINDOW };
}
function thumbCenterX() {               // 钮心横坐标 (页面坐标)
  const g = sliderGeom();
  return g.left + g.thumb / 2 + monthStart / g.span * (g.w - g.thumb);
}
function valueFromCenter(cx) {          // 想让钮心落在 cx (页面坐标) → 窗口首月下标
  const g = sliderGeom();
  const rel = (cx - g.left - g.thumb / 2) / (g.w - g.thumb);
  return Math.round(Math.min(1, Math.max(0, rel)) * g.span);
}

mSlider.addEventListener("pointerdown", e => {
  if (!e.isPrimary || e.button !== 0) return;
  e.preventDefault();                     // 原生拖拽 (钮心吸手指) 不要
  mSlider.focus();
  const cx = thumbCenterX();
  const g = sliderGeom();
  const inside = Math.abs(e.clientX - cx) <= g.thumb / 2 + 4;   // 抓在窗口内 (±4px 容差)
  const off = inside ? e.clientX - cx : 0;    // 窗外点下: 窗口先跳到指下再跟手
  const pid = e.pointerId;
  const move = ev => {
    if (ev.pointerId !== pid) return;
    const v = valueFromCenter(ev.clientX - off);
    if (v !== monthStart) {
      monthStart = v; mSlider.value = String(v);
      drawMonthlyWindow();
    }
  };
  if (!inside) move(e);
  // move/up 挂 window 级不捕获 (弹层拖拽同款: iOS Safari 对 touch 指针
  // capture 会当场 pointercancel, 手指出界 window 级照样收)
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", up);
});
mSlider.addEventListener("touchstart", e => e.preventDefault(), { passive: false });
mSlider.addEventListener("input", e => {     // 键盘方向键走原生
  monthStart = Number(e.target.value);
  drawMonthlyWindow();
});

/* ---------- 常去充电点: 竖排柱状 (前 7 + 其他) ----------
   2026-09-28 用户点名「统计的柱状图竖着放吧，下面的文字竖着排列」: 横向
   条形退役, 柱子竖起来 (次数降序从左到右), 充电点名竖排 (每字一行) 铺在
   柱子底下; 气泡按下标取行 (旧版按名字 find, 截断过的名字对不上会炸) */
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
  if (!hasEcharts) return;
  mkChart("loc").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 16, top: 16, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: (ps) => {
        const d = rows[ps[0].dataIndex];
        return `<b>${esc(d.location)}</b><br/>次数 ${d.sessions} · 快充 ${d.fast_sessions}` +
               `<br/>电量 ${num(d.energy_used)} kWh<br/>费用 ${money(d.cost)}`;
      } },
    xAxis: { type: "category", interval: 0,
             data: rows.map(d => stackLabel(truncateName(d.location, 7))),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.ink, fontSize: 10.5, lineHeight: 12 } },
    yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: rows.map(d => d.sessions), barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] },
               label: { show: true, position: "top", color: chartText.ink,
                        fontSize: 10.5, formatter: "{c} 次" } }],
  });
}

/* 窗口尺寸变化: 图表重绘 (网格 1↔2 列切换时宽度变了); 藏起期间网格变过
   列数, show() 里也调 statsResize 补一次 */
function statsResize() {
  Object.values(charts).forEach(c => c && c.resize());
}
let resizeTimer;
new ResizeObserver(() => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(statsResize, 120);
}).observe(document.body);
