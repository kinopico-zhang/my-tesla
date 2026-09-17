/* 轨迹播放节拍与描画路径: 白线描画路径替换 / 一步行驶秒 / 每点累计行驶秒 /
   已播时刻 → 下标与步内进度 / 弧长比例取点 / 瓦片坐标。都从 trackutil.js
   (几何/着色) 按域拆出 —— 只服务播放动画 (trips.js 的 zoomTick/playTrack
   与矢量预载扫路), 几何测量去 trackutil.js。
   UMD: 浏览器挂 window.TrackAnimation, node (测试) 走 module.exports
   (依赖同目录 trackutil.js 的 ptDistKm)。 */
/* UMD 挂载层: node (测试 require) 与浏览器 (生产 <script> 加载) 二选一。
   浏览器分支在 node 覆盖率里天然统计不到 (require 时 module 一定存在),
   c8 标记忽略; 挂载行为由 *_test 的 eval 桩用例验证。 */
/* c8 ignore start */
(function (root, factory) {
  if (typeof module === "object" && module.exports)
    module.exports = factory(require("./trackutil.js"));
  else root.TrackAnimation = factory(root.TrackUtil);
})(/** @type {Window | Record<string, unknown>} */(typeof self !== "undefined" ? self : this), function (rawTrackUtil) {
/* c8 ignore stop */
  "use strict";
  const TrackUtil = /** @type {typeof import("./trackutil.js")} */(rawTrackUtil);

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
    const km = TrackUtil.ptDistKm(a, b);
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

  return { splicePath: splicePath, animStepSec: animStepSec, animTimes: animTimes,
           animAt: animAt, pathPointAt: pathPointAt, lngLatToTile: lngLatToTile };
});
