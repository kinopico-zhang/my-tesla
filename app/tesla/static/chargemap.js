// chargemap.js — 充电地图: 热力图按地址聚合充电点, 颜色权重可切 电量/次数/费用 三视图
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

/* ---------- 三视图: 热力权重度量 ---------- */
const VIEWS = {
  energy:   { lb: "充电电量", fmt: v => Math.round(v) + " kWh" },
  sessions: { lb: "充电次数", fmt: v => v + " 次" },
  cost:     { lb: "充电费用", fmt: v => "¥" + Math.round(v) },
};
/* 热力梯度: 蓝 → 绿 → 黄 → 橙 → 红 (值越高越红), 图例梯度条用同一组色 */
const GRADIENT = { 0.2: "#3987e5", 0.45: "#1fa349", 0.65: "#d9b13c", 0.82: "#e08a3c", 1: "#e5484d" };
const PICK_PX = 36;    // 点击就近取点半径 (像素)

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
// URL → 初始状态: ?range= 快捷档; ?from=&to= 自定义区间; ?view= 三视图
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const timeSel = { v: range0, from: cFrom0, to: cTo0 };
let view = VIEWS[qs0.get("view")] ? qs0.get("view") : "energy";

let map = null, heatmap = null, pickMark = null, locations = [];

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

