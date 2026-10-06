// view/trips-stats-charts.js — 行程统计视图 (壳版 2/2, 2026-09-27 新增): 月度
// 趋势 (里程/电耗两幅柱状, 共享 12 个月时间窗滑块 —— 与充电统计同款交互,
// 窗口状态独立一份) + 常去地点 (竖排柱状画最常 12 根, 点柱名开改名弹层)
// + 驾驶员里程分布 (横向条形, 2026-09-30 用户点名「司机里程分布 → 驾驶员
//   里程分布, 并且这个图改成横向的」—— 名字横排不截断, 高度随人数走;
//   归集口径与行程卡片同款 —— 标注 > 默认驾驶员兜底, 2026-09-27 用户
//   点名「行驶统计加一个司机里程分布」) + 出发时段 (12 档柱状)
// + 单程距离/行驶时长两张次数口径分布柱状 + 车速分布 (真速度
//   分布, 纵轴 = 各速度段行驶里程 —— 2026-09-27 用户点名「车速分布, 不是
//   最大车速分布」「纵坐标是 km」; 档值是行车采样逐秒积分的 km 合计,
//   后端 speed_hist_cache 两级缓存) + 速度·电耗 (各速度段平均电耗 = 段
//   电量 ÷ 段里程, 2026-09-30 用户点名「横坐标应该是速度, 纵坐标是平均
//   电耗」; 旧「行程 Wh/km 落档计数」直方整链退役) 落档底座
//   renderDimBins 与充电统计共用。图表实例注册表与底座在 view/stats-
//   chart-trend.js (两统计视图共用), 时间窗滑块的指针自管逻辑与充电
//   那份同构、ts- 一份。
// v5 (2026-09-28): 两张名字条形图横向退役改竖排柱状 (用户点名「统计的
//   柱状图竖着放吧，下面的文字竖着排列」), 地点/司机名竖排铺柱底; 常去
//   地点气泡从按名字 find 改按下标取行 —— 截断过的名字对不上 find 会炸
//   (服务日志 window_error 实锤), 司机图本就按下标。
// v6 (2026-09-30): 常去地点撤「前 7 + 其他」折帽画最常 20 根, 副题说实话
//   (「最常 20 · 共 N 个」; 后端 [:12] 帽一并撤 —— 用户点名「8 个柱子,
//   你跟我说一共 12 个地点?」+「再拉长一点, 显示不全了」, 图加高 340,
//   名字截 10 字); 驾驶员里程分布改横向; 各图轴名补单位 (用户点名「横
//   纵坐标都要标记是什么」—— axNameStyle); 电耗分布重做成速度·电耗。
// v7 (2026-09-30): 常去地点柱位回 12 根 (用户点名「就保留 12 个吧」),
//   柱名挂点击开改名弹层 (trips-place-dialog, 存完重拉); 驾驶员轴名被
//   inverse 翻身带到轴底压横轴, 钉 nameLocation: "start" 翻回顶端。
// v8 (2026-09-30): 柱身也开改名弹层 (用户报「点击柱状图不弹出地点命名
//   窗口」—— 首版只认柱名轴标签)。
// v9 (2026-09-30): 柱身点击收回 (用户点名「点击文字才弹出框, 点击柱状图
//   只显示数据」—— 柱身点按走气泡看数, 只有柱名轴标签开改名弹层)。
// v10 (2026-09-30): 柱名点击补轴级 triggerEvent (用户报「点柱状图下面的地
//   名, 没有弹出重命名页面」—— 只写 axisLabel.triggerEvent 事件挂不上,
//   echarts 源里静默判定与 eventData 都读轴级旗; v7-v9 柱名点击从未通过)。
// v11 (2026-09-30): 常去地点柱顶次数标签退役 (用户点名「不需要在柱状图上
//   面标记次数」—— 看数走气泡)。
/* global $, esc, num, pad, thousands, tsHasEcharts, tMonthlyData,
          tLocData, tDrvData, tDimsData, chartText, loadTAll,
          openPlaceDialog,
          tooltipStyle, mkChart, renderDimBins, shortMonth, truncateName,
          stackLabel */
/* exported TS_MONTH_WINDOW, tsRenderMonthly, tsRenderLocations,
            tsRenderDrivers, tsRenderHour,
            tsRenderDist, tsRenderDur, tsRenderSpd, tsRenderWh */
