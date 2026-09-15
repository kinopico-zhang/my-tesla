// trips-list.js — 行程列表页前半: 卡片/懒加载/筛选 (时间/里程/省市区/
// 驾驶员)/日历/多选与分组。地图弹层与播放编排按域拆到 trips.js (同一
// 全局作用域, 本脚本先加载; 弹层代码在事件回调里引用这里的函数与状态)。
"use strict";
/* 页签菜单: 点空白处收起。
   注意: 级联菜单钻取会在点击处理器里 innerHTML 重渲染, 事件目标被脱链
   (closest() 找不到菜单祖先) —— 脱链的点击一定发生在某个菜单里, 不能当"点外面"关闭。 */
document.addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});
/* ============================ 工具 ============================ */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* 页面共用格式化 (format.js 先加载): 顶部解构, 下文沿用裸名。
   postJSON/trackCache 本页不用, 供后加载的 trips.js (弹层/播放) 引用。 */
/* exported postJSON, trackCache, urlTripKey */
const { pad, fmtCardDate, fmtDur, num } = FormatUtil;

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
  return r.json();
}

/* ============================ 行程列表 (单列) ============================ */
const PAGE = 24;
/* ---------- 顶栏时间筛选: 快捷档位下拉, 编码进 ?range= (分享/刷新保留) ---------- */
const TIME_RANGES = [
  { v: "24h", days: 1, lb: "24小时" },
  { v: "7d", days: 7, lb: "近一周" },
  { v: "30d", days: 30, lb: "近一月" },
  { v: "180d", days: 180, lb: "近半年" },
  { v: "1y", days: 365, lb: "近一年" },
  { v: "all", days: 0, lb: "全部" },
];
function timeFrom(v) {   // 档位 → from 本地日期 (含今天共 N 天; 24h 即"昨天起")
  const r = TIME_RANGES.find(x => x.v === v);
  if (!r || !r.days) return null;
  const d = new Date(); d.setDate(d.getDate() - (r.days - 1));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
const KM_BUCKETS = [   // 里程档位: URL 里存档位码, 请求时换算成 km_min/km_max
  { v: "all", lb: "全部", min: null, max: null },
  { v: "0-20", lb: "20km 内", min: 0, max: 20 },
  { v: "20-100", lb: "20–100km", min: 20, max: 100 },
  { v: "100-300", lb: "100–300km", min: 100, max: 300 },
  { v: "300+", lb: "300km 以上", min: 300, max: null },
];
// URL → 初始筛选: ?range= 快捷档; ?from=&to= 自定义区间; ?from_loc=/?to_loc=/?km= 筛选行
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const qs0 = new URLSearchParams(location.search);
let range0 = TIME_RANGES.some(r => r.v === qs0.get("range")) ? qs0.get("range") : "all";
let cFrom0 = null, cTo0 = null;
if (range0 === "all") {
  const f = qs0.get("from"), t = qs0.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { range0 = "custom"; cFrom0 = f; cTo0 = t; }
}
const locParam = k => {   // ?from_loc=省/市/区 (1~3 段, 脏参数丢弃)
  const segs = (qs0.get(k) || "").split("/").map(s => s.trim()).filter(Boolean);
  return segs.length && segs.length <= 3 && segs.every(s => s.length <= 30) ? segs.join("/") : "";
};
const state = { range: range0, cFrom: cFrom0, cTo: cTo0,
                fromLoc: locParam("from_loc"), toLoc: locParam("to_loc"),
                km: KM_BUCKETS.some(b => b.v === qs0.get("km")) ? qs0.get("km") : "all",
                drvId: /^\d+$/.test(qs0.get("driver_id") || "") ? +qs0.get("driver_id") : null,
                offset: 0, total: 0, loading: false, done: false, err: null };
const trackCache = new Map();       // id → {pts, ts} 全精度轨迹
let driversCache;   // 设置页驾驶员表 (undefined=还没拉过, null=失败, 数组=结果), 筛选行与弹层共用
const items = [];                   // 已加载卡片数据 (与 #list 子元素一一对应, 多选用)

const listEl = $("#list");

function renderCard(it) {
  const el = document.createElement("article");
  el.className = "card-t"; el.dataset.id = it.id;
  const avg = it.km != null && it.min ? Math.round(it.km / (it.min / 60)) : null;
  el.innerHTML = `
    <div class="ct-top">
      <span class="ct-date">${esc(fmtCardDate(it.start))}</span>
      ${it.driver ?   /* 有驾驶员就上卡: 显式标注正常亮, 默认兜底弱化 .def */
        `<span class="ct-drv${it.driver_id != null ? "" : " def"}">${esc(it.driver)}</span>` : ""}
      <span class="ct-arrow">→ 查看轨迹</span>
      <span class="pick" aria-hidden="true"></span>
    </div>
    <div class="ct-cells">
      <div class="ct-cell"><div class="lb">里程</div>
        <div class="val">${it.km != null ? num(it.km) + "<small>km</small>" : "—"}</div></div>
      <div class="ct-cell"><div class="lb">时长</div><div class="val">${fmtDur(it.min)}</div></div>
      ${it.kwh != null ? `<div class="ct-cell"><div class="lb">总电耗</div>
        <div class="val">${num(it.kwh)}<small>kWh</small></div></div>` : ""}
    </div>
    <div class="ct-addr">
      <div class="line from"><i class="dot"></i><span class="txt">${esc(it.from)}</span></div>
      <div class="line to"><i class="dot"></i><span class="txt">${esc(it.to)}</span></div>
    </div>
    <div class="ct-sub">${avg ? `均速 ${avg} km/h` : ""}${avg && it.wh_per_km != null ? " · " : ""}${it.wh_per_km != null ? `平均电耗 ${num(it.wh_per_km, 0)} Wh/km` : ""}</div>`;
  el.addEventListener("click", () => {
    if (document.body.classList.contains("selecting")) pickCard(el);
    else openTrip(it);
  });
  return el;
}

const tailEl = $("#tail");
function setTail() {
  tailEl.hidden = state.total === 0 && !state.loading && state.done && !state.err;
  $("#loader-spin").hidden = !state.loading;
  $("#endnote").hidden = !(state.done && state.total > 0);
  $("#empty").hidden = !(state.done && state.total === 0 && !state.err);
  $("#errbox").hidden = !state.err;
  $("#count-badge").textContent = state.total ? `共 ${state.total} 次` : "";
}

/* ---------- 刷新: 顶栏按钮 (下拉手势已按需求撤掉) ---------- */
async function refreshList() {
  if (state.loading) return;
  items.length = 0;
  listEl.innerHTML = "";
  state.offset = 0; state.total = 0; state.done = false; state.err = null;
  await loadMore();
  window.scrollTo({ top: 0 });
}

$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await refreshList();
  btn.classList.remove("busy");
});

