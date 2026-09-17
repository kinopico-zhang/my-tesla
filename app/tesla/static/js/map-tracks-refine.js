// map-tracks-refine.js — 足迹地图页 (3/5): 缩放渐进细化 —— 12 级以下用粗轨迹,
// 之上按视野请求高精度点位: 档位/视野框推算 (iOS 手势期 getBounds 兜底)/
// 手势中探测预判亮提示/缩回还原粗线/高精度线替换/选中单条全精度重取/
// 视野内批量细化。
// 由 map.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 map.html
// 里的顺序加载, 跨模块引用走全局); 底座在 map-page.js, 轨迹绘制
// 与选中在 map-tracks-render.js, 数据刷新与启动在 map-boot.js, 筛选 UI 与
// 收尾在 map-filters.js。
/* global $, diag, getJSON, makeTrackLines, map, mapReady, tracks, tracksById,
          coarseById, detailCache, fullCache, detailLines, selected: writable,
          selectedId, detailSeq: writable, detailBand: writable,
          refineTimer: writable */
/* exported selected, scheduleRefine, scheduleProbe, probeRefine, showRefineTip,
           refineSelected, refineVisible */
"use strict";
/* ---------- 缩放渐进细化: 12 级以下用粗轨迹, 之上按视野请求高精度点位 ---------- */
const DETAIL_ZOOM = 12;
function bandOf(z) { return z >= 15 ? 15 : z >= 14 ? 14 : z >= 13 ? 13
  : z >= DETAIL_ZOOM ? 12 : null; }

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
  const el = document.getElementById("map");
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
  refineTimer = setTimeout(refineVisible, 350);   // 防抖: 缩放/平移稳定后再查
}

let refinePending = 0;   // 在途细化请求数, 并发/被作废时提示不错乱
function showRefineTip(on, n) {
  $("#refine-tip").hidden = !on;
  if (on) $("#refine-tip-text").textContent =
    n ? "正在加载视野内 " + n + " 条高精度轨迹…" : "正在加载高精度轨迹…";
}

let probeTimer = null;
function scheduleProbe() {
  clearTimeout(probeTimer);
  probeTimer = setTimeout(probeRefine, 120);   // 手势事件高频, 节流预判
}
let probeLowN = 0;
function probeRefine() {   // 缩放/平移手势进行中: 视野内一旦有未缓存的轨迹, 提前亮提示
  try {
    if (!map) return;
    const z = map.getZoom();
    const band = bandOf(z);
    if (band === null) {
      if (z >= 10 && probeLowN++ < 5) diag("probe_below", { z: Math.round(z * 10) / 10 });
      if (!refinePending) showRefineTip(false);   // 缩回概览档, 无需细化
      return;
    }
    if (refinePending) return;                    // 已在加载, 提示本来就亮着
    const box = currentBox();
    if (!box) return;
    const cache = detailCache.get(band);
    for (const t of tracks) {
      if (!t.pts.some(p => p[0] >= box.w && p[0] <= box.e && p[1] >= box.s && p[1] <= box.n)) continue;
      const c = cache && cache.get(t.id);
      if (!c || c.box.w > box.w || c.box.e < box.e || c.box.s > box.s || c.box.n < box.n) {
        showRefineTip(true);   // 有要加载的轨迹 (缓存缺失或视野超出已查范围)
        diag("probe_show", { z: Math.round(map.getZoom() * 10) / 10, band });
        return;
      }
    }
  } catch (e) {
    diag("probe_err", { msg: String(e && e.message || e).slice(0, 200) });
  }
}

function revertDetail() {   // 缩回 13 级以下 / 切档: 细化线还原为粗线
  for (const [id, lines] of detailLines) {
    map.remove(lines);
    const c = coarseById.get(id);
    if (c) {
      map.add(c);
      if (id === selectedId) {   // 选中高亮转移回粗线
        selected = c;
        c.forEach(l => l.setOptions({ strokeOpacity: 1, strokeWeight: 4, zIndex: 99 }));
      }
    }
  }
  detailLines.clear();
  detailBand = null;
}