function loadAMap(key, securityCode) {
  return new Promise((resolve, reject) => {
    if (securityCode) window._AMapSecurityConfig = { securityJsCode: securityCode };
    const s = document.createElement("script");
    s.src = "https://webapi.amap.com/maps?v=2.0&plugin=AMap.HeatMap&key=" + encodeURIComponent(key);
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("高德地图脚本加载失败, 请检查网络"));
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

/* 渲染热力: 当前视图的数值做权重, 归一到 0..max 上梯度 */
function renderHeatmap() {
  closeSheet();
  const maxV = maxOfView();
  heatmap.setDataSet({
    data: locations.map(l => {
      const c = GCJ02.wgs84ToGcj02(l.lng, l.lat);   // WGS-84 → GCJ-02
      return { lng: c[0], lat: c[1], count: l[view] };
    }),
    max: maxV || 1,
  });
  renderLegend(maxV);
  fitToLocations();
  if (!locations.length) showError("该时间段没有充电记录");
}
function maxOfView() { return Math.max(...locations.map(l => l[view]), 0); }

/* 热力层不是地图覆盖物, setFitView 看不见它 —— 临时放一把隐形圆点拉视野再撤 */
function fitToLocations() {
  if (!locations.length) return;
  const marks = locations.map(l => new AMap.CircleMarker({
    center: GCJ02.wgs84ToGcj02(l.lng, l.lat), radius: 1,
  }));
  map.add(marks);
  map.setFitView(marks, false, [40, 40, 40, 40]);
  map.remove(marks);
}

/* 点击就近取点: 热力块没有可点对象, 谁的中心离点击处近 (阈值内) 就算谁 */
function pickNearest(ev) {
  if (!ev.pixel) return;
  let best = null, bestD = Infinity;
  locations.forEach(loc => {
    const p = map.lngLatToContainer(GCJ02.wgs84ToGcj02(loc.lng, loc.lat));
    const dx = p.getX() - ev.pixel.getX(), dy = p.getY() - ev.pixel.getY();
    const d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = loc; }
  });
  if (best && bestD <= PICK_PX * PICK_PX) selectLocation(best);
}

function selectLocation(loc) {
  $("#sh-name").textContent = loc.name;
  $("#sh-city").textContent = loc.city || "—";
  $("#sh-sessions").textContent = loc.sessions;
  $("#sh-fast").textContent = loc.fast_sessions;
  $("#sh-energy").innerHTML = loc.energy + "<small>kWh</small>";
  $("#sh-cost").textContent = loc.cost ? "¥" + loc.cost : "未记录";
  showPick(loc);
  $("#backdrop").classList.add("show");
  $("#sheet").classList.add("show");
}
function closeSheet() {
  hidePick();
  $("#backdrop").classList.remove("show");
  $("#sheet").classList.remove("show");
}
/* 选中点画个白圈: 热力块上看不出选中了哪一个 */
function showPick(loc) {
  hidePick();
  pickMark = new AMap.CircleMarker({
    center: GCJ02.wgs84ToGcj02(loc.lng, loc.lat),
    radius: 9, zIndex: 99, bubble: true,
    strokeColor: "#ffffff", strokeWeight: 2.5, strokeOpacity: 1,
    fillColor: "#ffffff", fillOpacity: .2,
  });
  map.add(pickMark);
}
function hidePick() {
  if (pickMark) { map.remove(pickMark); pickMark = null; }
}

/* 图例: 梯度条 + 当前视图的最小 / 中位 / 最大值 */
function gradientCss() {
  // GRADIENT 的键 "1" 是整数式键, Object.keys 会排在最前 —— 显式按数值排序
  const stops = Object.keys(GRADIENT).map(Number).sort((a, b) => a - b);
  return "linear-gradient(90deg," +
    stops.map(k => GRADIENT[k] + " " + Math.round(k * 100) + "%").join(",") + ")";
}
function renderLegend(maxV) {
  const lg = $("#legend");
  if (!locations.length) { lg.hidden = true; return; }
  lg.hidden = false;
  const v = VIEWS[view];
  $("#lg-mode").textContent = "颜色越红 · " + v.lb + "越多";
  $("#lg-ramp").style.background = gradientCss();
  const vals = locations.map(l => l[view]).sort((a, b) => a - b);
  const mid = vals[Math.floor(vals.length / 2)];
  $("#lg-row").innerHTML = [vals[0], mid, maxV].map(x => `<span>${v.fmt(x)}</span>`).join("");
}

function renderStats(list) {
  $("#stats").hidden = false;
  $("#st-places").textContent = list.length;
  $("#st-sessions").textContent = list.reduce((a, l) => a + l.sessions, 0);
  const energy = list.reduce((a, l) => a + l.energy, 0);
  $("#st-energy").innerHTML = Math.round(energy) + "<small>kWh</small>";
}

async function refresh(first) {
  $("#error").hidden = true;
  showLoading(true, first ? "正在加载充电地点…" : "正在更新…");
  try {
    locations = await getJSON("/tesla/charging/api/map-locations" + rangeParams());
    renderStats(locations);
    renderHeatmap();
    showLoading(false);
  } catch (e) {
    showError(e.message);
    showLoading(false);
  }
}

async function boot() {
  try {
    // 加时间戳穿透浏览器缓存 (旧响应可能缓存了 amap_key: null)
    const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
    if (!cfg.amap_key) {
      $("#keyhint").hidden = false;
      return;
    }
    await loadAMap(cfg.amap_key, cfg.security_code);
    map = new AMap.Map("map", {
      mapStyle: cfg.style || "amap://styles/dark", zoom: 11, center: [114.05, 22.55],
    });
    heatmap = new AMap.HeatMap(map, {
      radius: 26,          // 热力圆半径 (像素)
      opacity: [0, .8],
      gradient: GRADIENT,
    });
    map.on("click", pickNearest);
    // iOS Safari 会把双指缩放劫持成整页缩放: 拦截私有 gesture 事件, 手势只给高德
    for (const ev of ["gesturestart", "gesturechange"]) {
      document.getElementById("map").addEventListener(ev, e => e.preventDefault());
    }
    await refresh(true);
  } catch (e) {
    if (e.message !== "未登录") showError(e.message);
  }
}

function timeLabel() {
  if (timeSel.v === "custom")   // 自定义显示紧凑区间, 如 01/01–03/31
    return `${timeSel.from.slice(5).replace("-", "/")}–${timeSel.to.slice(5).replace("-", "/")}`;
  return TIME_RANGES.find(r => r.v === timeSel.v).lb;
}
function syncURL() {   // 筛选写进地址栏 (默认值不写, 链接保持干净)
  const u = new URL(location.href);
  if (timeSel.v === "custom") {
    u.searchParams.delete("range");
    u.searchParams.set("from", timeSel.from); u.searchParams.set("to", timeSel.to);
  } else {
    u.searchParams.delete("from"); u.searchParams.delete("to");
    if (timeSel.v === "all") u.searchParams.delete("range"); else u.searchParams.set("range", timeSel.v);
  }
  if (view === "energy") u.searchParams.delete("view"); else u.searchParams.set("view", view);
  history.replaceState(null, "", u);
}
function setTimeRange(v, skipRefresh) {
  timeSel.v = v;
  $("#time-lb").textContent = timeLabel();
  document.querySelectorAll("#time-opts button[data-v]").forEach(b =>
    b.classList.toggle("on", b.dataset.v === v));
  if (v !== "custom") $("#tm-dates").hidden = true;   // 回到快捷档, 收起日历
  syncURL();
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

/* 三视图切换: 只换热力度量, 不重新请求数据 */
$("#view-seg").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || b.dataset.v === view) return;
  view = b.dataset.v;
  $("#view-seg .on").classList.remove("on"); b.classList.add("on");
  syncURL();
  if (map && locations.length) renderHeatmap();   // 地图没起来时记着状态, boot 后首渲染
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
