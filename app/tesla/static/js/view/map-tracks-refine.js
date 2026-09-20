// view/map-tracks-refine.js — 足迹地图视图 (壳版 3/5): 缩放渐进细化 ——
// 12 级以下概览 (~40 点/条), 之上按档位换线: 13 级 ~2000 点/条, 14 级
// ~6000, 15 级全精度。坐标本来就整库全精度存在手机本地库里 (v4 全精度
// 下载), 细化纯本地抽稀换线, 不发请求。
// 3.0.1 起按用户口径「先把所有坐标缓存到手机本地, 放大到足够大的时候
// 精细化渲染所有的点」: 13/14 级全库轨迹都换到档, 15 级全库全精度
// (视野内的先换, 其余后台分轮补齐) —— 平移到哪都不闪 40 点粗线; 换档
// 不整版退回概览重来, 每条按自己的目标档增量升/降。分轮限量 (每轮一小
// 批), 没细化完自动续轮, 大库也不卡界面; 选中过的轨迹任何档位都保持
// 全精度。底座在 view/map-page.js, 轨迹绘制与选中在 map-tracks-render.js,
// 同步与启动在 view/map-boot.js, 筛选 UI 与收尾在 view/map-filters.js。
/* global diag, makeTrackLines, map, mapReady, tracks, coarseById,
          detailLines, fullIds, selected: writable, selectedId,
          refineTimer: writable, detailBand: writable, detailTier: writable */
/* exported scheduleRefine, refineVisible, refineSelected, selected */
"use strict";
/* ---------- 缩放渐进细化: 12 级以下概览, 之上按档位本地抽稀换线 ---------- */
const DETAIL_ZOOM = 13;
const BAND_PER = { 13: 2000, 14: 6000, 15: 0 };   // 0 = 全精度 (15 级全库全画)
const REFINE_BATCH = 80;      // 一轮最多换 80 条: 大批量建折线会顶住主线程
const REFINE_POINTS = 200000; // 一轮最多新增渲染点, 超了排下一轮接着扫

function bandOf(z) { return z >= 15 ? 15 : z >= 14 ? 14 : z >= DETAIL_ZOOM ? 13 : null; }

let boundsFbDiag = false;
function viewBounds() {
  // getBounds 在 iOS 手势期间会返回 undefined (官方类型即 Bounds | undefined)
  // 兜底: 用 中心 + 缩放级别 + 容器尺寸 按 Web 墨卡托公式推算视野
  const b = map.getBounds();
  if (b && b.southwest && b.northeast) return b;
  if (!boundsFbDiag) { boundsFbDiag = true; diag("bounds_fallback", { z: map.getZoom() }); }
  const c = map.getCenter();
  if (!c) return null;
  const z = map.getZoom();
  const el = document.getElementById("fp-map");
  const degPx = 360 / (256 * Math.pow(2, z));   // 每像素的经度跨度
  const wl = (el.clientWidth || 320) * degPx / 2;
  const hl = (el.clientHeight || 320) * degPx / 2 * Math.cos(c.lat * Math.PI / 180);
  return { southwest: { lng: c.lng - wl, lat: c.lat - hl },
           northeast: { lng: c.lng + wl, lat: c.lat + hl } };
}

function currentBox() {   // 当前视野 + 等比例外扩 (小视野外扩少, 避免拉进太多无关轨迹)
  const b = viewBounds();
  if (!b) return null;
  const M = Math.max((b.northeast.lng - b.southwest.lng) * 0.25, 0.005);
  return { w: b.southwest.lng - M, e: b.northeast.lng + M,
           s: b.southwest.lat - M, n: b.northeast.lat + M };
}

function scheduleRefine() {
  if (!map || !mapReady) return;
  clearTimeout(refineTimer);
  refineTimer = setTimeout(refineVisible, 350);   // 防抖: 缩放/平移稳定后再换线
}

