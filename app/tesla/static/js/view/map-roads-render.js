// view/map-roads-render.js — 足迹地图「走过的路」绘制 (道路层, 2026-09-29):
// 已证实段按当前全局格计数 (roadCells) 切段上连续热力色阶 (1 次暗蓝 → 青
// → 金 → 当前筛选最多次数红, 对数刻度渐变 —— 2026-09-29 用户点名「次数
// 用热力图连续的颜色来表示」), 相邻段共享端点不断线; 推断层 (gaps: 规划
// 补的/直连的/对账不过整程降级的) 画灰虚线「可能走过」—— 2026-09-29 用户
// 点名「不能有独立的道路, 没连上的调导航 API 推断, 虚线连接」, 不进次数
// 计数。点路不弹详情卡 (同日用户点名「点击路不要弹窗」—— 次数看颜色就
// 行, 点路选中/底部详情卡整链退役)。
// 缩放 <15 级时证实段只画主色单条折线降级 (全量分段折线数千条, 小屏设备
// 低倍下拖不动; 虚线段数有界不降级) —— 跨 15 级由缩放收尾的防抖
// (scheduleRoadZoom, 取代已退役的细化循环) 触发 redrawRoads 换画。
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
          overlays: writable */
/* exported makeRoadLines, roadLegend, roadBandSync,
           scheduleRoadZoom, roadZoomCrossed, redrawRoads, roadsViewportSync,
           roadsInView, roadInViewNow */
"use strict";
const ROAD_ZOOM = 15;    // 之上画分段桶色 (只画视野内), 之下每程主桶单线降级
                         // (原 13: 一屏还是整城的程数, 视野裁不住 —— 2026-09-29
                         //  「放大再缩小卡死」, 15 级视野 ~2km 才真小得住)
const VIEW_PAD = 0.6;    // 视野判定放宽 (bbox 相交的边距 = 视口的 60%: 平移不闪)
const ROAD_OPT = { strokeOpacity: 0.55, strokeWeight: 3, zIndex: 60,
                   lineJoin: "round" };
const GUESS_OPT = { strokeColor: "#8e99ab", strokeOpacity: 0.6,
                    strokeWeight: 2, strokeStyle: "dashed",
                    strokeDasharray: [8, 6], zIndex: 55,
                    lineJoin: "round" };
let roadBand = 0;        // 当前道路渲染档: 0=低倍主桶单线, 1=分段桶色
let roadRedrawGen = 0;   // 换画代号: 新一轮整版渲染接管时作废 (它会重画全部)
let roadZoomTimer = null;   // 跨档换画防抖 (缩放稳定后再换)
let viewSyncTimer = null;   // 平移/缩放收尾的视野增删防抖

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

function gbbOf(t) {   // 渲染坐标 bbox (懒算缓存在 t.gbb): 视野判定/汇总共用
  if (!t.gbb) {
    const pts = t.pts;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let i = 0; i < pts.length; i += 2) {
      const c = mapLib.gcj([pts[i], pts[i + 1]]);
      if (c[0] < x0) x0 = c[0];
      if (c[0] > x1) x1 = c[0];
      if (c[1] < y0) y0 = c[1];
      if (c[1] > y1) y1 = c[1];
    }
    t.gbb = [x0, y0, x1, y1];
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

function makeRoadLines(t) {   // 一条拟合路径 → 折线组: 证实段热力色 + 推断层虚线
  const pts = t.pts;
  if (!pts || pts.length < 4) return [];
  gbbOf(t);
  const cells = roadCellsById.get(t.id);
  const g = t.g || [];
  const spans = RoadsGrid.rowSpans(pts, g);   // 已证实段 (推断层之外)
  const band = map && map.getZoom() >= ROAD_ZOOM ? 1 : 0;   // 档随起画时的实时缩放
  let runs;
  if (band === 0)    // 低倍降级: 证实段整段主档一色单线
    runs = spans.map(s => ({ b: dominantStep(cells), i0: s[0], i1: s[1] - 2 }));
  else {
    runs = [];
    for (const s of spans)     // 各证实段独立切段 (段间隔着推断层)
      for (const r of RoadsGrid.runsByStep(pts.slice(s[0], s[1]), roadCells, roadMax))
        runs.push({ b: r.b, i0: s[0] + r.i0, i1: s[0] + r.i1 });
  }
  const lines = [];
  lines._band = band;   // 档位记账 (实时口径, 不吃 roadBand 变量的滞后):
                        // 平移/换画时同档不重建
  for (const r of runs) {
    const line = mapLib.polyline(Object.assign({}, ROAD_OPT, {
      path: pathFromFlat(pts.slice(r.i0, r.i1 + 2)),
      strokeColor: RoadsGrid.stepColor(r.b),
    }));
    lines.push(line);
  }
  for (const gi of g) {        // 推断层: 灰虚线「可能走过」(不进次数计数)
    const a = Math.max(0, gi[0] | 0) * 2;
    const b = Math.min(pts.length / 2 - 1, gi[1] | 0) * 2;
    if (b - a < 2) continue;   // 不足一节的区间跳过
    lines.push(mapLib.polyline(Object.assign({}, GUESS_OPT, {
      path: pathFromFlat(pts.slice(a, b + 2)) })));
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
  if (rb === drawnBand()) { roadBand = rb; return; }
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

function redrawRoads() {   // 跨 15 级换画: 低倍全量主桶单线 / 高倍只画视野内
  const gen = ++roadRedrawGen, rgen = renderGen;
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
      if (old && old._band === rb) continue;   // 同档已在屏: 不重建
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
    if (!map || !mapReady || map.getZoom() < ROAD_ZOOM) return;
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
