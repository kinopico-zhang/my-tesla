// tesla-time-range — 全局时间筛选 (抽屉顶部): 旧 5 页各自复制的 TIME_RANGES/
// 日历 5 份合 1。换档/选区间 → 通知订阅方 (boot 接成 refreshCurrent, 当前
// 视图整体刷新); URL 只在冷启消费一次 (?range=/?from=&to=, 旧书签着陆壳时
// 保留筛选语义), 之后筛选不进地址栏 (壳内地址恒 /tesla, 状态在
// localStorage)。时间档不持久化 —— 每次冷启回"全部" (时效性最强的筛选,
// 隔天回访该看全量; 车辆/类型那类偏好才值得记)。
"use strict";
/* global $, pad */
/* exported TIME_RANGES, trState, timeFrom, timeLabel, timeRangeParams,
            setTimeRange, onTimeChange */

/* ---------- 快捷档位 (与旧充电页同款) ---------- */
const TIME_RANGES = [
  { v: "24h", days: 1, lb: "24小时" },
  { v: "7d", days: 7, lb: "近一周" },
  { v: "30d", days: 30, lb: "近一月" },
  { v: "180d", days: 180, lb: "近半年" },
  { v: "1y", days: 365, lb: "近一年" },
  { v: "all", days: 0, lb: "全部" },
];
function timeFrom(v) {   // 档位 → from 本地日期 (含今天共 N 天; 24h 即"昨天起")
  const r = TIME_RANGES.find(x => x.v === v);
  if (!r || !r.days) return null;
  const d = new Date(); d.setDate(d.getDate() - (r.days - 1));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const TIME_CHANGE_FNS = [];
function onTimeChange(fn) { TIME_CHANGE_FNS.push(fn); }

/* ---------- 冷启消费旧 URL 一次 (?range= 快捷档; ?from=&to= 自定义区间) ---------- */
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const trQs = new URLSearchParams(location.search);
let trRange = TIME_RANGES.some(r => r.v === trQs.get("range")) ? trQs.get("range") : "all";
let trFrom = null, trTo = null;
if (trRange === "all") {
  const f = trQs.get("from"), t = trQs.get("to");
  if (DATE_RE.test(f || "") && DATE_RE.test(t || "") && f <= t) { trRange = "custom"; trFrom = f; trTo = t; }
}
const trState = { range: trRange, cFrom: trFrom, cTo: trTo };

function timeLabel() {
  if (trState.range === "custom")   // 自定义显示紧凑区间, 如 01/01–03/31
    return `${trState.cFrom.slice(5).replace("-", "/")}–${trState.cTo.slice(5).replace("-", "/")}`;
  return TIME_RANGES.find(r => r.v === trState.range).lb;
}

/* 各视图查询参数里拼时间的那截 (from/to; 全部档 = 空) */
function timeRangeParams() {
  if (trState.range === "custom") {
    const p = {};
    if (trState.cFrom) p.from = trState.cFrom;
    if (trState.cTo) p.to = trState.cTo;
    return p;
  }
  const from = timeFrom(trState.range);
  return from ? { from } : {};
}

function setTimeRange(v, skipNotify) {
  trState.range = v;
  $("#time-lb").textContent = timeLabel();
  document.querySelectorAll("#time-opts button[data-v]").forEach(b =>
    b.classList.toggle("on", b.dataset.v === v));
  if (v !== "custom") $("#tm-dates").hidden = true;   // 回到快捷档, 收起日历
  if (!skipNotify) TIME_CHANGE_FNS.forEach(fn => fn(v));
}

/* ---------- 自定义日历: 同一个日历连点两次 —— 第一下起点, 第二下终点 ----------
   终点早于起点自动交换; 已有区间再点 = 重新开始选; 只点一下就确定 = 单日。
   (与旧充电页逐字节同逻辑, 绑定对象换成抽屉里的 #time-menu 展开区。) */
let calYm = "", calA = null, calB = null;    // 显示月 / 草稿起止 (ISO 日期)
const calCn = iso => { const p = iso.split("-"); return `${+p[1]}月${+p[2]}日`; };
function calRender() {
  const [y, m] = calYm.split("-").map(Number);
  $("#tm-ym").textContent = `${y}年${m}月`;
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7;   // 周一开头
  const days = new Date(y, m, 0).getDate();
  const n = new Date();
  const today = `${n.getFullYear()}-${pad(n.getMonth() + 1)}-${pad(n.getDate())}`;
  $("#tm-next").disabled = calYm >= today.slice(0, 7);     // 未来月没有数据
  let h = "";
  for (let i = 0; i < lead; i++) h += "<i></i>";
  for (let d = 1; d <= days; d++) {
    const iso = `${calYm}-${pad(d)}`;
    const cls = iso === calA || iso === calB ? "on"
      : calA && calB && iso > calA && iso < calB ? "mid" : "";
    h += `<button class="${cls}${iso === today ? " today" : ""}"
            data-d="${iso}" aria-label="${iso}">${d}</button>`;
  }
  $("#tm-cal").innerHTML = h;
  $("#tm-sel").textContent = !calA ? "点选开始日期"
    : !calB ? `已选开始 ${calCn(calA)}, 再点结束日期`
    : `${calCn(calA)} – ${calCn(calB)}`;
}
function calShift(k) {
  const [y, m] = calYm.split("-").map(Number);
  const t = new Date(y, m - 1 + k, 1);
  calYm = `${t.getFullYear()}-${pad(t.getMonth() + 1)}`;
  calRender();
}
function calOpen() {   // 打开日历: 带出已应用的自定义区间, 没有则从当月起
  calA = trState.cFrom; calB = trState.cTo;
  calYm = (calA || `${new Date().getFullYear()}-${pad(new Date().getMonth() + 1)}`).slice(0, 7);
  calRender();
}
$("#tm-cal").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const d = b.dataset.d;
  if (!calA || calB) { calA = d; calB = null; }   // 新一轮: 重新选起点
  else if (d < calA) { calB = calA; calA = d; }   // 反着点: 自动交换
  else calB = d;                                  // 第二下 = 终点 (同一天 = 单日)
  calRender();
});
$("#tm-prev").addEventListener("click", () => calShift(-1));
$("#tm-next").addEventListener("click", () => calShift(1));
$("#time-opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || !b.dataset.v) return;   // 日历里的按钮 (日期/翻月/确定) 不走快捷档逻辑
  if (b.dataset.v === "custom") {   // 展开/收起日历, 连点两次选好再确定生效
    const box = $("#tm-dates");
    box.hidden = !box.hidden;
    if (!box.hidden) calOpen();
    return;
  }
  if (b.dataset.v === trState.range) return;
  $("#time-menu").removeAttribute("open");
  setTimeRange(b.dataset.v);
});
$("#tm-apply").addEventListener("click", () => {
  if (!calA) return;                // 一下都没点不生效
  $("#time-menu").removeAttribute("open");
  trState.cFrom = calA;             // 只点了起点 = 单日
  trState.cTo = calB || calA;
  setTimeRange("custom");
});
$("#time-menu").addEventListener("toggle", () => {   // 重开菜单回到已应用区间
  if ($("#time-menu").open && !$("#tm-dates").hidden) calOpen();
});
setTimeRange(trState.range, true);
