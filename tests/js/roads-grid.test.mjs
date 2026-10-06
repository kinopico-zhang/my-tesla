/* roads-grid.js 走过的路栅格计数的 node --test 单元测试: 格键 / DDA 采样
   不跳格 / 有序连续去重保折返 / 热力色阶 (对数刻度 + 四锚点逐通道插值) /
   分档切段共享端点与碎段并段 / packStat 打包往返 / rowSpans 推断层切分
   (可能走过的段不进计数) / thinFlat 显示抽稀 (只喂折线, 首尾必留)。 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const RoadsGrid = require("../../app/tesla/static/js/roads-grid.js");

const { cellKey, cellsForFlat, thinFlat, rowSpans, tOf, stepOf, colorOf,
        stepColor, runsByStep, packStat, cellCount, cellDay, dayOrdOf,
        dayStrOf } = RoadsGrid;

/* 格中心放点: 第 i 格 (避开格边界, 浮点余量 1/4 格) */
const P = i => [114 + (i + 0.25) * 0.0002, 22.5 + 0.00005];
const keyOf = i => cellKey(P(i)[0], P(i)[1]);


test("常量: 色阶档数与四锚点", () => {
  assert.equal(RoadsGrid.STEPS, 12);
  assert.equal(RoadsGrid.COLORS.length, 4);
  assert.equal(RoadsGrid.CELL, 0.0002);
});

test("cellKey: 同格同键, 邻格差 1 (经度) / 1e6 纬度一格", () => {
  assert.equal(cellKey(114.00005, 22.50005), cellKey(114.0001, 22.5001));
  assert.equal(cellKey(114.00025, 22.50005) - cellKey(114.00005, 22.50005), 1e6);
  assert.equal(cellKey(114.00005, 22.50025) - cellKey(114.00005, 22.50005), 1);
});

test("dayOrdOf / dayStrOf: 天序往返 (packStat 下半区)", () => {
  assert.equal(dayOrdOf("2020-01-01"), 0);
  for (const d of ["2020-02-29", "2026-09-29", "2044-12-31"]) {
    assert.equal(dayStrOf(dayOrdOf(d)), d);
  }
});

test("packStat: 次数×16384 + 天序往返; 负数/零/越界钳到界内", () => {
  const s = packStat(3, 100);
  assert.equal(cellCount(s), 3);
  assert.equal(cellDay(s), 100);
  assert.equal(cellCount(packStat(0, 5)), 1);              // 次数下限 1
  assert.equal(cellCount(packStat(2.7, 5)), 2);            // 非整数取整
  assert.equal(cellDay(packStat(2, 99999)), 16383);        // 天序上限
  assert.equal(cellDay(packStat(2, -3)), 0);
  assert.ok(cellCount(packStat(100000, 16383)) < 2 ** 53); // 乘积不越安全整数
});

test("tOf/stepOf: 对数刻度 1→0 端、max→1 端, 档位单调有界", () => {
  assert.equal(tOf(1, 100), 0);
  assert.equal(tOf(100, 100), 1);
  assert.equal(tOf(0, 100), 0);                  // 没记录的格按 1 次
  assert.equal(tOf(5, 1), 0);                    // max<=1: 单色保护
  assert.equal(tOf(1000, 100), 1);               // 超上限钳到 1 端
  assert.ok(tOf(10, 100) > tOf(2, 100));         // 对数拉开中间次数
  let prev = -1;
  for (const c of [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 100]) {
    const s = stepOf(c, 100);
    assert.ok(Number.isInteger(s) && s >= 0 && s < 12 && s >= prev);
    prev = s;
  }
  assert.equal(stepOf(1000, 100), 11);           // 巨数出不了界
});

test("colorOf: 锚点原色, 中点逐通道线性插值, 越界钳回两端", () => {
  assert.equal(colorOf(0), "#3d6fa8");
  assert.equal(colorOf(1 / 3), "#21a179");       // 中间锚点恰在 1/3、2/3
  assert.equal(colorOf(2 / 3), "#d9a521");
  assert.equal(colorOf(1), "#e5484d");
  assert.equal(colorOf(-0.5), "#3d6fa8");        // 越界钳
  assert.equal(colorOf(1.5), "#e5484d");
  assert.equal(colorOf(0.5), "#7da34d");         // 青↔金中点: 逐通道取半
  assert.equal(stepColor(0), "#3d6fa8");         // 档 → 色与 colorOf 同源
  assert.equal(stepColor(11), "#e5484d");
});

