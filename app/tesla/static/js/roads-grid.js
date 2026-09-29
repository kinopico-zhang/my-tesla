// roads-grid.js — 「走过之路」栅格计数 (纯逻辑, 无 DOM/无地图依赖):
// 把拟合到路上的路径栅格化到 ~20m 格 (CELL=0.0002°), 同格累加走过次数
// —— 服务端不做聚合 (单司机单车, 筛选组合开不动预聚合), 客户端把每程
// 路径的格序列存内存 (roadCellsById), 换筛选只重算合并 (roadCells),
// 不再发任何请求。
//   cellKey      经纬度 → 格键: floor(lng*5000)*1e6 + floor(lat*5000)
//                (中国域 < 2^53, Number 安全; 键随经纬单调, 无碰撞)
//   cellsForFlat 扁平 pts → 有序连续去重格键序列: DDA 按 CELL/2 (~10m)
//                步进采样, 高速段两点 200m+ 也不跳格; 「连续去重」= 相邻
//                同格只计一次 —— 折返/隔几格再进该格就再计, 走过次数的
//                语义就是它 (Set 全去重会把折返路算成一次)
//   tOf/stepOf   次数 → 0..1 / 色阶档 0..STEPS-1: 对数刻度 (1 次 = 0 端,
//                当前筛选最多次数 = 1 端, 常走与偶走都拉得开)
//   colorOf      0..1 → 四锚点 (暗蓝→青→金→红) 逐通道线性插值 —— 连续
//                热力色阶 (2026-09-29 用户点名「次数用热力图连续的颜色
//                来表示」); 图例渐变条同口径, 两边对得上
//   runsByStep   路径按格次数统计切段分色阶 (相邻 run 共享端点, 不断线;
//                <3 点碎段并给前段, 省折线对象)
//   packStat     次数 × 16384 + 天序 (自 2020-01-01): 一格一数同时带
//                「走过几次」与「最近哪天走过」(16384=2^14, 2044 年底前
//                天序不越界; 单司机走过次数实际 <2^38, 乘积不越 2^53)
// UMD: 浏览器挂 window.RoadsGrid, node (测试) 走 module.exports
// (与 trackutil.js 同款)。
/* c8 ignore start */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RoadsGrid = factory();
})(/** @type {Window | Record<string, unknown>} */(typeof self !== "undefined" ? self : this), function () {
/* c8 ignore stop */
  "use strict";
  const CELL = 0.0002;                  // 格边长 (度) ≈ 20m
  const GRID = 5000;                    // 1/CELL: 度 → 格
  const STEPS = 12;                     // 色阶档数 (视觉连续; 折线按档切段, 数量有界)
  const COLORS = ["#3d6fa8", "#21a179", "#d9a521", "#e5484d"];  // 锚点: 暗蓝→青→金→红
  const DAY_EPOCH = Date.UTC(2020, 0, 1);
  const DAY_MAX = 16383;                // packStat 下半区上限 (2^14-1)
  const STAT_BASE = 16384;

  function cellKey(lng, lat) {   // 经纬度 → 格键 (格与格单调可比, 无碰撞)
    return Math.floor(lng * GRID) * 1e6 + Math.floor(lat * GRID);
  }

  function dayOrdOf(dateStr) {   // "YYYY-MM-DD" → 天序 (packStat 下半区)
    return Math.floor((Date.parse(dateStr + "T00:00:00Z") - DAY_EPOCH) / 86400000);
  }
  function dayStrOf(ord) {       // 天序 → "YYYY-MM-DD" (详情卡「最近走过」)
    return new Date(DAY_EPOCH + ord * 86400000).toISOString().slice(0, 10);
  }

  function packStat(count, dayOrd) {   // 次数 + 天序 → 单个数
    return Math.max(1, count | 0) * STAT_BASE +
      Math.min(Math.max(dayOrd | 0, 0), DAY_MAX);
  }
  function cellCount(stat) { return Math.floor(stat / STAT_BASE); }
  function cellDay(stat) { return stat % STAT_BASE; }

  function tOf(count, max) {     // 次数 → 0..1: 对数刻度 (1 次=0 端, max 次=1 端)
    if (max <= 1) return 0;      // 全是 1 次 / 还没合并出计数: 单色保护
    return Math.min(1, Math.log(Math.max(1, count)) / Math.log(max));
  }
  function stepOf(count, max) {  // 次数 → 色阶档 0..STEPS-1 (切段/上色共用)
    return Math.min(STEPS - 1, Math.round(tOf(count, max) * (STEPS - 1)));
  }
  function colorOf(t) {          // 0..1 → 锚点色间逐通道线性插值 (CSS 渐变同口径)
    const u = Math.min(1, Math.max(0, t || 0)) * (COLORS.length - 1);
    const i = Math.min(COLORS.length - 2, Math.floor(u)), f = u - i;
    const ch = (c, k) => parseInt(c.slice(1 + 2 * k, 3 + 2 * k), 16);
    let out = "#";
    for (let k = 0; k < 3; k++) {
      const v = Math.round(ch(COLORS[i], k) +
                            (ch(COLORS[i + 1], k) - ch(COLORS[i], k)) * f);
      out += v.toString(16).padStart(2, "0");
    }
    return out;
  }
  function stepColor(step) {     // 色阶档 → 色 (折线与图例渐变条同源)
    return colorOf(step / (STEPS - 1));
  }

  function cellsForFlat(pts) {   // 扁平 [lng,lat,...] → 格键序列 (有序连续去重)
    const out = [];
    const n = pts ? pts.length : 0;
    if (n < 2) return out;
    let last = NaN;              // NaN !== 一切 → 首格必进
    const push = k => { if (k !== last) { out.push(k); last = k; } };
    if (n === 2) return [cellKey(pts[0], pts[1])];
    for (let i = 2; i < n; i += 2) {
      const x0 = pts[i - 2], y0 = pts[i - 1], x1 = pts[i], y1 = pts[i + 1];
      const dx = x1 - x0, dy = y1 - y0;
      // 相邻点 DDA 采样: 步长 CELL/2, 中间格全踩到 (双步防格角跳过)
      const steps = Math.max(1, Math.ceil(
        Math.max(Math.abs(dx), Math.abs(dy)) / (CELL / 2)));
      for (let s = 0; s < steps; s++)
        push(cellKey(x0 + dx * s / steps, y0 + dy * s / steps));
    }
    push(cellKey(pts[n - 2], pts[n - 1]));   // 终点必落格 (循环只到 n-2)
    return out;
  }

  function runsByStep(pts, stat, max) {   // pts 扁平, stat: Map(格键 → packStat)
    // 按点的所在格次数把路径切段: {b, i0, i1} (i 为扁平下标, 含端点;
    // b = 色阶档 0..STEPS-1)。换档处两段共享前一个顶点 (i0 = 前段 i1) ——
    // 段间不断线, 跨段那一小节归新档色。<3 点的碎段并给前段: 十几米的
    // 色斑不值得一条折线。
    const runs = [];
    const n = pts ? pts.length / 2 : 0;
    if (!n) return runs;
    let cur = -1, i0 = 0;
    for (let i = 0; i < n; i++) {
      const k = cellKey(pts[i * 2], pts[i * 2 + 1]);
      const b = stepOf(cellCount(stat.get(k) || 0), max);
      if (b !== cur) {
        if (cur >= 0) runs.push({ b: cur, i0: i0, i1: (i - 1) * 2 });
        cur = b;
        i0 = i > 0 ? (i - 1) * 2 : 0;   // 换桶处与前段共享顶点 (首点无前段)
      }
    }
    runs.push({ b: cur, i0: i0, i1: (n - 1) * 2 });
    if (runs.length < 2) return runs;
    const merged = [runs[0]];
    for (let r = 1; r < runs.length; r++) {
      const prev = merged[merged.length - 1], cur2 = runs[r];
      // 碎段 (<3 点) 并给前段; 并段后可能与再后一段同桶 → 顺势续上
      if (cur2.i1 - cur2.i0 < 4 || prev.b === cur2.b) prev.i1 = cur2.i1;
      else merged.push(cur2);
    }
    return merged;
  }

  function rowSpans(pts, g) {   // 推断层之外的已证实段: 扁平下标对 [f0, f1)
    // (pts.slice(f0, f1) 直接用)。g = 推断层顶点闭区间 [[a, b], ...] (服务端
    // gaps: 规划补的/直连的/整程降级的「可能走过」); 证实段与推断段共享
    // 边界顶点 —— 实线到 a 止、虚线从 a 起, 两线接上不断。次数计数只从
    // 证实段来 (可能走过 ≠ 走过)。
    const n = pts ? pts.length / 2 : 0;
    const out = [];
    if (n < 1) return out;
    if (!g || !g.length) return [[0, n * 2]];
    let v0 = 0;
    for (const rg of g) {
      const a = Math.max(0, Math.floor(rg[0])), b = Math.min(n - 1, Math.floor(rg[1]));
      if (b < a) continue;                            // 越界/空区间跳过
      if (a > v0) out.push([v0 * 2, (a + 1) * 2]);    // 与推断段共享端点 a
      v0 = Math.max(v0, b);                           // 下一段从 b 起 (共享端点)
    }
    if (v0 < n - 1) out.push([v0 * 2, n * 2]);
    return out;
  }

  return { CELL: CELL, GRID: GRID, STEPS: STEPS, COLORS: COLORS,
           cellKey: cellKey, cellsForFlat: cellsForFlat, rowSpans: rowSpans,
           tOf: tOf, stepOf: stepOf, colorOf: colorOf, stepColor: stepColor,
           runsByStep: runsByStep, packStat: packStat,
           cellCount: cellCount, cellDay: cellDay,
           dayOrdOf: dayOrdOf, dayStrOf: dayStrOf };
});