"use strict";

/* 轴名样式 (2026-09-30 用户点名「横纵坐标都要标记是什么」): 数值轴在
   顶端标量名 (km/kWh/次数/Wh per km), 类目轴在末端标内容名 (地点/驾驶
   员/月份) —— 刻度自己说不清的轴靠它 */
const axNameStyle = { color: chartText.axis, fontSize: 10 };

/* ---------- 月度趋势: 里程/电耗两幅柱状, 共享 12 个月时间窗 ---------- */
const TS_MONTH_WINDOW = 12;   // 窗口宽 (月); 历史不足一年时整段全显、滑块藏起
let tsMonthStart = 0;         // 当前窗口首月在 tMonthlyData 里的下标
let tsMonthlyLinked = false;  // 两幅柱状只 connect 一次

function tsRenderMonthly() {
  const n = tMonthlyData.length;
  const row = $("#ts-slider-row");
  if (!n) {
    $("#ts-monthly-sub").textContent = "暂无数据";
    $("#ts-km-total").textContent = "–";
    $("#ts-kwh-total").textContent = "–";
    row.hidden = true;
    return;
  }
  tsMonthStart = Math.max(0, n - TS_MONTH_WINDOW);   // 默认落在最近 12 个月
  row.hidden = n <= TS_MONTH_WINDOW;                 // 一年都没满: 没得滑
  if (!row.hidden) {
    const slider = $("#ts-window");
    slider.max = String(n - TS_MONTH_WINDOW);
    slider.value = String(tsMonthStart);
    slider.style.setProperty("--win", (TS_MONTH_WINDOW / n * 100) + "%");
    $("#ts-win-first").textContent = shortMonth(tMonthlyData[0].month);
    $("#ts-win-last").textContent = shortMonth(tMonthlyData[n - 1].month);
  }
  tsDrawWindow();
}

/* 滑块平移窗口: 两幅柱状 + 副题/窗口合计一起跟着走 (电耗没定标时合计亮 –) */
function tsDrawWindow() {
  const win = tMonthlyData.slice(tsMonthStart, tsMonthStart + TS_MONTH_WINDOW);
  const months = win.map(d => d.month);
  const km = win.map(d => Math.round(d.km * 10) / 10);
  const kwh = win.map(d => d.kwh == null ? 0 : d.kwh);
  $("#ts-monthly-sub").textContent =
    shortMonth(months[0]) + " – " + shortMonth(months[months.length - 1]);
  $("#ts-km-total").textContent = thousands(Math.round(km.reduce((a, b) => a + b, 0))) + " km";
  $("#ts-kwh-total").textContent = kwh.some(v => v > 0)
    ? num(kwh.reduce((a, b) => a + b, 0), 1) + " kWh" : "–";
  if (!tsHasEcharts) return;
  if (!tsMonthlyLinked) {
    echarts.connect([mkChart("tsKm"), mkChart("tsKwh")]);   // 两图同轴联动
    tsMonthlyLinked = true;
  }
  const xBase = {
    type: "category", data: months,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: "#383835" } },
  };
  mkChart("tsKm").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 8, top: 24, bottom: 2, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: ps => { const d = win[ps[0].dataIndex];
        return `<b>${ps[0].name}</b><br/>里程 ${num(d.km)} km<br/>${d.trips} 次`; } },
    xAxis: { ...xBase, axisLabel: { show: false } },   // 月份只在下面那幅标 (两图同轴联动)
    yAxis: { type: "value", name: "km", nameGap: 6, nameTextStyle: axNameStyle,
             splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10,
                          formatter: v => v >= 1000 ? (v / 1000) + "k" : v } },
    series: [{ type: "bar", name: "月度里程", data: km, barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] } }],
  });
  mkChart("tsKwh").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 40, top: 24, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: ps => { const d = win[ps[0].dataIndex];
        return `<b>${ps[0].name}</b><br/>电耗 ${d.kwh == null ? "—" : num(d.kwh) + " kWh"}` +
               `<br/>${d.trips} 次`; } },
    xAxis: { ...xBase, name: "月份", nameGap: 6, nameTextStyle: axNameStyle,
             axisLabel: { color: chartText.axis, fontSize: 10, interval: 0,
              // 月份轴防重叠 (充电统计同款): 首格和每个一月带年份, 其余只标月份数
              formatter: (v, i) => i === 0 || v.endsWith("-01")
                ? shortMonth(v) : v.slice(5) } },
    yAxis: { type: "value", name: "kWh", nameGap: 6, nameTextStyle: axNameStyle,
             splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10,
                          formatter: v => v >= 1000 ? (v / 1000) + "k" : v } },
    series: [{ type: "bar", name: "月度电耗", data: kwh, barMaxWidth: 16,
               itemStyle: { color: "#c98500", borderRadius: [4, 4, 0, 0] } }],
  });
}

