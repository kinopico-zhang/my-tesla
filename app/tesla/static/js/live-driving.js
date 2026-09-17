// live-driving.js — 当前驾驶页 (2/2): 地图尽力而为初始化 + 车辆蓝点与
// 速度色轨迹 (含轨迹末端接车点的尾巴线) + 状态轮询与收尾 (刷新/退出/启动)。
// 由 live.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 live.html
// 里的顺序加载, 跨模块引用走全局); 底座与面板渲染在 live-page.js。
/* global $, getJSON, GCJ02, TrackUtil, POLL_MS, TRACK_MS,
          cur: writable, driveId: writable, trackTimer: writable, map: writable,
          carMarker: writable, routeLine: writable, trackEnd: writable,
          tailLine: writable, serverSkew: writable,
          render, renderElapsed, showState */
/* exported serverSkew */
"use strict";
function setCar(lng, lat) {   // 车辆蓝点 (跟随: 每次刷新把车拉回视野中心)
  const p = GCJ02.wgs84ToGcj02(lng, lat);
  if (carMarker) carMarker.setPosition(p);
  else {
    carMarker = new AMap.Marker({ position: p, zIndex: 120, offset: new AMap.Pixel(-9, -9),
      content: '<div class="car-dot"></div>' });
    map.add(carMarker);
  }
  map.setCenter(p);
  /* 轨迹末端连到车: 轨迹接口 20s 一拉, 位置轮询 5s 一走, 节奏不同 —— 不补
     这根尾巴, 速度色轨迹的终点会脱离车点 (用户要求必须连着)。颜色跟当前
     车速档, 与历史轨迹同一套色阶。 */
  if (trackEnd) {
    if (tailLine) tailLine.setPath([trackEnd, p]);
    else {
      tailLine = new AMap.Polyline({ path: [trackEnd, p], strokeWeight: 5,
        strokeOpacity: 1, lineJoin: "round", lineCap: "round", zIndex: 90 });
      map.add(tailLine);
    }
    tailLine.setOptions({ strokeColor:
      TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(cur ? cur.speed || 0 : 0)] });
  }
}

async function refreshTrack() {
  if (!map || !driveId) return;
  try {
    const t = await getJSON("/tesla/trips/api/" + driveId + "/track");
    if (!map || t.id !== driveId) return;   // 行程已切换, 迟到的响应作废
    /* 速度着色 (与行程回放同套色阶: 慢红快绿), 相邻同档一段共享端点无缝 */
    const conv = pts => pts.map(q => GCJ02.wgs84ToGcj02(q[0], q[1]));
    if (routeLine) map.remove(routeLine);
    routeLine = TrackUtil.speedLines(t.pts).map(l => new AMap.Polyline({
      path: conv(l.pts), strokeColor: l.color, strokeWeight: 5, strokeOpacity: 1,
      lineJoin: "round", lineCap: "round", zIndex: 90 }));
    map.add(routeLine);
    const last = t.pts[t.pts.length - 1];
    trackEnd = GCJ02.wgs84ToGcj02(last[0], last[1]);
    if (cur && cur.lng != null) setCar(cur.lng, cur.lat);   // 尾巴立刻接到车
  } catch (e) { /* 刚出发位置点不足 2 个会 404, 下轮再取 */ }
}

function enterDriving(s) {
  driveId = s.drive_id;
  if (map && routeLine) { map.remove(routeLine); routeLine = null; }
  if (map && tailLine) { map.remove(tailLine); tailLine = null; }
  trackEnd = null;
  showState("live");
  refreshTrack();
  clearInterval(trackTimer);
  trackTimer = setInterval(refreshTrack, TRACK_MS);
}

async function poll() {
  let s;
  try {
    s = await getJSON("/tesla/live/api/status");
  } catch (e) { return; }   // 轮询失败保留当前画面, 下一轮再试
  if (s.now_utc != null) serverSkew = s.now_utc - Date.now() / 1000;
  if (s.driving) {
    if (!cur || !cur.driving || cur.drive_id !== s.drive_id) enterDriving(s);
    cur = s;
    render(s);
  } else if (cur && cur.driving) {   // 开着开着结束了: 给"已结束"态 + 行程深链
    const doneId = cur.drive_id;
    clearInterval(trackTimer);
    if (doneId != null) $("#ended-link").href = "/tesla/trips?id=" + doneId;
    cur = null;
    showState("ended");
  } else {
    cur = null;
    showState("idle");
  }
}

/* ---------- 地图尽力而为: 失败不挡统计, 只占位提示 ---------- */
async function initMap() {
  try {
    const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
    if (!cfg.amap_key) throw new Error("no key");
    if (cfg.security_code) window._AMapSecurityConfig = { securityJsCode: cfg.security_code };
    await new Promise((resolve, reject) => {
      const sc = document.createElement("script");
      sc.src = "https://webapi.amap.com/maps?v=2.0&key=" + encodeURIComponent(cfg.amap_key);
      sc.onload = resolve;
      sc.onerror = () => reject(new Error("script"));
      document.head.appendChild(sc);
    });
    map = new AMap.Map("map", { mapStyle: cfg.style || "amap://styles/dark",
      zoom: 16, center: [114.05, 22.55] });
    map.on("complete", () => {   // 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染
      const nudge = () => { if (map.getFeatures) map.setFeatures(map.getFeatures()); };
      setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);
    });
    // iOS Safari 双指缩放劫持成整页缩放: 手势只给高德
    for (const ev of ["gesturestart", "gesturechange"])
      document.getElementById("map").addEventListener(ev, e => e.preventDefault());
    if (cur && cur.driving) {   // 地图就位前首轮渲染可能已过: 补画车点 + 轨迹
      render(cur);
      refreshTrack();
    }
  } catch (e) {
    $("#map-fallback").hidden = false;
  }
}

setInterval(() => { if (cur && cur.driving) renderElapsed(cur); }, 1000);
document.addEventListener("visibilitychange", () => {   // 从后台切回立即刷新
  if (!document.hidden) poll();
});
/* 顶栏刷新: 重拉当前页数据 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await poll();
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
  location.href = "/login";
});

initMap();
poll();
setInterval(poll, POLL_MS);
