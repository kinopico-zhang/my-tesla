// tesla-common — My Tesla 3.0 单壳共用件: $/esc/getJSON/sendJSON/toast/
// layerMotion/loadEcharts (echarts 按需注入, 壳不再默认拖 1MB 库) + format.js
// 成员与 money 的壳内唯一解构 (旧页各自的那份随旧页退役, 视图脚本沿用裸名)。
// 与 music-common 同构: 经典脚本, 跨模块引用走全局, 头部自带注释。
"use strict";
/* global FormatUtil */
/* exported $, esc, getJSON, sendJSON, toast, layerMotion, loadEcharts, pad, num,
            fmtCardDate, fmtDur, parseLocal, money */

const $ = (s, el) => (el || document).querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* 页面共用格式化 (format.js 先于本文件加载): 壳内只解构这一次 */
const { pad, num, fmtCardDate, fmtDur, parseLocal } = FormatUtil;
const money = v => v == null ? "—" : "¥" + Number(v).toFixed(2).replace(/\.?0+$/, "");

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
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
   层动起来 (抽屉开合/视图切换) 时, 变换层从 fixed+磨砂件底下扫过会吐
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
