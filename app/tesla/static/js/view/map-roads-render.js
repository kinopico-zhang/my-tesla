// view/map-roads-render.js — 足迹地图「走过的路」绘制 (道路层, 2026-09-29):
// 已证实段按当前全局格计数 (roadCells) 切段上连续热力色阶 (1 次暗蓝 → 青
// → 金 → 当前筛选最多次数红, 对数刻度渐变 —— 2026-09-29 用户点名「次数
// 用热力图连续的颜色来表示」), 相邻段共享端点不断线; 折线 zIndex 按次数档
// 递增 (2026-09-30 用户点名「频繁的轨迹不应该被偶尔的轨迹遮挡, 越频繁的
// 路越要在上面的图层」—— 常走的路永远压着偶走的路, 推断层垫底); 推断层
// (gaps: 规划
// 补的/直连的/对账不过整程降级的) 画灰虚线「可能走过」—— 2026-09-29 用户
// 点名「不能有独立的道路, 没连上的调导航 API 推断, 虚线连接」, 不进次数
// 计数。点路不弹详情卡 (同日用户点名「点击路不要弹窗」—— 次数看颜色就
// 行, 点路选中/底部详情卡整链退役)。
// 时间回放走的是另一把计数 (playStat: 走到当时为止, 2026-10-02 用户点名
// 「一开始的路径不是黄的, 应该越来越黄」—— 同一条路越走越热, 见文末
// roadPlay* 一族)。
// 2026-10-02 性能批 (用户报「足迹地图很卡」, 自动开播起每开必演暴露的):
// 显示路径按缩放抽稀 (roadDecStep → thinFlat, 低倍一笔百米一点, 顶点数
// 掉一个量级)、bbox 角点换算 (逐点 gcj 是打开地图的隐藏大头)、回放升档
// 重染 120ms 合批 (挨帧重染同一批热路是走带卡顿的大头)。
// 缩放 <15 级时证实段只画主色单条折线降级 (全量分段折线数千条, 小屏设备
// 低倍下拖不动; 虚线段数有界不降级) —— 跨 15 级由缩放收尾的防抖
// (scheduleRoadZoom, 取代已退役的细化循环) 触发 redrawRoads 换画; 同档连
// 爬两级也整版重抽细一遍 (10-02 修「放大路径精度太低」: 线停在起画缩放的
// 抽稀精度, 低倍画的百米一点放到高倍就是几十像素一折)。
// ≥15 级只画视野内的路 (2026-09-29 手机端放到最大整页崩: 全量分段折线
// 几万条 Polyline 对象把 iOS 内存压爆 —— 视野外的摘线, 平移回来同档补线,
// 平移/缩放收尾的 roadsViewportSync 防抖增删)。分档线 13→15 且档位一律看
// 实时缩放, 不看 roadBand 变量 (变量等 350ms 换画防抖才追上, 跨档缩小的
// 当口还停在高档, 放大的视野被按高档口径一口气补出整城的分段线 —— 同日
// 用户反馈「放大再缩小, 页面卡死」即此; 且 13 级一屏本就装得下一个都会
// 区的行程, 视野裁剪形同虚设, 15 级视野 ~2km 才真小)。图例 roadLegend
// (多—少渐变条) 也在这层。
/* global mapLib, map, mapReady, RoadsGrid, pathFromFlat,
          roadCells, roadCellsById, roadMax, tracksById, linesById, renderGen,
          fpPlaying,
          overlays: writable */
/* exported makeRoadLines, roadLegend, roadBandSync,
           scheduleRoadZoom, roadZoomCrossed, redrawRoads, roadsViewportSync,
           roadsInView, roadInViewNow,
           roadPlayReset, roadPlayMerge, roadPlayBump, roadPlayEnd */
"use strict";
const ROAD_ZOOM = 15;    // 之上画分段桶色 (只画视野内), 之下每程主桶单线降级
                         // (原 13: 一屏还是整城的程数, 视野裁不住 —— 2026-09-29
                         //  「放大再缩小卡死」, 15 级视野 ~2km 才真小得住)
const VIEW_PAD = 0.6;    // 视野判定放宽 (bbox 相交的边距 = 视口的 60%: 平移不闪)
const ROAD_OPT = { strokeOpacity: 0.55, strokeWeight: 3,
                   lineJoin: "round" };   // zIndex 不在这层定: 证实线按次数档
                                         // 逐条抬 (60+b), 越频繁越靠上
const GUESS_OPT = { strokeColor: "#8e99ab", strokeOpacity: 0.6,
                    strokeWeight: 2, strokeStyle: "dashed",
                    strokeDasharray: [8, 6], zIndex: 55,
                    lineJoin: "round" };