const PRELOAD_PX = 800;   // 触底前多远开始预加载 (IO rootMargin 与链式续载共用)

async function loadMore() {
  if (state.loading || state.done) return;
  state.loading = true; state.err = null; setTail();
  try {
    const p = new URLSearchParams({ offset: state.offset, limit: PAGE });
    if (state.range === "custom") {   // 自定义起止 (日历)
      p.set("from", state.cFrom); p.set("to", state.cTo);
    } else {
      const from = timeFrom(state.range);
      if (from) p.set("from", from);
    }
    if (state.fromLoc) p.set("from_loc", state.fromLoc);
    if (state.toLoc) p.set("to_loc", state.toLoc);
    const kb = KM_BUCKETS.find(b => b.v === state.km);
    if (kb && kb.min != null) p.set("km_min", kb.min);
    if (kb && kb.max != null) p.set("km_max", kb.max);
    if (state.drvId != null) p.set("driver_id", state.drvId);
    const d = await getJSON("/tesla/trips/api/sessions?" + p.toString());
    state.total = d.total; state.offset += d.items.length;
    if (state.offset >= d.total) state.done = true;
    d.items.forEach(it => { items.push(it); listEl.appendChild(renderCard(it)); });
  } catch (e) {
    state.err = "数据加载失败: " + e.message;
  }
  state.loading = false; setTail();
  /* 首页填不满"视口+预载区"时, tail 一直留在交叉区里, IntersectionObserver
     只在进出过渡时回调, 不会再触发 —— 主动续载直到 tail 滚出预载区。
     (Chrome 桌面端宽屏下 24 张卡不足一屏, 曾因此永远卡在第一页。) */
  if (!state.done && !state.err &&
      tailEl.getBoundingClientRect().top < window.innerHeight + PRELOAD_PX)
    loadMore();
}

