/* trackutil.js 轨迹断档拆分与速度着色的 node --test 单元测试。
   拆自 trackutil.test.mjs (结构化重构, 代码逐字节未动)。 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const TrackUtil = require("../../app/tesla/static/js/trackutil.js");
const { splitGaps } = TrackUtil;

const M = 0.00001;   // ~1.1m, 城市打点步长

function track(n, step = M, start = 114) {
  return Array.from({ length: n }, (_, i) => [start + i * step, 22.5]);
}


test("正常轨迹不拆分", () => {
  const pts = track(500);
  const segs = splitGaps(pts);
  assert.equal(segs.length, 1);
  assert.equal(segs[0].length, 500);
});

test("城市轨迹中的 GPS 断档 (731m 瞬移) 在断点处拆开", () => {
  const pts = track(500);
  const jump = 0.0066;   // ~730m
  // 在中间插入一个瞬移点: 第 250 点突然跳到 731m 外
  const withGap = [...pts.slice(0, 250),
                   [pts[249][0] + jump, pts[249][1] + jump * 0.5],
                   ...pts.slice(250).map(p => [p[0] + jump, p[1] + jump * 0.5])];
  const segs = splitGaps(withGap);
  assert.equal(segs.length, 2);
  assert.ok(segs[0].length >= 2 && segs[1].length >= 2);
  // 第一段止于断点前最后一点, 第二段从瞬移点开始 (不直连)
  assert.deepEqual(segs[0][segs[0].length - 1], pts[249]);
  assert.deepEqual(segs[1][0], [pts[249][0] + jump, pts[249][1] + jump * 0.5]);
});

test("概览粗轨迹 (段长公里级) 不误拆", () => {
  const pts = track(40, 0.01);   // 每段 ~1.1km
  const segs = splitGaps(pts);
  assert.equal(segs.length, 1);
});

test("混合轨迹 (城市+高速段) 中位数阈值不被高速段拉高", () => {
  const city = track(300, M);
  const hwy = track(100, 0.0013);   // 高速 ~145m/段
  const pts = [...city, ...hwy];
  // 末尾再接一个城市段并制造 731m 断档
  const tail = track(100, M, 115).map(p => [p[0] + 0.2, p[1] + 0.2]);
  const withGap = [...pts, tail];
  const segs = splitGaps(withGap);
  assert.equal(segs.length, 2);   // 城市中位阈值 ~160m 下限, 145m 高速段不拆, 731m 断档拆
  assert.ok(segs[1].length >= 2);
});

test("短轨迹原样返回", () => {
  assert.deepEqual(splitGaps([[114, 22.5], [114.1, 22.6]]),
                   [[[114, 22.5], [114.1, 22.6]]]);
  assert.deepEqual(splitGaps(null), []);
});

test("全是孤立大跳点时退回整条, 不让轨迹消失", () => {
  const pts = [[114, 22.5], [115, 23.5], [113, 21.5]];
  assert.deepEqual(splitGaps(pts), [pts]);
});


/* ---------------- speedLines: 速度着色分档 ---------------- */
const C0 = "#e5484d", C4 = "#1fa349";   // 最慢红 / 最快绿

test("匀速轨迹只出一段, 颜色按速度档", () => {
  const slow = Array.from({ length: 10 }, (_, i) => [114 + i * 1e-4, 22.5, 8]);
  const fast = Array.from({ length: 10 }, (_, i) => [114 + i * 1e-4, 22.5, 120]);
  assert.equal(splitGaps, splitGaps);   // import 自检
  const ls = TrackUtil.speedLines(slow);
  assert.equal(ls.length, 1);
  assert.equal(ls[0].color, C0);
  assert.equal(ls[0].pts.length, 10);
  assert.equal(TrackUtil.speedLines(fast)[0].color, C4);
});

test("变速轨迹分段着色, 相邻段共享端点不留缝", () => {
  // 5 段: 0 → 20 → 50 → 80 → 120 km/h, 每档 3 个点
  const speeds = [0, 0, 0, 20, 20, 20, 50, 50, 50, 80, 80, 80, 120, 120, 120];
  const pts = speeds.map((s, i) => [114 + i * 1e-4, 22.5, s]);
  const ls = TrackUtil.speedLines(pts);
  assert.equal(ls.length, 5);
  assert.deepEqual(ls.map(l => l.color), TrackUtil.SPEED_COLORS);
  for (let i = 1; i < ls.length; i++) {
    // 前一段末点 == 后一段首点 (共享端点)
    assert.deepEqual(ls[i].pts[0], ls[i - 1].pts[ls[i - 1].pts.length - 1]);
  }
});

test("速度缺失按 0 处理", () => {
  const pts = [[114, 22.5, null], [114.001, 22.5, undefined], [114.002, 22.5, 5]];
  const ls = TrackUtil.speedLines(pts);
  assert.equal(ls.length, 1);
  assert.equal(ls[0].color, C0);
});


/* ---------------- cumDistKm: 播放中的实时里程 ---------------- */