let roadBand = 0;        // 当前道路渲染档: 0=低倍主桶单线, 1=分段桶色
let roadDrawnZoom = 0;   // 屏上线起画时的缩放 (同档内往里爬 ≥2 级整版换细一遍)
let roadRedrawGen = 0;   // 换画代号: 新一轮整版渲染接管时作废 (它会重画全部)
let roadZoomTimer = null;   // 跨档换画防抖 (缩放稳定后再换)
let viewSyncTimer = null;   // 平移/缩放收尾的视野增删防抖

function roadDecStep() {   // 显示抽稀阈 (度): ~1.5 个 CSS 像素的地面跨度
  // 缩得越低阈越大 (抽得越狠), 高倍自动缩到米级 (等于不抽)。折线的渲染
  // 成本随顶点数走 —— 拟合路径十几米一个点, 低倍下全窝在亚像素里
  return 540 / (256 * Math.pow(2, map ? map.getZoom() : 11));
}

function dominantStep(cells) {   // 该程最常处的格次数档 → 色阶档 (低倍单线的色)
  /* 取「众数」不取「最大」(2026-09-29 用户问「为什么放大后颜色会变」):
     低倍一条线只能一个色 —— 按最热格上色, 一条 95% 只走过 1 次的路只因
     压着一段常走的共线整条标红, 放大到分段上色又变回蓝, 像整条变色。
     改成按走过长度加权的最常见档: 低倍的色 = 高倍下占大头的色, 跨档
     只多出细节, 不再整条翻转。 */
  const hist = new Map();
  if (cells) for (const k of cells) {
    const b = RoadsGrid.stepOf(RoadsGrid.cellCount(roadCells.get(k) || 0) || 1,
                               roadMax);
    hist.set(b, (hist.get(b) || 0) + 1);
  }
  let best = 0, n = -1;
  for (const [b, c] of hist) if (c > n || (c === n && b > best)) { best = b; n = c; }
  return best || RoadsGrid.stepOf(1, roadMax);
}

/* ---------- 回放热力累计 (map-roads-playback 专用) ---------- */
/* 回放的色不是终态色 (2026-10-02 用户点名「一开始的路径不是黄的, 应该
   越来越黄」): 一条路按「回放到当时为止走过几次」上色 —— 累计计数
   playStat 与正常层同一把尺 (对数刻度上限仍是全局 roadMax), 走到最后
   正好收敛回终态色。升档的格经 playCellIdx (格 → 盖它的回放线) 找回早先画
   的线重染; 低倍线重算众数档 (与 dominantStep 同口径), 高倍线取最热格。 */
let playStat = null;        // 回放累计格计数 (格键 → packStat); null = 非回放
const playCellIdx = new Map();  // 格键 → 盖它的回放线 (升档重染索引)
let bumpAt = 0;                 // 上次重染冲刷时刻 (合批窗)
const bumpSoon = [];            // 窗内攒着的升档格 (冲刷时一并染)

