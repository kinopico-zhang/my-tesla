// tesla-paged-list — 分页列表骨架 (充电记录/行程列表共用): 触底预载 +
// 首屏不满链式续载 + IntersectionObserver 哨兵。IO 随视图 show/hide 建拆
// (藏着的视图不偷跑加载), refetch 罩 dim 半透明。
"use strict";
/* exported makePager, PRELOAD_PX */

const PRELOAD_PX = 800;   // 触底前多远开始预加载 (IO rootMargin 与链式续载共用)

/* cfg: { sentinel, container, limit,
          fetchPage(offset, limit) → {items, total},
          renderItem(it) → Node, paint(st)? }
   返回 { st, loadMore, refetch, start, stop }; st = {offset,total,loading,done,err},
   paint 在每次状态变化后回调 (视图自己刷 loader/endnote/errbox 那套尾巴)。 */
function makePager(cfg) {
  const st = { offset: 0, total: 0, loading: false, done: false, err: null };
  let io = null;
  const paint = () => { if (cfg.paint) cfg.paint(st); };

  async function loadMore(reset) {
    if (st.loading || (st.done && !reset)) return;
    st.loading = true; st.err = null; paint();
    try {
      const d = await cfg.fetchPage(st.offset, cfg.limit);
      if (reset) cfg.container.innerHTML = "";
      st.total = d.total; st.offset += d.items.length;
      /* 空页也当到底 (服务端 total 虚高时防链式续载死循环) */
      if (!d.items.length || st.offset >= d.total) st.done = true;
      d.items.forEach(it => cfg.container.appendChild(cfg.renderItem(it)));
    } catch (e) {
      st.err = "数据加载失败: " + e.message;
    }
    st.loading = false; paint();
    /* 首页填不满"视口+预载区"时, tail 一直留在交叉区里, IO 只在进出过渡时
       回调, 不会再触发 —— 主动续载直到 tail 滚出预载区。
       (Chrome 桌面端宽屏下 24 张卡不足一屏, 曾因此永远卡在第一页。) */
    if (!st.done && !st.err &&
        cfg.sentinel.getBoundingClientRect().top < window.innerHeight + PRELOAD_PX)
      loadMore(false);
  }

  async function refetch() {
    st.offset = 0; st.total = 0; st.done = false; st.err = null;
    cfg.container.classList.add("dim");
    await loadMore(true);
    cfg.container.classList.remove("dim");
  }

  function start() {
    if (io) return;
    io = new IntersectionObserver(es => {
      if (es[0].isIntersecting) loadMore(false);
    }, { rootMargin: PRELOAD_PX + "px" });
    io.observe(cfg.sentinel);
  }
  function stop() { if (io) { io.disconnect(); io = null; } }

  return { st, loadMore, refetch, start, stop };
}
