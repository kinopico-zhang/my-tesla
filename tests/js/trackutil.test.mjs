/* trackutil.js (splitGaps 轨迹断档拆分) 的 node --test 单元测试。 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const TrackUtil = require("../../app/tesla/static/trackutil.js");
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


/* ------- animStepSec/animTimes/animAt: 按行驶秒推进 (断档不瞬移) -------
   断档步 (隧道/信号丢失) 的秒数按"两端速度线性插值驶过"推算, 播放头得以
   在断档里以插值速度走完。纬度 22.5° 处 0.01° 经度 ≈ 1.029km。 */
const D1 = 1.029;   // 一步 0.01° 经度的公里数

test("animStepSec: 正常步用真实时间差 (推算值不大于真实值时不顶替)", () => {
  // 1.03km @ 90km/h ≈ 41s, 采样 60s → 照真实 60s
  assert.equal(TrackUtil.animStepSec([114, 22.5, 90], [114.01, 22.5, 90], 60), 60);
});

test("animStepSec: 断档步按两端均速推算 (30→60km/h 线性增速, 均速 45)", () => {
  // 2.06km / 45km/h = 164.6s, 比真实 70s 久 → 按推算 (车按这个速度在行进)
  const s = TrackUtil.animStepSec([114, 22.5, 30], [114.02, 22.5, 60], 70);
  assert.ok(Math.abs(s - 2 * D1 / 45 * 3600) < 0.5, "s=" + s);
});

test("animStepSec: 两端停车 (轮渡/拖车) 按 30km/h 保底; 真实更久照真实", () => {
  const est = 5 * D1 / 30 * 3600;              // 5.15km @ 30km/h ≈ 617s
  const s1 = TrackUtil.animStepSec([114, 22.5, 0], [114.05, 22.5, 0], 60);
  assert.ok(Math.abs(s1 - est) < 1, "s1=" + s1);
  assert.equal(TrackUtil.animStepSec([114, 22.5, 0], [114.05, 22.5, 0], 2700), 2700);
});

test("animStepSec: 停车步 (等灯, 两端 <1km/h 且没挪窝) 只计 2s", () => {
  assert.equal(TrackUtil.animStepSec([114, 22.5, 0], [114.000001, 22.5, 0], 30), 2);
  assert.equal(TrackUtil.animStepSec([114, 22.5, 0], [114.000001, 22.5, 0], 1), 1);
});

test("animTimes: ts 缺失按距离/均速推算 (与断档同口径, 不瞬移)", () => {
  const pts = [[114, 22.5, 30], [114.001, 22.5, 30], [114.02, 22.5, 60]];
  const vt = TrackUtil.animTimes(pts, []);
  const e1 = 0.1 * D1 / 30 * 3600;             // 103m @ 30km/h
  const e2 = 1.9 * D1 / 45 * 3600;             // 1.96km @ 45km/h (两端插值)
  assert.ok(Math.abs(vt[1] - e1) < 0.05 && Math.abs(vt[2] - e1 - e2) < 0.5,
            JSON.stringify(vt));
  assert.equal(TrackUtil.animTimes([[114, 22.5]]).length, 1);
});

test("animTimes: 有 ts 且推算不大于真实值 → 按真实秒累计", () => {
  // 10m @ 30km/h 推算 1.2s < 采样 4s → 照真实
  const pts = [[114, 22.5, 30], [114.0001, 22.5, 30], [114.0002, 22.5, 30]];
  assert.deepEqual(TrackUtil.animTimes(pts, [0, 4, 9]), [0, 4, 9]);
});

test("animAt: 负 elapsed (Chrome rAF 时间戳早于 t0) 钳制为起点", () => {
  // 实测抓到过 elapsed = -7.5ms → 旧版负下标 pts[-3][2] 崩溃 → "没有动画"
  const p = TrackUtil.animAt([0, 4, 9], -7.5, 9600);
  assert.deepEqual(p, { idx: 0, frac: 0 });
});