function playStepOf(k) {   // 累计里一格的色阶档 (与 dominantStep 同款 || 1 保底)
  return RoadsGrid.stepOf(RoadsGrid.cellCount(playStat.get(k) || 0) || 1, roadMax);
}
function playDomStep(cells) {   // 低倍主档: 走过长度加权的常见档 (读累计)
  const hist = new Map();
  if (cells) for (const k of cells) {
    const b = playStepOf(k);
    hist.set(b, (hist.get(b) || 0) + 1);
  }
  let best = 0, n = -1;
  for (const [b, c] of hist) if (c > n || (c === n && b > best)) { best = b; n = c; }
  return best || RoadsGrid.stepOf(1, roadMax);
}
function playMaxStep(cells) {   // 高倍回放线的档: 盖的格里最热
  let b = 0;
  if (cells) for (const k of cells) { const s = playStepOf(k); if (s > b) b = s; }
  return b || RoadsGrid.stepOf(1, roadMax);
}
function roadPlayReset() {   // 进回放/拖进度重铺: 累计清零 (色从冷起)
  playStat = new Map();
  playCellIdx.clear();
  bumpSoon.length = 0;
  bumpAt = 0;
}
function roadPlayMerge(t) {  // 一程并进累计 (计数口径同 mergeCells), 返升档的格
  const day = RoadsGrid.dayOrdOf(t.date || "");
  const per = new Map();
  for (const k of (roadCellsById.get(t.id) || [])) per.set(k, (per.get(k) || 0) + 1);
  const up = [];
  for (const [k, c] of per) {
    const old = playStat.get(k) || 0;
    const oc = RoadsGrid.cellCount(old), nc = oc + c;
    playStat.set(k, RoadsGrid.packStat(nc, Math.max(RoadsGrid.cellDay(old), day)));
    if (RoadsGrid.stepOf(nc, roadMax) > RoadsGrid.stepOf(oc || 1, roadMax)) up.push(k);
  }
  return up;
}
function roadPlayBump(up) {  // 升档的格 → 盖它的回放线重染 (一线一次, 不重算)
  // 120ms 合批窗: 走带每帧并一程, 挨帧重染同一批热路是卡顿大头 —— 窗内
  // 的升档格攒着, 到点一次冲刷 (同窗同线只染一次; playStat 已并到最新,
  // 染出来的就是最新档, 不怕晚)
  for (const k of up) bumpSoon.push(k);
  const now = performance.now();
  if (now - bumpAt < 120) return;
  bumpAt = now;
  const cells = bumpSoon.splice(0);
  const touched = new Set(), domCache = new Map();
  // domCache: 同一程的低倍线共享整程格序列, 众数档只算一遍
  for (const k of cells) for (const line of playCellIdx.get(k) || []) touched.add(line);
  for (const line of touched) {
    let b;
    if (line._dom) {
      b = domCache.get(line._cells);
      if (b === undefined) domCache.set(line._cells, b = playDomStep(line._cells));
    } else b = playMaxStep(line._cells);
    if (b === line._step) continue;
    line._step = b;
    line.setOptions({ strokeColor: RoadsGrid.stepColor(b), zIndex: 60 + b });
  }
}
function roadPlayEnd() {     // 收场: 累计与索引撤 (索引攥着线对象, 不清会漏)
  playStat = null;
  playCellIdx.clear();
  bumpSoon.length = 0;
}

function gbbOf(t) {   // 渲染坐标 bbox (懒算缓存在 t.gbb): 视野判定/汇总共用
  if (!t.gbb) {
    const pts = t.pts;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let i = 0; i < pts.length; i += 2) {   // WGS 域先框 (纯算术 —— 逐点
      if (pts[i] < x0) x0 = pts[i];             // gcj 是打开地图的隐藏大头,
      if (pts[i] > x1) x1 = pts[i];             // 上千程 × 上千点白换算一遍)
      if (pts[i + 1] < y0) y0 = pts[i + 1];
      if (pts[i + 1] > y1) y1 = pts[i + 1];
    }
    // 只换算两角: GCJ 偏移在一程跨度内渐变是米级, 视野判定有 60% 放宽、
    // 跟框有 2% 呼吸边, 这点误差无感 (t.gbb 依旧当渲染坐标用)
    const c0 = mapLib.gcj([x0, y0]), c1 = mapLib.gcj([x1, y1]);
    t.gbb = [c0[0], c0[1], c1[0], c1[1]];
  }
  return t.gbb;
}

function roadInView(t) {   // 道路 bbox 与放宽后的视野相交 (≥15 级的取舍口径)
  const b = map.getBounds();
  if (!b) return true;                        // 拿不到视野: 保守当可见
  const sw = b.getSouthWest ? b.getSouthWest() : b.southwest;
  const ne = b.getNorthEast ? b.getNorthEast() : b.northeast;
  const vw = (ne.lng - sw.lng) * VIEW_PAD, vh = (ne.lat - sw.lat) * VIEW_PAD;
  const g = gbbOf(t);
  return g[0] <= ne.lng + vw && g[2] >= sw.lng - vw &&
         g[1] <= ne.lat + vh && g[3] >= sw.lat - vh;
}

function roadsInView(list) {   // 渲染集里该画的子集: 低倍全量, 高倍只画视野内
  /* 档位看实时缩放, 不看 roadBand 变量 —— 变量要等 350ms 换画防抖才追上,
     跨档缩小的当口它还停在高档, 放大后的视野会被当成「高倍」过滤 (等于
     没滤): 整城的程全数放行, 正是 2026-09-29「缩小卡死」的放大器 */
  return (!map || map.getZoom() < ROAD_ZOOM) ? list : list.filter(roadInView);
}

function roadInViewNow(t) {   // 流式下载期「到一条画一条」的闸 (低倍全画)
  return !map || map.getZoom() < ROAD_ZOOM || roadInView(t);
}

