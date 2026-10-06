// view/live-driving.js — 驾驶视图 (壳版 2/2): 地图尽力而为初始化 + 车辆蓝点
// 与速度色轨迹 (含轨迹末端接车点的尾巴线) + 状态轮询 + 视图生命周期。
// 旧版 (js/live-driving.js) 的顶栏刷新/登出/eval 期启动全删 (壳件接管,
// 轮询进 registerView 的 show/hide —— 离开视图清定时器销毁地图, lvGen 代次
// 让在途的迟到响应作废; 足迹/充电地图保留实例秒开, 实时页每次进来重建;
// 建图等 #live 亮出来才动 (2026-09-26 地图白板修复, 见 initMap 调用点));
// 2026-09-26 状态页常显化 (用户点名「不管车辆什么状态都显示实时数据和地图
// 位置」): 空态/结束态占位屏退役, 停车常显面板+地图, 刚结束定格末帧。
// 2026-09-27 驻车地图补轨迹 (用户点名「状态是直接显示最后一段行程的轨迹,
// 以及车的当前位置」): 常态停车画最后一程的速度色轨迹 + 车位点并收进视野。
// v10 (2026-09-27): 地图顶中的最后一段行程直达钮退役 (用户点名「状态页面上
// 最后一段行程按钮，去掉」) —— 两态文案/内存跳转整链拆净, 面板定格与驻车
// 轨迹照旧。
// v13 (2026-10-04) 两笔: ① 用户报「右划要划好多次才打开菜单」—— 舞台两侧
// 14px 出血缝里的触摸谁也接不到 (卡内左缘条从 14px 才起), 补 #lv-gutter 视
// 图层缝条接力到物理屏缘 (足迹页 #fp-gutter 同款); ② 用户报「下拉时图标数
// 字陷到地图后面」—— ptrMove 把下拉位移挂到整舞台, 面板+画布一体跟手。
/* global $, getJSON, mapLib, TrackUtil, POLL_MS, TRACK_MS, shellState,
          cur: writable, driveId: writable, trackTimer: writable,
          lvMap: writable, carMarker: writable, routeLine: writable,
          trackEnd: writable, tailLine: writable, serverSkew: writable,
          lvRender, lvRenderParked, renderElapsed, showState, registerView,
          bindGestures, diag */
/* exported lvSetCar, poll, serverSkew */
"use strict";

/* ============================ 生命周期状态 ============================ */
let lvGen = 0;             // 视图代次: hide() 递增, 在途响应对不上就作废
let lvPollTimer = null;    // 5s 状态轮询
let lvTicker = null;       // 1s 已走时长走秒
let endedFreeze = false;   // 刚结束: 面板定格本次末帧, 不落停车常显
let parkedS = null;        // 最近一次停车态 (initMap 就位后补画车点用)
let parkedTrackKey = null; // 驻车轨迹已画的行程 id (5s 轮询不重拉不闪, 见 lvDrawLastTrack)

