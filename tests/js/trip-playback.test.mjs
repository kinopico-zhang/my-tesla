/* trip-playback.js (行程播放纯逻辑: 随速变焦/时长/能耗/分段) 的 node --test 单元测试。 */
import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const TripPlayback = require("../../app/tesla/static/trip-playback.js");
const {
  speedZoom, clampZoomBias, windowMeanSpeed, hysteresisZoom, easeZoomStep,
  animDurMs, energyWeightKm, energyStep, energyCurve, fracValue, splitSegments,
} = TripPlayback;

const TrackUtil = require("../../app/tesla/static/trackutil.js");
const M = 0.00001;   // ~1.1m, 城市打点步长

/* ---------------- 随速变焦 ---------------- */
test("speedZoom: 慢速拉近 15.3, 46km/h 一档, 高速夹紧 12.5", () => {
  assert.equal(speedZoom(0, 0), 15.3);
  assert.equal(speedZoom(46, 0), 14.3);
  assert.equal(speedZoom(92, 0), 13.3);
  assert.equal(speedZoom(138, 0), 12.5);   // 内圈下限
});

test("speedZoom: 基线偏移整条曲线平移, 外圈 ±2.5 推到头时夹紧", () => {
  assert.equal(speedZoom(0, 2.5), 17.8);
  assert.equal(speedZoom(0, -2.5), 12.8);
  assert.equal(speedZoom(138, -2.5), 10.5);   // 12.5-2.5=10 → 外圈下限
  assert.equal(speedZoom(0, 5), 18.5);        // 15.3+5 → 外圈上限 (bias 不自钳, 调用方管)
});

test("clampZoomBias: ±2.5 夹紧, 0.5 一档", () => {
  assert.equal(clampZoomBias(0.3), 0.5);
  assert.equal(clampZoomBias(0.24), 0);
  assert.equal(clampZoomBias(1.25), 1.5);
  assert.equal(clampZoomBias(3), 2.5);
  assert.equal(clampZoomBias(-3), -2.5);
});

test("windowMeanSpeed: 恒速轨迹均值即该速度 (窗口钳制不掺假)", () => {
  const vt = [0, 5000, 10000, 15000, 20000];
  const pts = vt.map(t => [114 + t, 22.5, 80]);
  assert.equal(windowMeanSpeed(vt, pts, 10000, 20000), 80);
});

test("windowMeanSpeed: 窗口两端出界取首/尾车速, 后段比前段快", () => {
  const vt = [0, 5000, 10000, 15000, 20000];
  const slow = vt.map((t, i) => [114 + i * M, 22.5, 10]);
  const fast = vt.map((t, i) => [114 + i * M, 22.5, 100]);
  const early = windowMeanSpeed(slow, slow, 0, 20000);        // 窗口 [-2s,5s] 大半出界
  const late = windowMeanSpeed(fast, fast, 20000, 20000);     // 窗口 [18s,25s] 大半出界
  assert.equal(early, 10);
  assert.equal(late, 100);
});

test("windowMeanSpeed: 斜坡车速取窗口内插值, 均值落在两端之间", () => {
  const vt = [0, 10000, 20000];
  const pts = [[114, 22.5, 0], [114 + M, 22.5, 50], [114 + 2 * M, 22.5, 100]];
  const v = windowMeanSpeed(vt, pts, 10000, 20000);
  assert.ok(v > 40 && v < 90, `窗口 [-2s,+5s] 覆盖中段, 得 ${v}`);
});

test("hysteresisZoom: 迟滞带 ±0.6 内保持当前档, 出带取整换档", () => {
  assert.equal(hysteresisZoom(14.5, 14), 14);   // 带内不动
  assert.equal(hysteresisZoom(14.6, 14), 14);   // 恰在带边界仍不动 (> 0.6 严格)
  assert.equal(hysteresisZoom(14.7, 14), 15);   // 出带 → round
  assert.equal(hysteresisZoom(13.3, 14), 13);   // 反向出带
});

