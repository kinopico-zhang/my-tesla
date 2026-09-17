// live-page.js — 当前驾驶页 (1/2): 页面底座 (菜单收起/$/getJSON) +
// 状态机状态量 + 数据面板渲染 (仪表数字 / 已走时长 / 信号中断提示)。
// 由 live.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 live.html
// 里的顺序加载, 跨模块引用走全局); 地图/轨迹/轮询在 live-driving.js。
/* global setCar */
/* exported $, getJSON, POLL_MS, TRACK_MS, STALE_AFTER_S, cur, driveId, trackTimer,
           map, carMarker, routeLine, trackEnd, tailLine, serverSkew,
           showState, fmtElapsed, setVal, render, renderElapsed, renderStale */
"use strict";
/* 点空白处收起页签菜单 */
document.addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const inside = t.closest("details.nav-menu");
  document.querySelectorAll("details.nav-menu[open]").forEach(m => {
    if (m !== inside) m.removeAttribute("open");
  });
});
const $ = s => document.querySelector(s);

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || ("HTTP " + r.status));
  return r.json();
}

/* ---------- 状态机: booting → live / idle, live → ended (行程闭合) ---------- */
const POLL_MS = 5000, TRACK_MS = 20000, STALE_AFTER_S = 120;
let cur = null;            // 最近一次 status (driving=true)
let driveId = null;        // 当前在渲染的行程 id
let trackTimer = null;
let map = null, carMarker = null, routeLine = null;
let trackEnd = null, tailLine = null;   // 轨迹末端 → 车当前位置的连线 (见 setCar)
let serverSkew = 0;        // 服务器时钟 - 手机时钟 (秒): 手机时间不准时走秒仍按服务器算

function showState(id) {
  for (const el of ["booting", "live", "ended", "idle"]) $("#" + el).hidden = el !== id;
}

const pad = n => String(n).padStart(2, "0");
function fmtElapsed(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
}
function setVal(sel, val, unit) {   // 数字进定宽盒 (位数变化不挤单位), null → "–"
  $(sel).innerHTML = '<span class="n">' + (val == null ? "–" : val) + "</span>"
    + (unit ? "<small>" + unit + "</small>" : "");
}

function render(s) {
  $("#lv-speed").textContent = s.speed == null ? "–" : Math.round(s.speed);
  $("#lv-sub").innerHTML =
    "出发 " + (s.start ? s.start.slice(11) : "–") +
    ' · 最高 <span class="n">' + (s.speed_max == null ? "–" : Math.round(s.speed_max)) + "</span> km/h";
  if (s.soc != null) {
    $("#lv-soc").textContent = s.soc + "%";
    const fill = $("#batt-fill");
    fill.style.width = s.soc + "%";
    fill.style.background = s.soc > 50 ? "#32d74b" : s.soc > 20 ? "#ffd60a" : "#ff453a";
  } else {
    $("#lv-soc").textContent = "–";
  }
  $("#lv-range").textContent = s.rated_range_km == null ? "–" : Math.round(s.rated_range_km);
  setVal("#lv-km", s.km == null ? null : s.km.toFixed(1), "km");
  setVal("#lv-kwh", s.kwh == null ? null : s.kwh.toFixed(1), "kWh");
  setVal("#lv-avg", s.wh_per_km == null ? null : s.wh_per_km, "Wh/km");
  setVal("#lv-vmax", s.speed_max == null ? null : Math.round(s.speed_max), "km/h");
  renderElapsed(s);
  renderStale(s);
  if (map && s.lng != null) setCar(s.lng, s.lat);
}

function renderElapsed(s) {
  /* 已行驶按服务器时钟算 (now_utc 校准偏差): 手机时钟不准时 Date.now 会把
     差值钳到 0, 用户看到的已行驶就一直是 0:00 (真机踩坑)。 */
  const sec = Math.max(0, Math.floor(Date.now() / 1000 + serverSkew - s.started_utc));
  $("#lv-elapsed").textContent = fmtElapsed(sec);
}

function renderStale(s) {   // 最新位置点太久没更新 → 提示信号中断 (隧道/无网)
  const hint = $("#stale-hint");
  const age = s.pos_utc ? Math.floor(Date.now() / 1000 - s.pos_utc) : 0;
  if (age > STALE_AFTER_S) {
    hint.hidden = false;
    hint.textContent = "信号可能中断 · 数据 " + Math.floor(age / 60) + " 分钟前更新";
  } else {
    hint.hidden = true;
  }
}