/* ---------- 时间窗滑块: 宽钮 = 窗口本体 (充电统计同款, 独立一份状态) ---------- */
const tsSlider = $("#ts-window");

function tsSliderGeom() {               // 轨道左缘/宽、钮宽、可走步数
  const r = tsSlider.getBoundingClientRect();
  const n = tMonthlyData.length;
  return { left: r.left, w: r.width, thumb: r.width * TS_MONTH_WINDOW / n,
           span: n - TS_MONTH_WINDOW };
}
function tsThumbCenterX() {             // 钮心横坐标 (页面坐标)
  const g = tsSliderGeom();
  return g.left + g.thumb / 2 + tsMonthStart / g.span * (g.w - g.thumb);
}
function tsValueFromCenter(cx) {        // 想让钮心落在 cx (页面坐标) → 窗口首月下标
  const g = tsSliderGeom();
  const rel = (cx - g.left - g.thumb / 2) / (g.w - g.thumb);
  return Math.round(Math.min(1, Math.max(0, rel)) * g.span);
}

tsSlider.addEventListener("pointerdown", e => {
  if (!e.isPrimary || e.button !== 0) return;
  e.preventDefault();                     // 原生拖拽 (钮心吸手指) 不要
  tsSlider.focus();
  const cx = tsThumbCenterX();
  const g = tsSliderGeom();
  const inside = Math.abs(e.clientX - cx) <= g.thumb / 2 + 4;   // 抓在窗口内 (±4px 容差)
  const off = inside ? e.clientX - cx : 0;    // 窗外点下: 窗口先跳到指下再跟手
  const pid = e.pointerId;
  const move = ev => {
    if (ev.pointerId !== pid) return;
    const v = tsValueFromCenter(ev.clientX - off);
    if (v !== tsMonthStart) {
      tsMonthStart = v; tsSlider.value = String(v);
      tsDrawWindow();
    }
  };
  if (!inside) move(e);
  // move/up 挂 window 级不捕获 (iOS Safari 对 touch 指针 capture 会当场
  // pointercancel, 手指出界 window 级照样收)
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", up);
});
tsSlider.addEventListener("touchstart", e => e.preventDefault(), { passive: false });
tsSlider.addEventListener("input", e => {     // 键盘方向键走原生
  tsMonthStart = Number(e.target.value);
  tsDrawWindow();
});

/* ---------- 常去地点: 竖排柱状画最常 12 根, 点柱名弹改名框 ----------
   2026-09-28 横向条形退役 (用户点名「统计的柱状图竖着放吧」); 气泡按下
   标取行 (旧版按名字 find, 截断过的名字对不上会炸)。2026-09-30 用户点名
   「8 个柱子, 你跟我说一共 12 个地点?」+「再拉长一点」: 后端 [:12] 帽撤
   掉全量回 (库里实有 478 个), 副题把总数说全; 同日再点名「就保留 12 个
   吧」+「点击地点名称弹出修改地点名称对话框」—— 柱位回 12 根, 柱名挂
   点击 (triggerEvent) 开 trips-place-dialog 改名, 存完 loadTAll 重拉;
   再点名「点击柱状图只显示数据」—— 柱身不弹框 (v8 曾放开又收回)。
   再点名「只看我停车是在哪, 而不是路过哪」—— 后端改按停车事件计数
   (挪车微程不计, 同一次停车不二计), 气泡口径跟着改口「次停车」。 */
let tLocRows = [];        // 当前画的行 (点柱名要拿回整行喂改名弹层)
let tsLocClickBound = false;