/* ---------------- cellsForFlat ---------------- */

test("cellsForFlat: 空输入 / 单点 / 同格两点", () => {
  assert.deepEqual(cellsForFlat(null), []);
  assert.deepEqual(cellsForFlat([]), []);
  assert.deepEqual(cellsForFlat([114.00005, 22.50005]), [keyOf(0)]); // n===2 直返
  // 同格相邻两点: 步长下限 1, 终点同格被连续去重
  assert.deepEqual(cellsForFlat([114.00005, 22.50005, 114.00006, 22.50005]),
                   [keyOf(0)]);
});

test("cellsForFlat: 长直线 DDA 逐格踩到不跳格 (50 格)", () => {
  const pts = [114.00005, 22.5, 114.01005, 22.5];   // 恰 50 格, 端点居格内 1/4
  const out = cellsForFlat(pts);
  assert.equal(out.length, 51);                     // 51 格全踩到
  assert.equal(out[0], cellKey(114.00005, 22.5));
  assert.equal(out[out.length - 1], cellKey(114.01005, 22.5));
  for (let i = 1; i < out.length; i++)
    assert.equal(out[i] - out[i - 1], 1e6);         // 逐格推进, 无跳格
});

test("cellsForFlat: 折返路 A→B→A 两端同格各计一次 (有序连续去重, 非 Set)", () => {
  const [ax, ay] = P(0), [bx, by] = P(4);
  const out = cellsForFlat([ax, ay, bx, by, ax, ay]);
  assert.equal(out[0], keyOf(0));
  assert.equal(out[out.length - 1], keyOf(0));      // 回到 A 再计一次
  assert.ok(out.includes(keyOf(4)));
  assert.ok(out.length > new Set(out).size);        // 折返重复进格被保留
  for (let i = 1; i < out.length; i++)
    assert.notEqual(out[i], out[i - 1]);            // 相邻同格已去重
});

/* ---------------- thinFlat (显示抽稀: 只喂折线 path, 格计数仍吃全量) ---------------- */

test("thinFlat: n≤4 或 step=0 原样直返 (没得抽)", () => {
  const four = [114, 22.5, 114.1, 22.5];
  assert.equal(thinFlat(four, 0.01), four);   // 顶点≤2 直返
  assert.equal(thinFlat(four, 0), four);
  const six = [114, 22.5, 114.1, 22.5, 114.2, 22.5];
  assert.equal(thinFlat(six, 0), six);
});

test("thinFlat: 距上一留点不足 step 的顶点抽掉, 够 step 的留", () => {
  const flat = [0, 0, 0.5, 0, 1.0, 0, 1.7, 0, 2.0, 0];
  assert.deepEqual(thinFlat(flat, 1), [0, 0, 1, 0, 2, 0]);
});

test("thinFlat: 首尾必留 (尾点贴着上一留点也留 —— 段间共享端点不断线)", () => {
  const flat = [0, 0, 0.1, 0, 0.2, 0, 0.25, 0];
  assert.deepEqual(thinFlat(flat, 1), [0, 0, 0.25, 0]);
});

/* ---------------- runsByStep ---------------- */

function runPts(counts) {   // counts: 每点所在格的次数 → 平铺点放进对应格
  const pts = [];
  const stat = new Map();
  counts.forEach((c, i) => {
    pts.push(...P(i));
    stat.set(keyOf(i), packStat(c, 0));
  });
  return { pts, stat };
}

test("runsByStep: 空输入 / 全程同档单段", () => {
  assert.deepEqual(runsByStep(null, new Map(), 10), []);
  assert.deepEqual(runsByStep([], new Map(), 10), []);
  const { pts, stat } = runPts([1, 1, 1, 1]);
  assert.deepEqual(runsByStep(pts, stat, 4),
                   [{ b: 0, i0: 0, i1: 6 }]);
});

