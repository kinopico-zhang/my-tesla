// chargemap-heatmap.js — 充电地图页 (2/3): 热力渲染 (WGS-84→GCJ-02, 按视图
// 加权归一) + 隐形圆点拉视野 + 点击就近取点 + 充电点详情底部弹层 + 图例
// 与汇总统计 + 数据刷新与地图启动 (boot)。
// 由 chargemap.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// chargemap.html 里的顺序加载, 跨模块引用走全局); 底座在 chargemap-page.js。
/* global $, GCJ02, VIEWS, GRADIENT, PICK_PX, view,
          map: writable, heatmap: writable, pickMark: writable,
          locations: writable, getJSON, rangeParams, loadAMap,
          showLoading, showError */
/* exported renderHeatmap, closeSheet, refresh, boot */
"use strict";
/* 渲染热力: 当前视图的数值做权重, 归一到 0..max 上梯度 */
function renderHeatmap() {
  closeSheet();
  const maxV = maxOfView();
  heatmap.setDataSet({
    data: locations.map(l => {
      const c = GCJ02.wgs84ToGcj02(l.lng, l.lat);   // WGS-84 → GCJ-02
      return { lng: c[0], lat: c[1], count: l[view] };
    }),
    max: maxV || 1,
  });
  renderLegend(maxV);
  fitToLocations();
  if (!locations.length) showError("该时间段没有充电记录");
}
function maxOfView() { return Math.max(...locations.map(l => l[view]), 0); }

/* 热力层不是地图覆盖物, setFitView 看不见它 —— 临时放一把隐形圆点拉视野再撤 */
function fitToLocations() {
  if (!locations.length) return;
  const marks = locations.map(l => new AMap.CircleMarker({
    center: GCJ02.wgs84ToGcj02(l.lng, l.lat), radius: 1,
  }));
  map.add(marks);
  map.setFitView(marks, false, [40, 40, 40, 40]);
  map.remove(marks);
}

/* 点击就近取点: 热力块没有可点对象, 谁的中心离点击处近 (阈值内) 就算谁 */
function pickNearest(ev) {
  if (!ev.pixel) return;
  let best = null, bestD = Infinity;
  locations.forEach(loc => {
    const p = map.lngLatToContainer(GCJ02.wgs84ToGcj02(loc.lng, loc.lat));
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
  $("#backdrop").classList.add("show");
  $("#sheet").classList.add("show");
}
function closeSheet() {
  hidePick();
  $("#backdrop").classList.remove("show");
  $("#sheet").classList.remove("show");
}
/* 选中点画个白圈: 热力块上看不出选中了哪一个 */
function showPick(loc) {
  hidePick();
  pickMark = new AMap.CircleMarker({
    center: GCJ02.wgs84ToGcj02(loc.lng, loc.lat),
    radius: 9, zIndex: 99, bubble: true,
    strokeColor: "#ffffff", strokeWeight: 2.5, strokeOpacity: 1,
    fillColor: "#ffffff", fillOpacity: .2,
  });
  map.add(pickMark);
}
function hidePick() {
  if (pickMark) { map.remove(pickMark); pickMark = null; }
}

/* 图例: 梯度条 + 当前视图的最小 / 中位 / 最大值 */
function gradientCss() {
  // GRADIENT 的键 "1" 是整数式键, Object.keys 会排在最前 —— 显式按数值排序
  const stops = Object.keys(GRADIENT).map(Number).sort((a, b) => a - b);
  return "linear-gradient(90deg," +
    stops.map(k => GRADIENT[k] + " " + Math.round(k * 100) + "%").join(",") + ")";
}
function renderLegend(maxV) {
  const lg = $("#legend");
  if (!locations.length) { lg.hidden = true; return; }
  lg.hidden = false;
  const v = VIEWS[view];
  $("#lg-mode").textContent = "颜色越红 · " + v.lb + "越多";
  $("#lg-ramp").style.background = gradientCss();
  const vals = locations.map(l => l[view]).sort((a, b) => a - b);
  const mid = vals[Math.floor(vals.length / 2)];
  $("#lg-row").innerHTML = [vals[0], mid, maxV].map(x => `<span>${v.fmt(x)}</span>`).join("");
}

function renderStats(list) {
  $("#stats").hidden = false;
  $("#st-places").textContent = list.length;
  $("#st-sessions").textContent = list.reduce((a, l) => a + l.sessions, 0);
  const energy = list.reduce((a, l) => a + l.energy, 0);
  $("#st-energy").innerHTML = Math.round(energy) + "<small>kWh</small>";
}

async function refresh(first) {
  $("#error").hidden = true;
  showLoading(true, first ? "正在加载充电地点…" : "正在更新…");
  try {
    locations = await getJSON("/tesla/charging/api/map-locations" + rangeParams());
    renderStats(locations);
    renderHeatmap();
    showLoading(false);
  } catch (e) {
    showError(e.message);
    showLoading(false);
  }
}

async function boot() {
  try {
    // 加时间戳穿透浏览器缓存 (旧响应可能缓存了 amap_key: null)
    const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
    if (!cfg.amap_key) {
      $("#keyhint").hidden = false;
      return;
    }
    await loadAMap(cfg.amap_key, cfg.security_code);
    map = new AMap.Map("map", {
      mapStyle: cfg.style || "amap://styles/dark", zoom: 11, center: [114.05, 22.55],
    });
    heatmap = new AMap.HeatMap(map, {
      radius: 26,          // 热力圆半径 (像素)
      opacity: [0, .8],
      gradient: GRADIENT,
    });
    map.on("click", pickNearest);
    // iOS Safari 会把双指缩放劫持成整页缩放: 拦截私有 gesture 事件, 手势只给高德
    for (const ev of ["gesturestart", "gesturechange"]) {
      document.getElementById("map").addEventListener(ev, e => e.preventDefault());
    }
    await refresh(true);
  } catch (e) {
    if (e.message !== "未登录") showError(e.message);
  }
}
