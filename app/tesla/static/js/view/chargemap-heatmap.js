// view/chargemap-heatmap.js — 充电地图视图 (壳版 2/3): 热力渲染 (渲染坐标
// 经 mapLib.gcj, 按视图加权归一) + 隐形圆点拉视野 + 点击就近取点 + 充电点
// 详情底部弹层 + 图例与汇总统计 + 数据刷新与地图启动 cmBoot (首进视图才跑)。
// 旧版 (js/chargemap-heatmap.js) 逐字节未动, 只换 id 前缀 (cm-) 与撞名
// 全局 (cmRefresh/cmRenderStats/cmCloseSheet/cmBoot); 请求带时间档
// (抽屉全局) 与 car_id; 建图建热力走 mapLib (服务商可切)。
/* global $, getJSON, shellState, timeRangeParams, mapLib, cmViews, GRADIENT,
          PICK_PX, cmMode, cmMap: writable, heatmap: writable,
          pickMark: writable, locations: writable, cmShowLoading, cmShowError */
/* exported renderHeatmap, cmCloseSheet, cmRefresh, cmBoot */
"use strict";
/* 渲染热力: 当前视图的数值做权重, 归一到 0..max 上梯度 */
function renderHeatmap() {
  cmCloseSheet();
  const maxV = maxOfView();
  heatmap.setDataSet({
    data: locations.map(l => {
      const c = mapLib.gcj([l.lng, l.lat]);   // WGS-84 → 渲染坐标 (高德 GCJ-02 / OSM 原样)
      return { lng: c[0], lat: c[1], count: l[cmMode] };
    }),
    max: maxV || 1,
  });
  renderLegend(maxV);
  fitToLocations();
  if (!locations.length) cmShowError("该时间段没有充电记录");
}
function maxOfView() { return Math.max(...locations.map(l => l[cmMode]), 0); }

/* 热力层不是地图覆盖物, setFitView 看不见它 —— 临时放一把隐形圆点拉视野再撤 */
function fitToLocations() {
  if (!locations.length) return;
  const marks = locations.map(l => mapLib.circleMarker({
    center: mapLib.gcj([l.lng, l.lat]), radius: 1,
  }));
  cmMap.add(marks);
  cmMap.setFitView(marks, false, [40, 40, 40, 40]);
  cmMap.remove(marks);
}

/* 点击就近取点: 热力块没有可点对象, 谁的中心离点击处近 (阈值内) 就算谁 */
function pickNearest(ev) {
  if (!ev.pixel) return;
  let best = null, bestD = Infinity;
  locations.forEach(loc => {
    const p = cmMap.lngLatToContainer(mapLib.gcj([loc.lng, loc.lat]));
    const dx = p.getX() - ev.pixel.getX(), dy = p.getY() - ev.pixel.getY();
    const d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = loc; }
  });
  if (best && bestD <= PICK_PX * PICK_PX) selectLocation(best);
}

function selectLocation(loc) {
  $("#sh-name").textContent = loc.name;
  $("#sh-city").textContent = loc.city || "—";
  $("#sh-sessions").textContent = loc.sessions;
  $("#sh-fast").textContent = loc.fast_sessions;
  $("#sh-energy").innerHTML = loc.energy + "<small>kWh</small>";
  $("#sh-cost").textContent = loc.cost ? "¥" + loc.cost : "未记录";
  showPick(loc);
  $("#cm-backdrop").classList.add("show");
  $("#cm-sheet").classList.add("show");
}
function cmCloseSheet() {
  hidePick();
  $("#cm-backdrop").classList.remove("show");
  $("#cm-sheet").classList.remove("show");
}
/* 选中点画个白圈: 热力块上看不出选中了哪一个 */
function showPick(loc) {
  hidePick();
  pickMark = mapLib.circleMarker({
    center: mapLib.gcj([loc.lng, loc.lat]),
    radius: 9, zIndex: 99, bubble: true,
    strokeColor: "#ffffff", strokeWeight: 2.5, strokeOpacity: 1,
    fillColor: "#ffffff", fillOpacity: .2,
  });
  cmMap.add(pickMark);
}
function hidePick() {
  if (pickMark) { cmMap.remove(pickMark); pickMark = null; }
}

/* 图例: 梯度条 + 当前视图的最小 / 中位 / 最大值 */
function gradientCss() {
  // GRADIENT 的键 "1" 是整数式键, Object.keys 会排在最前 —— 显式按数值排序
  const stops = Object.keys(GRADIENT).map(Number).sort((a, b) => a - b);
  return "linear-gradient(90deg," +
    stops.map(k => GRADIENT[k] + " " + Math.round(k * 100) + "%").join(",") + ")";
}
function renderLegend(maxV) {
  const lg = $("#cm-legend");
  if (!locations.length) { lg.hidden = true; return; }
  lg.hidden = false;
  const v = cmViews[cmMode];
  $("#lg-mode").textContent = "颜色越红 · " + v.lb + "越多";
  $("#lg-ramp").style.background = gradientCss();
  const vals = locations.map(l => l[cmMode]).sort((a, b) => a - b);
  const mid = vals[Math.floor(vals.length / 2)];
  $("#lg-row").innerHTML = [vals[0], mid, maxV].map(x => `<span>${v.fmt(x)}</span>`).join("");
}

function cmRenderStats(list) {
  $("#cm-stats").hidden = false;
  $("#st-places").textContent = list.length;
  $("#st-sessions").textContent = list.reduce((a, l) => a + l.sessions, 0);
  const energy = list.reduce((a, l) => a + l.energy, 0);
  $("#st-energy").innerHTML = Math.round(energy) + "<small>kWh</small>";
}

async function cmRefresh(first) {
  if (!cmMap) return;   // 地图还没起来 (视图没进过/配置缺 Key): 不空转
  $("#cm-error").hidden = true;
  cmShowLoading(true, first ? "正在加载充电地点…" : "正在更新…");
  try {
    const p = new URLSearchParams(timeRangeParams());
    if (shellState.carId != null) p.set("car_id", String(shellState.carId));
    locations = await getJSON("/tesla/charging/api/map-locations?" + p);
    cmRenderStats(locations);
    renderHeatmap();
    cmShowLoading(false);
  } catch (e) {
    cmShowError(e.message);
    cmShowLoading(false);
  }
}

async function cmBoot() {
  try {
    await mapLib.ready();   // 配置 + 引擎脚本 (高德要 Key, OSM 免 Key 开箱即用)
    cmMap = mapLib.createMap("cm-map", { zoom: 11, center: [114.05, 22.55] });
    heatmap = mapLib.heatMap(cmMap, {
      radius: 26,          // 热力圆半径 (像素)
      opacity: [0, .8],
      gradient: GRADIENT,
    });
    cmMap.on("click", pickNearest);
    // iOS Safari 会把双指缩放劫持成整页缩放: 拦截私有 gesture 事件, 手势只给地图
    for (const ev of ["gesturestart", "gesturechange"]) {
      document.getElementById("cm-map").addEventListener(ev, e => e.preventDefault());
    }
    await cmRefresh(true);
  } catch (e) {
    if (e.noKey) { $("#cm-keyhint").hidden = false; return; }   // 高德缺 Key: 专属引导卡
    if (e.message !== "未登录") cmShowError(e.message);
  }
}
