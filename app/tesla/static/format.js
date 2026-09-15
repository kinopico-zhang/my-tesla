/* format.js — 三页共用格式化 (充电记录/充电统计/行程列表): 本地时间解析 +
   卡片日期/时长/实时时长/数字文案。原在各页各抄一份, 抽成纯模块给
   node --test 直测 + tsc --checkJs 把关, 页面脚本顶部解构使用。
   UMD: 浏览器挂 window.FormatUtil, node (测试) 走 module.exports。 */
/* c8 ignore start */
/* UMD 挂载层: node (测试 require) 与浏览器 (生产 <script> 加载) 二选一。
   浏览器分支在 node 覆盖率里天然统计不到 (require 时 module 一定存在),
   c8 标记忽略; 挂载行为由 *_test 的 eval 桩用例验证。 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.FormatUtil = factory();
})(/** @type {Window | Record<string, unknown>} */(typeof self !== "undefined" ? self : this), function () {
/* c8 ignore stop */
  "use strict";

  const pad = n => String(n).padStart(2, "0");

  /* "2026-09-10 08:32" → 本地 Date (服务端已转北京时间; 手动解析, 兼容 iOS Safari) */
  function parseLocal(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(s || "");
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : new Date(s);
  }

  const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
  function fmtCardDate(s) {
    const d = parseLocal(s);
    return `${d.getMonth() + 1}月${d.getDate()}日 周${WEEK[d.getDay()]} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function fmtTime(s) {
    const d = parseLocal(s);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function fmtDur(min) {
    if (min == null) return "—";
    const h = Math.floor(min / 60), m = min % 60;
    /* "1时44分" 而非 "1小时44分": 统计格窄屏放不下长格式会折行 */
    return h ? `${h}时${m ? m + "分" : ""}` : `${m}分钟`;
  }
  /* 播放中实时时长: 秒 → "m:ss" / "h:mm:ss" */
  function fmtDurLive(sec) {
    sec = Math.max(0, Math.round(sec));
    const h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60, s = sec % 60;
    return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  }
  const num = (v, d = 1) => v == null ? "—" : Number(v).toFixed(d).replace(/\.0+$/, "");

  return { pad, parseLocal, WEEK, fmtCardDate, fmtTime, fmtDur, fmtDurLive, num };
});
