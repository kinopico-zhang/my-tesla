/* trip-playback.js — 行程播放纯逻辑: 随速变焦曲线/滑窗均速/迟滞缓动/
   播放时长/能耗模型/合并轨迹分段。弹层播放 (trips.js 的 zoomTick 与
   playTrack) 和矢量预载扫路 (preloadVectorTrack) 共用, 抽成纯模块给
   node --test 直测 + tsc --checkJs 把关; 页面编排 (地图实例/DOM/帧循环)
   留在 trips.js。
   UMD: 浏览器挂 window.TripPlayback, node (测试) 走 module.exports
   (依赖同目录 trackutil.js 的 animAt/splitGaps)。 */
/* c8 ignore start */
/* UMD 挂载层: node (测试 require) 与浏览器 (生产 <script> 加载) 二选一。
   浏览器分支在 node 覆盖率里天然统计不到 (require 时 module 一定存在),
   c8 标记忽略; 挂载行为由 *_test 的 eval 桩用例验证。 */
(function (root, factory) {
  if (typeof module === "object" && module.exports)
    module.exports = factory(require("./trackutil.js"));
  else root.TripPlayback = factory(root.TrackUtil);
})(/** @type {Window | Record<string, unknown>} */(typeof self !== "undefined" ? self : this), function (rawTrackUtil) {
/* c8 ignore stop */
  "use strict";
  const TrackUtil = /** @type {typeof import("./trackutil.js")} */(rawTrackUtil);

  /* ============================ 随速变焦 ============================ */
  /* 滑动窗 (播放时间轴): 过去 ZOOM_PAST_MS + 预看 ZOOM_FUT_MS, 均匀
     ZOOM_SAMPLES 个采样点的插值车速取均值。窗口随播放位置现算、无状态
     —— 开播/拖进度天然干净, 不用重攒。 */
  const ZOOM_PAST_MS = 2000, ZOOM_FUT_MS = 5000, ZOOM_SAMPLES = 8;
  /* 曲线: 慢速拉近 (12.5) / 高速拉远 (15.3), 46km/h 一档; 外圈 10.5/18.5
     是 ±2.5 基线偏移推到头时的极限夹紧 */
  const speedZoom = (v, bias) => Math.max(10.5, Math.min(18.5,
    Math.max(12.5, Math.min(15.3, 15.3 - v / 46)) + bias));
  /* 基线偏移 (整条曲线平移): ±2.5 夹紧, 0.5 一档 */
  const clampZoomBias = x => Math.max(-2.5, Math.min(2.5, Math.round(x * 2) / 2));

  /* 滑窗均速: animAt 自带钳制, 窗口两端出界取首/尾车速 */
  function windowMeanSpeed(vt, pts, t, dur) {
    let vSum = 0;
    for (let k = 0; k < ZOOM_SAMPLES; k++) {
      const tw = t - ZOOM_PAST_MS
        + (ZOOM_PAST_MS + ZOOM_FUT_MS) * k / (ZOOM_SAMPLES - 1);
      const p = TrackUtil.animAt(vt, tw, dur);
      const va = pts[p.idx][2] || 0,
            vb = p.idx + 1 < pts.length ? (pts[p.idx + 1][2] || 0) : va;
      vSum += va + (vb - va) * p.frac;
    }
    return vSum / ZOOM_SAMPLES;
  }

  /* 迟滞带 ±0.6: 出带才换目标档 —— 档位边界的速度抖动 (等灯起步)
     不至于来回打摆 */
  const hysteresisZoom = (zt, cur) => Math.abs(zt - cur) > 0.6 ? Math.round(zt) : cur;

  /* 指数趋近 + 速率上限 (1.5 档/s): 低帧率下单帧也不会跳档 (纯指数在
     2.5fps 下一帧能挪半档), 高帧率下恒为平滑缓动 */
  function easeZoomStep(target, shown, dt) {
    const step = (target - shown) * (1 - Math.exp(-dt / 600));
    const cap = 1.5 * dt / 1000;
    let next = shown + Math.max(-cap, Math.min(cap, step));
    if (Math.abs(target - next) < 0.01) next = target;
    return next;
  }

  /* ============================ 播放时长 ============================ */
  /* (1× 基准, ms): 点数与里程取大, 3~300s。只看点数会亏待被下采样的
     超长轨迹 (260km 也被压到 12 秒放完, 根本看不清路), 里程分量让长途
     慢下来; 系数 1.4s/km ≈ 镜头以 0.7km/s 扫过 —— 再快肉眼跟不上
     (超长封顶 300s, 嫌慢有倍速按钮)。矢量预载扫路也用它换算窗口时刻
     (口径必须一致)。 */
  const animDurMs = (n, km) => Math.min(Math.max(n / 300, 3 + km * 1.4), 300) * 1000;

  /* ============================ 能耗模型 ============================ */
  /* 逐点能耗权重: 每公里 = 滚阻 1 + 风阻 3·(v/100)² (v 为 km/h), 全程
     定标到整体 kWh。没有逐点功耗数据, 播放中的动态电耗/平均电耗按它
     累积 —— 快段每公里贵一点, 停车不走就不耗, 收尾自然落回整体值。 */
  const energyWeightKm = v => 1 + 3 * Math.pow(v / 100, 2);   // 每公里相对能耗
  function energyStep(pts, cum, i) {   // 第 i 步 (i-1 → i, 步速取两端均值)
    return (cum[i] - cum[i - 1])
      * energyWeightKm(((pts[i - 1][2] || 0) + (pts[i][2] || 0)) / 2);
  }
  function energyCurve(pts, cum) {     // 逐点累计 (播放中的实时 (模型) 能耗)
    const ecum = [0];
    for (let i = 1; i < pts.length; i++) ecum.push(ecum[i - 1] + energyStep(pts, cum, i));
    return ecum;
  }

  /* 分数进度取值: 末步夹紧 (能耗/里程/时间插值共用) */
  function fracValue(arr, idx, frac) {
    const a = arr[idx], b = idx + 1 >= arr.length ? a : arr[idx + 1];
    return a + (b - a) * frac;
  }

  /* ============================ 合并轨迹分段 ============================ */
  /* 每段单独跑单段行程同一套 splitGaps —— 各段下采样后采样密度差着量级
     (短市区段步长几十米, 长途段公里级), 拼成一个数组用全局阈值会把整条
     长途段拆成孤立单点丢掉, 只剩几十条飞线。段与段之间的真实跳变交给
     gapsBetween 按距离阈值正常补路。 */
  function splitSegments(pts, starts) {
    if (!starts || !starts.length) return TrackUtil.splitGaps(pts);
    const segs = [];
    for (let k = 0; k < starts.length; k++) {
      const end = k + 1 < starts.length ? starts[k + 1] : pts.length;
      if (end > starts[k]) segs.push(...TrackUtil.splitGaps(pts.slice(starts[k], end)));
    }
    return segs.length ? segs : TrackUtil.splitGaps(pts);
  }

  return {
    speedZoom, clampZoomBias, windowMeanSpeed, hysteresisZoom, easeZoomStep,
    animDurMs, energyWeightKm, energyStep, energyCurve, fracValue,
    splitSegments, ZOOM_PAST_MS, ZOOM_FUT_MS, ZOOM_SAMPLES,
  };
});