test("animAt: 超出时长 (后台切回/帧延迟) 钳制到末点; 单点/全零节拍不炸", () => {
  assert.deepEqual(TrackUtil.animAt([0, 4, 9], 999999, 9600), { idx: 2, frac: 0 });
  assert.deepEqual(TrackUtil.animAt([0], 999, 1000), { idx: 0, frac: 0 });
  assert.deepEqual(TrackUtil.animAt([0, 0, 0], 500, 1000), { idx: 2, frac: 0 });
});

test("animAt: 播到断档正中间 → 落在断档步内 (idx=断档起点, frac≈0.5)", () => {
  // vt = [0, 10, 174] (断档步 164s): 总 174s, 走到一半 87s = 10 + 77/164
  const vt = [0, 10, 174];
  const p = TrackUtil.animAt(vt, 0.5 * 9600, 9600);
  assert.equal(p.idx, 1);
  assert.ok(Math.abs(p.frac - 77 / 164) < 0.001, JSON.stringify(p));
});

test("animAt: vt 落在 (或无限逼近) 某点时刻 → 该点 (frac≈0)", () => {
  // 浮点换算 (elapsed→q) 会有 1ulp 误差, 允许落在前一步的 1e-9 进度内
  const p = TrackUtil.animAt([0, 10, 174], 10 / 174 * 9600, 9600);
  assert.ok(p.idx === 1 && p.frac === 0 || p.idx === 0 && p.frac > 1 - 1e-9,
            JSON.stringify(p));
});

test("pathPointAt: 按弧长比例在折线上取点 (断档里头部沿道路走)", () => {
  const path = [[0, 0], [1, 0], [1, 1]], cum = [0, 1, 2];
  assert.deepEqual(TrackUtil.pathPointAt(path, cum, 0), [0, 0]);
  assert.deepEqual(TrackUtil.pathPointAt(path, cum, 0.25), [0.5, 0]);
  assert.deepEqual(TrackUtil.pathPointAt(path, cum, 0.75), [1, 0.5]);
  assert.deepEqual(TrackUtil.pathPointAt(path, cum, 1), [1, 1]);
  assert.deepEqual(TrackUtil.pathPointAt(path, cum, -1), [0, 0]);   // 钳制
  assert.deepEqual(TrackUtil.pathPointAt(path, cum, 2), [1, 1]);
});


/* ---------------- cumDistKm: 播放中的实时里程 ---------------- */

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


/* ---------------- splicePath: 断档跳变段替换为道路路径 ---------------- */

test("splicePath: 无路由时退回前缀切片", () => {
  const path = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]];
  assert.deepEqual(TrackUtil.splicePath(path, [], 4), path);
  assert.deepEqual(TrackUtil.splicePath(path, [], 2), [[0, 0], [1, 0], [2, 0]]);
});

test("splicePath: 播过断档后跳变段被道路路径替换 (route 含两端)", () => {
  const path = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]];
  const route = [[2, 0], [2.5, 0.5], [3, 0]];   // path[2]→path[3] 的道路路径
  const splices = [{ aIdx: 2, bIdx: 3, route }];
  // 播到 idx=2 (还没过断档 bIdx=3): 原样前缀
  assert.deepEqual(TrackUtil.splicePath(path, splices, 2),
                   [[0, 0], [1, 0], [2, 0]]);
  // 播到 idx=4 (已过断档): path[2..3] 被 route 整段替换
  assert.deepEqual(TrackUtil.splicePath(path, splices, 4),
                   [[0, 0], [1, 0], [2, 0], [2.5, 0.5], [3, 0], [4, 0]]);
});

