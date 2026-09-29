/* trips-sheet-stats.js (行程详情左滑动态/统计页) 纯函数的 node --test 单元
   测试: 模型能耗定标 / 图表 y 轴整刻度。(播放竖线的横轴插值 cursorT 与
   海拔卡前缀最大/爬升 prefixMax/prefixClimb 随 2026-09-23 用户点名「不需要
   动画, 直接展示全貌」退役; speedHist 分桶随 2026-09-24 官方口径对账退役
   —— 三卡数据改服务端原始 positions 聚合, 见 tests/test_trip_hist.py。)
   DOM 侧 (分页/canvas 手绘/三图联动点查/直方图点柱读值) 由 python 静态
   测试钉片段。 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const TripStats = require("../../app/tesla/static/js/view/trips-sheet-stats.js");

test("kwhAt: 模型累计按整条定标到官方总电耗 (播放实时格同款比例)", () => {
  assert.ok(Math.abs(TripStats.kwhAt(5, 10, 8.4) - 4.2) < 1e-9);
  assert.equal(TripStats.kwhAt(5, 0, 8.4), 0);   // 模型全零 (全程没动) 不除零
  assert.ok(Math.abs(TripStats.kwhAt(10, 10, 8.4) - 8.4) < 1e-9);
});

test("niceCeil: 抬到整刻度 (1.2/1.5/2/…/8/10×10ⁿ 阶梯)", () => {
  assert.equal(TripStats.niceCeil(97), 100);     // 过 8 就近 decade 整百
  assert.equal(TripStats.niceCeil(118), 120);
  assert.equal(TripStats.niceCeil(121), 150);
  assert.equal(TripStats.niceCeil(8.4), 10);     // 电耗 kWh 顶格也走同一阶梯
  assert.equal(TripStats.niceCeil(1), 1.2);
  assert.equal(TripStats.niceCeil(0), 1);        // 防零除兜底
});
