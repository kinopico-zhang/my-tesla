/* format.js (三页共用格式化) 的 node --test 单元测试。 */
import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const FormatUtil = require("../../app/tesla/static/format.js");
const { pad, parseLocal, fmtCardDate, fmtTime, fmtDur, fmtDurLive, num } = FormatUtil;

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
    new URL("../../app/tesla/static/format.js", import.meta.url), "utf8");
  const sandbox = { self: {} };   // vm 上下文自带 JS 内建, 不带 module → 走浏览器分支
  const ctx = vm.createContext(sandbox);
  vm.runInContext(src, ctx);
  assert.equal(typeof ctx.self.FormatUtil.fmtDur, "function");
  assert.equal(ctx.self.FormatUtil.fmtDur(104), "1时44分");
});