test("easeZoomStep: 指数趋近 + 1.5 档/s 速率上限 + 0.01 内吸附", () => {
  const stepped = easeZoomStep(15, 14, 1000);          // 步长 0.81 < cap 1.5
  assert.ok(Math.abs(stepped - 14.811) < 0.001);
  assert.equal(easeZoomStep(20, 10, 1000), 11.5);      // 步长 8.1 被 cap 钳到 1.5
  assert.equal(easeZoomStep(14.005, 14, 1000), 14.005); // 距目标 <0.01 直接吸附
  // 反向 (target < shown) 同样受限: 15 → 14, 0.5s 步长 1-e^(-5/6) ≈ 0.565
  assert.ok(Math.abs(easeZoomStep(14, 15, 500) - 14.4345982) < 1e-6);
});

/* ---------------- 播放时长 ---------------- */
test("animDurMs: 点数与里程取大, 3s~300s 夹紧", () => {
  assert.equal(animDurMs(300, 0), 3000);      // 恰好 3s 下限
  assert.equal(animDurMs(100, 0), 3000);      // 点少 → 3s 下限
  assert.equal(animDurMs(100, 1), 4400);      // 1km 里程分量 1.4s
  assert.equal(animDurMs(100, 1.4), 4960);    // 里程 4.96s > 点数 0.33s
  assert.equal(animDurMs(10, 0), 3000);
  assert.equal(animDurMs(100000, 0), 300000);    // 纯点数 333s 也被 300s 上限夹住
  assert.equal(animDurMs(100000, 1000), 300000); // 里程 1403s 同样封顶
});

/* ---------------- 能耗模型 ---------------- */
test("energyWeightKm: 滚阻 1 + 风阻 3·(v/100)²", () => {
  assert.equal(energyWeightKm(0), 1);
  assert.equal(energyWeightKm(50), 1.75);
  assert.equal(energyWeightKm(100), 4);
});

test("energyStep: 步速取两端均值 (i-1 → i)", () => {
  const pts = [[114, 22.5, 0], [114 + M, 22.5, 100]];   // 均值 50 → 权重 1.75
  assert.equal(energyStep(pts, [0, 1], 1), 1.75);
});

test("energyCurve: 恒速 100km/h 全程 → 每公里 4 倍权重", () => {
  const pts = [[114, 22.5, 100], [114 + M, 22.5, 100], [114 + 2 * M, 22.5, 100]];
  assert.deepEqual(energyCurve(pts, [0, 1, 2]), [0, 4, 8]);
});

test("fracValue: 线性插值 + 末步夹紧", () => {
  assert.equal(fracValue([0, 10, 20], 0, 0.5), 5);
  assert.equal(fracValue([0, 10, 20], 1, 0.25), 12.5);
  assert.equal(fracValue([0, 10, 20], 2, 0.7), 20);   // 末步取自身
});

/* ---------------- 合并轨迹分段 ---------------- */
test("splitSegments: 无 starts 时整体走 splitGaps (退化为单段行程)", () => {
  const pts = Array.from({ length: 50 }, (_, i) => [114 + i * M, 22.5]);
  const segs = splitSegments(pts, null);
  assert.equal(segs.length, 1);
  assert.equal(segs[0].length, 50);
});

test("splitSegments: 每段独立识别断档, 段间跳变不在此拆", () => {
  const tight = Array.from({ length: 6 }, (_, i) => [114 + i * M, 22.5]);
  const segs = splitSegments(tight, [0, 3]);
  assert.equal(segs.length, 2);
  assert.deepEqual(segs.map(s => s.length), [3, 3]);

  // 段间跳变 (索引 5→6 瞬移 ~730m): 交给 gapsBetween 补路, splitSegments 不拆
  const withJump = [...tight, [114.0066, 22.5]];
  const segs2 = splitSegments(withJump, [0, 3]);
  assert.equal(segs2.length, 2);   // 第二段 [3..7) 内部无断档 → 仍 1 段

  // starts 指到末尾 (空段) 被跳过
  const segs3 = splitSegments(tight, [0, 6]);
  assert.equal(segs3.length, 1);
});

