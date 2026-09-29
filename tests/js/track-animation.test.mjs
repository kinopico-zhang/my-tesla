/* track-animation.js (播放节拍 animStepSec/animTimes/animAt + 描画路径
   splicePath/pathPointAt/accelArc/routePrefix + 瓦片坐标 lngLatToTile) 的
   node --test 单元测试。从 trackutil.test.mjs 按域拆来 (几何/着色留在那边)。 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const TrackAnimation = require("../../app/tesla/static/js/track-animation.js");

/* 断档步 (隧道/信号丢失) 的秒数按"两端速度线性插值驶过"推算, 播放头得以
   在断档里以插值速度走完。纬度 22.5° 处 0.01° 经度 ≈ 1.029km。 */
const D1 = 1.029;   // 一步 0.01° 经度的公里数

test("animStepSec: 正常步用真实时间差 (推算值不大于真实值时不顶替)", () => {
  // 1.03km @ 90km/h ≈ 41s, 采样 60s → 照真实 60s
  assert.equal(TrackAnimation.animStepSec([114, 22.5, 90], [114.01, 22.5, 90], 60), 60);
});

test("animStepSec: 断档步按两端均速推算 (30→60km/h 线性增速, 均速 45)", () => {
  // 2.06km / 45km/h = 164.6s, 比真实 70s 久 → 按推算 (车按这个速度在行进)
  const s = TrackAnimation.animStepSec([114, 22.5, 30], [114.02, 22.5, 60], 70);
  assert.ok(Math.abs(s - 2 * D1 / 45 * 3600) < 0.5, "s=" + s);
});

test("animStepSec: 两端停车 (轮渡/拖车) 按 30km/h 保底; 真实更久照真实", () => {
  const est = 5 * D1 / 30 * 3600;              // 5.15km @ 30km/h ≈ 617s
  const s1 = TrackAnimation.animStepSec([114, 22.5, 0], [114.05, 22.5, 0], 60);
  assert.ok(Math.abs(s1 - est) < 1, "s1=" + s1);
  assert.equal(TrackAnimation.animStepSec([114, 22.5, 0], [114.05, 22.5, 0], 2700), 2700);
});

test("animStepSec: 停车步 (等灯, 两端 <1km/h 且没挪窝) 只计 2s", () => {
  assert.equal(TrackAnimation.animStepSec([114, 22.5, 0], [114.000001, 22.5, 0], 30), 2);
  assert.equal(TrackAnimation.animStepSec([114, 22.5, 0], [114.000001, 22.5, 0], 1), 1);
});

test("animTimes: ts 缺失按距离/均速推算 (与断档同口径, 不瞬移)", () => {
  const pts = [[114, 22.5, 30], [114.001, 22.5, 30], [114.02, 22.5, 60]];
  const vt = TrackAnimation.animTimes(pts, []);
  const e1 = 0.1 * D1 / 30 * 3600;             // 103m @ 30km/h
  const e2 = 1.9 * D1 / 45 * 3600;             // 1.96km @ 45km/h (两端插值)
  assert.ok(Math.abs(vt[1] - e1) < 0.05 && Math.abs(vt[2] - e1 - e2) < 0.5,
            JSON.stringify(vt));
  assert.equal(TrackAnimation.animTimes([[114, 22.5]]).length, 1);
});

test("animTimes: 有 ts 且推算不大于真实值 → 按真实秒累计", () => {
  // 10m @ 30km/h 推算 1.2s < 采样 4s → 照真实
  const pts = [[114, 22.5, 30], [114.0001, 22.5, 30], [114.0002, 22.5, 30]];
  assert.deepEqual(TrackAnimation.animTimes(pts, [0, 4, 9]), [0, 4, 9]);
});

test("animAt: 负 elapsed (Chrome rAF 时间戳早于 t0) 钳制为起点", () => {
  // 实测抓到过 elapsed = -7.5ms → 旧版负下标 pts[-3][2] 崩溃 → "没有动画"
  const p = TrackAnimation.animAt([0, 4, 9], -7.5, 9600);
  assert.deepEqual(p, { idx: 0, frac: 0 });
});

