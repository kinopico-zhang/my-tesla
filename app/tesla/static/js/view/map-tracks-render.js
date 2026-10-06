// view/map-tracks-render.js — 足迹地图视图 (壳版 2/5): 绘制 —— 只画
// 「走过的路」(2026-09-29 用户点名「只显示走过的路就行了, 不需要显示每
// 一条轨迹」: 原始轨迹层整链退役, 没拟合到的程等 worker 拟合好再
// 出现)。分块异步绘制 (每帧一小批, 不卡主线程) + 流式下载期到一条画
// 一条 (地图跟着新路扩大)。点路不弹详情卡 (同日用户点名「点击路不要
// 弹窗」, 选中态/底部详情弹层整链退役)。
// 时间回放 (2026-10-01 播放条, map-roads-playback): renderTracks 入口反调
// fpPlayExit(false) —— 换筛选/同步任何重渲染都是对回放态的否决。
// ≥15 级只画视野内的路 (2026-09-29 手机端放到最大整页崩: 全量分段折线
// 几万条对象把 iOS 内存压爆) —— 视野集 roadsInView 由 map-roads-render
// 给; 高倍不重铺视野 (用户正在看的地方不被 setFitView 拽走), 平移收尾
// 的 roadsViewportSync 按视野增删。
// 底座在 view/map-page.js, 分桶上色/图例/跨 15 级换画在
// view/map-roads-render.js, 同步与启动在 view/map-boot.js,
// 筛选 UI 与收尾在 view/map-filters.js。
/* global diag, mapLib, RoadsGrid, manifestIdx, fpRowVisible, map,
          overlays, tracks, tracksById, linesById,
          renderGen, makeRoadLines, roadLegend, roadBandSync,
          roadsInView, roadInViewNow, roadBand, fpPlaying, fpPlayExit,
          overlays: writable,
          tracks: writable, tracksById: writable, linesById: writable,
          renderGen: writable */
/* exported renderTracks, appendIfVisible, pathFromFlat, tracksRendering,
            tracks, tracksById */
"use strict";
let renderedIds = new Set();   // 已入账的路 (流式下载期防重复画/重复记账)
let tracksRendering = false;   // 整版渲染在途 (回放进场快照不完整 → 收场整版重建)

// 分块异步绘制: 上千条线连坐标换算一次性做完会卡死主线程几秒,
// 每帧只画一小批, 期间页面可交互 (路一段段自己冒出来, 不再有进度条)
// hidden = 暗铺 (2026-10-04 修「播放完又播放了一遍」): 回放收场兜底的重铺
// 明着画就是第二遍回放的观感 (分块渐进冒线 + 收尾 setFitView) —— 批批藏
// 起, 铺完由收场方一帧换装 (回放终帧顶屏, 终色与终态同口径); 收尾的
// setFitView/图例也让给收场方, 镜头留在回放终帧, 换装零跳动
function renderTracks(list, hidden) {
  return new Promise(done => {
    const gen = ++renderGen;
    const fin = () => { tracksRendering = false; done(gen); };   // 在途旗四口全收口; gen 带出去 (暗铺换装对账)
    tracksRendering = true;
    // 实例没了让路; 时间回放中 (fpPlaying, map-roads-playback): 出口钩先收
    // 掉回放态 —— 换筛选/同步任何重渲染都是对回放的否决, 本次渲染接着干
    if (fpPlaying) fpPlayExit(false);
    if (!map) return fin();
    if (overlays.length) map.remove(overlays);
    overlays = [];
    linesById = new Map();
    renderedIds = new Set(list.map(t => t.id));
    tracks = list;
    tracksById = new Map(list.map(t => [t.id, t]));
    const total = list.length;
    if (!total) { fin(); roadLegend(false); return; }
    roadBandSync();   // 起手先定档: 高倍只画视野内的 (渲染量爆炸的闸)
    const draw = roadsInView(list);
    const CHUNK = 50;
    let i = 0;
    (function step() {
      if (gen !== renderGen) { fin(); return; }   // 已被新一轮渲染取代
      const end = Math.min(i + CHUNK, draw.length);
      const batch = [];
      for (; i < end; i++) {
        const lines = makeRoadLines(draw[i]);   // 分桶上色 (map-roads-render)
        batch.push(...lines);
        linesById.set(draw[i].id, lines);
      }
      map.add(batch);
      if (hidden) for (const l of batch) l.hide();   // 暗铺: 藏着入屏, 换装一帧亮
      overlays = overlays.concat(batch);
      if (i < draw.length) {
        requestAnimationFrame(step);
      } else {
        // 低倍才重铺视野; 高倍保住用户正看的地方 (平移收尾按视野增删);
        // 在放也让路 —— 回放中镜头跟框说了算 (10-02 日志定位 9.1↔11 拉锯);
        // 暗铺也让路 (镜头留在回放终帧)
        if (roadBand === 0 && !fpPlaying && !hidden) map.setFitView(overlays, false, [40, 40, 40, 40]);
        roadBandSync();          // setFitView 后档位可能变 (跨档换画交给缩放收尾防抖)
        if (!hidden) roadLegend(true);   // 暗铺的图例随换装亮 (map-roads-playback)
        diag("tracks_rendered", { n: overlays.length, band: roadBand, hidden: !!hidden });
        fin();
      }
    })();
  });
}

function appendIfVisible(t) {   // 流式下载期: 到一条画一条 (当前筛选可见才入账)
  // 实例没了不画; 回放中照画但整组藏起 (正常层本就藏着, 收场 show 亮回,
  // 中途下载的新路一段不落)
  if (!map) return;
  const row = manifestIdx.get(t.id);
  if (!row || !fpRowVisible(row) || renderedIds.has(t.id)) return;
  renderedIds.add(t.id);
  tracks.push(t);               // 视野内汇总的可见集跟着长
  tracksById.set(t.id, t);      // 平移回来时 roadsViewportSync 从这找路
  if (!roadInViewNow(t)) return;   // 高倍视野外: 只记账不占屏 (平移回来再画)
  const lines = makeRoadLines(t);
  if (fpPlaying) for (const l of lines) l.hide();   // 回放中: 跟正常层一起藏着
  map.add(lines);
  overlays = overlays.concat(lines);
  linesById.set(t.id, lines);
  if (!fpPlaying) roadLegend(true);   // 回放中图例保持收起, 浮标说了算
}

function pathFromFlat(seg, step) {   // 扁平段 [lng, lat, ...] → 渲染坐标路径
  // (step = 显示抽稀阈 (度), map-roads-render 的 roadDecStep 按缩放给: 亚像素
  //  顶点抽掉, 折线渲染成本随顶点数走 —— 2026-10-02 用户报「足迹地图很卡」)
  const path = [];
  const use = step ? RoadsGrid.thinFlat(seg, step) : seg;
  for (let i = 0; i < use.length; i += 2)
    path.push(mapLib.gcj([use[i], use[i + 1]]));   // WGS-84 → 渲染坐标 (高德 GCJ-02)
  return path;
}