function timeLabel() {
  if (state.range === "custom")   // 自定义显示紧凑区间, 如 01/01–03/31
    return `${state.cFrom.slice(5).replace("-", "/")}–${state.cTo.slice(5).replace("-", "/")}`;
  return TIME_RANGES.find(r => r.v === state.range).lb;
}
function filterQS() {   // 时间/起终点/里程 → 参数串 (无 ? 前缀), 地址栏与请求共用
  const p = new URLSearchParams();
  if (state.range === "custom") { p.set("from", state.cFrom); p.set("to", state.cTo); }
  else if (state.range !== "all") p.set("range", state.range);
  if (state.fromLoc) p.set("from_loc", state.fromLoc);
  if (state.toLoc) p.set("to_loc", state.toLoc);
  if (state.km !== "all") p.set("km", state.km);
  if (state.drvId != null) p.set("driver_id", state.drvId);
  return p.toString();
}
function listURL(key) {   // 行程页地址栏: 筛选参数 + 可选行程深链 (?id=/ ?ids=)
  const parts = [filterQS(),
                 key ? `${/[-,]/.test(key) ? "ids=" : "id="}${key}` : null].filter(Boolean);
  return "/tesla/trips" + (parts.length ? "?" + parts.join("&") : "");
}
function urlTripKey() {   // 地址栏里的行程深链 (?id=X / ?ids=a,b)
  /* ids= 逗号串经分享渠道常被再编码成 %2C (微信/备忘录都会), 先解一遍再配 */
  const m = /[?&](?:id|ids)=([\d,%-]+)/.exec(location.search);
  return m ? decodeURIComponent(m[1]) : null;
}
function syncURL() {   // 筛选写进地址栏 (默认值不写, 保留打开中的行程深链)
  history.replaceState(history.state, "", listURL(urlTripKey()));
}
function resetList() {   // 筛选变化: 清空列表重新拉
  items.length = 0; listEl.innerHTML = "";
  state.offset = 0; state.total = 0; state.done = false; state.err = null;
  setTail();
  loadMore();
}
function setTimeRange(v, skipReload) {
  state.range = v;
  $("#time-lb").textContent = timeLabel();
  document.querySelectorAll("#time-opts button[data-v]").forEach(b =>
    b.classList.toggle("on", b.dataset.v === v));
  if (v !== "custom") $("#tm-dates").hidden = true;   // 回到快捷档, 收起日历
  syncURL();
  if (!skipReload) resetList();
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
  calA = state.cFrom; calB = state.cTo;
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
  if (b.dataset.v === state.range) return;
  $("#time-menu").removeAttribute("open");
  setTimeRange(b.dataset.v);
});
$("#tm-apply").addEventListener("click", () => {
  if (!calA) return;                // 一下都没点不生效
  $("#time-menu").removeAttribute("open");
  state.cFrom = calA;               // 只点了起点 = 单日
  state.cTo = calB || calA;
  setTimeRange("custom");
});
$("#time-menu").addEventListener("toggle", () => {   // 重开菜单回到已应用区间
  if ($("#time-menu").open && !$("#tm-dates").hidden) calOpen();
});
setTimeRange(state.range, true);              // 初始化: 只同步标签/选中态, 不重拉

/* ---------- 筛选行: 起终点省市区级联 / 里程范围 ----------
   树来自 /trips/api/regions (省→市→区县, 次数降序)。点层级行钻下一级,
   顶部 "全部X" 行选中当前层 (省/市/区县任一级都能作为筛选条件), 叶子直接选中。 */