test("runsByStep: 换档切段共享端点 (前段 i1 = 后段 i0)", () => {
  const { pts, stat } = runPts([1, 1, 1, 8, 8, 8, 1, 1, 1]);
  const runs = runsByStep(pts, stat, 32);
  assert.equal(runs.length, 3);                     // 1 次 / 8 次 / 1 次
  assert.deepEqual(runs.map(r => r.b), [0, 7, 0]);  // log8/log32 = 0.6 → 第 7 档
  assert.equal(runs[1].i0, runs[0].i1);             // 共享顶点不断线
  assert.equal(runs[2].i0, runs[1].i1);
  assert.equal(runs[2].i1, pts.length - 2);         // 末段到终点
});

test("runsByStep: 中间次数落中间档 (连续色阶, 非 0 即顶)", () => {
  const { pts, stat } = runPts([1, 1, 4, 4, 4, 32, 32, 32]);
  const runs = runsByStep(pts, stat, 32);
  assert.deepEqual(runs.map(r => r.b), [0, 4, 11]); // log4/log32 = 0.4 → 第 4 档
});

test("runsByStep: <3 点碎段并给前段 (中档一格被前段吸收)", () => {
  const { pts, stat } = runPts([1, 1, 1, 2, 5, 5, 5]);   // 中段只有 1 点
  const runs = runsByStep(pts, stat, 5);
  assert.equal(runs.length, 2);
  assert.deepEqual(runs.map(r => r.b), [0, 11]);
  assert.equal(runs[0].i1, runs[1].i0);             // 吸收后仍共享端点
});

test("runsByStep: 并段后与再后段同档顺势续上 (0·短中档·0 → 一段)", () => {
  const { pts, stat } = runPts([1, 1, 1, 2, 1, 1, 1]);
  assert.deepEqual(runsByStep(pts, stat, 5),
                   [{ b: 0, i0: 0, i1: 12 }]);      // 全并成一段 (起始色)
});

test("runsByStep: 格没进过统计按 1 次 (stat.get 缺键)", () => {
  const { pts } = runPts([1, 1]);                   // stat 只给前两格
  const pts2 = [...pts, ...P(2), ...P(3)];          // 后两格无记录
  const runs = runsByStep(pts2, new Map([[keyOf(0), packStat(5, 0)],
                                         [keyOf(1), packStat(5, 0)]]), 5);
  assert.deepEqual(runs.map(r => r.b), [11, 0]);    // 5 次顶档 / 无记录起始色
});

/* ---------------- rowSpans ---------------- */

test("rowSpans: 无推断层整程一段; 空输入空段", () => {
  const pts = [...P(0), ...P(1), ...P(2), ...P(3)];
  assert.deepEqual(rowSpans(pts, null), [[0, pts.length]]);
  assert.deepEqual(rowSpans(pts, []), [[0, pts.length]]);
  assert.deepEqual(rowSpans([], []), []);
  assert.deepEqual(rowSpans(null), []);
});

test("rowSpans: 推断层挖洞, 证实段与推断段共享边界顶点", () => {
  const pts = [...P(0), ...P(1), ...P(2), ...P(3), ...P(4)];   // 5 顶点
  // 推断顶点 1..3 (含): 证实段 [0..1] 与 [3..4] (都含边界顶点)
  assert.deepEqual(rowSpans(pts, [[1, 3]]), [[0, 4], [6, 10]]);
});

test("rowSpans: 整程推断 = 无证实段 (可能走过不进计数)", () => {
  const pts = [...P(0), ...P(1), ...P(2)];
  assert.deepEqual(rowSpans(pts, [[0, 2]]), []);
});

test("rowSpans: 越界/乱序区间钳回界内, 退化区间不产单点段", () => {
  const pts = [...P(0), ...P(1), ...P(2)];          // 3 顶点
  assert.deepEqual(rowSpans(pts, [[-5, 1]]), [[2, 6]]);  // 钳到 [0,1]
  assert.deepEqual(rowSpans(pts, [[2, 99]]), [[0, 6]]);  // 钳到 [2,2]
  assert.deepEqual(rowSpans(pts, [[5, 2]]), [[0, 6]]);   // 空区间跳过
});
