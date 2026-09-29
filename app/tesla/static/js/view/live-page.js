// view/live-page.js — 驾驶视图 (壳版 1/2): 底座 —— 状态机状态量 + 数据面板
// 渲染 (车速表盘 / 已走时长 / 信号中断提示 / 停车常显面板)。
// 旧版 (js/live-page.js) 的菜单收起/$/getJSON 全删 (壳公共件接管); 撞名
// 全局带 lv 前缀: render→lvRender (分组视图占了裸名), map→lvMap (足迹
// 视图), setCar→lvSetCar (壳的车辆切换器)。文件名沿用旧名 (basename 折叠)。
// v6 (2026-09-28): 用户点名「当前车速改成仪表盘样式, 旁边是电池电量,
// 剩下的数据放在下面」—— 车速从大数字改 SVG 表盘, 刻度与数字由
// lvBuildGauge 铺进壳里的静态 SVG。v7 同日追点「仪表盘没指针啊, 车速放
// 在仪表盘下面…电池图标放大点」+「已行驶后面单位是分钟或小时」: 表盘定稿
// 半圆带指针, 车速大数字读在表盘正下方; 时长改带单位 (分钟/小时)。
// v8 同日再追点「仪表盘最高速度设置成 180 吧」: 上限 240→180, 刻度角度
// 改为随 GAUGE_MAX 算 (不再钉死 0.75°/km/h 的 240 口径)。
/* global $, lvSetCar */
/* exported POLL_MS, TRACK_MS, STALE_AFTER_S, cur, driveId, trackTimer, lvMap,
           carMarker, routeLine, trackEnd, tailLine, serverSkew, showState,
           fmtElapsed, setVal, lvRender, lvRenderParked, renderElapsed,
           renderStale */
"use strict";

/* ---------- 状态机: booting → live 常驻 (2026-09-26 用户点名「不管车辆
     什么状态都显示实时数据和地图位置」—— 空态/结束态占位屏退役) ---------- */
const POLL_MS = 5000, TRACK_MS = 20000, STALE_AFTER_S = 120;
let cur = null;            // 最近一次 status (driving=true)
let driveId = null;        // 当前在渲染的行程 id
let trackTimer = null;
let lvMap = null, carMarker = null, routeLine = null;
let trackEnd = null, tailLine = null;   // 轨迹末端 → 车当前位置的连线 (见 lvSetCar)
let serverSkew = 0;        // 服务器时钟 - 手机时钟 (秒): 手机时间不准时走秒仍按服务器算

function showState(id) {
  for (const el of ["booting", "live"]) $("#" + el).hidden = el !== id;
}

function fmtElapsed(sec) {   // 已行驶带单位 (用户点名「已行驶后面单位是分钟或
  const m = Math.floor(sec / 60);   // 小时」): 不足 1 小时报分钟, 以上报「N 小时 M 分」
  if (m < 60) return m + " 分钟";
  const h = Math.floor(m / 60), r = m % 60;
  return r ? h + " 小时 " + r + " 分" : h + " 小时";
}
function setVal(sel, val, unit) {   // 数字进定宽盒 (位数变化不挤单位), null → "–"
  $(sel).innerHTML = '<span class="n">' + (val == null ? "–" : val) + "</span>"
    + (unit ? "<small>" + unit + "</small>" : "");
}

function lvRenderBattery(s) {   // 电量 (开车/停车两态共用): 百分比住电池图标里
  if (s.soc != null) {
    $("#lv-soc").textContent = s.soc + "%";
    const fill = $("#batt-fill");
    fill.style.width = s.soc + "%";
    fill.style.background = s.soc > 50 ? "#32d74b" : s.soc > 20 ? "#ffd60a" : "#ff453a";
  } else {
    $("#lv-soc").textContent = "–";
    $("#batt-fill").style.width = "0%";   // 没数据不留上一场的残条
  }
  $("#lv-range").textContent = s.rated_range_km == null ? "–" : Math.round(s.rated_range_km);
}

/* ---------- 车速表盘 (2026-09-28 用户点名「当前车速改成仪表盘样式」+ 追点
   「仪表盘没指针啊, 车速放在仪表盘下面」+「最高速度设置成 180」) ----------
   半圆表盘 (180°): 0 km/h 在左端, 180 km/h 在右端, 每 20 km/h 一根刻度
   (整 60 加粗带数字), 一次性铺进壳里的静态 SVG; 行驶时弧亮到当前车速
   (pathLength=100 归一) + 指针同步转 (两样都吃 CSS 过渡, 5s 轮询的跳变抹
   成平滑扫), 车速数字读在表盘正下方 (app.html 里 .gauge-readout 跟在
   svg 后面)。 */