function tsRenderLocations() {
  if (!tLocData.length) return;
  const rows = tLocData.slice(0, 12);   // 2026-09-30 用户点名「保留 12 个」
  tLocRows = rows;
  $("#ts-loc-sub").textContent =
    `最常 ${rows.length} · 共 ${tLocData.length} 个地点 · 点名字改名`;
  if (!tsHasEcharts) return;
  mkChart("tsLoc").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 40, top: 26, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: ps => {
        const d = rows[ps[0].dataIndex];
        return `<b>${esc(d.name)}</b><br/>${d.trips} 次停车 (挪车不计)`;
      } },
    xAxis: { type: "category", interval: 0, name: "地点",
             nameGap: 6, nameTextStyle: axNameStyle,
             triggerEvent: true,   // 轴级旗: 点击才挂 eventData (componentType
             // /dataIndex 都靠它; 只写 axisLabel.triggerEvent 的话标签照样不
             // 响 —— echarts 源里静默与事件挂载都只读轴级, v7-v9 实踩)
             data: rows.map(d => stackLabel(truncateName(d.name, 10))),
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.ink, fontSize: 10.5, lineHeight: 12,
                          triggerEvent: true } },   // 柱名可点 → 改名框
    yAxis: { type: "value", minInterval: 1, name: "次数",
             nameGap: 6, nameTextStyle: axNameStyle,
             splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: rows.map(d => d.trips), barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] } }],
               // 柱顶不标次数 (2026-09-30 用户点名「不需要在柱状图上面标记
               // 次数」—— 看数走气泡)
  });
  if (!tsLocClickBound) {   // 柱名点击只接一次 (实例缓存, 重复 on 会叠)
    tsLocClickBound = true;
    mkChart("tsLoc").on("click", e => {
      // 只认柱名 (xAxis 轴标签) 开弹层; 柱身 (series) 点按留给气泡看数
      // —— 用户点名「点击文字才弹出框, 点击柱状图只显示数据」(2026-09-30,
      // v8 曾把柱身也放开, 当晚收回)
      if (e.componentType !== "xAxis") return;
      const row = tLocRows[e.dataIndex];
      if (row) openPlaceDialog(row, loadTAll);
    });
  }
}

/* ---------- 驾驶员里程分布: 横向条形 ----------
   2026-09-27 用户点名「行驶统计加一个司机里程分布」(竖排柱状); 2026-09-30
   点名「司机里程分布 → 驾驶员里程分布. 并且这个图改成横向的」—— 名字
   横排铺条侧不再截断竖排, 里程条从左往右, 高度随人数走 (一行一格, 不
   折「其他」—— 驾驶员就几个人)。
   归集口径与行程卡片同款 (后端 trip_driver_stats): 显式标注 > 默认驾驶员
   兜底, 都没有的归「未标注」—— 卡片上显示谁, 这里就记谁; 条端标 km
   合计, 横轴千位缩 k */
function tsRenderDrivers() {
  if (!tDrvData) return;
  if (!tDrvData.length) {
    $("#ts-drv-sub").textContent = "暂无数据";
    return;
  }
  const rows = tDrvData;
  const totalKm = tDrvData.reduce((a, d) => a + d.km, 0);
  $("#ts-drv-sub").textContent =
    `共 ${tDrvData.length} 名 · 合计 ${thousands(Math.round(totalKm))} km`;
  if (!tsHasEcharts) return;
  const box = $("#chart-ts-drv");
  box.style.height = Math.max(176, rows.length * 40 + 16) + "px";
  const chart = mkChart("tsDrv");
  chart.resize();          // 已建实例吃新高度 (换车重拉人数变了)
  chart.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 56, top: 24, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: ps => { const d = rows[ps[0].dataIndex];
        return `<b>${esc(d.name)}</b><br/>${num(d.km)} km · ${d.trips} 次`; } },
    yAxis: { type: "category", inverse: true, data: rows.map(d => d.name),
             name: "驾驶员", nameLocation: "start",   // inverse 翻身会把默认
             // 'end' 带到轴底压着横轴 (2026-09-30 用户报「驾驶员三个字和横
             // 轴重叠了」) —— 钉 start 翻回视觉顶端, 与其他图轴名同槽位
             nameGap: 6, nameTextStyle: axNameStyle,
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.ink, fontSize: 11 } },
    xAxis: { type: "value", name: "km", nameGap: 6, nameTextStyle: axNameStyle,
             splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10,
                          formatter: v => v >= 1000 ? (v / 1000) + "k" : v } },
    series: [{ type: "bar", data: rows.map(d => d.km), barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [0, 4, 4, 0] },
               label: { show: true, position: "right", color: chartText.ink,
                        fontSize: 10.5,
                        formatter: ps => thousands(Math.round(ps.value)) + " km" } }],
  });
}

