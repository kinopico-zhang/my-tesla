// view/chargemap-heatmap.js — 充电地图视图 (壳版 2/3): 热力渲染 (渲染坐标
// 经 mapLib.gcj, 按视图加权归一) + 隐形圆点拉视野 + 点击就近取点 + 充电点
// 详情底部弹层 + 图例与汇总统计 + 数据刷新与地图启动 cmBoot (首进视图才跑)。
// 2026-09-27 用户点名 (两条): ① 缩放/平移时图例极值与页顶汇总都按「视野内」
// 的地点动态算, 热力归一 max 同步跟视野 (视野内最大永远是红端, 最小是蓝端);
// ② 图例搬回画布内左下角 (脚下只留居中的视角档 pills)。
// 请求带 car_id; 建图建热力走 mapLib (服务商可切)。
/* global $, getJSON, shellState, mapLib, cmViews, GRADIENT,
          PICK_PX, cmMode, cmMap: writable, heatmap: writable,
          pickMark: writable, locations: writable, cmShowLoading, cmShowError */
/* exported renderHeatmap, cmCloseSheet, cmRefresh, cmBoot */
"use strict";
let hmNormMax = 0;   // 热力当前归一用的 max (视野内最大; 0 = 还没喂过)
/* 渲染热力: 全量点位都喂 (视野外的不渲染), 归一 max 跟着视野走 */
function feedHeatmap(maxV) {
  heatmap.setDataSet({
    data: locations.map(l => {
      const c = mapLib.gcj([l.lng, l.lat]);   // WGS-84 → 渲染坐标 (高德 GCJ-02)
      return { lng: c[0], lat: c[1], count: l[cmMode] };
    }),
    max: maxV || 1,
  });
  hmNormMax = maxV;
}
function maxOfView() { return Math.max(...locations.map(l => l[cmMode]), 0); }

/* 视野内地点子集: 取视野框双版本兼容 (高德 2.0 是方法 / 旧版是属性) */
function visibleLocations() {
  if (!cmMap || !locations.length) return [];
  const b = cmMap.getBounds();
  const sw = b.getSouthWest ? b.getSouthWest() : b.southwest;
  const ne = b.getNorthEast ? b.getNorthEast() : b.northeast;
  return locations.filter(l => {
    const c = mapLib.gcj([l.lng, l.lat]);
    return c[0] >= sw.lng && c[0] <= ne.lng && c[1] >= sw.lat && c[1] <= ne.lat;
  });
}

/* 视野落定 (moveend/zoomend/首渲染/换档): 汇总三数 + 图例极值按视野内算,
   热力归一 max 变了才重喂 (视野内最大始终红端 —— 梯度 1 端就是红) */
function updateViewport() {
  if (!cmMap || !heatmap) return;
  const vis = visibleLocations();
  cmRenderStats(vis);
  renderLegend(vis);
  const maxV = Math.max(...vis.map(l => l[cmMode]), 0);
  if (maxV !== hmNormMax) feedHeatmap(maxV);
}

function renderHeatmap() {
  cmCloseSheet();
  if (!cmMap || !heatmap) return;   // 实例刚被 maplib:swap 销毁: 重建后 cmBoot 会重画
  feedHeatmap(maxOfView());         // 先全量归一铺上, fit 后 updateViewport 收敛到视野
  fitToLocations();
  updateViewport();
  if (!locations.length) cmShowError("该时间段没有充电记录");
}

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

/* 图例 (画布内左下角浮卡, 2026-09-27 用户点名搬回图内): 少 → 多 梯度条
   + 视野内的最小 / 中位 / 最大值 (极值随视野动态算, 同日点名; 视角名由
   脚下 pills 亮着, 不再重复一行文字) */
function gradientCss() {
  // GRADIENT 的键 "1" 是整数式键, Object.keys 会排在最前 —— 显式按数值排序
  const stops = Object.keys(GRADIENT).map(Number).sort((a, b) => a - b);
  return "linear-gradient(90deg," +
    stops.map(k => GRADIENT[k] + " " + Math.round(k * 100) + "%").join(",") + ")";
}
function renderLegend(vis) {
  const lg = $("#cm-legend");
  if (!vis.length) { lg.hidden = true; return; }
  lg.hidden = false;
  $("#lg-ramp").style.background = gradientCss();
  const v = cmViews[cmMode];
  const vals = vis.map(l => l[cmMode]).sort((a, b) => a - b);
  const mid = vals[Math.floor(vals.length / 2)];
  $("#lg-row").innerHTML = [vals[0], mid, vals[vals.length - 1]]
    .map(x => `<span>${v.fmt(x)}</span>`).join("");
}

function cmRenderStats(list) {   // 页顶汇总三数: 只数视野内地点 (updateViewport 喂)
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
    const p = new URLSearchParams();   // 时间不筛, 全时段 (3.3.0 下线)
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
    await mapLib.ready();   // 配置 + 引擎脚本 (高德, 要 Key)
    cmMap = mapLib.createMap("cm-map", { zoom: 11, center: [114.05, 22.55] });
    heatmap = mapLib.heatMap(cmMap, {
      radius: 26,          // 热力圆半径 (像素)
      opacity: [0, .8],
      gradient: GRADIENT,
    });
    cmMap.on("click", pickNearest);
    // 视野落定 (平移/缩放收尾): 极值/汇总按新视野重算, 热力归一跟最大值走
    for (const ev of ["moveend", "zoomend"]) cmMap.on(ev, updateViewport);
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
