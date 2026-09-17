// map-tracks-render.js — 足迹地图页 (2/5): 轨迹绘制 —— 分块异步绘制 (每帧一小批,
// 不卡主线程) + GPS 断档拆多段折线 + 点击选中高亮与行程信息底部弹层。
// 由 map.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 map.html
// 里的顺序加载, 跨模块引用走全局); 底座在 map-page.js,
// 缩放渐进细化在 map-tracks-refine.js, 数据刷新与启动在 map-boot.js, 筛选
// UI 与收尾在 map-filters.js。
/* global $, diag, showLoading, showRefineTip, scheduleRefine, refineSelected,
          GCJ02, TrackUtil, map: writable, overlays: writable, selected: writable,
          selectedId: writable, tracks: writable, tracksById: writable,
          coarseById: writable, detailLines, detailBand: writable,
          renderGen: writable, detailSeq: writable */
/* exported renderTracks, makeTrackLines, selectTrack, closeSheet, selectedId,
          tracks, tracksById, detailBand, detailSeq */
"use strict";
// 分块异步绘制: 上千条线连坐标换算一次性做完会卡死主线程几秒,
// 每帧只画一小批, 期间页面可交互, 加载层实时显示进度
function renderTracks(list) {
  return new Promise(done => {
    const gen = ++renderGen;
    detailSeq++;                       // 作废在途的细化请求
    detailLines.clear();
    detailBand = null;                 // 粗线重画完成后按当前缩放重新细化
    showRefineTip(false);              // 重渲染阶段由大加载层接管提示
    if (selected) selected.forEach(l => l.setOptions({ strokeOpacity: 0.45, strokeWeight: 2, zIndex: 50 }));
    selected = null; selectedId = null;
    closeSheet();
    if (overlays.length) map.remove(overlays);
    overlays = [];
    coarseById = new Map();
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
        const lines = makeTrackLines(t.pts, t);
        batch.push(...lines);
        coarseById.set(t.id, lines);
      }
      map.add(batch);
      overlays = overlays.concat(batch);
      if (i < total) {
        $("#loading-text").textContent = "正在绘制轨迹 " + i + " / " + total + "…";
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

function makeTrackLines(pts, t) {   // 一条轨迹因 GPS 断档可能拆成多段折线
  const lines = TrackUtil.splitGaps(pts).map(seg => {
    const line = new AMap.Polyline({
      path: seg.map(p => GCJ02.wgs84ToGcj02(p[0], p[1])),  // WGS-84 → GCJ-02
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
  refineSelected(t);
  map.setFitView(lines, false, [70, 70, 70, 240]);
  $("#sh-date").textContent = t.date;
  $("#sh-km").innerHTML = t.km + "<small>km</small>";
  const m = t.min || 0;
  $("#sh-dur").textContent = m >= 60 ? Math.floor(m / 60) + " 小时 " + (m % 60) + " 分" : m + " 分钟";
  $("#backdrop").classList.add("show");
  $("#sheet").classList.add("show");
}
function closeSheet() {
  if (selected) selected.forEach(l => l.setOptions({ strokeOpacity: 0.45, strokeWeight: 2, zIndex: 50 }));
  selected = null;
  selectedId = null;
  $("#backdrop").classList.remove("show");
  $("#sheet").classList.remove("show");
}
