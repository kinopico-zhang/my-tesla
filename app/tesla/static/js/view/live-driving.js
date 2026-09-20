// view/live-driving.js — 驾驶视图 (壳版 2/2): 地图尽力而为初始化 + 车辆蓝点
// 与速度色轨迹 (含轨迹末端接车点的尾巴线) + 状态轮询 + 视图生命周期。
// 旧版 (js/live-driving.js) 的顶栏刷新/登出/eval 期启动全删 (抽屉接管,
// 轮询与建图进 registerView 的 show/hide —— 离开视图清定时器销毁地图,
// lvGen 代次让在途的迟到响应作废; 足迹/充电地图保留实例秒开, 实时页
// 每次进来重建); 结束态链接改内存跳转 (navigate + openByKey, 零历史条目)。
/* global $, getJSON, mapLib, TrackUtil, POLL_MS, TRACK_MS, shellState,
          cur: writable, driveId: writable, trackTimer: writable,
          lvMap: writable, carMarker: writable, routeLine: writable,
          trackEnd: writable, tailLine: writable, serverSkew: writable,
          lvRender, renderElapsed, showState, registerView, bindGestures,
          navigate, openByKey */
/* exported lvSetCar, poll, serverSkew */
"use strict";

/* ============================ 生命周期状态 ============================ */
let lvGen = 0;             // 视图代次: hide() 递增, 在途响应对不上就作废
let lvPollTimer = null;    // 5s 状态轮询
let lvTicker = null;       // 1s 已走时长走秒
let lvEndedKey = null;     // 结束态深链 key ("2200"), 内存跳转用

function lvSetCar(lng, lat) {   // 车辆蓝点 (跟随: 每次刷新把车拉回视野中心)
  const p = mapLib.gcj([lng, lat]);
  if (carMarker) carMarker.setPosition(p);
  else {
    carMarker = mapLib.marker({ position: p, zIndex: 120, offset: mapLib.pixel(-9, -9),
      content: '<div class="car-dot"></div>' });
    lvMap.add(carMarker);
  }
  lvMap.setCenter(p);
  /* 轨迹末端连到车: 轨迹接口 20s 一拉, 位置轮询 5s 一走, 节奏不同 —— 不补
     这根尾巴, 速度色轨迹的终点会脱离车点 (用户要求必须连着)。颜色跟当前
     车速档, 与历史轨迹同一套色阶。 */
  if (trackEnd) {
    if (tailLine) tailLine.setPath([trackEnd, p]);
    else {
      tailLine = mapLib.polyline({ path: [trackEnd, p], strokeWeight: 5,
        strokeOpacity: 1, lineJoin: "round", lineCap: "round", zIndex: 90 });
      lvMap.add(tailLine);
    }
    tailLine.setOptions({ strokeColor:
      TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(cur ? cur.speed || 0 : 0)] });
  }
}

async function refreshTrack() {
  if (!lvMap || !driveId) return;
  try {
    const t = await getJSON("/tesla/trips/api/" + driveId + "/track");
    if (!lvMap || t.id !== driveId) return;   // 行程已切换, 迟到的响应作废
    /* 速度着色 (与行程回放同套色阶: 慢红快绿), 相邻同档一段共享端点无缝 */
    if (routeLine) lvMap.remove(routeLine);
    routeLine = TrackUtil.speedLines(t.pts).map(l => mapLib.polyline({
      path: l.pts.map(q => mapLib.gcj(q)), strokeColor: l.color, strokeWeight: 5,
      strokeOpacity: 1, lineJoin: "round", lineCap: "round", zIndex: 90 }));
    lvMap.add(routeLine);
    const last = t.pts[t.pts.length - 1];
    trackEnd = mapLib.gcj(last);
    if (cur && cur.lng != null) lvSetCar(cur.lng, cur.lat);   // 尾巴立刻接到车
  } catch (e) { /* 刚出发位置点不足 2 个会 404, 下轮再取 */ }
}

function enterDriving(s) {
  driveId = s.drive_id;
  if (lvMap && routeLine) { lvMap.remove(routeLine); routeLine = null; }
  if (lvMap && tailLine) { lvMap.remove(tailLine); tailLine = null; }
  trackEnd = null;
  showState("live");
  refreshTrack();
  clearInterval(trackTimer);
  trackTimer = setInterval(refreshTrack, TRACK_MS);
}

