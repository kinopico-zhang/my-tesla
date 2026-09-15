// map.js — 由 map.html 内联脚本抽出 (位置/顺序/语义不变), 供 lint 与测试
"use strict";
/* 页签菜单: 点空白处收起。
   注意: 日历点选会在点击处理器里 innerHTML 重渲染, 事件目标被脱链
   (closest() 找不到菜单祖先) —— 脱链的点击一定发生在某个菜单里, 不能当"点外面"关闭。 */
document.addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});
const $ = s => document.querySelector(s);
const PAGE_V = "v11";   // 页面版本: 诊断时确认浏览器是否在跑最新代码

/* ---------- 诊断探针: 浏览器端异常/高德请求失败自动回传服务端日志 ---------- */
let diagCount = 0;
function diag(stage, extra) {
  if (diagCount++ > 40) return;
  try {
    fetch("/tesla/map/api/diag", {
      method: "POST", headers: { "Content-Type": "application/json" },
      keepalive: true,
      body: JSON.stringify(Object.assign({ stage, ua: navigator.userAgent.slice(0, 100) }, extra)),
    }).catch(() => {});
  } catch (e) { /* 探针自身绝不能影响页面 */ }
}
window.addEventListener("error", e => diag("window_error",
  { msg: ((e.message || "") + " @" + (e.filename || "") + ":" + (e.lineno || 0)).slice(0, 300) }));
window.addEventListener("unhandledrejection", e => diag("promise_rejection",
  { msg: String((e.reason && e.reason.message) || e.reason || "").slice(0, 300) }));
(function patchConsole() {
  for (const lvl of ["error", "warn"]) {
    const orig = console[lvl].bind(console);
    console[lvl] = (...args) => {
      diag("console_" + lvl, { msg: args.map(a => String((a && a.message) || a)).join(" | ").slice(0, 400) });
      orig(...args);
    };
  }
})();
(function patchNetwork() {  // 捕获高德请求的真实失败 (状态码 + 响应体)
  const origFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    return origFetch(url, opts).then(r => {
      if (r.status >= 400 && String(url).includes("amap.com"))
        diag("amap_fetch_" + r.status, { url: String(url).slice(0, 250) });
      return r;
    }).catch(e => {
      if (String(url).includes("amap.com"))
        diag("amap_fetch_err", { url: String(url).slice(0, 250), err: String(e).slice(0, 150) });
      throw e;
    });
  };
  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.addEventListener("load", () => {
      if (this.status >= 400 && String(url).includes("amap.com"))
        diag("amap_xhr_" + this.status,
             { url: String(url).slice(0, 250), resp: String(this.responseText || "").slice(0, 250) });
    });
    return origOpen.call(this, method, url, ...rest);
  };
})();

let map = null, overlays = [], selected = null, selectedId = null, mapReady = false;
/* ---------- 顶栏时间筛选: 快捷档位下拉, 编码进 ?range= (分享/刷新保留) ---------- */
const TIME_RANGES = [
  { v: "24h", days: 1, lb: "24小时" },
  { v: "7d", days: 7, lb: "近一周" },
  { v: "30d", days: 30, lb: "近一月" },
  { v: "180d", days: 180, lb: "近半年" },
  { v: "1y", days: 365, lb: "近一年" },
  { v: "all", days: 0, lb: "全部" },
];
const pad = n => String(n).padStart(2, "0");
const fmtDate = d => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());

function timeFrom(v) {   // 档位 → from 本地日期 (含今天共 N 天; 24h 即"昨天起")
  const r = TIME_RANGES.find(x => x.v === v);
  if (!r || !r.days) return null;
  const d = new Date(); d.setDate(d.getDate() - (r.days - 1));
  return fmtDate(d);
}
// URL → 初始时间: ?range= 快捷档; ?from=&to= 自定义区间
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const timeSel = { v: range0, from: cFrom0, to: cTo0 };
let drvId = /^\d+$/.test(qs0.get("driver_id") || "") ? +qs0.get("driver_id") : null;
                                             // 驾驶员筛选 (null = 全部), URL 深链可带
