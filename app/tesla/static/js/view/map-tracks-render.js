// view/map-tracks-render.js — 足迹地图视图 (壳版 2/5): 绘制 —— 只画
// 「走过的路」(2026-09-29 用户点名「只显示走过的路就行了, 不需要显示每
// 一条轨迹」: 原始轨迹层整链退役, 没拟合到的程等 worker 拟合好再
// 出现)。分块异步绘制 (每帧一小批, 不卡主线程) + 流式下载期到一条画
// 一条 (地图跟着新路扩大)。点路不弹详情卡 (同日用户点名「点击路不要
// 弹窗」, 选中态/底部详情弹层整链退役)。
// ≥15 级只画视野内的路 (2026-09-29 手机端放到最大整页崩: 全量分段折线
// 几万条对象把 iOS 内存压爆) —— 视野集 roadsInView 由 map-roads-render
// 给; 高倍不重铺视野 (用户正在看的地方不被 setFitView 拽走), 平移收尾
// 的 roadsViewportSync 按视野增删。
// 底座在 view/map-page.js, 分桶上色/图例/跨 15 级换画在
// view/map-roads-render.js, 同步与启动在 view/map-boot.js,
// 筛选 UI 与收尾在 view/map-filters.js。
/* global $, diag, showLoading, mapLib, manifestIdx, fpRowVisible, map,
          overlays, tracks, tracksById, linesById,
          renderGen, makeRoadLines, roadLegend, roadBandSync,
          roadsInView, roadInViewNow, roadBand,
          overlays: writable,
          tracks: writable, tracksById: writable, linesById: writable,
          renderGen: writable */
/* exported renderTracks, appendIfVisible, pathFromFlat, tracks, tracksById */
"use strict";
let renderedIds = new Set();   // 已入账的路 (流式下载期防重复画/重复记账)

// 分块异步绘制: 上千条线连坐标换算一次性做完会卡死主线程几秒,
// 每帧只画一小批, 期间页面可交互, 加载层实时显示进度
function renderTracks(list) {
  return new Promise(done => {
    const gen = ++renderGen;
    if (!map) return done();   // 实例刚被 maplib:swap 销毁: 本轮作废, 重建后 fpSync 全量重画
    if (overlays.length) map.remove(overlays);
    overlays = [];
    linesById = new Map();
    renderedIds = new Set(list.map(t => t.id));
    tracks = list;
    tracksById = new Map(list.map(t => [t.id, t]));
    const total = list.length;
    if (!total) { done(); roadLegend(false); return; }
    roadBandSync();   // 起手先定档: 高倍只画视野内的 (渲染量爆炸的闸)
    const draw = roadsInView(list);
    showLoading(true, "正在绘制走过的路 0 / " + draw.length + "…");
    const CHUNK = 50;
    let i = 0;
    (function step() {
      if (gen !== renderGen) { done(); return; }   // 已被新一轮渲染取代
      const end = Math.min(i + CHUNK, draw.length);
      const batch = [];
      for (; i < end; i++) {
        const lines = makeRoadLines(draw[i]);   // 分桶上色 (map-roads-render)
        batch.push(...lines);
        linesById.set(draw[i].id, lines);
      }
      map.add(batch);
      overlays = overlays.concat(batch);
      if (i < draw.length) {
        $("#fp-loading-text").textContent = "正在绘制走过的路 " + i + " / " + draw.length + "…";
        requestAnimationFrame(step);
      } else {
        // 低倍才重铺视野; 高倍保住用户正看的地方 (平移收尾按视野增删)
        if (roadBand === 0) map.setFitView(overlays, false, [40, 40, 40, 40]);
        showLoading(false);
        roadBandSync();          // setFitView 后档位可能变 (跨档换画交给缩放收尾防抖)
        roadLegend(true);        // 图例亮起 (多—少渐变条)
        diag("tracks_rendered", { n: overlays.length, band: roadBand });
        done();
      }
    })();
  });
}

function appendIfVisible(t) {   // 流式下载期: 到一条画一条 (当前筛选可见才入账)
  if (!map) return;             // 实例刚被 maplib:swap 销毁 (重建后 fpSync 重画)
  const row = manifestIdx.get(t.id);
  if (!row || !fpRowVisible(row) || renderedIds.has(t.id)) return;
  renderedIds.add(t.id);
  tracks.push(t);               // 视野内汇总的可见集跟着长
  tracksById.set(t.id, t);      // 平移回来时 roadsViewportSync 从这找路
  if (!roadInViewNow(t)) return;   // 高倍视野外: 只记账不占屏 (平移回来再画)
  const lines = makeRoadLines(t);
  map.add(lines);
  overlays = overlays.concat(lines);
  linesById.set(t.id, lines);
  roadLegend(true);             // 第一条路上屏 → 图例亮起
}

function pathFromFlat(seg) {   // 扁平段 [lng, lat, ...] → 渲染坐标路径
  const path = [];
  for (let i = 0; i < seg.length; i += 2)
    path.push(mapLib.gcj([seg[i], seg[i + 1]]));   // WGS-84 → 渲染坐标 (高德 GCJ-02)
  return path;
}