function lvSetCar(lng, lat, follow = true) {   // follow=false: 只挪点不追焦 (驻车画轨迹时别抢视野)
  const p = mapLib.gcj([lng, lat]);
  if (carMarker) carMarker.setPosition(p);
  else {
    carMarker = mapLib.marker({ position: p, zIndex: 120, offset: mapLib.pixel(-9, -9),
      content: '<div class="car-dot"></div>' });
    lvMap.add(carMarker);
  }
  if (follow) lvMap.setCenter(p);
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

async function lvDrawLastTrack(s) {
  /* 常态停车地图画最后一程轨迹 + 车位点 (2026-09-27 用户点名「状态是直接
     显示最后一段行程的轨迹, 以及车的当前位置」): 与驾驶态同一套速度色线;
     画完把轨迹和车点一起收进视野 (追焦车位会切掉大半程)。按行程 id 记账,
     5s 轮询不重拉不闪 —— 换了行程/重进视图才重画; 拉不到 (刚记完位置点未
     齐等) 归零记账下轮再试, 车位点先居中收场。 */
  if (!lvMap) return;
  if (!s.last_drive || s.last_drive.id == null) {
    if (routeLine) { lvMap.remove(routeLine); routeLine = null; }   // 换车后没有最后一程: 上一场的驻车轨迹不留残线
    parkedTrackKey = null;
    return;
  }
  const id = s.last_drive.id;
  if (parkedTrackKey === id) return;
  parkedTrackKey = id;
  const gen = lvGen;
  try {
    const t = await getJSON("/tesla/trips/api/" + id + "/track");
    if (gen !== lvGen || !lvMap || parkedTrackKey !== id) return;   // 迟到作废
    if (routeLine) lvMap.remove(routeLine);
    routeLine = TrackUtil.speedLines(t.pts).map(l => mapLib.polyline({
      path: l.pts.map(q => mapLib.gcj(q)), strokeColor: l.color, strokeWeight: 5,
      strokeOpacity: 1, lineJoin: "round", lineCap: "round", zIndex: 90 }));
    lvMap.add(routeLine);
    if (carMarker) lvMap.setFitView([...routeLine, carMarker], true, [40, 40, 40, 40]);
  } catch (e) {
    parkedTrackKey = null;   // 归零记账: 下一轮 (5s) 重试
    if (gen === lvGen && lvMap && s.lng != null) lvMap.setCenter(mapLib.gcj([s.lng, s.lat]));
  }
}

function enterDriving(s) {
  driveId = s.drive_id;
  parkedTrackKey = null;   // 驻车轨迹翻篇: 这程结束后回停车态要重画
  if (lvMap && routeLine) { lvMap.remove(routeLine); routeLine = null; }
  if (lvMap && tailLine) { lvMap.remove(tailLine); tailLine = null; }
  trackEnd = null;
  showState("live");
  /* 地图等 #live 亮出来才建 (2026-09-26 用户实报「当前驾驶页面地图显示出
     来不了」): 高德在 display:none 的 0×0 容器里建图, 之后掀开容器也不重
     排, 永远白板 —— 以前进视图就抢建, 引擎缓存住时配置一个来回快过首轮
     状态, 建图落在隐藏容器里的概率极大。驾驶态/停车态每次进来重建
     (lvHide 已销毁)。 */
  if (!lvMap) initMap();
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
    endedFreeze = false;
    $("#lv-title").textContent = "状态：行驶";   // 页面标题两态 (2026-09-27 用户点名)
    if (!cur || !cur.driving || cur.drive_id !== s.drive_id) enterDriving(s);
    cur = s;
    parkedS = null;
    lvRender(s);
  } else if (cur && cur.driving) {
    /* 开着开着结束了: 面板定格本次行程末帧 (不掀占位屏), 地图留着轨迹和
       车点; 轮询照走, 下一程起播自动翻篇。文案落结束态 (驻车分支会改写
       它, 这里每次显式钉回)。 */
    clearInterval(trackTimer);
    endedFreeze = true;
    $("#lv-title").textContent = "状态：驻车";   // 已停: 标题跟着落停车态
    cur = null;
  } else if (!endedFreeze) {
    /* 常态停车: 面板常显最后已知电量/续航 + 车速 0, 最后一段行程的时长/
       四格 (2026-09-27 用户点名), 地图画最后一程轨迹 + 车位点
       (lvDrawLastTrack, 2026-09-27 用户点名) */
    $("#lv-title").textContent = "状态：驻车";
    showState("live");            // #live 常驻 (booting 只盖首轮响应前)
    if (!lvMap) initMap();        // 建图同样等 #live 亮出来 (白板教训)
    parkedS = s;                  // 地图就位前先记下, 就位后补画
    lvRenderParked(s);
    lvDrawLastTrack(s);
  }
}

/* ---------- 地图尽力而为: 失败不挡统计, 只占位提示 ---------- */
async function initMap() {
  if (lvMap) return;                          // 防重 (enterDriving 每次行程切换都问)
  const gen = lvGen;
  try {
    await mapLib.ready();   // 配置 + 引擎脚本 (高德单服务商, 要 Key)
    if (gen !== lvGen) return;
    lvMap = mapLib.createMap("lv-map", { zoom: 16, center: [114.05, 22.55] });
    lvMap.on("complete", () => {   // 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染
      const nudge = () => { if (lvMap && lvMap.getFeatures) lvMap.setFeatures(lvMap.getFeatures()); };
      setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);
    });
    // iOS Safari 双指缩放劫持成整页缩放: 手势只给地图
    for (const ev of ["gesturestart", "gesturechange"])
      document.getElementById("lv-map").addEventListener(ev, e => e.preventDefault());
    if (cur && cur.driving) {   // 地图就位前首轮渲染可能已过: 补画车点 + 轨迹
      lvRender(cur);
      refreshTrack();
    } else if (parkedS) {       // 停车常显态同样补画 (车点/面板数据/最后一程轨迹)
      lvRenderParked(parkedS);
      lvDrawLastTrack(parkedS);
    }
  } catch (e) {
    if (gen === lvGen) $("#map-fallback").hidden = false;
  }
}