let tracks = [];                  // 当前筛选后的粗轨迹对象
let tracksById = new Map();       // id → 粗轨迹对象 (点击信息用)
let coarseById = new Map();       // id → 粗线 Polyline
let detailLines = new Map();      // id → 细化线 Polyline (替换粗线)
let detailBand = null;            // 当前细化档位: null / 13 / 14 / 15
let detailCache = new Map();      // 档位 → Map(id → {box, pts})
let renderGen = 0;                // 渲染代号: 切换筛选时作废进行中的批次
let detailSeq = 0;                // 作废在途的细化请求
let refineTimer = null;
let fullCache = new Map();        // id → 全精度 pts (点过的轨迹单独全取, 永不降级)

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ("HTTP " + r.status));
  return r.json();
}

function rangeParams() {
  if (timeSel.v === "custom")   // 自定义起止 (日历)
    return `?from=${timeSel.from}&to=${timeSel.to}`;
  const from = timeFrom(timeSel.v);
  return from ? "?from=" + from : "";
}
function trackParams() {        // 时间 + 驾驶员一起拼 (tracks/summary 同口径)
  const p = rangeParams();
  return drvId == null ? p : p + (p ? "&" : "?") + "driver_id=" + drvId;
}

function loadAMap(key, securityCode) {
  return new Promise((resolve, reject) => {
    if (securityCode) window._AMapSecurityConfig = { securityJsCode: securityCode };
    const s = document.createElement("script");
    s.src = "https://webapi.amap.com/maps?v=2.0&key=" + encodeURIComponent(key);
    s.onload = () => resolve();
    s.onerror = () => { diag("amap_script_fail", { src: s.src.slice(0, 120) });
                        reject(new Error("高德地图脚本加载失败, 请检查网络")); };
    document.head.appendChild(s);
  });
}

function showLoading(on, text) {
  $("#loading").hidden = !on;
  if (text) $("#loading-text").textContent = text;
}
function showError(msg) {
  $("#error").hidden = false;
  $("#error-text").textContent = msg || "加载失败";
}

function renderStats(s) {
  $("#stats").hidden = false;
  $("#st-drives").textContent = Number(s.drives).toLocaleString();
  $("#st-km").innerHTML = Number(s.distance_km).toLocaleString() + "<small>km</small>";
  $("#st-hours").innerHTML = (s.duration_min / 60).toFixed(1) + "<small>小时</small>";
}

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

async function refresh(first) {
  $("#error").hidden = true;
  showLoading(true, first ? "正在加载轨迹…" : "正在更新…");
  try {
    const p = trackParams();
    const [t, s] = await Promise.all([
      getJSON("/tesla/map/api/tracks" + p),
      getJSON("/tesla/map/api/summary" + p),
    ]);
    renderStats(s);
    await renderTracks(t.tracks);   // 分块绘制, 结束时自行收起加载层
    if (!t.tracks.length) showError("该时间段没有行驶轨迹");
  } catch (e) {
    showError(e.message);
    showLoading(false);
  }
}

async function boot() {
  try {
    // 加时间戳穿透浏览器缓存 (旧响应可能缓存了 amap_key: null)
    const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
    diag("config_ok", { has_key: !!cfg.amap_key, has_scode: !!cfg.security_code, v: PAGE_V });
    if (!cfg.amap_key) {
      $("#keyhint").hidden = false;
      return;
    }
    await loadAMap(cfg.amap_key, cfg.security_code);
    diag("amap_script_loaded", { ver: (window.AMap && AMap.version) || "?" });
    map = new AMap.Map("map", {
      mapStyle: cfg.style || "amap://styles/dark", zoom: 11, center: [114.05, 22.55],
    });
    map.on("complete", () => {
      mapReady = true; diag("map_complete");
      /* 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染 (首次打开
         一两秒地名才出现的原因), setFeatures 同值重设 = 只触发重渲染 */
      const nudge = () => { if (map.getFeatures) map.setFeatures(map.getFeatures()); };
      setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);
    });
    // iOS Safari 会把双指缩放劫持成整页缩放: 拦截私有 gesture 事件, 手势只给高德
    for (const ev of ["gesturestart", "gesturechange"]) {
      document.getElementById("map").addEventListener(ev, e => e.preventDefault());
    }
    // 事件触发诊断 (每类前 N 次上报) + 手势中预判亮提示
    const evtN = {};
    const trackEvt = (name, val, times = 1) => {
      evtN[name] = (evtN[name] || 0) + 1;
      if (evtN[name] <= times) diag("evt_" + name, val || {});
    };
    map.on("zoomstart", () => { trackEvt("zoomstart"); scheduleProbe(); });
    map.on("zoomchange", () => { trackEvt("zoomchange", { z: Math.round(map.getZoom() * 10) / 10 }, 10); scheduleProbe(); });
    map.on("mapmove", () => { trackEvt("mapmove"); scheduleProbe(); });
    map.on("dragging", () => { trackEvt("dragging"); scheduleProbe(); });
    map.on("zoomend", () => { trackEvt("zoomend", { z: Math.round(map.getZoom() * 10) / 10 }, 15); probeRefine(); scheduleRefine(); });
    map.on("moveend", () => { trackEvt("moveend"); probeRefine(); scheduleRefine(); });
    diag("map_created");
    setTimeout(() => {
      if (!mapReady) {
        diag("map_incomplete_15s", { amap: !!window.AMap });
        showLoading(true, "地图引擎初始化未完成…已自动上报诊断, 请反馈给管理员");
      }
    }, 15000);
    await refresh(true);
    diag("boot_done", { tracks: overlays.length });
  } catch (e) {
    diag("boot_error", { msg: String(e && e.message || e).slice(0, 300) });
    if (e.message !== "未登录") showError(e.message);
  }
}

