/* trackutil.js UMD 挂载与边界兜底的 node --test 单元测试: 无 module
   时挂 self, 连 self 都没有时挂 this; 纬度 0 与时间戳持平的兜底。
   拆自 trackutil.test.mjs (结构化重构, 代码逐字节未动)。 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const TrackUtil = require("../../app/tesla/static/js/trackutil.js");

const M = 0.00001;   // ~1.1m, 城市打点步长

function track(n, step = M, start = 114) {
  return Array.from({ length: n }, (_, i) => [start + i * step, 22.5]);
}


test("浏览器挂载: 无 module 时挂到 self (window.TrackUtil)", () => {
  const src = readFileSync(path.join(
    path.dirname(fileURLToPath(import.meta.url)), "..", "..",
    "app", "tesla", "static", "js", "trackutil.js"), "utf8");
  const fakeSelf = {};
  new Function("module", "exports", "self", src)(undefined, undefined, fakeSelf);
  assert.equal(typeof fakeSelf.TrackUtil.splitGaps, "function");
  assert.equal(fakeSelf.TrackUtil.splitGaps(track(50)).length, 1);
});

test("self 也未定义 (Worker 等): 兜底 this (= globalThis) 挂载", () => {
  const src = readFileSync(path.join(
    path.dirname(fileURLToPath(import.meta.url)), "..", "..",
    "app", "tesla", "static", "js", "trackutil.js"), "utf8");
  new Function("module", "exports", "self", src)(undefined, undefined, undefined);
  assert.equal(typeof globalThis.TrackUtil.splitGaps, "function");
  delete globalThis.TrackUtil;
});

/* ------- 防御分支: 退化输入 (缺纬度/坏时间戳/零长段) 不出 NaN 不炸 -------
   splitGaps 里另有两处兜底 (lens 空时 med=0 / 全孤立点原样返回) 在
   正常输入下不可达 (长度守卫保证 lens 非空; 采样段两端必成对存活),
   留作安全网, 覆盖率容忍这两支。 */
test("ptDistKm: 纬度 0 (赤道) 走 || 0 兜底, 结果正常", () => {
  const km = TrackUtil.ptDistKm([114, 0], [114.01, 0]);
  assert.ok(Number.isFinite(km) && km > 1 && km < 1.5);   // 0.01° ≈ 1.1km
});

test("gapsBetween: 端点纬度 0 走 || 0 兜底, 仍量得出跳变", () => {
  const gaps = TrackUtil.gapsBetween([[[114, 0]], [[114.01, 0]]]);
  assert.equal(gaps.length, 1);
  assert.ok(gaps[0].km > 1 && gaps[0].km < 1.5);
});

test("meanPowerW: 时间戳持平/回退的段跳过 (不贡献平均)", () => {
  const w = TrackUtil.meanPowerW(
    [[0, 0, 0, 1000], [0, 0, 0, 1000], [0, 0, 0, 1000]], [0, 0, 5]);
  assert.equal(w, 1000);   // 只有 dt=5 的第 2 段计入
});