const GAUGE_MAX = 180;
const GAUGE_CX = 110, GAUGE_CY = 96;   // 表心: 指针的 CSS transform-origin 同此 (钉在测试)

(function lvBuildGauge() {   // 刻度与数字: 坐标全算好, 藏着的容器里也能建
  const NS = "http://www.w3.org/2000/svg";
  const ticks = $("#lv-gauge-ticks"), labels = $("#lv-gauge-labels");
  for (let s = 0; s <= GAUGE_MAX; s += 20) {
    const major = s % 60 === 0;
    // 刻度角度随 GAUGE_MAX 算 (180 上限 → 每 20 km/h 一格 20°), 换上限只动常量
    const th = (180 - s * 180 / GAUGE_MAX) * Math.PI / 180;
    const px = r => GAUGE_CX + r * Math.cos(th);
    const py = r => GAUGE_CY - r * Math.sin(th);
    const t = document.createElementNS(NS, "line");
    t.setAttribute("x1", px(70)); t.setAttribute("y1", py(70));
    t.setAttribute("x2", px(major ? 63 : 66)); t.setAttribute("y2", py(major ? 63 : 66));
    t.setAttribute("class", major ? "gt major" : "gt");
    ticks.appendChild(t);
    if (major) {
      const lb = document.createElementNS(NS, "text");
      lb.setAttribute("x", px(51)); lb.setAttribute("y", py(51));
      lb.setAttribute("class", "gl");
      lb.textContent = String(s);
      labels.appendChild(lb);
    }
  }
})();

function lvSetGauge(speed) {   // 弧亮到当前车速 + 指针转到当前车速 (过渡交给 CSS)
  const f = speed == null ? 0 : Math.min(speed, GAUGE_MAX) / GAUGE_MAX;
  const arc = $("#lv-gauge-arc");
  arc.style.strokeDasharray = (f * 100).toFixed(2) + " 100";
  arc.style.visibility = f > 0.004 ? "visible" : "hidden";
  $("#lv-gauge-needle").style.transform = "rotate(" + (f * 180 - 90).toFixed(1) + "deg)";
}

function lvRender(s) {
  $("#lv-speed").textContent = s.speed == null ? "–" : Math.round(s.speed);
  lvSetGauge(s.speed);
  /* 副行只报出发时刻 (最高车速格 2026-09-29 用户点名删掉, 不在这补) */
  $("#lv-sub").textContent = "出发 " + (s.start ? s.start.slice(11) : "–");
  lvRenderBattery(s);
  setVal("#lv-km", s.km == null ? null : s.km.toFixed(1), "km");
  setVal("#lv-kwh", s.kwh == null ? null : s.kwh.toFixed(1), "kWh");
  renderElapsed(s);
  renderStale(s);
  if (lvMap && s.lng != null) lvSetCar(s.lng, s.lat);
}

function lvRenderParked(s) {
  /* 不在驾驶也常显 (2026-09-26 用户点名): 电量/续航取车辆最后已知值,
     车速 0。2026-09-27 用户点名「驻车的时候, 显示最后一段行程」: 有已结束
     行程时, 已走时长/行程两格填最后一程 (后端 _trip_item, 与行程列表同口
     径), 没有则保持空格; 同日再点名「不用显示最后行程的时间」—— 副行只留
     日期认出是哪一程, 起止时刻撤掉。地图有最后一程轨迹时不追焦车位
     (lvDrawLastTrack 画完收视野, 5s 轮询别再拉回车位), 没轨迹照旧追焦。 */
  const d = s.last_drive;
  $("#lv-speed").textContent = "0";
  lvSetGauge(0);   // 驻车收弧: 表盘归零, 读数亮 0
  if (d) {
    $("#lv-elapsed").textContent = d.min == null ? "–" : fmtElapsed(d.min * 60);
    $("#lv-sub").textContent = "最后行程 " + d.date;
    setVal("#lv-km", d.km == null ? null : d.km.toFixed(1), "km");
    setVal("#lv-kwh", d.kwh == null ? null : d.kwh.toFixed(1), "kWh");
  } else {
    $("#lv-elapsed").textContent = "–";
    $("#lv-sub").textContent = "–";
    setVal("#lv-km", null);
    setVal("#lv-kwh", null);
  }
  lvRenderBattery(s);
  $("#stale-hint").hidden = true;
  if (lvMap && s.lng != null) lvSetCar(s.lng, s.lat, !d);
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