const boxCache = new Map();   // id → [w, s, e, n] 轨迹包络盒 (首次用到时算一次)
function trackOverlaps(t, box) {   // 包络盒与视野框相交 (全精度 pts 扫一遍太贵, 盒缓存)
  let b = boxCache.get(t.id);
  if (!b) {
    const p = t.pts;
    let w = 180, s = 90, e = -180, n = -90;
    for (let i = 0; i < p.length; i += 2) {
      const x = p[i], y = p[i + 1];
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > n) n = y;
    }
    b = [w, s, e, n];
    boxCache.set(t.id, b);
  }
  return b[0] <= box.e && b[2] >= box.w && b[1] <= box.n && b[3] >= box.s;
}

function revertDetail() {   // 缩回 12 级以下: 细化线还原为概览线
  for (const [id, lines] of detailLines) {
    map.remove(lines);
    const c = coarseById.get(id);
    if (c) {
      map.add(c);
      if (id === selectedId) {   // 选中高亮转移回概览线
        selected = c;
        c.forEach(l => l.setOptions({ strokeOpacity: 1, strokeWeight: 4, zIndex: 99 }));
      }
    }
  }
  detailLines.clear();
  detailTier.clear();
  detailBand = null;
}

function targetPer(t, band) {   // 该轨迹当前该画多细 (per 值, 0 = 全精度)
  if (fullIds.has(t.id)) return 0;   // 选中过的永不降级
  return BAND_PER[band];             // 13→2000, 14→6000, 15→全库全精度 (用户点名)
}

function applyDetail(t, per) {   // 用抽稀档 (0=全精度) 的线替换该轨迹现有的线
  const old = detailLines.get(t.id);
  if (old) map.remove(old);
  const c = coarseById.get(t.id);
  if (c) map.remove(c);
  const lines = makeTrackLines(t, per);
  map.add(lines);
  detailLines.set(t.id, lines);
  detailTier.set(t.id, per);
  if (t.id === selectedId) {     // 该线正被选中: 高亮转移到细化线
    selected = lines;
    lines.forEach(l => l.setOptions({ strokeOpacity: 1, strokeWeight: 4, zIndex: 99 }));
  }
}

function refineSelected(t) {   // 点击选中: 内存直取全精度, 同步换线 (不发请求)
  fullIds.add(t.id);
  applyDetail(t, 0);
}

function refineVisible() {
  if (!map) return;
  const band = bandOf(map.getZoom());
  if (band === null) {
    if (detailBand !== null) revertDetail();
    return;
  }
  detailBand = band;      // 换档不整版回概览: 每条按自己的目标档增量升/降
  const box = currentBox();
  let fresh = 0, freshPts = 0;
  const upgrade = (t, want) => {          // 换一条 (预算共享, 超了喊停)
    if (fresh >= REFINE_BATCH || freshPts >= REFINE_POINTS) return false;
    applyDetail(t, want);
    fresh++;
    freshPts += Math.min(t.pts.length / 2, want || Infinity);
    return true;
  };
  // 视野内的先换到当前档 (用户正看着的优先; 15 级全库都要全精度, 这里只管排队)
  if (box) {
    for (let k = tracks.length - 1; k >= 0; k--) {
      const t = tracks[k];
      if (!trackOverlaps(t, box)) continue;
      const want = targetPer(t, band);
      if (detailLines.has(t.id) && detailTier.get(t.id) === want) continue;
      if (!upgrade(t, want)) break;
    }
  }
  // 所有轨迹都要细化到当前档 (用户点名), 从最新倒序: 超预算时优先保证近期轨迹
  for (let k = tracks.length - 1; k >= 0; k--) {
    const t = tracks[k];
    const want = targetPer(t, band);
    if (detailLines.has(t.id) && detailTier.get(t.id) === want) continue;
    if (!upgrade(t, want)) break;
  }
  if (fresh >= REFINE_BATCH || freshPts >= REFINE_POINTS) {
    // 预算用尽还没扫完: 排下一轮接着补 (交互一来自会重排, 不冲突)
    clearTimeout(refineTimer);
    refineTimer = setTimeout(refineVisible, 80);
  }
}