/* ---------- 出发时段: 12 档柱状 (每 2 小时一组, 与充电开始时段同款) ---------- */
function tsRenderHour() {
  if (!tDimsData) return;
  const hours = tDimsData.by_hour;
  const total = hours.reduce((a, b) => a + b, 0);
  const peak = hours.indexOf(Math.max(...hours));
  $("#ts-hour-sub").textContent = total
    ? `最常 ${pad(peak * 2)}-${pad(peak * 2 + 2)} 点出发 · 共 ${total} 次` : "暂无数据";
  if (!tsHasEcharts || !total) return;
  mkChart("tsHour").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 40, top: 26, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
               formatter: ps => `${pad(ps[0].dataIndex * 2)}:00 – ` +
                                `${pad(ps[0].dataIndex * 2 + 2)}:00 · <b>${ps[0].value} 次</b>` },
    xAxis: { type: "category", data: hours.map((_, i) => String(i * 2)),
             name: "点", nameGap: 6, nameTextStyle: axNameStyle,
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.axis, fontSize: 10, interval: 0 } },
    yAxis: { type: "value", minInterval: 1, name: "次数",
             nameGap: 6, nameTextStyle: axNameStyle,
             splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", data: hours, barMaxWidth: 16,
               itemStyle: { color: "#3987e5", borderRadius: [4, 4, 0, 0] } }],
  });
}

/* ---------- 三张分布柱状: 单程距离 / 行驶时长 / 车速 ----------
   LB = 完整区间文案 (副题/气泡), AX = 轴标 (档位起点), COLORS 随档渐进;
   落档口径在后端 trip_stats (TRIP_*_EDGES), 与充电统计同款 _bump;
   轴名 (km/分/km/h...) 是 2026-09-30 用户点名「横纵坐标都要标记是什么」*/
const DIST_LB = ["<2", "2-5", "5-10", "10-20", "20-50", "50-100",
                 "100-150", "150-200", "200-300", "≥300"];
const DIST_AX = ["0", "2", "5", "10", "20", "50", "100", "150", "200", "300"];
const DIST_COLORS = ["#a9c4e9", "#93b7e4", "#7dabde", "#6aa5da", "#589cd6",
                     "#4794e2", "#3a8ce4", "#2f83df", "#2878d9", "#1f6fd8"];
const TDUR_LB = ["<10分", "10-20分", "20-30分", "30-45分", "45-60分", "1-1.5时",
                 "1.5-2时", "2-3时", "3-5时", "≥5时"];
const TDUR_AX = ["0", "10", "20", "30", "45", "60", "90", "120", "180", "300"];   // 分钟
const TDUR_COLORS = ["#9fc5c8", "#8bbcb6", "#79b3a8", "#69aa9c", "#5aa190",
                     "#4c9985", "#3f917a", "#348870", "#2a7f66", "#20765c"];
const SPD_LB = ["<20", "20-40", "40-60", "60-80", "80-100", "100-120",
                "120-140", "140-160", "≥160"];
const SPD_AX = ["<20", "20", "40", "60", "80", "100", "120", "140", "160"];
const SPD_COLORS = ["#636366", "#74809a", "#879dbf", "#7ba2d2", "#679fd9",
                    "#5c9dd9", "#4a94e2", "#3987e5", "#2d7ce0"];
/* 速度·电耗柱色: 金黄系 (电的家族色, 与月度电耗同调) 随速度档渐进 */
const WH_COLORS = ["#6e5c2e", "#7d672d", "#8f742c", "#a07c28", "#b08425",
                   "#c08a12", "#c98500", "#d38f13", "#d9951f", "#e09a2b"];

