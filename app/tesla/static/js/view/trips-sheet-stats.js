// view/trips-sheet-stats.js — 行程详情左滑统计页 (2026-09-22 用户点名
// 「往左划显示行程统计页面」→「统计改成动态, 整个页面都换掉」→ 2026-09-23
// 点名「不需要动画, 直接展示全貌」):
// 轨迹页 (地图) ↔ 动态页 ↔ 统计页 的原生 snap 横滑整页对
// 换, 弹层底一行页标题 + 白点页标 (tp-foot, 2026-09-23 用户点名用最下方
// 的空白: 类似 iOS 桌面的白点, 几页几个点、点亮当前页; 2026-09-24 点名
// 竖排 —— 圆点在上标题在下, 点整块切下一页, 末页绕回第一页; 右上角页
// 标题同日退役让位给驾驶员); 地图横滑归地图平移, 头部/数字带/播放条横滑
// 转发切页 (数字带/播放条 2026-09-27 随三页独立住回轨迹页 —— touch-action
// 拦滚的区原生不滚, 转发是主路; 撤的从来只是翻页收放, 图上的轴名/刻度
// 全保着)。三页各管各的 (2026-09-27 用户点名「三个页面不需要联动」):
// 动态页读数据会话 (curSess —— openTrip 播放编排里 playTrack(defer) 先于
// 地图预载, 预载没完会话早已就绪), 统计页读服务端直方图 (开弹层即取
// tripHistKick, 与轨迹下载/地图预载全程无关), 两页空态各跟各的数据,
// 互不等待; 布局恒定 (数字带/播放条不再随翻页收放, 地图/图卡尺寸全程
// 不变, 整带收放那套退役)。
// 三张图 canvas 手绘 (不为
// 三张小图拉整库
// echarts): 速度图双轴 —— 红绿速度 + 右轴蓝线里程累计; 电耗图双轴 ——
// 总电耗累计为主轴 + 右轴橙线百公里电耗 kWh/100km (真实能耗 1km 里程滑
// 窗: 功率×时间积分定标官方总电耗, 停车耗电照算 —— 红灯处缓缓上抬; 起
// 步段窗没攒满用从起步攒到当前的动态窗, 开头不再铺平线; 没功耗数据的行
// 程退回单累计曲线); 海拔图缺采样沿用最近一次可用值铺平不断线 (2026-09-25
// 用户点名; 断口来自补路点/零星缺采样)。曲线一开
// 就画全程 (不跟播放逐段长了, 2026-09-23 用户点名; 图卡标题同日点名撤
// 掉, 轴的名字顶上)。
// 统计页 (2026-09-23 用户点名, 同日点名拆成两张卡; 2026-09-24 对账官方
// 口径改造, 同日二次对账修公式): 三卡数据全部服务端在原始 positions 上
// 聚合 (接口 /hist 懒取, 见 fetchTrackHist), 档沿自然十进整除 0-9/10-19
// (2026-09-24 用户点名; 面板原式 speed×单位CASE/10 是 numeric 真除四舍五
// 入, 档值 80 = 75-84 —— 上午两版逐字对齐面板后按点名改自然档, 有意差
// 半档); 第一张速度直方图 (柱 = 各档
// 时间, 分; 柱色按档中值归轨迹线五档配色), 第二张各档行驶里程 (km,
// 2026-09-24
// 用户点名; 蓝 = 里程轴同色) —— 这两张是自家口径 (全地形, 不过滤行程);
// 第三张各档电耗 Wh/km (橙柱, 官方 Grafana「不同速度下的能耗」面板
// 逐条同口径: 平地段 |Δ海拔|<1m, Σ(power·speed)/Σ(speed)×10, 只收 ≥1km
// 行程 —— 首版误成 ÷平地均速×1000, 120 档比面板低 20%/低速档
// 高数倍, 2026-09-24 用户拿面板对账点名修掉; 0 档官方默认砍掉, 同日
// 用户点名照画 (纯停车采样速度为 0 在公式里零贡献, 这档只剩蠕行),
// 卡名也照说的省成「电耗」; 没功耗/没平地段/全 <1km 的
// 行程整卡收起, 同海拔卡)。点柱读值, 再点撤掉, 三张卡同一份选中; 电耗卡
// 读数带该档平地平均功率 (面板 avg_power = AVG(power) 采样均值, 一起读)。
// 轴的含义单位标在顶格刻度上, 刻度字号 12px (2026-09-23 用户点名放大);
// 两轴的名字在顶带成对 (左轴名在左、右轴名在右, 同字号, 色跟轴 ——
// 「速度对里程」「电耗对 kWh/100km」, 海拔单轴名在左; 速度轴名铺曲线同款红
// 黄绿渐变, 2026-09-23 用户点名)。三张图共用同一条时间横
// 轴 (同一 t0/span 与画布宽, 时刻↔像素一一对齐 —— 2026-09-23 用户点名
// 「时间要对齐」); 点任意一张图, 三张同时落竖线读出该点各轴的值 (再点原
// 处撤掉)。小 rAF 弹层开着就跑 (数据一到就画, 不看人在哪页), 只盯数据
// 变化 (换会话/流式追加/直方图到了) 重建, 平时零重绘; 翻页飞行中记静默
// 窗, 重活等落定 (2026-09-27 用户报「卡卡的」主线程元凶: 飞行途中全量
// 重画)。播放侧在会话对象上多挂 ts/it/cum/ecum 一行, 本模块不进播放循环。
/* global TrackUtil, FormatUtil, curSess, getJSON */
/* exported TripStats */
/* UMD 挂载层: node (测试 require) 只拿纯函数; 浏览器加载后接线 DOM
   (c8 标记忽略的理由与 track-animation.js 同款)。 */
/* c8 ignore start */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.TripStats = api;
    boot(root, api);
  }
})(/** @type {Window | Record<string, unknown>} */(typeof self !== "undefined" ? self : this),
    function () {
/* c8 ignore stop */
  "use strict";

  /* 模型累计能耗 → 定标 kWh: 整条定到官方总电耗 (播放实时格同款比例) */
  function kwhAt(model, modelTotal, kwh) {
    return modelTotal > 0 ? kwh * model / modelTotal : 0;
  }

  /* 图表 y 轴顶格值: 抬到 1.2/1.5/2/2.5/3/4/5/6/8×10ⁿ 的整刻度 */
  const NICE = [1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8];
  function niceCeil(v) {
    if (!(v > 0)) return 1;
    const k = Math.pow(10, Math.floor(Math.log(v) / Math.LN10));
    for (const m of NICE) if (v <= m * k + 1e-9) return m * k;
    return 10 * k;
  }

  return { kwhAt: kwhAt, niceCeil: niceCeil };
});

