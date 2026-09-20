// view/trips-list-url.js — 行程列表视图 (壳版 2/6): 触底续载 loadMore
// (PRELOAD_PX 预载区, 首屏不满"视口+预载区"链式补载) 与筛选变化 resetList。
// 旧版 (js/trips-list-url.js) 的地址栏一族 (filterQS/listURL/urlTripKey/
// syncURL/setTimeRange) 全删: 3.0 壳零历史条目, 筛选住 localStorage
// (tesla-shell), 打开的行程由弹层自己 replaceState 镜像 (trips-sheet-open);
// 时间档上移抽屉全局 (tesla-time-range 的 timeRangeParams 直接穿参)。
// 文件名沿用旧名 (命名普查按 basename 折叠, 旧页与壳版同名不同目录)。
/* global getJSON, TR_PAGE, KM_BUCKETS, timeRangeParams, shellState, state,
   items, listEl, tailEl, renderCard, setTail, PRELOAD_PX */
/* exported loadMore, resetList */
"use strict";

async function loadMore() {
  if (state.loading || state.done) return;
  state.loading = true; state.err = null; setTail();
  try {
    /* 时间档全局 (抽屉): {from?, to?} 直接摊平; 车与行程筛选各自拼 */
    const p = new URLSearchParams({ offset: state.offset, limit: TR_PAGE,
                                     ...timeRangeParams() });
    if (shellState.carId != null) p.set("car_id", String(shellState.carId));
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

function resetList() {   // 筛选变化: 清空列表重新拉 (不滚顶, 旧页同款)
  items.length = 0; listEl.innerHTML = "";
  state.offset = 0; state.total = 0; state.done = false; state.err = null;
  setTail();
  loadMore();
}