function tsRenderDist() {
  if (!tDimsData) return;
  const bins = tDimsData.by_dist;
  const total = bins.reduce((a, b) => a + b, 0);
  const maxI = bins.indexOf(Math.max(...bins));
  renderDimBins("tsDist", "#ts-dist-sub", bins, DIST_AX, DIST_COLORS,
    `最常单程 ${DIST_LB[maxI]} km · 共 ${total} 次`,
    i => `单程 ${DIST_LB[i]} km · <b>${bins[i]} 次</b>`, "km", "次数");
}

function tsRenderDur() {
  if (!tDimsData) return;
  const bins = tDimsData.by_dur;
  const total = bins.reduce((a, b) => a + b, 0);
  const maxI = bins.indexOf(Math.max(...bins));
  renderDimBins("tsDur", "#ts-dur-sub", bins, TDUR_AX, TDUR_COLORS,
    `最常 ${TDUR_LB[maxI]} · 共 ${total} 次`,
    i => `${TDUR_LB[i]} · <b>${bins[i]} 次</b>`, "分", "次数");
}

function tsRenderSpd() {
  if (!tDimsData) return;
  const bins = tDimsData.by_spd;               // 档值 = 该速度段行驶里程 (km)
  const over120 = bins.slice(5).reduce((a, b) => a + b, 0);
  renderDimBins("tsSpd", "#ts-spd-sub", bins, SPD_AX, SPD_COLORS,
    `≥120 km/h 共 ${thousands(Math.round(over120))} km`,
    i => `${SPD_LB[i]} km/h · <b>${num(bins[i])} km</b>`, "km/h", "km");
}

/* ---------- 速度·电耗: 各速度段平均电耗 (横轴速度, 纵轴平均电耗) ----------
   2026-09-30 用户点名「电耗分布横纵坐标不对, 横坐标应该是速度, 纵坐标是
   平均电耗」—— 旧「每次行程 Wh/km 落档计数」直方整链退役 (前端 WH_LB/
   WH_AX 与后端 by_wh 落档口径), 换行车功率逐秒积分: 每速度段 kWh (含
   动能回收与附件负载, 后端 by_spd_kwh) ÷ 段里程 (by_spd) → 平均 Wh/km;
   回收多于耗电的段是负值 (长下坡), 如实画; 样本不足 10 km 的段不参与
   「最省」评比 (160+ 的稀罕段几公里定不了效率) */
function tsRenderWh() {
  if (!tDimsData) return;
  const km = tDimsData.by_spd;
  const kwh = tDimsData.by_spd_kwh;
  const avg = km.map((k, i) => k > 0 ? kwh[i] / k * 1000 : null);
  let best = -1;
  avg.forEach((v, i) => {
    if (km[i] >= 10 && (best < 0 || v < avg[best])) best = i;
  });
  $("#ts-wh-sub").textContent = best < 0 ? "暂无数据"
    : `${SPD_LB[best]} km/h 最省 · ${Math.round(avg[best])} Wh/km · 功率积分含动能回收`;
  if (!tsHasEcharts || best < 0) return;
  mkChart("tsWh").setOption({
    animationDuration: 250,
    grid: { left: 6, right: 40, top: 26, bottom: 0, containLabel: true },
    tooltip: { ...tooltipStyle, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: ps => { const i = ps[0].dataIndex;
        return `${SPD_LB[i]} km/h<br/>里程 ${num(km[i])} km` +
               (avg[i] == null ? "" : `<br/><b>${Math.round(avg[i])} Wh/km</b>`); } },
    xAxis: { type: "category", interval: 0, data: SPD_AX, name: "km/h",
             nameGap: 6, nameTextStyle: axNameStyle,
             axisTick: { show: false }, axisLine: { lineStyle: { color: "#383835" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    yAxis: { type: "value", name: "Wh/km", nameGap: 6, nameTextStyle: axNameStyle,
             splitLine: { lineStyle: { color: "#2c2c2a" } },
             axisLabel: { color: chartText.axis, fontSize: 10 } },
    series: [{ type: "bar", barMaxWidth: 16, borderRadius: [4, 4, 0, 0],
               data: avg.map((v, i) => ({ value: v,
                        itemStyle: { color: WH_COLORS[i] } })) }],
  });
}