function timeLabel() {
  if (timeSel.v === "custom")   // 自定义显示紧凑区间, 如 01/01–03/31
    return `${timeSel.from.slice(5).replace("-", "/")}–${timeSel.to.slice(5).replace("-", "/")}`;
  return TIME_RANGES.find(r => r.v === timeSel.v).lb;
}
function setTimeRange(v, skipRefresh) {
  timeSel.v = v;
  $("#time-lb").textContent = timeLabel();
  document.querySelectorAll("#time-opts button[data-v]").forEach(b =>
    b.classList.toggle("on", b.dataset.v === v));
  if (v !== "custom") $("#tm-dates").hidden = true;   // 回到快捷档, 收起日历
  const u = new URL(location.href);                   // 筛选写进地址栏 (默认值不写)
  if (v === "custom") {
    u.searchParams.delete("range");
    u.searchParams.set("from", timeSel.from); u.searchParams.set("to", timeSel.to);
  } else {
    u.searchParams.delete("from"); u.searchParams.delete("to");
    if (v === "all") u.searchParams.delete("range"); else u.searchParams.set("range", v);
  }
  history.replaceState(null, "", u);
  if (!skipRefresh) refresh(false);
}
/* ---------- 自定义日历: 同一个日历连点两次 —— 第一下起点, 第二下终点 ----------
   终点早于起点自动交换; 已有区间再点 = 重新开始选; 只点一下就确定 = 单日。 */