test("splicePath: 多处断档按序替换", () => {
  const path = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [6, 0]];
  const splices = [
    { aIdx: 1, bIdx: 2, route: [[1, 0], [1.5, 1], [2, 0]] },
    { aIdx: 4, bIdx: 5, route: [[4, 0], [4.5, -1], [5, 0]] },
  ];
  assert.deepEqual(TrackUtil.splicePath(path, splices, 6),
                   [[0, 0], [1, 0], [1.5, 1], [2, 0], [3, 0], [4, 0],
                    [4.5, -1], [5, 0], [6, 0]]);
  // 播到 idx=3 (过第一处, 没过第二处 bIdx=5): 只替换第一处
  assert.deepEqual(TrackUtil.splicePath(path, splices, 3),
                   [[0, 0], [1, 0], [1.5, 1], [2, 0], [3, 0]]);
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

/* ---- lngLatToTile (播放前预载沿途瓦片: slippy 瓦片格坐标) ---- */
test("lngLatToTile: 原点/边界 (z1 半球格)", () => {
  assert.deepEqual(TrackUtil.lngLatToTile(0, 0, 1), [1, 1]);
  assert.deepEqual(TrackUtil.lngLatToTile(-180, 0, 1), [0, 1]);
  assert.deepEqual(TrackUtil.lngLatToTile(0, 85.05, 1), [1, 0]);
  assert.deepEqual(TrackUtil.lngLatToTile(0, -85.05, 1), [1, 1]);
});

test("lngLatToTile: 北京 z10 = 843/387 (OSM 标准参考值)", () => {
  assert.deepEqual(TrackUtil.lngLatToTile(116.39, 39.91, 10), [843, 387]);
});

test("lngLatToTile: 纬度超出墨卡托范围被钳制, 不产生 NaN", () => {
  /* 恰在 ±85.05112878° 边界上 floor 结果有 1 格浮点抖动, 断言"有限且贴边" */
  const north = TrackUtil.lngLatToTile(116, 99, 10);
  const south = TrackUtil.lngLatToTile(116, -99, 10);
  assert.ok(north.every(Number.isFinite) && north[1] <= 1);
  assert.ok(south.every(Number.isFinite) && south[1] >= 1022);
});

/* UMD 浏览器分支 (生产 <script> 加载路径): 挂 self; self 缺失时兜底 this */

test("浏览器挂载: 无 module 时挂到 self (window.TrackUtil)", () => {
  const src = readFileSync(path.join(
    path.dirname(fileURLToPath(import.meta.url)), "..", "..",
    "app", "tesla", "static", "trackutil.js"), "utf8");
  const fakeSelf = {};
  new Function("module", "exports", "self", src)(undefined, undefined, fakeSelf);
  assert.equal(typeof fakeSelf.TrackUtil.splitGaps, "function");
  assert.equal(fakeSelf.TrackUtil.splitGaps(track(50)).length, 1);
});

test("self 也未定义 (Worker 等): 兜底 this (= globalThis) 挂载", () => {
  const src = readFileSync(path.join(
    path.dirname(fileURLToPath(import.meta.url)), "..", "..",
    "app", "tesla", "static", "trackutil.js"), "utf8");
  new Function("module", "exports", "self", src)(undefined, undefined, undefined);
  assert.equal(typeof globalThis.TrackUtil.splitGaps, "function");
  delete globalThis.TrackUtil;
});

test("pathPointAt 退化输入: 单点路径原样返回", () => {
  assert.deepEqual(TrackUtil.pathPointAt([[113.9, 22.6]], [0], 0.5), [113.9, 22.6]);
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

test("animAt: 节拍含 NaN (坏时间戳) 不炸, frac 兜底 0", () => {
  assert.deepEqual(TrackUtil.animAt([0, NaN, 5], 2.5, 5), { idx: 0, frac: 0 });
});

test("pathPointAt: 零长段 (累计里程重复) 分母兜底 1, 不出 NaN", () => {
  const p = TrackUtil.pathPointAt(
    [[114, 22], [114.001, 22], [114.002, 22]], [0, 0, 0.003], 0);
  assert.deepEqual(p, [114, 22]);   // q=0 命中 cum 相邻相等的段
});
