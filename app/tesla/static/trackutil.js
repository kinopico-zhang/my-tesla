/* 轨迹折线工具: 识别 GPS 断档大跳变 (隧道/信号丢失时相邻点瞬移几百米),
   把折线在跳变处拆成多段 —— 不拆的话两点间直连"飞线"会穿过街区。
   阈值自适应 (段长中位数的 10 倍, 下限 ~0.0016° ≈ 160m):
   - 城市轨迹段长 10-30m, 断档 700m+ → 拆;
   - 概览粗轨迹 (40 点/条, 段长常达公里级) → 阈值跟着变大, 不误拆。
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
     供断档补路的"绕行检测/裁剪定位"用。 */
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

  /* ---- 白线描画路径: 断档跳变段替换为已解析的真实道路路径 ----
     splices: [{aIdx, bIdx, route: [[lng,lat], ...]}] 按 aIdx 升序;
     route 含两端 (从 path[aIdx] 到 path[bIdx] 的道路路径, 端点已吸附道路),
     整段替换 path[aIdx..bIdx]。返回 path[0..upto] 按此替换后的描画路径。 */
  function splicePath(path, splices, upto) {
    if (!splices.length) return path.slice(0, upto + 1);
    const parts = [];
    let from = 0;
    for (const g of splices) {
      if (g.bIdx > upto) break;             // 播放头还没到这条断档
      parts.push(path.slice(from, g.aIdx), g.route);
      from = g.bIdx + 1;
    }
    parts.push(path.slice(from, upto + 1));
    return Array.prototype.concat.apply([], parts);
  }

  /* ---- 播放节拍: 一步 (相邻两点) 占多少"行驶秒" ----
     正常步取真实时间差 dts; 跨断档步 (隧道/信号丢失, 相邻点却相距数百米)
     没有真实采样, 按"车以两端速度线性插值驶过这段路"推算: 秒 = 距离 / 均速
     ((v_a+v_b)/2, 线性增速的平均; 两端都停着按 30km/h 保底, 不然轮渡/拖车
     这类断档永远走不完), 真实间隔更久则照真实。两端几乎没动的"停车步"
     (等灯) 只计 2s —— 照真实等车时长计的话, 停停走走会把播放时长吃掉大半
     (合并轨迹的 ts 本就跳过停车, 这里对齐口径)。 */
  function animStepSec(a, b, dts) {
    const km = ptDistKm(a, b);
    const v = ((a[2] || 0) + (b[2] || 0)) / 2;
    if (km < 0.002 && v < 1) return Math.min(dts, 2);
    return Math.max(dts, km / Math.max(v, 30) * 3600);
  }

  /* ---- 播放节拍: 每点累计"行驶秒" vt[i] (i 之前的动画一共要走多少秒) ----
     ts 缺失/长度不符时退化为纯推算节拍 (dts 按 1s, 仍是距离/均速口径,
     断档步照常推算, 不会瞬移)。 */
  function animTimes(pts, ts) {
    const vt = [0];
    const ok = ts && ts.length >= pts.length;
    for (let i = 1; i < pts.length; i++)
      vt.push(vt[i - 1] + animStepSec(pts[i - 1], pts[i],
                                      ok ? Math.max(0, ts[i] - ts[i - 1]) : 1));
    return vt;
  }

  /* ---- 动画: 已播放毫秒 + vt → {idx, frac} ----
     按行驶秒推进 (不是下标均匀): 断档步在 animTimes 里被拉长到推算行驶秒,
     播放头得以在断档里以两端插值速度走完, 而不是一帧瞬移到对岸。frac 是
     该步内的小数进度, 调用方据此插值头部位置 (断档里沿道路路径走)。
     Chrome 的 rAF 回调时间戳是"帧开始时刻", 可能早于 scheduling 前一刻取的
     performance.now() (t0)。命中缓存的轨迹在同一帧内开播就会得到负 t →
     负下标 → 读 pts[-3][2] 直接崩溃, 表现为"这条轨迹没有动画" (Safari 时间戳
     不回退所以不复现)。钳制 elapsed 到 [0, dur]。 */
  function animAt(vt, elapsed, dur) {
    const total = vt[vt.length - 1] || 0;
    if (!(total > 0)) return { idx: vt.length - 1, frac: 0 };
    const q = Math.min(Math.max(elapsed / dur, 0), 1) * total;
    let lo = 0, hi = vt.length - 1;          // 二分: 最大的 i 使 vt[i] ≤ q
    while (lo < hi) {
      const m = (lo + hi + 1) >> 1;
      if (vt[m] <= q) lo = m; else hi = m - 1;
    }
    if (lo >= vt.length - 1) return { idx: lo, frac: 0 };
    const span = vt[lo + 1] - vt[lo];
    return { idx: lo, frac: span > 0 ? (q - vt[lo]) / span : 0 };
  }

  /* ---- 折线按弧长比例取点 (f ∈ [0,1] 全程的比例) ----
     断档里播放头沿道路路径走: route + 其累计里程 (cumDistKm) + 当前进度
     → 头部坐标。 */
  function pathPointAt(path, cum, f) {
    const q = Math.min(Math.max(f, 0), 1) * cum[cum.length - 1];
    for (let i = 1; i < path.length; i++) {
      if (cum[i] >= q) {
        const t = (q - cum[i - 1]) / (cum[i] - cum[i - 1] || 1);
        return [path[i - 1][0] + (path[i][0] - path[i - 1][0]) * t,
                path[i - 1][1] + (path[i][1] - path[i - 1][1]) * t];
      }
    }
    return path[path.length - 1];
  }

  /* ---- Web 墨卡托瓦片坐标 (slippy tile): GCJ 经纬度 → z 层的格 x/y。
     播放前预载沿途瓦片用 (URL 里换 x/y/z 即可复算整条路的瓦片)。 ---- */
  function lngLatToTile(lng, lat, z) {
    const n = Math.pow(2, z);
    const x = Math.floor((lng + 180) / 360 * n);
    const clamped = Math.max(-85.05112878, Math.min(85.05112878, lat));
    const rad = clamped * Math.PI / 180;
    const y = Math.floor((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * n);
    return [x, y];
  }

  return { splitGaps: splitGaps, gapsBetween: gapsBetween, speedLines: speedLines, cumDistKm: cumDistKm, meanPowerW: meanPowerW, splicePath: splicePath,
           animStepSec: animStepSec, animTimes: animTimes, animAt: animAt, pathPointAt: pathPointAt,
           speedBucket: speedBucket, ptDistKm: ptDistKm, bearingDeg: bearingDeg,
           lngLatToTile: lngLatToTile,
           SPEED_COLORS: SPEED_COLORS, MIN_GAP_KM: MIN_GAP_KM, _segLen: segLen };
});