/* ============================ 生命周期 ============================ */
document.addEventListener("visibilitychange", () => {   // 从后台切回立即刷新
  if (!document.hidden && !$("#view-live").hidden) poll();
});

/* 手势面: 面板区 (仪表/电池/格子) 右划开抽屉/下拉刷新; 首帧等待也整面;
   画布本体 touch-action:none 全给地图引擎, 卡内 40px 左缘条 (#lv-edge) +
   视图层缝条 (#lv-gutter, 2026-10-04 补: 舞台两侧 14px 出血缝里的右划
   谁也接不到 —— 用户报「划了好多次才打开」, 足迹页 #fp-gutter 同款接力)
   一起覆盖到物理屏缘。ptrMove 挂整舞台: 下拉时标题/面板/画布一体跟手,
   不再面板单独沉进画布后面 (2026-10-04 用户点名「要一个整体」)。 */
const lvStage = $(".live-stage");
bindGestures($("#lv-panels"), { drawer: true, ptr: true, onRefresh: poll, ptrMove: lvStage });
bindGestures($("#booting"), { drawer: true, ptr: true, onRefresh: poll, ptrMove: lvStage });
bindGestures($("#lv-edge"), { drawer: true });
bindGestures($("#lv-gutter"), { drawer: true, ptr: true, onRefresh: poll, ptrMove: lvStage });

/* 缝条取证 (2026-10-04, 足迹页 fp 探针同款): 起手/收手/被抢 (cancel —— 抢
   走的触摸没有 end, 正是 tesla-gesture 自愈要医的病) 三笔 + 首启信标,
   再犯翻服务日志就能定罪到具体哪一环 (抽屉开张信标在足迹页脚本里全局
   包了 openDrawer, 状态页也吃得到)。 */
const lvGutProbe = new Map();
let lvGutN = 0, lvBootedDiag = false;
$("#lv-gutter").addEventListener("touchstart", e => {
  const t = e.changedTouches[0];
  lvGutProbe.set(t.identifier, [t.clientX, t.clientY]);
  if (lvGutN++ < 10)
    diag("lv_gutter_touch", { x: Math.round(t.clientX), y: Math.round(t.clientY) });
}, { passive: true });
$("#lv-gutter").addEventListener("touchend", e => {
  for (const t of e.changedTouches) {
    const s = lvGutProbe.get(t.identifier);
    lvGutProbe.delete(t.identifier);
    if (s && lvGutN++ < 10)
      diag("lv_gutter_end", { dx: Math.round(t.clientX - s[0]), dy: Math.round(t.clientY - s[1]) });
  }
}, { passive: true });
$("#lv-gutter").addEventListener("touchcancel", e => {
  for (const t of e.changedTouches) {
    if (lvGutProbe.delete(t.identifier) && lvGutN++ < 10)
      diag("lv_gutter_cancel", { x: Math.round(t.clientX), y: Math.round(t.clientY) });
  }
}, { passive: true });

function lvShow() {
  lvGen++;
  if (!lvBootedDiag) { lvBootedDiag = true; diag("lv_boot", {}); }   // 首启信标: 确认手机真跑上 v13 (排查旧缓存混跑)
  $("#map-fallback").hidden = true;   // 上次失败的占位先收起, 这轮重试
  poll();                             // 建图在驾驶态 (enterDriving), 这里只探状态
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
  endedFreeze = false; parkedS = null;   // 定格/补画状态不过夜
  parkedTrackKey = null;
  $("#lv-title").textContent = "状态";   // 标题归中性, 首轮状态回来再定两态
  showState("booting");        // 回来时从等待态重新起
}
registerView("live", {
  title: "驾驶",
  el: $("#view-live"),
  show: lvShow,
  hide: lvHide,
  refresh: poll,   // 下拉刷新 (换时间档对实时页无意义, 轮询本就不带时间参)
});