test("animAt: 超出时长 (后台切回/帧延迟) 钳制到末点; 单点/全零节拍不炸", () => {
  assert.deepEqual(TrackAnimation.animAt([0, 4, 9], 999999, 9600), { idx: 2, frac: 0 });
  assert.deepEqual(TrackAnimation.animAt([0], 999, 1000), { idx: 0, frac: 0 });
  assert.deepEqual(TrackAnimation.animAt([0, 0, 0], 500, 1000), { idx: 2, frac: 0 });
});

test("animAt: 播到断档正中间 → 落在断档步内 (idx=断档起点, frac≈0.5)", () => {
  // vt = [0, 10, 174] (断档步 164s): 总 174s, 走到一半 87s = 10 + 77/164
  const vt = [0, 10, 174];
  const p = TrackAnimation.animAt(vt, 0.5 * 9600, 9600);
  assert.equal(p.idx, 1);
  assert.ok(Math.abs(p.frac - 77 / 164) < 0.001, JSON.stringify(p));
});

test("animAt: vt 落在 (或无限逼近) 某点时刻 → 该点 (frac≈0)", () => {
  // 浮点换算 (elapsed→q) 会有 1ulp 误差, 允许落在前一步的 1e-9 进度内
  const p = TrackAnimation.animAt([0, 10, 174], 10 / 174 * 9600, 9600);
  assert.ok(p.idx === 1 && p.frac === 0 || p.idx === 0 && p.frac > 1 - 1e-9,
            JSON.stringify(p));
});

test("pathPointAt: 按弧长比例在折线上取点 (断档里头部沿道路走)", () => {
  const path = [[0, 0], [1, 0], [1, 1]], cum = [0, 1, 2];
  assert.deepEqual(TrackAnimation.pathPointAt(path, cum, 0), [0, 0]);
  assert.deepEqual(TrackAnimation.pathPointAt(path, cum, 0.25), [0.5, 0]);
  assert.deepEqual(TrackAnimation.pathPointAt(path, cum, 0.75), [1, 0.5]);
  assert.deepEqual(TrackAnimation.pathPointAt(path, cum, 1), [1, 1]);
  assert.deepEqual(TrackAnimation.pathPointAt(path, cum, -1), [0, 0]);   // 钳制
  assert.deepEqual(TrackAnimation.pathPointAt(path, cum, 2), [1, 1]);
});

test("pathPointAt 退化输入: 单点路径原样返回", () => {
  assert.deepEqual(TrackAnimation.pathPointAt([[113.9, 22.6]], [0], 0.5), [113.9, 22.6]);
});


/* ---------------- splicePath: 断档跳变段替换为道路路径 ---------------- */

test("splicePath: 无路由时退回前缀切片", () => {
  const path = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]];
  assert.deepEqual(TrackAnimation.splicePath(path, [], 4), path);
  assert.deepEqual(TrackAnimation.splicePath(path, [], 2), [[0, 0], [1, 0], [2, 0]]);
});

test("splicePath: 播过断档后跳变段被道路路径替换 (route 含两端)", () => {
  const path = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]];
  const route = [[2, 0], [2.5, 0.5], [3, 0]];   // path[2]→path[3] 的道路路径
  const splices = [{ aIdx: 2, bIdx: 3, route }];
  // 播到 idx=2 (还没过断档 bIdx=3): 原样前缀
  assert.deepEqual(TrackAnimation.splicePath(path, splices, 2),
                   [[0, 0], [1, 0], [2, 0]]);
  // 播到 idx=4 (已过断档): path[2..3] 被 route 整段替换
  assert.deepEqual(TrackAnimation.splicePath(path, splices, 4),
                   [[0, 0], [1, 0], [2, 0], [2.5, 0.5], [3, 0], [4, 0]]);
});

test("splicePath: 多处断档按序替换", () => {
  const path = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [6, 0]];
  const splices = [
    { aIdx: 1, bIdx: 2, route: [[1, 0], [1.5, 1], [2, 0]] },
    { aIdx: 4, bIdx: 5, route: [[4, 0], [4.5, -1], [5, 0]] },
  ];
  assert.deepEqual(TrackAnimation.splicePath(path, splices, 6),
                   [[0, 0], [1, 0], [1.5, 1], [2, 0], [3, 0], [4, 0],
                    [4.5, -1], [5, 0], [6, 0]]);
  // 播到 idx=3 (过第一处, 没过第二处 bIdx=5): 只替换第一处
  assert.deepEqual(TrackAnimation.splicePath(path, splices, 3),
                   [[0, 0], [1, 0], [1.5, 1], [2, 0], [3, 0]]);
});