const REGIONS = { start: [], end: [] };
function bindLocMenu(menuId, optsId, key, lbId, prefix, treeKey) {
  const menuEl = $("#" + menuId), optsEl = $("#" + optsId), lbEl = $("#" + lbId);
  const stack = [];   // 当前钻取路径 (省名/市名), 空 = 省列表
  const setLoc = v => {
    state[key] = v;
    lbEl.textContent = prefix + (v ? v.split("/").pop() : "全部");   // 显示末级, title 全路径
    lbEl.parentElement.title = v;
  };
  const nodesAt = () => {   // stack 对应的节点层
    let nodes = REGIONS[treeKey];
    for (const s of stack) {
      const n = nodes.find(x => x.name === s);
      nodes = n ? n.children : [];
    }
    return nodes;
  };
  const render = () => {
    const sel = state[key], cur = stack.join("/");
    const rows = nodesAt().map(n => {
      const path = (cur ? cur + "/" : "") + n.name;
      return `<button class="loc-row${path === sel ? " on" : ""}" data-n="${esc(n.name)}">` +
        `<span class="nm">${esc(n.name)}</span>` +
        `<span class="cnt">${n.count}${n.children.length ? " ›" : ""}</span></button>`;
    }).join("");
    optsEl.innerHTML =
      (stack.length ? `<button class="loc-back" data-b="1">‹ 返回</button>` +
        `<div class="loc-crumb">${esc(stack.join(" · "))}</div>` : "") +
      `<button data-a="${esc(cur)}"${sel === cur ? ' class="on"' : ""}>` +
      `${cur ? "全部" + esc(stack[stack.length - 1]) : "全部"}</button>` + rows;
  };
  optsEl.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.b) { stack.pop(); return render(); }   // ‹ 返回
    if (b.dataset.a !== undefined) {                     // "全部X" = 选中当前层
      menuEl.removeAttribute("open");
      setLoc(b.dataset.a);
      syncURL(); resetList();
      return;
    }
    const node = nodesAt().find(n => n.name === b.dataset.n);
    if (!node) return;
    if (node.children.length) { stack.push(node.name); return render(); }   // 钻下一级
    menuEl.removeAttribute("open");                     // 叶子 (区县) 直接选中
    setLoc([...stack, node.name].join("/"));
    syncURL(); resetList();
  });
  menuEl.addEventListener("toggle", () => {   // 关闭时把视图重置到当前所选的父层,
    if (menuEl.open) return;                  // 下次打开即所见 (toggle 异步, 开时才渲会闪旧视图)
    stack.length = 0;
    if (state[key]) stack.push(...state[key].split("/").slice(0, -1));
    render();
  });
  setLoc(state[key]);   // URL 带筛选时同步标签
  if (state[key]) stack.push(...state[key].split("/").slice(0, -1));
  render();
  return render;
}
const renderLocStart = bindLocMenu("fc-menu", "fc-opts", "fromLoc", "fc-lb", "起点: ", "start");
const renderLocEnd = bindLocMenu("tc-menu", "tc-opts", "toLoc", "tc-lb", "终点: ", "end");
$("#km-opts").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b || b.dataset.k === state.km) return;
  $("#km-menu").removeAttribute("open");
  state.km = b.dataset.k;
  $("#km-opts .on").classList.remove("on"); b.classList.add("on");
  $("#km-lb").textContent = "里程: " + KM_BUCKETS.find(x => x.v === state.km).lb;
  syncURL(); resetList();
});
$("#km-lb").textContent = "里程: " + KM_BUCKETS.find(b => b.v === state.km).lb;
if (state.km !== "all") {
  $("#km-opts .on").classList.remove("on");
  $(`#km-opts button[data-k="${state.km}"]`).classList.add("on");
}
(async () => {   // 起终点省市区树 (次数降序); 拉不到就只有"全部"
  try {
    const rg = await getJSON("/tesla/trips/api/regions");
    REGIONS.start = rg.start || [];
    REGIONS.end = rg.end || [];
  } catch (_e) { /* keep empty */ }
  renderLocStart(); renderLocEnd();
})();

/* 驾驶员筛选: 选项来自设置页的驾驶员表 (没配驾驶员整颗筛选藏掉); 筛选口径与
   卡片一致 —— 选默认驾驶员 = 标注它的 + 未标注的 (后端合并处理) */
(async () => {
  if (driversCache === undefined) {
    try { driversCache = await getJSON("/tesla/api/drivers"); }
    catch { driversCache = null; }
  }
  const drivers = driversCache || [];
  if (!drivers.length) return;
  const opts = $("#drv-opts");
  opts.innerHTML = `<button data-id=""${state.drvId == null ? ' class="on"' : ""}>全部</button>` +
    drivers.map(d =>
      `<button data-id="${d.id}"${state.drvId === d.id ? ' class="on"' : ""}>${esc(d.name)}</button>`).join("");
  if (state.drvId != null) {               // URL 深链带入的驾驶员要存在才算数
    const hit = drivers.find(d => d.id === state.drvId);
    if (hit) $("#drv-lb").textContent = "驾驶员: " + hit.name;
    else {
      state.drvId = null;
      opts.querySelector(".on")?.classList.remove("on");
      opts.querySelector('button[data-id=""]').classList.add("on");
    }
  }
  $("#drv-menu").hidden = false;
})();
$("#drv-opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const v = b.dataset.id === "" ? null : +b.dataset.id;
  if (v === state.drvId) return;
  $("#drv-menu").removeAttribute("open");
  state.drvId = v;
  $("#drv-opts .on").classList.remove("on"); b.classList.add("on");
  $("#drv-lb").textContent = "驾驶员: " + b.textContent;
  syncURL(); resetList();
});

