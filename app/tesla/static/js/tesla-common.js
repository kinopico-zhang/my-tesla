// tesla-common — My Tesla 3.0 单壳共用件: $/esc/getJSON/sendJSON/toast/
// layerMotion/loadEcharts (echarts 按需注入, 壳不再默认拖 1MB 库) + format.js
// 成员与 money 的壳内唯一解构 (旧页各自的那份随旧页退役, 视图脚本沿用裸名)。
// 与 music-common 同构: 经典脚本, 跨模块引用走全局, 头部自带注释。
"use strict";
/* global FormatUtil */
/* exported $, esc, getJSON, sendJSON, toast, layerMotion, loadEcharts, pad, num,
            fmtCardDate, fmtDur, parseLocal, fmtPlaceShort, fmtPlace, money,
            TESLA_MARK */

const $ = (s, el) => (el || document).querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* 页面共用格式化 (format.js 先于本文件加载): 壳内只解构这一次 */
const { pad, num, fmtCardDate, fmtDur, parseLocal, fmtPlaceShort, fmtPlace } = FormatUtil;
const money = v => v == null ? "—" : "¥" + Number(v).toFixed(2).replace(/\.?0+$/, "");

/* Tesla 文字标 (官方字标, Wikimedia Commons「Tesla Motors Logo.svg」, 8 条
   子路径 = T/E/S/L/A): 充电记录里特斯拉官方桩的附加角标内容 (2026-09-27
   用户两轮点名: 先拿文字 logo 替掉「Tesla 超充」字样, 再定附加标 + 白字
   不套底)。原件两层 transform (内层 y 翻转矩阵 + 外层平移) 已烘进坐标,
   只剩一条 path; 官方红 #e82127 不写死 —— fill 用 currentColor, 配色跟
   所在容器的 CSS color 走 (.tesla-mark 白字); 长宽比 7.67:1, 尺寸由
   .tesla-mark svg 管。 */
const TESLA_MARK =
  '<svg viewBox="0 0 1236.01 161.13" aria-hidden="true" focusable="false">' +
  '<path fill="currentColor" d="M849.25 0.2L817.93 0.28L817.93 161.01L961.58 ' +
  '161.01C977.29 154.34 985.71 142.82 988.96 129.36L849.17 129.36L849.25 0.2Z' +
  'M1083.66 32.32L1203.49 32.32C1220.13 29.03 1232.53 14.33 1236.01 0.12L' +
  '1051.12 0.12C1054.57 14.33 1067.15 29.03 1083.66 32.32M695.6 31.87C712.25 ' +
  '27.03 726.27 14.33 729.69 0.24L553.86 0.24L553.86 95.21L697.78 95.21L697.78 ' +
  '128.55L584.9 128.65C567.2 133.57 552.24 145.44 544.74 161.13L553.86 ' +
  '160.97L728.71 160.97L728.71 63.64L584.9 63.64L584.9 31.87L695.6 31.87Z' +
  'M1055.95 160.97L1087.12 160.97L1087.12 96.27L1200.56 96.27L1200.56 ' +
  '160.97L1231.7 160.97L1231.7 63.93L1055.95 63.77L1055.95 160.97ZM311.69 ' +
  '32.22L431.5 32.22C448.16 28.9 460.54 14.21 464.02 0L279.15 0C282.6 14.21 ' +
  '295.16 28.9 311.69 32.22M0 0.37C3.6 14.43 15.77 28.76 32.46 32.38L82.89 ' +
  '32.38L85.45 33.4L85.45 160.64L116.96 160.64L116.96 33.4L119.81 32.38L170.3 ' +
  '32.38C187.15 28.03 199.06 14.43 202.62 0.37L202.62 0.06L0 0.06L0 0.37Z' +
  'M311.69 160.99L431.5 160.99C448.16 157.65 460.54 143 464.02 128.77L279.15 ' +
  '128.77C282.6 143 295.16 157.65 311.69 160.99M311.69 95.74L431.5 95.74C448.16 ' +
  '92.45 460.54 77.75 464.02 63.54L279.15 63.54C282.6 77.75 295.16 92.45 311.69 ' +
  '95.74"/></svg>';

async function getJSON(url) {
  // 不再强制 no-store (2026-09-25 用户点名「充分利用浏览器的缓存」):
  // 缓存策略交给服务端的 Cache-Control —— 轨迹类接口带 ETag 每次重校验
  // (命中 304 省几百 KB), 其余接口服务端本来就该 no-store; 浏览器强刷
  // (Cmd+R) 依旧穿透缓存, 不受影响。
  const r = await fetch(url);
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/* 带方法的请求 (设置四视图的保存/增删改): 401 走登录, 业务错抛 detail
   (旧设置页 api() 的壳版, 全壳就这一份) */
async function sendJSON(url, opts) {
  const r = await fetch(url, Object.assign({ cache: "no-store" }, opts));
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error((body && body.detail) || `${r.status} ${r.statusText}`);
  return body;
}

/* ---------- toast (屏底筛选条上方, music 同位) ---------- */
let toastTimer = 0;
function toast(msg) {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}

/* ---------- 层运动反制 (frosted-ghost) ----------
   层动起来 (视图切换) 时, 变换层从 fixed+磨砂件底下扫过会吐
   重影 —— 运动期暂撤磨砂换实底 (body.layer-anim, tesla-base.css 管
   换底), 停稳自动摘掉。每次调用续期, 静止 400ms 后恢复磨砂。 */
let layerAnimTimer = 0;
function layerMotion() {
  document.body.classList.add("layer-anim");
  clearTimeout(layerAnimTimer);
  layerAnimTimer = setTimeout(
    () => document.body.classList.remove("layer-anim"), 400);
}

/* ---------- echarts 按需注入 ----------
   充电详情曲线/统计图表第一次要用时才拉 echarts.min.js (壳的 HTML 不再
   默认引它); 老页面直开时已在 (script 标签先于本文件), 直接复用。 */
let echartsLoading = null;
function loadEcharts() {
  if (typeof echarts !== "undefined") return Promise.resolve(echarts);
  if (echartsLoading) return echartsLoading;
  echartsLoading = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/tesla/static/echarts.min.js";
    script.onload = () => resolve(echarts);
    script.onerror = () => {
      echartsLoading = null;
      reject(new Error("图表库加载失败"));
    };
    document.head.appendChild(script);
  });
  return echartsLoading;
}