/* ---------------- routePrefix: 断档步道路前缀 (蓝实线沿路生长) ----------------
   2026-09-22 补定义: 3.0 拆 trips.js 时函数体没跟着搬, 引用处悬空 —— 首播
   带断档的行程一进断档步当场 ReferenceError 掐死帧循环 (2233 实报: 播到
   六成停住); 断档补路回传存档后断档消失才像"自愈"。 */
const ROUTE = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]];
const RCUM = [0, 1, 2, 3, 4];                       // 每步 1 "km", 全程 4
const SP = { aIdx: 7, bIdx: 8, route: ROUTE, rcum: RCUM };

test("routePrefix: 起步 (frac=0) 只有近岸点 + 头位", () => {
  const head = TrackAnimation.pathPointAt(ROUTE, RCUM, 0);
  assert.deepEqual(TrackAnimation.routePrefix(SP, 0, head), [ROUTE[0], head]);
});

test("routePrefix: 中段裁到弧长落点前, 尾点即头位", () => {
  const head = TrackAnimation.pathPointAt(ROUTE, RCUM, 0.5);   // q=2 → 恰在 r2
  assert.deepEqual(TrackAnimation.routePrefix(SP, 0.5, head),
                   [ROUTE[0], ROUTE[1], head]);
});

test("routePrefix: 到头 (frac=1) 整条道路铺满, 头位即末点", () => {
  const head = TrackAnimation.pathPointAt(ROUTE, RCUM, 1);
  assert.deepEqual(TrackAnimation.routePrefix(SP, 1, head),
                   [...ROUTE.slice(0, 4), head]);
  assert.deepEqual(head, ROUTE[4]);
});

test("routePrefix: 前缀随 frac 单调变长, 主体是道路点前缀, 尾点=头位", () => {
  let prev = 0;
  for (const f of [0, 0.13, 0.37, 0.5, 0.68, 0.9, 1]) {
    const head = TrackAnimation.pathPointAt(ROUTE, RCUM, f);
    const pre = TrackAnimation.routePrefix(SP, f, head);
    assert.equal(pre[pre.length - 1], head, "尾点必须是调用方算好的头位");
    assert.ok(pre.length >= prev, "前缀只长不短 (头在哪线到哪)");
    prev = pre.length;
    for (let i = 0; i < pre.length - 1; i++)
      assert.equal(pre[i], ROUTE[i], "主体必须是道路点的前缀");
  }
});

test("routePrefix: 零长步 (累计里程重复) 不炸不出 NaN", () => {
  const rcum = [0, 0, 1, 1], route = [[0, 0], [0, 0], [1, 0], [1, 0]];
  const head = TrackAnimation.pathPointAt(route, rcum, 0.5);
  const pre = TrackAnimation.routePrefix({ route, rcum }, 0.5, head);
  assert.ok(pre.every(p => Number.isFinite(p[0]) && Number.isFinite(p[1])));
  assert.equal(pre[pre.length - 1], head);
});


/* ---------------- accelArc: 断档步匀加速 (时间进度 → 弧长进度) ----------------
   用户点名 (2026-09-22): 断档补出来的路没有真实采样, 按两端速度匀加速驶过
   (初速 v0 起步 / 终速 v1 收尾), 不按时间线性匀速滑。x/s = τ(2v0+τ(v1-v0))
   /(v0+v1); 车速读数随 τ 线性插值恰是匀加速的瞬时速度, 两边口径对得上。 */
test("accelArc: 两端同速退回线性 (τ 原样)", () => {
  for (const tau of [0, 0.25, 0.5, 0.9, 1])
    assert.ok(Math.abs(TrackAnimation.accelArc(tau, 60, 60) - tau) < 1e-12);
});

test("accelArc: 静止起步的加速段走平方 (v0=0 → x/s=τ²)", () => {
  for (const tau of [0, 0.3, 0.5, 0.8, 1])
    assert.ok(Math.abs(TrackAnimation.accelArc(tau, 0, 90) - tau * tau) < 1e-12);
});

test("accelArc: 30→60 加速段前慢后快, 半程只走 37.5/90", () => {
  // 物理: x(T/2)/s = (v0/2 + aT/8)/(v0 + aT/2), aT=30 → 18.75/45
  assert.ok(Math.abs(TrackAnimation.accelArc(0.5, 30, 60) - 0.5 * 75 / 90) < 1e-12);
});

