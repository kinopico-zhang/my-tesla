/* 轨迹折线工具: 识别 GPS 断档大跳变 (隧道/信号丢失时相邻点瞬移几百米),
   把折线在跳变处拆成多段 —— 不拆的话两点间直连"飞线"会穿过街区。
   阈值自适应 (段长中位数的 10 倍, 下限 ~0.0016° ≈ 160m):
   - 城市轨迹段长 10-30m, 断档 700m+ → 拆;
   - 概览粗轨迹 (40 点/条, 段长常达公里级) → 阈值跟着变大, 不误拆。
   本文件管几何/着色/测距/功耗; 播放节拍与描画路径 (animAt/splicePath/
   pathPointAt/lngLatToTile) 按域拆去了 track-animation.js。
   UMD: 浏览器挂 window.TrackUtil, node (测试) 走 module.exports。 */
/* UMD 挂载层: node (测试 require) 与浏览器 (生产 <script> 加载) 二选一。
   浏览器分支在 node 覆盖率里天然统计不到 (require 时 module 一定存在),
   c8 标记忽略; 挂载行为由 *_test 的 eval 桩用例验证。 */
/* c8 ignore start */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.TrackUtil = factory();
})(/** @type {Window | Record<string, unknown>} */(typeof self !== "undefined" ? self : this), function () {
/* c8 ignore stop */
  "use strict";
  const MIN_GAP = 0.0016;   // ~160m, 城市里正常采样不会一步跨这么远

  function segLen(a, b) {   // 段长 (取经纬度差较大者, 度)
    return Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
  }

  function splitGaps(pts) {
    if (!pts || pts.length < 3) return pts ? [pts] : [];
    // 抽样取段长中位数 (不是平均数: 混着高速段的轨迹平均会被拉高)
    const lens = [];
    for (let i = 1; i < pts.length; i += 7) lens.push(segLen(pts[i - 1], pts[i]));
    lens.sort((a, b) => a - b);
    const med = lens.length ? lens[lens.length >> 1] : 0;
    const thresh = Math.max(MIN_GAP, med * 10);
    const segs = [];
    let cur = [pts[0]];
    for (let i = 1; i < pts.length; i++) {
      if (segLen(pts[i - 1], pts[i]) > thresh) { segs.push(cur); cur = []; }
      cur.push(pts[i]);
    }
    segs.push(cur);
    const ok = segs.filter(s => s.length >= 2);
    return ok.length ? ok : [pts];   // 全是孤立点时按原样画, 不能让轨迹消失
  }

  /* ---- 速度着色: 慢=红 快=绿 (行程弹层轨迹) ----
     pts 每点 [lng, lat, speed_km_h]; 相邻点同档连成一段, 相邻段共享端点。
     返回 [{color, pts: [[lng,lat], ...]}], 坐标保持 WGS-84, 由调用方转 GCJ-02。 */
  const SPEED_STOPS = [15, 40, 70, 100];   // 分档阈值 km/h
  const SPEED_COLORS = ["#e5484d", "#e08a2e", "#d9b42a", "#9dbb32", "#1fa349"];

  function speedBucket(s) {
    let i = 0;
    while (i < SPEED_STOPS.length && s >= SPEED_STOPS[i]) i++;
    return i;
  }

  function speedLines(pts) {
    const lines = [];
    let cur = null;                            // {color, pts}
    for (let i = 1; i < pts.length; i++) {
      const s = Math.max(pts[i - 1][2] || 0, pts[i][2] || 0);   // 段速取两端较大
      const color = SPEED_COLORS[speedBucket(s)];
      if (!cur || cur.color !== color) {
        if (cur) lines.push(cur);
        cur = { color: color, pts: [pts[i - 1]] };   // 共享端点, 段间不留缝
      }
      cur.pts.push(pts[i]);
    }
    if (cur) lines.push(cur);
    return lines;
  }

  /* ---- 累计里程: 轨迹点 → 每点累计公里数 (等距圆柱近似, 展示精度足够) ----
     cum[i] = 起点到第 i 点的里程 (km), cum[0] = 0; 播放动画实时里程用它。 */
  function cumDistKm(pts) {
    const cum = [0];
    const kx = 111.32 * Math.cos((pts[0][1] || 0) * Math.PI / 180);  // 每经度 km
    const ky = 110.57;                                                // 每纬度 km
    for (let i = 1; i < pts.length; i++) {
      const dx = (pts[i][0] - pts[i - 1][0]) * kx;
      const dy = (pts[i][1] - pts[i - 1][1]) * ky;
      cum.push(cum[i - 1] + Math.sqrt(dx * dx + dy * dy));
    }
    return cum;
  }

  /* ---- 两点距离 (km, 等距圆柱近似, 与 cumDistKm 同一套数学) ----
     供断档补路的"绕行检测/裁剪定位"和播放节拍 (track-animation.js) 用。 */
  function ptDistKm(a, b) {
    const kx = 111.32 * Math.cos(((a[1] + b[1]) / 2 || 0) * Math.PI / 180);
    const dx = (b[0] - a[0]) * kx, dy = (b[1] - a[1]) * 110.57;
    return Math.sqrt(dx * dx + dy * dy);
  }

  /* ---- 两点方位角 (0~360°, 北=0 顺时针): 判断路线起步方向是否背离行驶方向 ---- */
  function bearingDeg(a, b) {
    return (Math.atan2(b[0] - a[0], b[1] - a[1]) * 180 / Math.PI + 360) % 360;
  }

  /* ---- 相邻段之间的断档 (供"缺失段"蓝色虚线): [{pts: [a, b], km: 跳变公里数}] ----
     注意 splitGaps 会丢掉只含 1 个点的孤立段 (GPS 野点), 这时相邻返回段的
     边界距离可能很小, 不是真断档 —— 按最小跳变距离过滤掉。 */
  const MIN_GAP_KM = 0.16;   // 与 MIN_GAP (~160m) 对齐

  function gapsBetween(segs) {
    const gaps = [];
    for (let i = 1; i < segs.length; i++) {
      const a = segs[i - 1][segs[i - 1].length - 1], b = segs[i][0];
      const kx = 111.32 * Math.cos((((a[1] || 0) + (b[1] || 0)) / 2) * Math.PI / 180);
      const ky = 110.57;
      const km = Math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * ky);
      if (km >= MIN_GAP_KM) gaps.push({ pts: [a, b], km: km });
    }
    return gaps;
  }

  /* ---- 平均功耗 (W): 相邻点按时间差加权平均, 没有功耗数据的段不计入 ----
     pts[i][3] 为瓦特 (正=放电 负=回收, 可 null), ts[i] 为相对起点秒。 */
  function meanPowerW(pts, ts) {
    let es = 0, t = 0;                       // Σ W·s, Σ s
    for (let i = 1; i < pts.length; i++) {
      const dt = ts[i] - ts[i - 1];
      if (!(dt > 0)) continue;
      const a = pts[i - 1][3], b = pts[i][3];
      if (a == null && b == null) continue;  // 这段没数据, 时间也不计
      const p = a == null ? b : b == null ? a : (a + b) / 2;
      es += p * dt; t += dt;
    }
    return t ? es / t : null;
  }

  return { splitGaps: splitGaps, gapsBetween: gapsBetween, speedLines: speedLines, cumDistKm: cumDistKm,
           meanPowerW: meanPowerW,
           speedBucket: speedBucket, ptDistKm: ptDistKm, bearingDeg: bearingDeg,
           SPEED_COLORS: SPEED_COLORS, MIN_GAP_KM: MIN_GAP_KM, _segLen: segLen };
});