function makeRoadLines(t, live) {   // 一条拟合路径 → 折线组: 证实段热力色 + 推断层虚线
  // live = 回放层 (map-roads-playback): 色读走到当时为止的累计 playStat, 并
  // 给升档重染记索引; 正常层不传 —— 读全局 roadCells 的终态色 (流式下载期
  // appendIfVisible 回放中也走这里, 必须保持终态口径, 收场亮回才是终色)
  const pts = t.pts;
  if (!pts || pts.length < 4) return [];
  gbbOf(t);
  const cells = roadCellsById.get(t.id);
  const g = t.g || [];
  const spans = RoadsGrid.rowSpans(pts, g);   // 已证实段 (推断层之外)
  const band = map && map.getZoom() >= ROAD_ZOOM ? 1 : 0;   // 档随起画时的实时缩放
  const dstep = roadDecStep();   // 显示抽稀阈 (只喂 path, 格计数仍吃全量点)
  let runs;
  if (band === 0)   // 低倍降级: 证实段整段主档一色单线; 回放读累计的众数档
    // (全程格子一起算 —— 与正常层同一口径, 走到最后色正好收敛; 各段共用全程
    //  格序列, 升档重染时一程的段一起换色, 不出现一段一段不同色)
    runs = spans.map(s => (
      { b: live ? playDomStep(cells) : dominantStep(cells),
        i0: s[0], i1: s[1] - 2, ks: live ? cells : null }));
  else {
    runs = [];
    for (const s of spans)     // 各证实段独立切段 (段间隔着推断层)
      for (const r of RoadsGrid.runsByStep(pts.slice(s[0], s[1]),
                                           live ? playStat : roadCells, roadMax))
        runs.push({ b: r.b, i0: s[0] + r.i0, i1: s[0] + r.i1 });
  }
  const lines = [];
  lines._band = band;   // 档位记账 (实时口径, 不吃 roadBand 变量的滞后):
                        // 平移/换画时同档不重建
  for (const r of runs) {
    const line = mapLib.polyline(Object.assign({}, ROAD_OPT, {
      path: pathFromFlat(pts.slice(r.i0, r.i1 + 2), dstep),
      strokeColor: RoadsGrid.stepColor(r.b),
      // 图层序 = 频次序 (2026-09-30 用户点名「越频繁的路越要在上面的图层」):
      // 次数档 0..11 → 60..71, 常走的路永远压着偶走的路; 推断层钉 55 在一切
      // 证实线之下。低倍主色单线同理 (b = 该程主档) —— 两档模式都走这条
      zIndex: 60 + r.b,
    }));
    if (live) {   // 回放线记账: 后面再走到这些格要升档重染 (越来越热)
      line._cells = r.ks || RoadsGrid.cellsForFlat(pts.slice(r.i0, r.i1 + 2));
      line._dom = band === 0;   // 低倍线按众数重算 (与正常层同口径), 高倍线按最热
      line._step = r.b;
      for (const k of line._cells) {
        // 只登记还会再热的格: 全局计数 ≤1 的格到头也是 1 次, 档不会再升
        if (RoadsGrid.cellCount(roadCells.get(k) || 0) < 2) continue;
        let a = playCellIdx.get(k);
        if (!a) playCellIdx.set(k, a = []);
        a.push(line);
      }
    }
    lines.push(line);
  }
  for (const gi of g) {        // 推断层: 灰虚线「可能走过」(不进次数计数)
    const a = Math.max(0, gi[0] | 0) * 2;
    const b = Math.min(pts.length / 2 - 1, gi[1] | 0) * 2;
    if (b - a < 2) continue;   // 不足一节的区间跳过
    lines.push(mapLib.polyline(Object.assign({}, GUESS_OPT, {
      path: pathFromFlat(pts.slice(a, b + 2), dstep) })));
  }
  return lines;
}

function roadLegend(show) {   // 图例显隐: 多—少渐变条 (2026-09-29 用户点名
  // 「去掉虚线, 去掉数字, 只保留多和少」—— 虚线样例/次数帽/拟合进度行整排退役)
  const lg = document.getElementById("fp-legend");
  if (lg) lg.hidden = !show;
}

function roadBandSync() {   // 渲染起手/收尾: 道路档位对齐当前缩放
  roadBand = map && map.getZoom() >= ROAD_ZOOM ? 1 : 0;
  roadDrawnZoom = map ? map.getZoom() : 0;   // 屏上线按这个缩放抽的稀
}

function scheduleRoadZoom() {   // 缩放/下载收尾来排一次跨档检查 (350ms 防抖)
  clearTimeout(roadZoomTimer);
  roadZoomTimer = setTimeout(() => {
    if (map && mapReady) roadZoomCrossed(map.getZoom());
  }, 350);
}

function drawnBand() {   // 屏上线的档位 (以第一组为准; 空屏用变量兜)
  for (const lines of linesById.values()) return lines._band;
  return roadBand;
}