test("accelArc: 收尾减速 (v1=0) 前快后慢, 半程已走 0.75", () => {
  assert.ok(Math.abs(TrackAnimation.accelArc(0.5, 90, 0) - 0.75) < 1e-12);
});

test("accelArc: 端点恒落 0/1 且单调 (各种两端组合)", () => {
  for (const [v0, v1] of [[0, 0], [30, 60], [80, 20], [0, 120], [15, 15], [120, 0]]) {
    let prev = -1e-9;
    for (let k = 0; k <= 20; k++) {
      const x = TrackAnimation.accelArc(k / 20, v0, v1);
      assert.ok(x >= prev - 1e-12, `单调 (${v0},${v1},${k})`);
      assert.ok(x >= 0 && x <= 1, `夹在 [0,1] (${v0},${v1},${k})`);
      prev = x;
    }
    assert.equal(TrackAnimation.accelArc(0, v0, v1), 0);
    assert.ok(Math.abs(TrackAnimation.accelArc(1, v0, v1) - 1) < 1e-12);
  }
});

test("accelArc: 两端都停 (轮渡/拖车) 没有可加速的物理, 线性兜底", () => {
  assert.equal(TrackAnimation.accelArc(0.4, 0, 0), 0.4);
});


/* ---- lngLatToTile (播放前预载沿途瓦片: slippy 瓦片格坐标) ---- */
test("lngLatToTile: 原点/边界 (z1 半球格)", () => {
  assert.deepEqual(TrackAnimation.lngLatToTile(0, 0, 1), [1, 1]);
  assert.deepEqual(TrackAnimation.lngLatToTile(-180, 0, 1), [0, 1]);
  assert.deepEqual(TrackAnimation.lngLatToTile(0, 85.05, 1), [1, 0]);
  assert.deepEqual(TrackAnimation.lngLatToTile(0, -85.05, 1), [1, 1]);
});

test("lngLatToTile: 北京 z10 = 843/387 (OSM 标准参考值)", () => {
  assert.deepEqual(TrackAnimation.lngLatToTile(116.39, 39.91, 10), [843, 387]);
});

test("lngLatToTile: 纬度超出墨卡托范围被钳制, 不产生 NaN", () => {
  /* 恰在 ±85.05112878° 边界上 floor 结果有 1 格浮点抖动, 断言"有限且贴边" */
  const north = TrackAnimation.lngLatToTile(116, 99, 10);
  const south = TrackAnimation.lngLatToTile(116, -99, 10);
  assert.ok(north.every(Number.isFinite) && north[1] <= 1);
  assert.ok(south.every(Number.isFinite) && south[1] >= 1022);
});

/* UMD 浏览器分支 (生产 <script> 加载路径): 依赖先行 (root.TrackUtil) */
test("浏览器挂载: 无 module 时挂到 self, 并取到 trackutil 依赖", () => {
  const src = readFileSync(path.join(
    path.dirname(fileURLToPath(import.meta.url)), "..", "..",
    "app", "tesla", "static", "js", "track-animation.js"), "utf8");
  const fakeSelf = { TrackUtil: require("../../app/tesla/static/js/trackutil.js") };
  new Function("module", "exports", "self", src)(undefined, undefined, fakeSelf);
  assert.equal(typeof fakeSelf.TrackAnimation.animAt, "function");
  assert.equal(fakeSelf.TrackAnimation.animAt([0, 4, 9], -7.5, 9600).idx, 0);
});

/* ------- 防御分支: 退化输入 (坏时间戳/零长段) 不出 NaN 不炸 ------- */
test("animAt: 节拍含 NaN (坏时间戳) 不炸, frac 兜底 0", () => {
  assert.deepEqual(TrackAnimation.animAt([0, NaN, 5], 2.5, 5), { idx: 0, frac: 0 });
});

test("pathPointAt: 零长段 (累计里程重复) 分母兜底 1, 不出 NaN", () => {
  const p = TrackAnimation.pathPointAt(
    [[114, 22], [114.001, 22], [114.002, 22]], [0, 0, 0.003], 0);
  assert.deepEqual(p, [114, 22]);   // q=0 命中 cum 相邻相等的段
});
