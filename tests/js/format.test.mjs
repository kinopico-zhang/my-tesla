/* format.js (三页共用格式化) 的 node --test 单元测试。 */
import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const FormatUtil = require("../../app/tesla/static/js/format.js");
const { pad, parseLocal, fmtCardDate, fmtFullDate, fmtFullStamp, shiftStamp,
        fmtTime, fmtDur, fmtDurLive, num, fmtRegion, fmtPlaceShort,
        fmtPlace } = FormatUtil;

test("pad: 个位补零, 两位原样", () => {
  assert.equal(pad(5), "05");
  assert.equal(pad(12), "12");
  assert.equal(pad(0), "00");
});

test("parseLocal: 空格/T 分隔符同义, 手动解析不受 iOS Safari new Date(string) 限制", () => {
  const a = parseLocal("2026-01-01 09:05");
  const b = parseLocal("2026-01-01T09:05");
  assert.deepEqual(a, b);
  assert.equal(a.getFullYear(), 2026);
  assert.equal(a.getMonth(), 0);
  assert.equal(a.getDate(), 1);
  assert.equal(a.getHours(), 9);
  assert.equal(a.getMinutes(), 5);
});

test("parseLocal: 正则不匹配的串回落 new Date (合法 ISO 仍解析)", () => {
  const d = parseLocal("2026-06-15");   // 走回落分支
  assert.ok(!Number.isNaN(d.getTime()));
  assert.ok(Number.isNaN(parseLocal("").getTime()));   // 空串 → Invalid Date
});

test("fmtCardDate: 月日 + 周几 + 时分 (2026-01-01 是周四)", () => {
  assert.equal(fmtCardDate("2026-01-01 09:05"), "1月1日 周四 09:05");
  assert.equal(fmtCardDate("2026-12-31 23:59"), "12月31日 周四 23:59");
});

test("fmtFullDate: 年月日 + 周几 (行程弹层头部用, 不带时刻)", () => {
  assert.equal(fmtFullDate("2026-01-01 09:05"), "2026年1月1日 周四");
  assert.equal(fmtFullDate("2026-12-31 23:59"), "2026年12月31日 周四");
});

test("fmtFullStamp: 年月日 + 时分, 星期让位 (分组播放副标题用, 用户点名要具体几点几分)", () => {
  assert.equal(fmtFullStamp("2026-01-01 09:05"), "2026年1月1日 09:05");
  assert.equal(fmtFullStamp("2026-12-31 23:59"), "2026年12月31日 23:59");
});

test("shiftStamp: 段首时刻 + 段内行驶秒 → 同格式串 (播放中时刻跟轨迹走; 跨零点跨日自然滚)", () => {
  assert.equal(shiftStamp("2026-01-01 09:05", 0), "2026-01-01 09:05");
  assert.equal(shiftStamp("2026-01-01 09:05", 95), "2026-01-01 09:06");   // 09:06:35 取整到分
  assert.equal(shiftStamp("2026-01-01 09:05"), "2026-01-01 09:05");       // 秒缺席按 0
  assert.equal(shiftStamp("2026-09-10 23:48", 20 * 60), "2026-09-11 00:08");   // 深夜段过零点
  assert.equal(shiftStamp("2026-12-31 23:30", 45 * 60), "2027-01-01 00:15");   // 跨年也滚
});

test("fmtTime: 只取时分", () => {
  assert.equal(fmtTime("2026-01-01T09:05"), "09:05");
});

test("fmtDur: 紧凑中文时长 (统计格窄屏不折行)", () => {
  assert.equal(fmtDur(null), "—");
  assert.equal(fmtDur(0), "0分钟");
  assert.equal(fmtDur(44), "44分钟");
  assert.equal(fmtDur(60), "1时");
  assert.equal(fmtDur(104), "1时44分");
  assert.equal(fmtDur(125), "2时5分");
});

test("fmtDurLive: 播放中实时时长 m:ss / h:mm:ss, 负数钳 0, 秒四舍五入", () => {
  assert.equal(fmtDurLive(0), "0:00");
  assert.equal(fmtDurLive(59.6), "1:00");
  assert.equal(fmtDurLive(65), "1:05");
  assert.equal(fmtDurLive(3725), "1:02:05");
  assert.equal(fmtDurLive(-5), "0:00");
});

test("num: null → —, 位数裁剪且去尾零", () => {
  assert.equal(num(null), "—");
  assert.equal(num(1.0), "1");
  assert.equal(num(12.34), "12.3");
  assert.equal(num(12.34, 2), "12.34");
  assert.equal(num(0.04), "0");
  assert.equal(num("3.5"), "3.5");   // 字符串数字也接
});

test("UMD 浏览器分支: 挂 window.FormatUtil (vm 沙箱, module 未定义)", () => {
  const src = readFileSync(
    new URL("../../app/tesla/static/js/format.js", import.meta.url), "utf8");
  const sandbox = { self: {} };   // vm 上下文自带 JS 内建, 不带 module → 走浏览器分支
  const ctx = vm.createContext(sandbox);
  vm.runInContext(src, ctx);
  assert.equal(typeof ctx.self.FormatUtil.fmtDur, "function");
  assert.equal(ctx.self.FormatUtil.fmtDur(104), "1时44分");
});

test("fmtRegion: 省市区链优先, 退化到市级再到空", () => {
  assert.equal(fmtRegion({ region: "广东省 · 深圳市 · 龙岗区", city: "深圳市",
                           location: "华为立体车库" }), "广东省 · 深圳市 · 龙岗区");
  assert.equal(fmtRegion({ region: null, city: "东莞市", location: "长安镇" }), "东莞市");
  assert.equal(fmtRegion({ region: null, city: null, location: "x" }), "");
});

test("fmtPlace: 只留最小两段 (区 · 地名), 退化链与光地名", () => {
  assert.equal(fmtPlace({ region: "广东省 · 深圳市 · 龙岗区", city: null,
                          location: "华为立体车库" }),
               "龙岗区 · 华为立体车库");
  assert.equal(fmtPlace({ region: "广东省 · 深圳市", city: null,
                          location: "长安镇" }),
               "深圳市 · 长安镇");
  assert.equal(fmtPlace({ region: null, city: "东莞市", location: "长安镇" }),
               "东莞市 · 长安镇");
  assert.equal(fmtPlace({ region: null, city: null, location: "未知位置" }),
               "未知位置");
});

test("fmtPlaceShort: 卡片用的两段数组 (前缀 + 地名)", () => {
  assert.deepEqual(fmtPlaceShort({ region: "广东省 · 深圳市 · 龙岗区",
                                   city: null, location: "华为立体车库" }),
                   ["龙岗区", "华为立体车库"]);
  assert.deepEqual(fmtPlaceShort({ region: null, city: null, location: "x" }),
                   ["x"]);   // 无地区信息: 光地名, 没有前缀段
});