function roadZoomCrossed(zoom) {   // 防抖到点来问: 档位变没变 (变则换画)
  const rb = zoom >= ROAD_ZOOM ? 1 : 0;
  if (rb === drawnBand()) {
    roadBand = rb;
    /* 同档往里连爬两级: 起画时按低倍抽稀的线在高倍下显棱角 —— 整版重铺
       一遍细的 (往外缩不重铺: 细线缩小看没有棱角, 白换)。得带 repath 强制
       换: 早先这路是空转, redrawRoads 里「同档已在屏不重建」把重铺全跳了
       (10-02 用户报「放大路径精度太低」即此)。高倍只动视野内的, 也走这条 */
    if (zoom - roadDrawnZoom >= 2) redrawRoads(true);
    return;
  }
  roadBand = rb;
  redrawRoads();
}

function syncOverlays() {   // overlays 跟 linesById 对账 (摘线/补线后)
  overlays = [];
  for (const lines of linesById.values()) overlays.push(...lines);
}

function _dropOut(keep) {   // 摘掉 keep 之外的道路线 (视野外/旧档)
  for (const [id, lines] of linesById) {
    if (keep.has(id)) continue;
    map.remove(lines);
    linesById.delete(id);
  }
  syncOverlays();
}

function redrawRoads(repath) {   // 跨 15 级换画: 低倍全量主桶单线 / 高倍只画视野内
  if (fpPlaying) return;   // 时间回放中 (map-roads-playback): 换画让路, 停止时整版重建
  const gen = ++roadRedrawGen, rgen = renderGen;
  roadDrawnZoom = map ? map.getZoom() : 0;   // 本轮按这个缩放抽稀
  const roads = roadsInView([...tracksById.values()]);   // 高倍: 只换画视野内的
  const keep = new Set(roads.map(t => t.id));
  const CHUNK = 80;
  let i = 0;
  (function step() {
    // roadRedrawGen 变 = 又跨档重画; renderGen 变 = 新一轮整版渲染接管
    // (它自己会重画全部) —— 两种情况本轮都作废
    if (gen !== roadRedrawGen || rgen !== renderGen || !map) return;
    const end = Math.min(i + CHUNK, roads.length);
    const rb = map.getZoom() >= ROAD_ZOOM ? 1 : 0;   // 档看实时缩放 (同记账口径)
    for (; i < end; i++) {
      const t = roads[i];
      const old = linesById.get(t.id);
      // 同档已在屏: 不重建 —— repath 例外 (同档重抽稀: 屏上线按旧缩放抽的)
      if (old && old._band === rb && !repath) continue;
      if (old) map.remove(old);
      const lines = makeRoadLines(t);
      map.add(lines);
      linesById.set(t.id, lines);
    }
    if (i < roads.length) { requestAnimationFrame(step); return; }
    _dropOut(keep);   // 收尾: 视野外/换下来的线摘掉 (低倍 keep=全量, 无摘)
  })();
}

function roadsViewportSync() {   // 平移/缩放收尾 (250ms 防抖): 高倍按视野增删
  clearTimeout(viewSyncTimer);
  viewSyncTimer = setTimeout(() => {
    /* 退出闸看实时缩放, 不看 roadBand 变量: 跨档缩小的当口 350ms 换画防抖
       还没到, 变量还停在高档 —— 缩小后的大视野上按高档口径补分段线, 一次
       就是整城 (2026-09-29「放大再缩小, 页面卡死」即此); 低倍整版换画由
       roadZoomCrossed 接管, 这里不抢跑 */
    if (fpPlaying || !map || !mapReady || map.getZoom() < ROAD_ZOOM) return;
    const inView = roadsInView([...tracksById.values()]);
    _dropOut(new Set(inView.map(t => t.id)));          // 先摘视野外的 (腾内存)
    const add = inView.filter(t => !linesById.has(t.id));   // 已在屏 (同档)
    const gen = roadRedrawGen, rgen = renderGen;   // 换画/整版渲染接管则作废
    let i = 0;
    (function step() {   // 补线分帧 (同 redrawRoads 的 80/帧): 大平移几百条也不卡一帧
      if (gen !== roadRedrawGen || rgen !== renderGen || !map ||
          map.getZoom() < ROAD_ZOOM) return;   // 补到一半跨回低倍: 作废
      const end = Math.min(i + 80, add.length);
      for (; i < end; i++) {
        const lines = makeRoadLines(add[i]);
        map.add(lines);
        linesById.set(add[i].id, lines);
      }
      syncOverlays();
      if (i < add.length) requestAnimationFrame(step);
    })();
  }, 250);
}