/* ============================ 浏览器接线 ============================ */
function boot(root, pure) {
  const doc = root.document;
  const pager = doc.getElementById("tp-pager");
  const sheet = doc.getElementById("sheet");
  if (!pager || !sheet) return;
  const EMPTY = doc.getElementById("tps-empty");
  const EMPTYH = doc.getElementById("tps-empty-h");   // 统计页自己的空态
  const FOOT_LB = ["行驶轨迹", "行驶数据", "行驶统计"];   // 弹层底一行页标题 (tp-foot-lb)
  const footLb = doc.getElementById("tp-foot-lb");
  const footDots = doc.querySelectorAll("#tp-dots i");   // 白点页标, 亮当前页
  let page = 0, rafOn = false, builtFor = null, builtN = 0;
  let curIt = null, quietUntil = 0;    // 开弹层的行程条目 (统计页数据源) / 翻页静默窗到点
  let t0 = 0, span = 1, charts = [];   // build() 产物: 时间轴 + 三张图的画法
  let inspIdx = null;                  // 点查下标 (三图联动, 全局一份)
  let hist = null, histSel = null;     // 统计页直方图数据 + 选中档 (点柱读值)

  /* 切页: 横滑 (页签 2026-09-22 用户点名撤掉) + 点底行页标区切下一页
     (2026-09-24 用户点名, 末页绕回第一页; 2026-09-22 点名的是右上角页
     标题, 2026-09-24 该位让给驾驶员); 底行页标题与白点都跟着换 —— 白点
     几个几个亮, 一眼看出共几页、当前在哪页 (2026-09-23 用户点名 iOS
     桌面同款) */
  const syncPage = () => {
    if (footLb) footLb.textContent = FOOT_LB[page] || FOOT_LB[0];
    footDots.forEach((el, k) => el.classList.toggle("on", k === page));
  };
  /* 切页滚动只跟页位 (标题/白点) —— 布局恒定 (2026-09-27 用户点名三页
     独立: 数字带/播放条住轨迹页不再收放, 落定后没有要补的重排, 整带收放
     那套退役); 滑动/惯性进行中记静默窗, build/重画等翻页落定 (同日用户报
     「卡卡的」主线程元凶: 飞行途中全量重画三张图) */
  pager.addEventListener("scroll", () => {
    quietUntil = Date.now() + 200;   // 每帧续期, 滚停 200ms 后重活恢复
    const p = Math.round(pager.scrollLeft / Math.max(1, pager.clientWidth));
    if (p === page) return;
    page = p;
    syncPage();
  }, { passive: true });
  /* 点底行页标区 (圆点+标题整块) = 切下一页, 末页绕回第一页循环
     (2026-09-24 用户点名); scrollTo 会触发上面的 scroll, page/标题/rAF
     随之同步 */
  const N_PAGES = pager.children.length || 1;
  const foot = doc.getElementById("tp-foot");
  if (foot) foot.addEventListener("click", () => {
    const next = (page + 1) % N_PAGES;
    pager.scrollTo({ left: next * pager.clientWidth, behavior: "smooth" });
  });
  /* 横滑转发 (头部 + 数字带 + 播放条): 地图自己吃横滑 (平移), 这三处要
     切页 —— 头部一直在分页外没主; 数字带/播放条 2026-09-25 随三页等高
     修平从轨迹页挪出分页, 原生滚页没了, 转发成了主路 (更早裹在分页里时
     它就是 iOS snap 橡皮筋/斜起手死手势的保底, 2026-09-22 用户实报「有
     时候左滑滑不动」), touchend 时够横的滑一律 scrollTo 强制切页 ——
     原生先动了也只是殊途同归; 竖向不管 (数字带还有下滑收起)。播放条的
     进度条起手不算 (拖进度条横移几十像素是常态, closest 排除) */
  for (const sel of ["#sheet .sh-head", "#sheet .sh-cells", "#sheet .playbar"]) {
    const zone = doc.querySelector(sel); if (!zone) continue;
    let x0 = 0, y0 = 0, on = false;
    zone.addEventListener("touchstart", e => {
      on = e.touches.length === 1 && !e.target.closest(".pb-seek");
      if (on) { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }
    }, { passive: true });
    zone.addEventListener("touchend", e => {
      if (!on) return;
      on = false;
      const t = e.changedTouches[0]; if (!t) return;
      const dx = t.clientX - x0, dy = t.clientY - y0;
      if (Math.abs(dx) < 56 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
      /* 三页通用 (2026-09-23 加统计页): 左滑下一页/右滑上一页, 到头不滚
         —— 末页绕回只留给底行页标区点击那一路 */
      pager.scrollTo({ left: Math.min(N_PAGES - 1, Math.max(0, page + (dx < 0 ? 1 : -1)))
                               * pager.clientWidth, behavior: "smooth" });
    }, { passive: true });
  }
  /* 分页内图表页 (动态/统计) 转发保底 (2026-09-27 用户实报「左滑不动, 要滑
     好几遍才行」→ 修后又报「还是不灵敏, 卡卡的」): 切页主路是原生滚页 ——
     两页手势已收纯横轴 (touch-action: pan-x, 见 tesla-trips-sheet.css),
     iOS 可认领的轴只剩一个, 起手即跟手; 这里只兜仲裁没认出来、分页器纹丝
     未动的死手势, 够横的滑松手直接切页。原生已滚 (哪怕一点) 就不掺和 ——
     动量/snap 自己收尾, 再补一次 smooth scrollTo 会和飞行中的滚动打架
     (二次起步的顿挫)。目标页用起手快照定 —— 原生若已切走, scroll 监听会
     先把 page 跟着挪, 用它会连跳两页; touchcancel 也算 —— iOS 认领原生
     滚动后发的是 cancel 不是 end。地图页不转发 (横滑归地图平移)。 */
  for (const sel of ["#sheet .tp-stats", "#sheet .tp-hist"]) {
    const zone = doc.querySelector(sel); if (!zone) continue;
    let x0 = 0, y0 = 0, startPage = 0, on = false;
    zone.addEventListener("touchstart", e => {
      on = e.touches.length === 1;
      if (on) { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; startPage = page; }
    }, { passive: true });
    const fwd = e => {
      if (!on) return;
      on = false;
      const t = e.changedTouches[0]; if (!t) return;
      const dx = t.clientX - x0, dy = t.clientY - y0;
      if (Math.abs(dx) < 56 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
      if (Math.abs(pager.scrollLeft - startPage * pager.clientWidth) > 4) return;
      pager.scrollTo({ left: Math.min(N_PAGES - 1, Math.max(0, startPage + (dx < 0 ? 1 : -1)))
                               * pager.clientWidth, behavior: "smooth" });
    };
    zone.addEventListener("touchend", fwd, { passive: true });
    zone.addEventListener("touchcancel", fwd, { passive: true });
  }
  /* 关弹层即复位回地图页: observer 回调在下一帧绘制前跑, 滑出动画里
     不会闪一下切页; 下一次打开从轨迹页起 (统计页是看一眼的事)。
     开弹层即起小循环 (2026-09-27 三页独立): 三页数据各画各的, 不看人在
     哪页 —— 会话/直方图先于用户滑过去就已画好; 关了 tick 自己停 */
  new MutationObserver(() => {
    if (sheet.classList.contains("show")) startRaf();
    else if (page !== 0) pager.scrollLeft = 0;
  }).observe(sheet, { attributes: true, attributeFilter: ["class"] });
  root.addEventListener("resize", () => {
    if (!rafOn) return;
    if (builtFor) { build(); renderAll(); }
    else if (hist) drawHist();   // 统计页独立成画期 (会话未起): 柱状跟新尺寸
  });

  /* 点图查值 (2026-09-22 用户点名, 2026-09-23 点名三图联动): 点任意一张
     图, 竖线就近落到采样点 —— 三张图共用同一条时间轴, 落点时刻一致, 三
     张同时亮竖线各自读值; 点回原处 (±12px 内) 撤掉。换行程/流式追加会
     重建, 点查状态自然清零 */
  for (const cv of doc.querySelectorAll("#tp-stats canvas")) {
    cv.addEventListener("click", e => {
      const box = cv.getBoundingClientRect();
      if (!builtFor || !box.width || span <= 0) return;
      const t = t0 + Math.min(Math.max(e.clientX - box.left, 0), box.width)
                     / box.width * span;
      const tsB = builtFor.ts, NB = tsB.length;
      let i = 0;
      while (i + 1 < NB && tsB[i + 1] <= t) i++;
      if (i + 1 < NB && t - tsB[i] > tsB[i + 1] - t) i++;   // 就近取点
      const px = v => (tsB[v] - t0) / span * box.width;
      inspIdx = inspIdx != null && Math.abs(px(i) - px(inspIdx)) < 12 ? null : i;
      renderAll();
    });
  }

  /* 左侧 y 刻度槽宽 (drawBars 画柱与统计页点柱分档共用, 详见 drawBars 处) */
  const HIST_GUT = 34;

  /* 统计页点柱读值 (2026-09-23 用户点名; 同日拆两张卡, 两张同一份选中):
     点哪根柱选中哪档, 卡顶带读出该档的值 (色跟各卡自己的柱), 再点同一
     根撤掉。直方图横轴是速度档不是时间, 不进三图联动, 自成一套选中态 */
  for (const cv of doc.querySelectorAll("#tp-hist canvas")) {
    cv.addEventListener("click", e => {
      const box = cv.getBoundingClientRect();
      if (!hist || !box.width) return;
      const K = hist.t.length;               // 档数随这趟最快速度走
      const k = Math.min(K - 1, Math.max(0,   // 槽宽与 drawBars 同一常量
        Math.floor((e.clientX - box.left - HIST_GUT)
                   / (box.width - HIST_GUT) * K)));
      histSel = histSel === k ? null : k;
      renderAll();
    });
  }

  /* 自转小循环: 弹层开着就跑 (开弹层 MutationObserver 起, 关了自停) ——
     三页数据各画各的, 不看人在哪页; 静态全量图不逐帧重画, 只盯数据变化
     (换会话/流式追加 N 变了/直方图到了) 重建, 平时零重绘 */
  function startRaf() {
    if (rafOn) return;
    rafOn = true;
    requestAnimationFrame(function tick() {
      if (!rafOn) return;
      if (!sheet.classList.contains("show")) { rafOn = false; return; }
      const s = curSess;
      /* 两页空态各跟各的数据 (2026-09-27 用户点名三页独立): 动态页等的是
         轨迹会话 (curSess —— openTrip 里 playTrack(defer) 先于地图预载, 预
         载没完也早已就绪), 统计页等的是服务端直方图 (curIt.hist, 开弹层
         即取, 与轨迹/地图无关) —— 不再「轨迹还没加载完, 统计页跟着转圈」 */
      EMPTY.hidden = !!s;
      EMPTYH.hidden = !!(curIt && curIt.hist !== undefined);
      const busy = Date.now() < quietUntil;   // 翻页飞行中: 重活等落定
      if (!busy && s && s.ts && s.ts.length
          && (s !== builtFor || (s.N || s.pts.length) !== builtN)) {
        /* build 一抛不许带走整个循环 (2026-09-23 事故: 工具库漏导出
           SPEED_STOPS, build 抛错后重排队排不上, 动态/统计两页图全空还
           零线索) —— 失败这趟留旧图, 控制台留痕, 循环保活: 换会话/流式
           追加 (N 变了) 还能自救 */
        try {
          build();
          renderAll();
        } catch (err) { console.error(err); }
      }
      /* 统计页独立成画: 直方图先于轨迹会话到 (开弹层即取), 柱状图不等
         地图; 会话已起 (build 先画过) 也走这补 —— hist 后到时第三卡与
         柱状一起亮, 不再等下一轮重建 */
      if (!busy && curIt && curIt.hist != null && hist !== curIt.hist) {
        hist = curIt.hist;
        doc.getElementById("tps-card-hist2").hidden =
          !(hist.pk && hist.pk.some(v => v != null));
        drawHist();
      }
      if (rafOn) requestAnimationFrame(tick);
    });
  }

  /* ---- 三张图: build 定轴定卡 (y 轴定格在全程值), renderAll 全量画 ---- */
  function build() {
    /* 读数据会话不是播放会话 (2026-09-27 三页独立): openTrip 里 playTrack
       (defer) 先于地图预载, 预载没完 curSess 早已就绪 —— 动态页不等地图
       就能定轴成画 (anim 要到 sess.begin() 才非空, 读它预载期永远空) */
    const s = curSess;
    if (!s || !s.ts || !s.ts.length) return;
    builtFor = s;
    builtN = s.N || s.pts.length;
    inspIdx = null;
    histSel = null;
    const { pts, ts, it, cum, ecum } = s;
    const N = pts.length;
    t0 = ts[0] || 0;
    span = Math.max(1, (ts[N - 1] || 0) - t0);
    charts = [];

    let vPeak = 0;
    for (const p of pts) if ((p[2] || 0) > vPeak) vPeak = p[2] || 0;
    const vShow = it.speed_max != null ? it.speed_max : vPeak;
    const kmTotal = cum && cum.length === N ? (cum[N - 1] || 0) : 0;
    const fmtKm = v => v >= 10 ? String(Math.round(v)) : String(Math.round(v * 10) / 10);
    charts.push({
      cv: "tps-cv-spd", ys: pts.map(p => p[2] || 0),
      hi: pure.niceCeil(vShow),
      /* 速度图配色与轨迹线同口径: 段速取两端较大值 (trackutil.speedLines) */
      color: i => TrackUtil.SPEED_COLORS[
        TrackUtil.speedBucket(Math.max(pts[i][2] || 0, pts[i + 1][2] || 0))],
      fmtY: v => String(Math.round(v)),
      unit: "km/h",                              // 轴含义: 顶格刻度带单位
      tag: "速度",                               // 左轴名 (与右上角「里程」成对)
      tagGrad: TrackUtil.SPEED_COLORS,           // 轴名铺曲线同款红黄绿渐变 (用户点名)
      /* 双轴 (2026-09-22 用户点名「速度曲线加一个里程」): 右轴蓝线 = 里程
         累计 —— 与速度对照, 拥堵段平着走、巡航段匀着爬, 一眼看出快慢吃
         在里程上。右上角轴名 tag + 点查读数 tip (同日用户点名): 颜色都
         跟轴走, 读数左右两轴各报一个值 */
      y2: kmTotal > 0 ? {
        ys: cum, hi: pure.niceCeil(kmTotal), color: "#3987e5", unit: "km",
        tag: "里程", fmtY: fmtKm,
      } : null,
      tip: i => {
        const segs = [{ t: Math.round(pts[i][2] || 0) + " km/h",
                        c: "rgba(235,235,245,.85)" }];
        if (kmTotal > 0) segs.push({ t: fmtKm(cum[i]) + " km", c: "#3987e5" });
        return segs;
      },
    });

    /* 功率门槛与真实能耗逐点累计 (kWh, 电耗图右轴与统计页直方图共用):
       段能耗 = 两端功率均值 × 时长秒 (单端空用另一端, 补路点两眼全空按
       0 —— 隧道里的耗电由总账定标兜底; kW·s → kWh 除 3600, ts 是相对秒,
       当毫秒除 3.6e6 少一千倍 —— 总账定标把它抵消了数值碰巧对, 但时间
       直方图同款错误藏不住, 2026-09-23 用户报「柱子都太短」牵出) */
    let pMin = Infinity, pMax = -Infinity;
    for (const p of pts) {
      const v = p[3];
      if (v == null) continue;
      if (v < pMin) pMin = v;
      if (v > pMax) pMax = v;
    }
    const hasPw = pMax > -Infinity && Math.max(pMax, -pMin) > 0.5;   // kW 门槛 (session 同口径)
    const E = [0];
    for (let i = 1; i < N; i++) {
      const a = pts[i - 1][3], b = pts[i][3];
      const pw = a == null ? (b || 0) : b == null ? a : (a + b) / 2;
      E.push(E[i - 1] + pw * (ts[i] - ts[i - 1]) / 3600);
    }

    const eTotal = ecum && ecum[N - 1] || 0;
    const hasKwh = it.kwh != null && eTotal > 0;
    doc.getElementById("tps-card-kwh").hidden = !hasKwh;
    if (hasKwh) {
      /* 电耗卡双轴: 主轴 = 总电耗累计 kWh (能耗模型定标到整趟, 蓝线带面积
         —— 原来的电耗曲线), 右轴橙线 = 百公里电耗 kWh/100km (同日用户点
         名换的单位, 车机同款)。右轴口径 2026-09-23 用户三轮点名 (「功率
         改成 kWh/km」→「停车也需要耗电, 算真实的」): 能耗 = 功率×时间
         的真实积分 (停车时功率就是空调/电子件的负载, 照积 —— 车不挪分
         子涨、分母冻住, 红灯处曲线缓缓上抬), 总账定标到官方总电耗 (官
         方值是续航差×效率系数的电池口径, 功率遥测的积分漂移不进曲线)。
         滑窗按里程不按时间 (用户点名 1km): 值 = 窗内能耗差 ÷ 里程差
         ×100, 起步尖峰自然揉平; 起步段窗没攒满不硬铺平线 —— 窗长从起步
         攒到当前 (动态窗, 用户点名「前期数据不足用动态窗口」), 交汇处
         与满窗值无缝衔接; 行程不足 1km 窗缩到 1/3 里程 (同日用户点名)。
         没功耗数据的行程没有右轴, 退回单累计曲线 */
      const W = Math.min(1, Math.max((it.km || 0) / 3, .05));   // 1km 滑窗, 短行程缩窗
      const pk = hasPw && E[N - 1] > 1e-6 ? new Array(N).fill(null) : null;
      if (pk) {
        let j = 0;                                  // 双指针: 最小的满窗 [j..i]
        for (let i = 0; i < N; i++) {
          while (j + 1 < i && cum[i] - cum[j + 1] >= W - 1e-9) j++;
          const d = cum[i] - cum[j];
          if (d >= W - 1e-9)
            pk[i] = (E[i] - E[j]) / d * 100 * it.kwh / E[N - 1];  // kWh/100km, 定标官方
          else if (cum[i] >= .05)                   // 起步动态窗: 从起步攒到当前
            pk[i] = E[i] / cum[i] * 100 * it.kwh / E[N - 1];
        }
        /* 起步前位移不足 50m 的点 (动态窗也不够格, 除数太小没意义) 拿首个
           有效值回铺 —— 只剩开头一小截; 走过 50m 后满窗/动态窗总有一款接
           住, 一路有值不断空 (2026-09-23 用户点名「停车也耗电」), hold 兜
           底防御 (理论上不会再空) */
        let first = 0;
        while (first < N && pk[first] == null) first++;
        if (first < N) {
          for (let k = 0; k < first; k++) pk[k] = pk[first];   // 首段回铺
          let hold = pk[first];
          for (let i = first + 1; i < N; i++) {
            if (pk[i] != null) hold = pk[i];
            else pk[i] = hold;
          }
        }
      }
      const hasPk = !!pk && pk.some(v => v != null);
      let hi2 = 1, lo2 = 0;
      if (hasPk) {
        /* 轴定到全程 min..max: 头一版按 95 分位定 + 越轴夹平, 尖峰被削了
           顶 (2026-09-23 用户实报「曲线显示不全」), 改回全量盖住 */
        let m2 = Infinity, x2 = -Infinity;
        for (const v of pk) if (v != null) {
          if (v < m2) m2 = v;
          if (v > x2) x2 = v;
        }
        hi2 = pure.niceCeil(Math.max(x2, 10));       // 百公里口径整刻度, 兜 10
        lo2 = m2 < 0 ? -pure.niceCeil(Math.max(-m2, 2)) : 0;   // 回收侧同法
      }
      charts.push({
        cv: "tps-cv-kwh",
        ys: ecum.map(v => pure.kwhAt(v, eTotal, it.kwh)),
        hi: pure.niceCeil(it.kwh), fill: "rgba(224,138,46,.16)",
        labColor: "#3987e5", unit: "kWh",         // 左轴跟累计曲线配色
        tag: "电耗",                              // 左轴名 (与右上角「kWh/100km」成对)
        fmtY: v => v.toFixed(1),
        y2: hasPk ? {
          ys: pk, lo: lo2, hi: hi2,
          color: "#e08a2e", tag: "kWh/100km", fmtY: v => v.toFixed(1),
        } : null,
        tip: i => {
          const segs = [{ t: pure.kwhAt(ecum[i] || 0, eTotal, it.kwh)
                          .toFixed(1) + " kWh", c: "#3987e5" }];
          if (hasPk) {
            const v = pk[i];
            segs.push({ t: (v == null ? "—" : v.toFixed(1)) + " kWh/100km",
                        c: "#e08a2e" });
          }
          return segs;
        },
      });
    }

    /* 海拔缺采样不断线 (2026-09-25 用户点名「海拔不要出现断点, 如果没有
       数据, 沿用最近一次可用的值」): 断口来自补路点 (信号断档的贴路补点
       没海拔) 和零星缺采样 —— 缺的点沿用最近一次可用值铺平, 点查读数跟
       画出来的值走; 开头还没见过海拔的点没值可沿用, 仍从首个有效值起笔
       (全库实测首点都带海拔, 实际碰不到) */
    const alt = pts.map(p => p[4]);
    let aMin = Infinity, aMax = -Infinity, lastA = null;
    for (let i = 0; i < alt.length; i++) {
      const v = alt[i];
      if (v != null) {
        lastA = v;
        if (v < aMin) aMin = v;
        if (v > aMax) aMax = v;
      } else if (lastA != null) alt[i] = lastA;   // 沿用最近一次可用值
    }
    doc.getElementById("tps-card-alt").hidden = aMax < aMin;
    if (aMax >= aMin) {
      const pad = Math.max(15, (aMax - aMin) * .12);
      charts.push({
        cv: "tps-cv-alt", ys: alt, lo: aMin - pad, hi: aMax + pad,
        fill: "rgba(57,135,229,.14)", labColor: "#3987e5", unit: "m",
        tag: "海拔",                              // 单轴: 名字在左上角
        fmtY: v => String(Math.round(v)),
        tip: i => {
          const e = alt[i];                       // 读数跟画出来的值走 (补值也读得出)
          return [{ t: (e == null ? "—" : String(Math.round(e))) + " m",
                    c: "#3987e5" }];
        },
      });
    }
    /* 统计页三卡 (2026-09-24 对账官方口径): 速度档直方图改服务端在原始
       positions 上聚合 —— 旧客户端算法 (下采样载荷 + floor 档沿 + 混地形
       + 滚阻风阻模型定标) 与官方 SpeedRates 面板差数倍 (单条 38km 实测
       80 档 129 vs 官方 86 Wh/km, 模型形状 ≠ 真实逐点功耗); 新口径
       自然档沿 + 平地地形 + 官方公式 (Σ(power·speed)/Σ(speed)×10,
       Wh/km), 单位也从 kWh/100km 换 Wh/km 对齐面板与弹层数字带。载荷没
       带才走这里的兜底取数 (主路: openTrip 开弹层即调 tripHistKick) */
    hist = null;
    if (N > 1) {
      if (it.hist) hist = it.hist;
      else if (!it.histTried) fetchTrackHist(it);
    }
    /* 电耗卡没数据整卡收起 (没功耗/没平地段/全 <1km 的行程), 同海拔卡;
       全 None 的 pk 数组也算没数据 (真有数据的档才亮卡)。在途亮空框那套
       (在途位) 随 2026-09-27 三页独立退役: 空态 (EMPTYH) 盖整页,
       撤掉与三卡首亮同一拍, 没有卡蹦出来挤别人的时机 */
    doc.getElementById("tps-card-hist2").hidden =
      !(hist && hist.pk && hist.pk.some(v => v != null));
  }

  /* 统计页数据入口 (openTrip 开弹层即调, 2026-09-27 用户点名三页独立):
     直方图服务端只要行程身份, 与轨迹下载/地图预载全程无关; curIt 记住
     当前行程, 空态/独立成画都跟它走。it.hist 落在行程条目上 (列表对象
     复用 = 天然缓存, 重开秒出); undefined = 还没取过 */
  root.tripHistKick = it => {
    curIt = it;
    if (it.hist === undefined) fetchTrackHist(it);
  };

  /* 速度档直方图取数: 单条秒回, 分组首开几秒 (每段原料服务端算好落自有
     库缓存, 之后永久秒回)。数据到了 tick 自会画 (会话没起也画 —— 统计页
     不等地图); 失败 it.hist = null 落定 (空态撤掉, 不留永久「读取中」),
     下次冷开列表对象新建再试 (histTried 防同一次重复发)。状态全落在 it
     上, 快速连开两个行程也互不干扰 —— 旧的全局在途闸 (请求令牌 + 在途
     位) 随三页独立一起退役 */
  function fetchTrackHist(it) {
    it.histTried = true;
    const key = it.merged ? (it.mergeKey || it.ids.join(",")) : String(it.id);
    getJSON(`/tesla/trips/api/hist?ids=${key}`)
      .then(d => { it.hist = d; })
      .catch(() => { it.hist = null; });   // 失败落定: 空态撤掉, 不留永久读取中
  }

  /* 全量画一遍 (静态: 不跟播放头走, 只有重建/点查/resize 会调) */
  function renderAll() {
    if (!builtFor) return;
    for (const c of charts) drawSeries(c);
    drawHist();
  }

  /* 通用折线 (静态全量, 2026-09-23 用户点名「不需要动画, 直接展示全貌」):
     时间横轴三张图共用 (同一 t0/span 与画布宽, 时刻↔像素一一对齐), 抽稀
     (≤1400 点, 保尾), 上下留白, 三道网格 + y 刻度, 按色分 Path2D 一次描
     完; o.fill 给了就在基线下铺面积 (缺值分段铺 —— 海拔 2026-09-25 起
     前向补值不断线, 这套兜着别的缺值曲线)。双轴: o.y2 = { ys,
     lo, hi, fmtY, color, unit } 给了就叠第二条曲线 —— 右轴定格 lo..hi
     (省 lo = 0..hi, 功率回收为负要定到负), 与主轴同一像素区间的仿射映
     射, 右侧刻度正好骑在这三道网格线上。轴的含义单位标在顶格刻度
     (o.unit / y2.unit), 左轴配色 o.labColor 跟主曲线 (多色曲线省略用中
     性灰), 右轴固定副轴色; 两轴的名字各标在顶带 (o.tag 左 / y2.tag 右,
     同字号成对, 色跟轴)。刻度字号 12px (2026-09-23 用户点名放大)。模块
     级 inspIdx (点图查值, 三图联动) 非空就落竖线, 顶带读出该点各轴的值,
     每段颜色跟各自轴 */
  function drawSeries(o) {
    const cv = doc.getElementById(o.cv);
    const box = cv.parentElement;
    const w = box.clientWidth, h = box.clientHeight;
    if (!w || !h || span <= 0) return;
    const dpr = root.devicePixelRatio || 1;
    const W = Math.round(w * dpr), H = Math.round(h * dpr);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const ts = builtFor.ts, ys = o.ys, N = ys.length;
    const lo = o.lo != null ? o.lo : 0;
    const hi = Math.max(o.hi, lo + 1e-9);
    const y2 = o.y2 || null;
    const lo2 = y2 && y2.lo != null ? y2.lo : 0;   // 右轴也能定负 (功率回收)
    const hi2 = y2 ? Math.max(y2.hi, lo2 + 1e-9) : 0;
    const TOP = 30, BOT = 14;   // 顶带两行 (轴名/点查读数 + 顶格刻度) / x 刻度行
    const yOf = v => TOP + (1 - (v - lo) / (hi - lo)) * (h - TOP - BOT);
    const yOf2 = v => TOP + (1 - (v - lo2) / (hi2 - lo2)) * (h - TOP - BOT);
    const xOf = i => (ts[i] - t0) / span * w;
    const stride = Math.max(1, Math.ceil(N / 1400));   // 抽稀, 尾点必在
    /* 一条全量曲线: 按色分组 Path2D; runs 给了就顺路收连续非空段 (面积
       用, 只有主轴要面积) */
    const pathOf = (vals, mapY, colorAt, runs) => {
      const out = new Map();
      let run = null, pi = -1, px = null, py = 0;
      const seg = (x, yy, c) => {
        let pth = out.get(c);
        if (!pth) out.set(c, pth = new Path2D());
        pth.moveTo(px, py); pth.lineTo(x, yy);
      };
      for (let i = 0; i <= N - 1; i += stride) {
        if (i !== 0 && i + stride > N - 1) i = N - 1;   // 尾点必在
        const y = vals[i], x = xOf(i);
        if (y == null) { px = null; run = null; continue; }
        const yy = mapY(y);
        if (px != null) seg(x, yy, colorAt ? colorAt(pi) : "#3987e5");
        if (runs) { if (!run) runs.push(run = []); run.push([x, yy]); }
        px = x; py = yy; pi = i;
      }
      return out;
    };
    const runs = [];                             // 面积用: 连续非空段 [x, y][]
    const byColor = pathOf(ys, yOf, o.color, o.fill ? runs : null);
    const byColor2 = y2 ? pathOf(y2.ys, yOf2, () => y2.color) : null;
    ctx.strokeStyle = "rgba(255,255,255,.08)";
    ctx.fillStyle = o.labColor || "rgba(235,235,245,.32)";   // 左轴色跟主曲线
    ctx.font = "12px -apple-system, sans-serif";   // 刻度字号 (用户点名放大)
    ctx.lineWidth = 1;
    for (const v of [hi, (hi + lo) / 2, lo]) {
      const y = yOf(v);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      let s = o.fmtY ? o.fmtY(v) : String(Math.round(v));
      if (v === hi && o.unit) s += " " + o.unit;   // 含义单位标在顶格刻度
      ctx.fillText(s, 2, y - 3);
    }
    if (o.tag) {   // 左轴名: 与右上角右轴名成对 (一左一右同字号, 色跟轴)
      if (o.tagGrad) {   // 轴名铺渐变 (速度图: 曲线同款红黄绿, 用户点名)
        const tw = ctx.measureText(o.tag).width;
        const g = ctx.createLinearGradient(2, 0, 2 + tw, 0);
        o.tagGrad.forEach((gc, k) => g.addColorStop(k / (o.tagGrad.length - 1), gc));
        ctx.fillStyle = g;
      } else ctx.fillStyle = o.labColor || "rgba(235,235,245,.85)";
      ctx.fillText(o.tag, 2, 11);
    }
    if (y2) {                                     // 右轴刻度: 副轴色+单位, 骑同一道网格
      ctx.fillStyle = y2.color;
      for (const v of [hi2, (hi2 + lo2) / 2, lo2]) {
        let s = y2.fmtY ? y2.fmtY(v) : String(Math.round(v));
        if (v === hi2 && y2.unit) s += " " + y2.unit;
        ctx.fillText(s, w - ctx.measureText(s).width - 2, yOf2(v) - 3);
      }
      if (y2.tag)   // 右上角轴名: 与刻度同色, 一眼对上右轴是谁
        ctx.fillText(y2.tag, w - ctx.measureText(y2.tag).width - 2, 11);
      ctx.fillStyle = "rgba(235,235,245,.32)";    // x 轴刻度回到中性灰
    }
    ctx.fillText("0", 2, h - 3);
    const xEnd = FormatUtil.fmtDurLive(t0 + span);
    ctx.fillText(xEnd, w - ctx.measureText(xEnd).width - 2, h - 3);
    if (o.fill) {
      ctx.fillStyle = o.fill;
      for (const r of runs) {
        if (r.length < 2) continue;
        ctx.beginPath();
        ctx.moveTo(r[0][0], h - BOT);
        for (const q of r) ctx.lineTo(q[0], q[1]);
        ctx.lineTo(r[r.length - 1][0], h - BOT);
        ctx.closePath(); ctx.fill();
      }
    }
    ctx.lineWidth = 1.6;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (const [c, pth] of byColor) { ctx.strokeStyle = c; ctx.stroke(pth); }
    if (byColor2) {                               // 副轴线细一号, 主次分明
      ctx.lineWidth = 1.2;
      for (const [c, pth] of byColor2) { ctx.strokeStyle = c; ctx.stroke(pth); }
    }
    /* 点查 (三图联动): 虚线竖线落在采样点上, 顶带读出这一刻各轴的值 ——
       每段颜色跟各自轴 (与轴名同一套对应); inspIdx 是模块级共享下标,
       三张图同帧各画各的 */
    if (inspIdx != null && o.tip) {
      const x = xOf(inspIdx);
      ctx.strokeStyle = "rgba(235,235,245,.55)";
      ctx.setLineDash([3, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + .5, TOP); ctx.lineTo(x + .5, h - BOT);
      ctx.stroke();
      ctx.setLineDash([]);
      const segs = o.tip(inspIdx);
      const dot = " · ";
      let tw = (segs.length - 1) * ctx.measureText(dot).width;
      for (const sg of segs) tw += ctx.measureText(sg.t).width;
      let tx = Math.min(Math.max(2, x - tw / 2), w - tw - 2);
      if (o.tag)                                  // 别压左上角轴名
        tx = Math.max(ctx.measureText(o.tag).width + 8, tx);
      if (y2 && y2.tag)                           // 别压右上角轴名
        tx = Math.max(2, Math.min(tx, w - ctx.measureText(y2.tag).width - 8 - tw));
      for (let k = 0; k < segs.length; k++) {
        if (k) {
          ctx.fillStyle = "rgba(235,235,245,.4)";
          ctx.fillText(dot, tx, 11);
          tx += ctx.measureText(dot).width;
        }
        ctx.fillStyle = segs[k].c;
        ctx.fillText(segs[k].t, tx, 11);
        tx += ctx.measureText(segs[k].t).width;
      }
    }
  }

  /* 统计页三卡 (2026-09-23 用户点名拆开, 不再柱叠线; 2026-09-24 加里程卡
     + 换官方口径): 第一张速度直方图 (柱 = 各档时间), 第二张各档里程
     (2026-09-24 用户点名, 蓝 = 里程轴同色), 第三张各档电耗 (平地口径,
     Wh/km, 官方 SpeedRates 面板同口径, 没平地段/没功耗的行程整卡收起)。
     三卡共用 drawBars: x 轴 = 速度档 (档位标签 + 末角 km/h), 顶带左角
     轴名 + 选中档读数; 选中态 histSel 一份共享 (点柱选中再点撤掉,
     点哪张卡都同步) */
  /* 档沿自然十进整除 (2026-09-24 用户点名: 0-9/10-19/…): 点柱读数的档
     区间照实写; 面板原式其实是 numeric 真除四舍五入 (档值 80 = 75-84,
     上午两版逐字对齐过), 用户点名要自然档 —— 与面板有意差半档, 公式/
     过滤口径不动; 柱色按档中值 (档值+4.5) 归轨迹线那五档配色 —— 色阶
     语义不变 (慢红快绿) */
  const lbBin = k => k * hist.step + "-" + (k * hist.step + 9);
  const binColor = k => TrackUtil.SPEED_COLORS[
    TrackUtil.speedBucket(k * hist.step + 4.5)];
  /* 柱区从槽右沿起 (HIST_GUT 定义在前段点柱读值处): 窄屏 (~375px) 上
     y 刻度原来标在 x=2, 与第一根柱 (常是全场最高) 面对面压字, 左下角还
     两个 0 叠影 (2026-09-23 用户实报「坐标轴和数字偏移了」) —— 槽里
     只住 y 刻度与轴名 */

  function drawBars(cvId, vals, o) {
    const cv = doc.getElementById(cvId);
    const box = cv.parentElement;
    const w = box.clientWidth, h = box.clientHeight;
    if (!w || !h || !hist) return;
    const dpr = root.devicePixelRatio || 1;
    const W = Math.round(w * dpr), H = Math.round(h * dpr);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const K = vals.length;   // 均匀 10km/h 档, 档数随这趟最快速度走
    const TOP = 30, BOT = 28;   // 顶带两行 / 底部: 刻度数字行 + 末角单位行
    const px0 = HIST_GUT, pw = w - px0;   // 柱区: 让出左侧刻度槽
    let m = Infinity, x = -Infinity;
    for (const v of vals) if (v != null) {
      if (v < m) m = v;
      if (v > x) x = v;
    }
    if (x === -Infinity) return;                // 全空: 卡留给空态
    const lo = m < 0 ? -pure.niceCeil(Math.max(-m, 2)) : 0;
    const hi = pure.niceCeil(Math.max(x, o.hiMin || 1));
    const yOf = v => TOP + (1 - (v - lo) / (hi - lo)) * (h - TOP - BOT);
    ctx.font = "12px -apple-system, sans-serif";
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(255,255,255,.08)";
    ctx.fillStyle = o.labColor || "rgba(235,235,245,.32)";
    for (const v of [hi, (hi + lo) / 2, lo]) {   // 三道网格 + y 刻度 (槽内)
      const y = yOf(v);
      ctx.beginPath(); ctx.moveTo(px0, y); ctx.lineTo(w, y); ctx.stroke();
      let s = o.fmtY(v);
      if (v === hi && o.unit) s += " " + o.unit;   // 含义单位标在顶格刻度
      ctx.fillText(s, 2, y - 3);
    }
    ctx.fillStyle = "rgba(235,235,245,.85)";
    ctx.fillText(o.tag, 2, 11);                  // 左轴名 (卡里唯一轴)
    const slot = pw / K, bw = Math.min(slot * .58, 64);
    const yZero = yOf(0);
    for (let k = 0; k < K; k++) {                // 柱: 选中压暗其余
      const v = vals[k];
      if (v == null) continue;
      ctx.globalAlpha = histSel == null ? .8 : histSel === k ? .95 : .25;
      ctx.fillStyle = o.color(k);
      const y = yOf(v), z = yZero;               // 负值 (回收档) 从 0 线往下
      ctx.fillRect(px0 + slot * (k + .5) - bw / 2, Math.min(y, z), bw, Math.abs(z - y));
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = "rgba(235,235,245,.32)";
    /* x 轴 = 真刻度轴: 档沿逐根画刻度短线 (对齐柱与数字), 数字标档左沿
       (TeslaMate 板同款); 档多时数字隔档标 —— 窄屏 13 档 ≈ 26px/档,
       三位数 20px+ 全标会挤成一串, 间隔取整到装得下 30px; 末档沿必标,
       末一枚离 K 不足一格时让位 */
    ctx.strokeStyle = "rgba(235,235,245,.32)";
    ctx.beginPath();
    for (let k = 0; k <= K; k++) {
      const tx = px0 + slot * k;
      ctx.moveTo(tx + .5, yZero); ctx.lineTo(tx + .5, yZero + 4);
    }
    ctx.stroke();
    const skip = Math.max(1, Math.ceil(30 / slot));
    const ticks = [];
    for (let k = 0; k <= K; k += skip) ticks.push(k);
    if (ticks[ticks.length - 1] !== K) {
      if (K - ticks[ticks.length - 1] < skip) ticks.pop();   // 挤到末档: 让位
      ticks.push(K);
    }
    for (const k of ticks) {
      const lb = String(k * hist.step);
      const tw = ctx.measureText(lb).width;
      ctx.fillText(lb, Math.min(Math.max(2, px0 + slot * k - tw / 2), w - tw - 2), h - 15);
    }
    ctx.fillText("km/h", w - ctx.measureText("km/h").width - 2, h - 3);
    if (histSel == null || vals[histSel] == null) return;
    const segs = o.tip(histSel);                 // 选中读数 (顶带居中)
    const dot = " · ";
    let tw = (segs.length - 1) * ctx.measureText(dot).width;
    for (const sg of segs) tw += ctx.measureText(sg.t).width;
    let tx = Math.min(Math.max(2, w / 2 - tw / 2), w - tw - 2);
    for (let i = 0; i < segs.length; i++) {
      if (i) {
        ctx.fillStyle = "rgba(235,235,245,.4)";
        ctx.fillText(dot, tx, 11);
        tx += ctx.measureText(dot).width;
      }
      ctx.fillStyle = segs[i].c;
      ctx.fillText(segs[i].t, tx, 11);
      tx += ctx.measureText(segs[i].t).width;
    }
  }

  function drawHist() {
    /* 第一张: 速度直方图 —— 柱 = 各档时间 (分钟), 档色按档中值归轨迹线配色 */
    drawBars("tps-cv-hist", hist ? hist.t : null, {
      tag: "时间", unit: "分钟", hiMin: 1,
      fmtY: v => String(Math.round(v)),
      color: binColor,
      tip: k => [
        { t: lbBin(k) + " km/h", c: "rgba(235,235,245,.85)" },
        { t: (hist.t[k] >= 10 ? Math.round(hist.t[k])
                              : Math.round(hist.t[k] * 10) / 10) + " 分钟",
          c: binColor(k) }],
    });
    /* 第二张: 各档行驶里程 (2026-09-24 用户点名) —— 蓝 = 里程轴同色,
       里程 = 相邻采样里程差累加 (真实路面里程, 非弦距) */
    drawBars("tps-cv-histkm", hist ? hist.km : null, {
      tag: "里程", unit: "km", hiMin: 1,
      fmtY: v => v >= 10 ? String(Math.round(v)) : String(Math.round(v * 10) / 10),
      color: () => "#3987e5",
      tip: k => [
        { t: lbBin(k) + " km/h", c: "rgba(235,235,245,.85)" },
        { t: (hist.km[k] >= 10 ? Math.round(hist.km[k])
                               : Math.round(hist.km[k] * 10) / 10) + " km",
          c: "#3987e5" }],
    });
    /* 第三张: 各档电耗 (Wh/km, 标题照 2026-09-24 用户点名省掉「平地」,
       数据仍是官方 Grafana「不同速度下的能耗」面板逐条同口径: 平地段
       Σ(power·speed)/Σ(speed)×10, 只收 ≥1km 行程, 0 档照画, 自然档沿
       (与面板的四舍五入档有意差半档, 见文件头); 没功耗/没平地段/全 <1km
       的行程 build 里整卡收起)。点柱读数带该档
       平地平均功率 (面板 avg_power 同口径) */
    if (hist && hist.pk) drawBars("tps-cv-hist2", hist.pk, {
      tag: "电耗", unit: "Wh/km", hiMin: 10,
      fmtY: v => String(Math.round(v)),
      color: () => "#e08a2e",                    // 电耗副轴同色
      tip: k => [
        { t: lbBin(k) + " km/h", c: "rgba(235,235,245,.85)" },
        { t: Math.round(hist.pk[k]) + " Wh/km", c: "#e08a2e" },
        { t: (hist.pw[k] == null ? "—" : hist.pw[k].toFixed(1)) + " kW",
          c: "rgba(235,235,245,.6)" }],
    });
  }
}