test("splitSegments: 空段列表回落整体 splitGaps", () => {
  const pts = Array.from({ length: 5 }, (_, i) => [114 + i * M, 22.5]);
  assert.equal(splitSegments(pts, []).length, 1);
});

/* ---------------- UMD 挂载 ---------------- */
test("UMD 浏览器分支: 依赖 root.TrackUtil, 挂 window.TripPlayback", () => {
  const src = readFileSync(
    new URL("../../app/tesla/static/trip-playback.js", import.meta.url), "utf8");
  const sandbox = { self: { TrackUtil } };   // vm 上下文无 module → 浏览器分支
  const ctx = vm.createContext(sandbox);
  vm.runInContext(src, ctx);
  assert.equal(ctx.self.TripPlayback.speedZoom(0, 0), 15.3);
  assert.deepEqual(ctx.self.TripPlayback.splitSegments(
    [[114, 22.5], [114 + M, 22.5]], null).length, 1);
});

/* ---------------- 分支兜底 ---------------- */
test("windowMeanSpeed: 采样点落在末点之后, 取尾点速度 (idx+1 越界钳制)", () => {
  const vt = [0, 4000];                       // 窗口 [t-2s, t+5s] 覆盖到 4000 之后
  const pts = [[114, 22.5, 40], [114 + M, 22.5, 40]];
  assert.equal(windowMeanSpeed(vt, pts, 4000, 4000), 40);
});

test("energyStep: 缺速点 (undefined/0) 走 || 0 兜底按静止算", () => {
  const pts = [[114, 22.5], [114 + M, 22.5, 100]];   // 前点无速度位 → 按 0
  assert.equal(energyStep(pts, [0, 1], 1), 1.75);    // 均速 50 → 权重 1.75
  const zero = [[114, 22.5, 0], [114 + M, 22.5, 100]];
  assert.equal(energyStep(zero, [0, 1], 1), 1.75);   // 显式 0 同样兜底
});

test("splitSegments: starts 全指到界外 (无有效段) 回落整体 splitGaps", () => {
  const pts = Array.from({ length: 6 }, (_, i) => [114 + i * M, 22.5]);
  assert.equal(splitSegments(pts, [6]).length, 1);   // [6..6) 空段 → 回落
});

test("windowMeanSpeed: 采样落在缺速点上按静止插值 (va 的 || 0 兜底)", () => {
  const vt = [0, 4000];
  const pts = [[114, 22.5], [114 + M, 22.5, 80]];   // 首点无速度位 → 0
  const v = windowMeanSpeed(vt, pts, 0, 4000);      // 窗口 [-2s,5s] 多半在首点
  assert.ok(v >= 0 && v < 60, `首点按 0 插值, 得 ${v}`);
});

test("energyStep: 后点缺速同样按静止算 (pts[i] 的 || 0 兜底)", () => {
  const pts = [[114, 22.5, 100], [114 + M, 22.5]];  // 后点无速度位 → 0
  assert.equal(energyStep(pts, [0, 1], 1), 1.75);   // 均速 50 → 权重 1.75
});

test("windowMeanSpeed: 前看向缺速的中间点, vb 同样按静止算", () => {
  const vt = [0, 4000, 8000];
  const pts = [[114, 22.5, 80], [114 + M, 22.5], [114 + 2 * M, 22.5, 80]];
  const v = windowMeanSpeed(vt, pts, 0, 8000);   // 窗口 [0-2s, 5s] 前看向第 2 点
  assert.ok(v >= 0 && v < 70, `缺速点按 0 插值, 得 ${v}`);
});