/* 懒加载: 触底前 PRELOAD_PX 预加载下一页 */
new IntersectionObserver(es => {
  if (es[0].isIntersecting) loadMore();
}, { rootMargin: PRELOAD_PX + "px" }).observe(tailEl);

$("#retry").addEventListener("click", () => { state.err = null; loadMore(); });
$("#logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.replace("/login");
});

/* ============================ 多选: 连续行程拼成一条轨迹 ============================ */
const MERGE_MAX = 100;             // 合并接口上限 (后端 /api/merged 校验 2~100 段)
let selAnchor = -1;                 // 范围锚点 (点选的第一张卡)
let selRange = [-1, -1];            // 当前选中范围 [from, to] (闭区间, 必连续)

function applyPick() {
  const [a, b] = selRange, on = a >= 0;
  [...listEl.children].forEach((el, i) => el.classList.toggle("picked", on && i >= a && i <= b));
  const n = on ? b - a + 1 : 0;
  const km = on ? items.slice(a, b + 1).reduce((s, it) => s + (it.km || 0), 0) : 0;
  $("#sel-count").textContent = n;
  $("#sel-km").textContent = num(km);
  /* 上限提示: 划选超上限, 或全选封顶 (列表还有更多段装不进) 都亮 */
  $("#sel-cap").hidden = n < MERGE_MAX || items.length <= MERGE_MAX;
  $("#sel-go").disabled = n < 2 || n > MERGE_MAX;
  $("#gp-btn").disabled = n < 2 || n > MERGE_MAX;   // 存分组与合并播放同一上限
  $("#sel-all").textContent =             // 已选全部 → 再点一次变清空
    on && a === 0 && b === items.length - 1 ? "清空" : "全选";
}

/* 两段式点选: 点第一张卡定锚, 点另一张 → 锚点到该处的连续范围; 再点锚点清空重来 */
function pickCard(el) {
  const i = [...listEl.children].indexOf(el);
  if (i < 0) return;
  if (selAnchor < 0) { selAnchor = i; selRange = [i, i]; }
  else if (i === selAnchor) { selAnchor = -1; selRange = [-1, -1]; }
  else selRange = [Math.min(selAnchor, i), Math.max(selAnchor, i)];
  applyPick();
}

function enterSelect() {
  document.body.classList.add("selecting");
  $("#selbar").hidden = false;
  selAnchor = -1; selRange = [-1, -1];
  applyPick();
}
function exitSelect() {
  document.body.classList.remove("selecting");
  $("#selbar").hidden = true;
  $("#selbar").classList.remove("naming");
  selAnchor = -1; selRange = [-1, -1];
  applyPick();
}
/* 长按卡片进多选 (多选按钮已撤, 这是唯一入口); 触屏长按 / 桌面按住 480ms
   → 进多选并选中这张卡。移动超 10px (滚动/下拉) 即取消; 长按后紧跟的
   click 吞掉, 别又把弹层打开。 */
