// live.js — 由 live.html 内联脚本抽出 (位置/顺序/语义不变), 供 lint 与测试
"use strict";
/* 点空白处收起页签菜单 */
document.addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});
const $ = s => document.querySelector(s);

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ("HTTP " + r.status));
  return r.json();
}

/* ---------- 状态机: booting → live / idle, live → ended (行程闭合) ---------- */
const POLL_MS = 5000, TRACK_MS = 20000, STALE_AFTER_S = 120;
let cur = null;            // 最近一次 status (driving=true)
let driveId = null;        // 当前在渲染的行程 id
let trackTimer = null;
let map = null, carMarker = null, routeLine = null;
let trackEnd = null, tailLine = null;   // 轨迹末端 → 车当前位置的连线 (见 setCar)
let serverSkew = 0;        // 服务器时钟 - 手机时钟 (秒): 手机时间不准时走秒仍按服务器算

function showState(id) {
  for (const el of ["booting", "live", "ended", "idle"]) $("#" + el).hidden = el !== id;
}

const pad = n => String(n).padStart(2, "0");
function fmtElapsed(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
}
function setVal(sel, val, unit) {   // 数字进定宽盒 (位数变化不挤单位), null → "–"
  $(sel).innerHTML = '<span class="n">' + (val == null ? "–" : val) + "</span>"
    + (unit ? "<small>" + unit + "</small>" : "");
}

function render(s) {
  $("#lv-speed").textContent = s.speed == null ? "–" : Math.round(s.speed);
  $("#lv-sub").innerHTML =
    "出发 " + (s.start ? s.start.slice(11) : "–") +
    ' · 最高 <span class="n">' + (s.speed_max == null ? "–" : Math.round(s.speed_max)) + "</span> km/h";
  if (s.soc != null) {
    $("#lv-soc").textContent = s.soc + "%";
    const fill = $("#batt-fill");
    fill.style.width = s.soc + "%";
    fill.style.background = s.soc > 50 ? "#32d74b" : s.soc > 20 ? "#ffd60a" : "#ff453a";
  } else {
    $("#lv-soc").textContent = "–";
  }
  $("#lv-range").textContent = s.rated_range_km == null ? "–" : Math.round(s.rated_range_km);
  setVal("#lv-km", s.km == null ? null : s.km.toFixed(1), "km");
  setVal("#lv-kwh", s.kwh == null ? null : s.kwh.toFixed(1), "kWh");
  setVal("#lv-avg", s.wh_per_km == null ? null : s.wh_per_km, "Wh/km");
  setVal("#lv-vmax", s.speed_max == null ? null : Math.round(s.speed_max), "km/h");
  renderElapsed(s);
  renderStale(s);
  if (map && s.lng != null) setCar(s.lng, s.lat);
}

function renderElapsed(s) {
  /* 已行驶按服务器时钟算 (now_utc 校准偏差): 手机时钟不准时 Date.now 会把
     差值钳到 0, 用户看到的已行驶就一直是 0:00 (真机踩坑)。 */
  const sec = Math.max(0, Math.floor(Date.now() / 1000 + serverSkew - s.started_utc));
  $("#lv-elapsed").textContent = fmtElapsed(sec);
}

function renderStale(s) {   // 最新位置点太久没更新 → 提示信号中断 (隧道/无网)
  const hint = $("#stale-hint");
  const age = s.pos_utc ? Math.floor(Date.now() / 1000 - s.pos_utc) : 0;
  if (age > STALE_AFTER_S) {
    hint.hidden = false;
    hint.textContent = "信号可能中断 · 数据 " + Math.floor(age / 60) + " 分钟前更新";
  } else {
    hint.hidden = true;
  }
}

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