async function poll() {
  const gen = lvGen;            // 离开视图后的迟到响应不再起定时器/改状态
  let s;
  try {
    const q = shellState.carId != null ? "?car_id=" + shellState.carId : "";
    s = await getJSON("/tesla/live/api/status" + q);
  } catch (e) { return; }   // 轮询失败保留当前画面, 下一轮再试
  if (gen !== lvGen) return;
  if (s.now_utc != null) serverSkew = s.now_utc - Date.now() / 1000;
  if (s.driving) {
    if (!cur || !cur.driving || cur.drive_id !== s.drive_id) enterDriving(s);
    cur = s;
    lvRender(s);
  } else if (cur && cur.driving) {   // 开着开着结束了: 给"已结束"态 + 行程深链
    const doneId = cur.drive_id;
    clearInterval(trackTimer);
    if (doneId != null) {
      lvEndedKey = String(doneId);
      $("#ended-link").href = "/tesla?view=trips&id=" + doneId;   // href 只作兜底, 点击走内存跳转
    }
    cur = null;
    showState("ended");
  } else {
    cur = null;
    showState("idle");
  }
}

/* ---------- 地图尽力而为: 失败不挡统计, 只占位提示 ---------- */
async function initMap() {
  const gen = lvGen;
  try {
    await mapLib.ready();   // 配置 + 引擎脚本 (高德/OSM 由设置页定, OSM 免 Key)
    if (gen !== lvGen) return;
    lvMap = mapLib.createMap("lv-map", { zoom: 16, center: [114.05, 22.55] });
    lvMap.on("complete", () => {   // 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染
      const nudge = () => { if (lvMap.getFeatures) lvMap.setFeatures(lvMap.getFeatures()); };
      setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);
    });
    // iOS Safari 双指缩放劫持成整页缩放: 手势只给地图
    for (const ev of ["gesturestart", "gesturechange"])
      document.getElementById("lv-map").addEventListener(ev, e => e.preventDefault());
    if (cur && cur.driving) {   // 地图就位前首轮渲染可能已过: 补画车点 + 轨迹
      lvRender(cur);
      refreshTrack();
    }
  } catch (e) {
    if (gen === lvGen) $("#map-fallback").hidden = false;
  }
}

/* ============================ 生命周期 ============================ */
document.addEventListener("visibilitychange", () => {   // 从后台切回立即刷新
  if (!document.hidden && !$("#view-live").hidden) poll();
});

/* 结束态链接: 壳内内存跳转到行程视图并直开该条 (零历史条目) */
$("#ended-link").addEventListener("click", e => {
  e.preventDefault();
  if (lvEndedKey != null) { navigate("trips"); openByKey(lvEndedKey); }
});

/* 手势面: 面板区 (仪表/电池/格子) 右划开抽屉/下拉刷新; 空态/结束态整面
   都是; 画布本体 touch-action:none 全给地图引擎, 左缘 24px 条供右划 */
bindGestures($("#lv-panels"), { drawer: true, ptr: true, onRefresh: poll });
bindGestures($("#booting"), { drawer: true, ptr: true, onRefresh: poll });
bindGestures($("#ended"), { drawer: true, ptr: true, onRefresh: poll });
bindGestures($("#idle"), { drawer: true, ptr: true, onRefresh: poll });
bindGestures($("#lv-edge"), { drawer: true });

function lvShow() {
  lvGen++;
  $("#map-fallback").hidden = true;   // 上次失败的占位先收起, 这轮重试
  initMap();
  poll();
  lvPollTimer = setInterval(poll, POLL_MS);
  lvTicker = setInterval(() => { if (cur && cur.driving) renderElapsed(cur); }, 1000);
}
function lvHide() {
  lvGen++;                     // 在途轮询/建图/轨迹拉取全作废
  clearInterval(lvPollTimer); lvPollTimer = null;
  clearInterval(lvTicker); lvTicker = null;
  clearInterval(trackTimer); trackTimer = null;
  if (lvMap) lvMap.destroy();  // 实时地图每次进来重建 (足迹/充电地图才保留实例)
  lvMap = null; carMarker = null; routeLine = null; tailLine = null;
  trackEnd = null; cur = null; driveId = null;
  showState("booting");        // 回来时从等待态重新起
}
registerView("live", {
  title: "驾驶",
  el: $("#view-live"),
  show: lvShow,
  hide: lvHide,
  refresh: poll,   // 抽屉刷新 (换时间档对实时页无意义, 轮询本就不带时间参)
});