(function setupLongPress() {
  const HOLD_MS = 480;
  let timer = null, card = null, x0 = 0, y0 = 0, fired = false, suppress = false;
  const clear = () => {
    if (timer) clearTimeout(timer);
    timer = null; card = null; fired = false;
  };
  const start = (x, y, target) => {
    suppress = false;
    if (document.body.classList.contains("selecting")) return;
    card = target.closest(".card-t");
    if (!card) return;
    x0 = x; y0 = y;
    timer = setTimeout(() => {
      timer = null; fired = true; suppress = true;
      enterSelect(); pickCard(card);
    }, HOLD_MS);
  };
  const move = (x, y) => {
    if (timer != null && Math.hypot(x - x0, y - y0) > 10) clear();
  };
  listEl.addEventListener("touchstart", e => {
    if (e.touches.length !== 1) { clear(); return; }
    start(e.touches[0].clientX, e.touches[0].clientY, e.target);
  }, { passive: true });
  listEl.addEventListener("touchmove",
    e => move(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
  listEl.addEventListener("touchend", e => {
    if (fired) { e.preventDefault(); suppress = false; }   // click 不会再产生
    clear();
  }, { passive: false });
  listEl.addEventListener("touchcancel", clear, { passive: true });
  listEl.addEventListener("mousedown", e => {   // 桌面: 按住不放同样进多选
    if (e.button === 0) start(e.clientX, e.clientY, e.target);
  });
  window.addEventListener("mousemove", e => move(e.clientX, e.clientY));
  window.addEventListener("mouseup", clear);
  listEl.addEventListener("click", e => {       // 长按紧随的 click 不开弹层
    if (suppress) { suppress = false; e.stopPropagation(); e.preventDefault(); }
  }, true);
  listEl.addEventListener("contextmenu", e => {  // iOS 长按呼系统菜单会掐掉触摸
    if (e.target.closest(".card-t")) e.preventDefault();
  });
})();
$("#sel-cancel").addEventListener("click", exitSelect);
/* 全选: 选中当前筛选下的全部行程, 没装够的页先补载; 合并接口一次最多
   MERGE_MAX 段, 超出只选最新的 (列表按时间倒序) 前 100 段。已选全部时
   按钮变"清空", 再点一次取消选择。 */
$("#sel-all").addEventListener("click", async () => {
  const isAll = selRange[0] === 0 && selRange[1] === items.length - 1;
  if (!isAll) {
    const btn = $("#sel-all");
    btn.disabled = true;
    try {
      const target = Math.min(state.total || items.length, MERGE_MAX);
      while (!state.done && !state.err && items.length < target) await loadMore();
    } finally { btn.disabled = false; }
    if (state.err) return;        // 补载失败: 列表区已有重试入口, 不动现有选择
  }
  selAnchor = -1;
  selRange = isAll || items.length < 2 ? [-1, -1]
    : [0, Math.min(MERGE_MAX, items.length) - 1];
  applyPick();
});
$("#sel-go").addEventListener("click", () => {
  const ids = items.slice(selRange[0], selRange[1] + 1).map(it => it.id);
  exitSelect();
  openMerged(ids);
});

/* ============================ 轨迹分组 ============================ */
/* 逻辑分组存自有库 (api/groups), 行程原数据不动; 管理 (打开/改名/删除) 在
   独立的分组页, 本页只留创建入口 (多选 → 存为分组)。打开分组 = 行程页
   ?ids= 深链合并播放, 关弹层自动回分组页 (见 closeTrip)。 */
let gpIds = [];         // 进入命名模式时快照的选中 ids (之后划选变动不影响本次保存)
let toastTimer = null;

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  requestAnimationFrame(() => el.classList.add("on"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove("on");
    setTimeout(() => { el.hidden = true; }, 250);
  }, 1800);
}

// ---- 多选栏: 存为分组 (命名模式, 预填日期跨度) ----
$("#gp-btn").addEventListener("click", () => {
  gpIds = items.slice(selRange[0], selRange[1] + 1).map(it => it.id);
  const dNew = items[selRange[0]].date.slice(5);   // 列表时间倒序: [0] 最新 [末] 最旧
  const dOld = items[selRange[1]].date.slice(5);
  $("#gp-name").value = dNew === dOld ? dNew : `${dOld}~${dNew}`;   // 预填日期跨度, 可改
  $("#gp-save").disabled = false;
  $("#selbar").classList.add("naming");
  setTimeout(() => $("#gp-name").select(), 50);    // 等命名行布局稳定再全选
});

$("#gp-name-cancel").addEventListener("click", () =>
  $("#selbar").classList.remove("naming"));

$("#gp-name").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); $("#gp-save").click(); }
  else if (e.key === "Escape") { $("#selbar").classList.remove("naming"); }
});

$("#gp-save").addEventListener("click", async () => {
  const name = $("#gp-name").value.trim();
  if (!name) { toast("名字不能为空"); return; }
  const btn = $("#gp-save");
  btn.disabled = true;
  try {
    const r = await fetch("/tesla/trips/api/groups", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, ids: gpIds }),
    });
    if (r.status === 401) { location.replace("/login"); return; }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
    toast(`已存分组「${name}」`);
    exitSelect();
  } catch (err) {
    toast(`存分组失败: ${err.message}`);
    btn.disabled = false;
  }
});

