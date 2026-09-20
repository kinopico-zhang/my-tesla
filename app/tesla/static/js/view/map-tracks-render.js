// view/map-tracks-render.js — 足迹地图视图 (壳版 2/5): 轨迹绘制 —— 分块异步
// 绘制 (每帧一小批, 不卡主线程) + 全精度扁平 pts 的段拆/抽稀 + 流式下载期
// 到一条画一条 (地图跟着轨迹扩大) + 点击选中高亮与行程信息底部弹层。
// v4 起服务端不再抽稀: 概览 ~40 点/条与缩放档位抽稀都在客户端做
// (TrackUtil.decimateFlat); 轨迹本体 (全精度) 在内存/本地库, 细化不请求。
// 底座在 view/map-page.js, 缩放渐进细化在 view/map-tracks-refine.js,
// 同步与启动在 view/map-boot.js, 筛选 UI 与收尾在 view/map-filters.js。
/* global $, diag, showLoading, scheduleRefine, refineSelected, mapLib,
          TrackUtil, manifestIdx, fpRowVisible, map, overlays, selected,
          selectedId, tracks, tracksById, coarseById, detailLines, detailBand,
          detailTier, renderGen, fullIds, refineTimer, overlays: writable,
          selected: writable, selectedId: writable, tracks: writable,
          tracksById: writable, coarseById: writable, detailBand: writable,
          detailTier: writable, renderGen: writable */
/* exported renderTracks, appendIfVisible, makeTrackLines, pathFromFlat,
           selectTrack, closeSheet, selectedId, tracks, tracksById, detailBand */
"use strict";
const COARSE_PER = 40;      // 概览档每条轨迹抽到 ~40 点 (与旧服务端粗轨迹口径一致)
let renderedIds = new Set();   // 已在屏上的轨迹 (流式下载期防重复画)

// 分块异步绘制: 上千条线连坐标换算一次性做完会卡死主线程几秒,
// 每帧只画一小批, 期间页面可交互, 加载层实时显示进度
function renderTracks(list) {
  return new Promise(done => {
    const gen = ++renderGen;
    clearTimeout(refineTimer);         // 上一轮细化续扫作废 (新渲染集自己重排)
    detailLines.clear();
    detailTier.clear();
    detailBand = null;                 // 概览线重画完成后按当前缩放重新细化
    fullIds.clear();
    if (selected) selected.forEach(l => l.setOptions({ strokeOpacity: 0.45, strokeWeight: 2, zIndex: 50 }));
    selected = null; selectedId = null;
    closeSheet();
    if (overlays.length) map.remove(overlays);
    overlays = [];
    coarseById = new Map();
    renderedIds = new Set(list.map(t => t.id));
    tracks = list;
    tracksById = new Map(list.map(t => [t.id, t]));
    const total = list.length;
    if (!total) { done(); return; }
    showLoading(true, "正在绘制轨迹 0 / " + total + "…");
    const CHUNK = 50;
    let i = 0;
    (function step() {
      if (gen !== renderGen) { done(); return; }   // 已被新一轮渲染取代
      const end = Math.min(i + CHUNK, total);
      const batch = [];
      for (; i < end; i++) {
        const t = list[i];
        const lines = makeTrackLines(t, COARSE_PER);
        batch.push(...lines);
        coarseById.set(t.id, lines);
      }
      map.add(batch);
      overlays = overlays.concat(batch);
      if (i < total) {
        $("#fp-loading-text").textContent = "正在绘制轨迹 " + i + " / " + total + "…";
        requestAnimationFrame(step);
      } else {
        map.setFitView(overlays, false, [40, 40, 40, 40]);
        showLoading(false);
        diag("tracks_rendered", { n: overlays.length });
        done();
        scheduleRefine();              // 若已缩放到 13 级以上, 立即细化视野内轨迹
      }
    })();
  });
}

function appendIfVisible(t) {   // 流式下载期: 到一条画一条 (当前筛选可见才画)
  const row = manifestIdx.get(t.id);
  if (!row || !fpRowVisible(row) || renderedIds.has(t.id)) return;
  const lines = makeTrackLines(t, COARSE_PER);
  map.add(lines);
  overlays = overlays.concat(lines);
  coarseById.set(t.id, lines);
  renderedIds.add(t.id);
  tracks.push(t);               // 细化遍历的可见集跟着长
  tracksById.set(t.id, t);
}

function pathFromFlat(seg) {   // 扁平段 [lng, lat, ...] → 渲染坐标路径
  const path = [];
  for (let i = 0; i < seg.length; i += 2)
    path.push(mapLib.gcj([seg[i], seg[i + 1]]));   // WGS-84 → 渲染坐标 (高德 GCJ-02 / OSM 原样)
  return path;
}

function makeTrackLines(t, per) {   // 一条轨迹: 抽稀到 ~per 点 (0=全精度), 断档拆多段折线
  let pts = t.pts;
  if (per && pts.length / 2 > per) pts = TrackUtil.decimateFlat(pts, per);
  const lines = TrackUtil.splitGapsFlat(pts).map(seg => {
    const line = mapLib.polyline({
      path: pathFromFlat(seg),
      strokeColor: "#3987e5", strokeOpacity: 0.45, strokeWeight: 2,
      lineJoin: "round", cursor: "pointer", zIndex: 50,
    });
    line.on("click", () => selectTrack(lines, t));
    return line;
  });
  return lines;
}

function selectTrack(lines, t) {
  if (selected) selected.forEach(l => l.setOptions({ strokeOpacity: 0.45, strokeWeight: 2, zIndex: 50 }));
  selected = lines;
  selectedId = t.id;
  lines.forEach(l => l.setOptions({ strokeOpacity: 1, strokeWeight: 4, zIndex: 99 }));
  refineSelected(t);            // 本地全精度细化 (内存直取, 见 map-tracks-refine.js)
  map.setFitView(lines, false, [70, 70, 70, 240]);
  $("#fp-sh-date").textContent = t.date;
  $("#fp-sh-km").innerHTML = t.km + "<small>km</small>";
  const m = t.min || 0;
  $("#fp-sh-dur").textContent = m >= 60 ? Math.floor(m / 60) + " 小时 " + (m % 60) + " 分" : m + " 分钟";
  $("#fp-backdrop").classList.add("show");
  $("#fp-sheet").classList.add("show");
}
function closeSheet() {
  if (selected) selected.forEach(l => l.setOptions({ strokeOpacity: 0.45, strokeWeight: 2, zIndex: 50 }));
  selected = null;
  selectedId = null;
  $("#fp-backdrop").classList.remove("show");
  $("#fp-sheet").classList.remove("show");
}