let calYm = "", calA = null, calB = null;    // 显示月 / 草稿起止 (ISO 日期)
const calCn = iso => { const p = iso.split("-"); return `${+p[1]}月${+p[2]}日`; };
function calRender() {
  const [y, m] = calYm.split("-").map(Number);
  $("#tm-ym").textContent = `${y}年${m}月`;
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7;   // 周一开头
  const days = new Date(y, m, 0).getDate();
  const n = new Date();
  const today = `${n.getFullYear()}-${pad(n.getMonth() + 1)}-${pad(n.getDate())}`;
  $("#tm-next").disabled = calYm >= today.slice(0, 7);     // 未来月没有数据
  let h = "";
  for (let i = 0; i < lead; i++) h += "<i></i>";
  for (let d = 1; d <= days; d++) {
    const iso = `${calYm}-${pad(d)}`;
    const cls = iso === calA || iso === calB ? "on"
      : calA && calB && iso > calA && iso < calB ? "mid" : "";
    h += `<button class="${cls}${iso === today ? " today" : ""}"
            data-d="${iso}" aria-label="${iso}">${d}</button>`;
  }
  $("#tm-cal").innerHTML = h;   // 重渲染会脱链点击目标, "点空白处收起" 的守卫兜底
  $("#tm-sel").textContent = !calA ? "点选开始日期"
    : !calB ? `已选开始 ${calCn(calA)}, 再点结束日期`
    : `${calCn(calA)} – ${calCn(calB)}`;
}
function calShift(k) {
  const [y, m] = calYm.split("-").map(Number);
  const t = new Date(y, m - 1 + k, 1);
  calYm = `${t.getFullYear()}-${pad(t.getMonth() + 1)}`;
  calRender();
}
function calOpen() {   // 打开日历: 带出已应用的自定义区间, 没有则从当月起
  calA = timeSel.from; calB = timeSel.to;
  calYm = (calA || `${new Date().getFullYear()}-${pad(new Date().getMonth() + 1)}`).slice(0, 7);
  calRender();
}
$("#tm-cal").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const d = b.dataset.d;
  if (!calA || calB) { calA = d; calB = null; }   // 新一轮: 重新选起点
  else if (d < calA) { calB = calA; calA = d; }   // 反着点: 自动交换
  else calB = d;                                  // 第二下 = 终点 (同一天 = 单日)
  calRender();
});
$("#tm-prev").addEventListener("click", () => calShift(-1));
$("#tm-next").addEventListener("click", () => calShift(1));
$("#time-opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || !b.dataset.v) return;   // 日历里的按钮 (日期/翻月/确定) 不走快捷档逻辑
  if (b.dataset.v === "custom") {   // 展开/收起日历, 连点两次选好再确定生效
    const box = $("#tm-dates");
    box.hidden = !box.hidden;
    if (!box.hidden) calOpen();
    return;
  }
  if (b.dataset.v === timeSel.v) return;
  $("#time-menu").removeAttribute("open");
  setTimeRange(b.dataset.v);
});
$("#tm-apply").addEventListener("click", () => {
  if (!calA) return;                // 一下都没点不生效
  $("#time-menu").removeAttribute("open");
  timeSel.from = calA;              // 只点了起点 = 单日
  timeSel.to = calB || calA;
  setTimeRange("custom");
});
$("#time-menu").addEventListener("toggle", () => {   // 重开菜单回到已应用区间
  if ($("#time-menu").open && !$("#tm-dates").hidden) calOpen();
});
setTimeRange(timeSel.v, true);
/* 驾驶员筛选: 选项来自设置页的驾驶员表 (没配驾驶员整颗筛选藏掉); 口径与
   行程页一致 —— 选默认驾驶员 = 标注它的 + 未标注的 (后端合并处理) */
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
(async () => {
  let drivers = [];
  try { drivers = await getJSON("/tesla/api/drivers"); } catch (_e) { /* keep 空 */ }
  if (!drivers.length) return;               // 没配驾驶员, 筛选不出现
  const opts = $("#drv-opts");
  opts.innerHTML = `<button data-id=""${drvId == null ? ' class="on"' : ""}>全部</button>` +
    drivers.map(d =>
      `<button data-id="${d.id}"${drvId === d.id ? ' class="on"' : ""}>${esc(d.name)}</button>`).join("");
  if (drvId != null) {                       // URL 深链带入的驾驶员要存在才算数
    const hit = drivers.find(d => d.id === drvId);
    if (hit) $("#drv-lb").textContent = "驾驶员: " + hit.name;
    else {
      drvId = null;
      opts.querySelector('button[data-id=""]').classList.add("on");
    }
  }
  $("#drv-menu").hidden = false;
  $("#filters").hidden = false;   // 筛选行只剩驾驶员, 有驾驶员才亮 (没有就不占行)
})();
$("#drv-opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const v = b.dataset.id === "" ? null : +b.dataset.id;
  if (v === drvId) return;
  $("#drv-menu").removeAttribute("open");
  drvId = v;
  $("#drv-opts .on").classList.remove("on"); b.classList.add("on");
  $("#drv-lb").textContent = "驾驶员: " + b.textContent;
  const u = new URL(location.href);          // 筛选写进地址栏 (默认值不写)
  if (drvId == null) u.searchParams.delete("driver_id");
  else u.searchParams.set("driver_id", drvId);
  history.replaceState(null, "", u);
  refresh(false);
});
$("#retry").addEventListener("click", () => refresh(false));
$("#recheck").addEventListener("click", () => location.reload());
$("#backdrop").addEventListener("click", closeSheet);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSheet(); });
$("#zin").addEventListener("click", () => map && map.zoomIn());
$("#zout").addEventListener("click", () => map && map.zoomOut());
/* 顶栏刷新: 重拉当前页数据 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await refresh(false);
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
  location.href = "/login";
});

boot();
