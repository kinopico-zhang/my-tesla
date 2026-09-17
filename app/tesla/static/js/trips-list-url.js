// trips-list-url.js — 行程页 (2/6): 触底续载 loadMore (PRELOAD_PX 预载区,
// 首屏不满"视口+预载区"链式补载) 与地址栏 —— 筛选参数编码 (filterQS /
// listURL / urlTripKey 行程深链 ?id= / ?ids=)、syncURL 同步、筛选变化
// resetList 重拉、setTimeRange 档位切换。
// 由 trips-list.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// trips.html 里的顺序加载, 跨模块引用走全局); 底座在 trips-list-page.js。
/* global $, getJSON, PAGE, TIME_RANGES, timeFrom, KM_BUCKETS, state, items,
   listEl, tailEl, renderCard, setTail */
/* exported PRELOAD_PX, loadMore, timeLabel, filterQS, listURL, urlTripKey,
   syncURL, resetList, setTimeRange */
"use strict";
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