function applyDetail(id, pts, force) {   // 用高精度线替换该行程的粗线
  if (!force && fullCache.has(id)) return;   // 该轨迹已是全精度, 不降级
  const t = tracksById.get(id);
  if (!t) return;
  const old = detailLines.get(id);
  if (old) map.remove(old);       // 之前只覆盖旧视野, 现在换成更宽的
  const c = coarseById.get(id);
  if (c) map.remove(c);
  const lines = makeTrackLines(pts, t);
  map.add(lines);
  detailLines.set(id, lines);
  if (id === selectedId) {        // 该线正被选中: 高亮转移到细化线
    selected = lines;
    lines.forEach(l => l.setOptions({ strokeOpacity: 1, strokeWeight: 4, zIndex: 99 }));
  }
}

async function refineSelected(t) {
  // 点击的轨迹单独全精度重取: 单条 ~1-2s, 点过的缓存复用
  if (fullCache.has(t.id)) {
    if (selectedId === t.id) applyDetail(t.id, fullCache.get(t.id), true);
    return;
  }
  refinePending++;
  showRefineTip(true);
  $("#refine-tip-text").textContent = "正在加载选中轨迹…";
  try {
    const d = await getJSON("/tesla/map/api/tracks/detail?ids=" + t.id +
      "&zoom=15&w=-180&s=-90&e=180&n=90");   // 全球框 = 整条轨迹, 单条 → 全精度
    if (d.tracks.length) {
      fullCache.set(t.id, d.tracks[0].pts);
      if (selectedId === t.id) applyDetail(t.id, d.tracks[0].pts, true);
    }
  } catch (e) { /* 静默失败, 细化线仍在 */ }
  finally {
    refinePending--;
    if (!refinePending) showRefineTip(false);
  }
}

async function refineVisible() {
  const band = bandOf(map.getZoom());
  if (band === null) {
    showRefineTip(false);
    if (detailBand !== null) revertDetail();
    return;
  }
  if (band !== detailBand) { revertDetail(); detailBand = band; }
  const box = currentBox();
  if (!box) return;
  const cache = detailCache.get(band) || new Map();
  detailCache.set(band, cache);
  const seq = ++detailSeq;
  const need = [];
  let scanned = 0;
  // 从最新轨迹倒序取: 密集走廊超上限时, 优先保证近期轨迹精细
  for (let k = tracks.length - 1; k >= 0 && scanned < 150; k--) {
    const t = tracks[k];
    if (!t.pts.some(p => p[0] >= box.w && p[0] <= box.e && p[1] >= box.s && p[1] <= box.n)) continue;
    scanned++;
    const c = cache.get(t.id);
    if (c && c.box.w <= box.w && c.box.e >= box.e && c.box.s <= box.s && c.box.n >= box.n) {
      if (!detailLines.has(t.id)) applyDetail(t.id, c.pts);   // 缓存已覆盖当前视野
      continue;
    }
    need.push(t.id);            // 没缓存或视野超出已查范围 → 请求
  }
  if (!need.length) { showRefineTip(false); return; }
  diag("refine_fetch", { band, n: need.length });
  refinePending++;
  showRefineTip(true, need.length);
  try {
    const d = await getJSON("/tesla/map/api/tracks/detail?ids=" + need.join(",") +
      "&zoom=" + band + "&w=" + box.w.toFixed(4) + "&s=" + box.s.toFixed(4) +
      "&e=" + box.e.toFixed(4) + "&n=" + box.n.toFixed(4));
    if (seq !== detailSeq || band !== detailBand) return;   // 已被新视野/重渲染取代
    for (const t of d.tracks) {
      cache.set(t.id, { box, pts: t.pts });
      applyDetail(t.id, t.pts);
    }
  } catch (err) {
    diag("detail_fail", { msg: String(err && err.message || err).slice(0, 150) });
  } finally {
    refinePending--;
    if (!refinePending) showRefineTip(false);
  }
}
