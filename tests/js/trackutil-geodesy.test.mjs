/* trackutil.js 测量函数的 node --test 单元测试: 累计里程, 断档输出,
   时间加权功耗, 点距与方位角。
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


test("cumDistKm: 向东每步 0.01° ≈ 1.03km (纬度 22.5°)", () => {
  const pts = [[114, 22.5], [114.01, 22.5], [114.02, 22.5]];
  const cum = TrackUtil.cumDistKm(pts);
  assert.equal(cum.length, 3);
  assert.equal(cum[0], 0);
  const step = 111.32 * Math.cos(22.5 * Math.PI / 180) * 0.01;  // ≈ 1.0286
  assert.ok(Math.abs(cum[1] - step) < 0.001, `cum[1]=${cum[1]}`);
  assert.ok(Math.abs(cum[2] - 2 * step) < 0.002);
});

test("cumDistKm: 对角步长按勾股定理累计", () => {
  // 向东北 45°: 每步 dx=0.01°, dy=0.01°, 约 1.455km
  const pts = [[114, 22.5], [114.01, 22.51], [114.02, 22.52]];
  const cum = TrackUtil.cumDistKm(pts);
  const kx = 111.32 * Math.cos(22.5 * Math.PI / 180), ky = 110.57;
  const step = Math.sqrt(kx ** 2 + ky ** 2) * 0.01;
  assert.ok(Math.abs(cum[1] - step) < 0.001);
  assert.ok(Math.abs(cum[2] - 2 * step) < 0.002);
});

test("cumDistKm: 单点为 0, 起点纬度缺失不炸", () => {
  assert.deepEqual(TrackUtil.cumDistKm([[114, 22.5]]), [0]);
  assert.equal(TrackUtil.cumDistKm([[114, null], [114.01, 0]])[1] > 1, true);
});


/* ---------------- gapsBetween: 真断档才画蓝色虚线 ---------------- */

test("gapsBetween: 真断档 (731m 跳变) 输出端点和公里数", () => {
  const pts = track(500);
  const jump = 0.0066;
  const withGap = [...pts.slice(0, 250),
                   [pts[249][0] + jump, pts[249][1] + jump * 0.5],
                   ...pts.slice(250).map(p => [p[0] + jump, p[1] + jump * 0.5])];
  const gaps = TrackUtil.gapsBetween(splitGaps(withGap));
  assert.equal(gaps.length, 1);
  assert.deepEqual(gaps[0].pts, [pts[249], [pts[249][0] + jump, pts[249][1] + jump * 0.5]]);
  assert.ok(gaps[0].km > 0.7 && gaps[0].km < 0.8, `km=${gaps[0].km}`);
});

test("gapsBetween: 孤立野点被 splitGaps 丢弃后的伪断档 (<160m) 不输出", () => {
  // A...B 野点C(跳出 731m) D(紧邻 B) E...: splitGaps 拆出 [A..B][C][D..E],
  // 丢掉单点段 C 后相邻段边界 B→D 很近, 不是真断档
  const pts = track(300);
  const jump = 0.0066;
  const b = pts[299];
  // 野点后轨迹在紧邻 B 处继续 (正常步长), 不再有大跳变
  const tail = Array.from({ length: 50 }, (_, i) => [b[0] + (i + 1) * M, b[1]]);
  const withOutlier = [...pts, [b[0] + jump, b[1] + jump], [b[0], b[1] + 0.0001], ...tail];
  const segs = splitGaps(withOutlier);
  assert.ok(segs.length >= 2, "应已拆段");
  assert.equal(TrackUtil.gapsBetween(segs).length, 0);
});


/* ---------------- meanPowerW: 按时间加权的平均功耗 ---------------- */

test("meanPowerW: 按时间加权, 段功耗取两端平均", () => {
  // 段1 0→10s: (1000+1000)/2×10; 段2 10→30s: (1000+4000)/2×20
  // → (10000 + 50000)/30 = 2000W
  const pts = [[114, 22.5, 10, 1000], [114.001, 22.5, 20, 1000],
               [114.002, 22.5, 30, 4000]];
  const ts = [0, 10, 30];
  assert.equal(TrackUtil.meanPowerW(pts, ts), 2000);
});

test("meanPowerW: 单端缺失用另一端, 双缺段不计入", () => {
  // 0-10s: a=1000 b=null → 1000; 10-20s: 双 null 跳过; 20-40s: a=null b=6000 → 6000
  // → (1000×10 + 6000×20) / 30
  const pts = [[114, 22.5, 10, 1000], [114.001, 22.5, 20, null],
               [114.002, 22.5, 30, null], [114.003, 22.5, 30, 6000]];
  const ts = [0, 10, 20, 40];
  assert.equal(TrackUtil.meanPowerW(pts, ts), (1000 * 10 + 6000 * 20) / 30);
});

test("meanPowerW: 全无数据/零时长返回 null", () => {
  assert.equal(TrackUtil.meanPowerW([[114, 22.5, 10, null], [114.001, 22.5, 20, null]],
                                    [0, 10]), null);
  assert.equal(TrackUtil.meanPowerW([[114, 22.5, 10, 5000]], [0]), null);
});

/* ---- ptDistKm / bearingDeg (断档补路的方向校验) ---- */
test("ptDistKm: 东移 0.01° ≈ 1.03km (cos22°), 北移 0.01° ≈ 1.11km", () => {
  assert.ok(Math.abs(TrackUtil.ptDistKm([114, 22], [114.01, 22]) - 1.03) < 0.02);
  assert.ok(Math.abs(TrackUtil.ptDistKm([114, 22], [114, 22.01]) - 1.11) < 0.02);
  assert.equal(TrackUtil.ptDistKm([114, 22], [114, 22]), 0);
});

test("bearingDeg: 北 0 东 90 南 180 西 270", () => {
  assert.equal(Math.round(TrackUtil.bearingDeg([114, 22], [114, 22.01])), 0);
  assert.equal(Math.round(TrackUtil.bearingDeg([114, 22], [114.01, 22])), 90);
  assert.equal(Math.round(TrackUtil.bearingDeg([114, 22], [114, 22 - 0.01])), 180);
  assert.equal(Math.round(TrackUtil.bearingDeg([114, 22], [114 - 0.01, 22])), 270);
});

/* UMD 浏览器分支 (生产 <script> 加载路径): 挂 self; self 缺失时兜底 this */
