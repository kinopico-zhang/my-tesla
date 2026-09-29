// tesla-shell — 全局壳状态: 车辆筛选 (carId, null=全部=现行为) + 各视图
// 筛选偏好 + 上次停留视图, localStorage 持久化 (3.0 起 URL 不再镜像筛选,
// 换车/筛选不再动地址栏); 车辆切换通知 (订阅方一次性整体刷新)。
"use strict";
/* exported shellState, saveShell, setCar, onCarChange, saveLastView,
            readLastView */

const shellState = {
  carId: null,          // null = 全部 (默认; 单车用户恒 null)
  filters: {},          // 视图键 → 该视图筛选偏好 (形状由视图模块自管)
};

const CAR_CHANGE_FNS = [];
/** 订阅车辆切换 (车辆 chip 触发; 订阅方 = 壳的 refreshCurrent, 整体刷新)。 */
function onCarChange(fn) { CAR_CHANGE_FNS.push(fn); }

function saveShell() {
  try { localStorage.setItem("tesla.shell", JSON.stringify(shellState)); }
  catch (_error) { /* 隐私模式存不进就算了 */ }
}
try {
  const saved = JSON.parse(localStorage.getItem("tesla.shell") || "null");
  if (saved && typeof saved === "object") {
    if (saved.carId === null || Number.isInteger(saved.carId)) {
      shellState.carId = saved.carId;
    }
    if (saved.filters && typeof saved.filters === "object") {
      shellState.filters = saved.filters;
    }
  }
} catch (_error) { /* 坏档当没存过 */ }

/* 冷启消费旧充电页链接的筛选参数 (?type=/?region=/?cost=), 折进本会话偏好。
   参数优先于存档 (旧语义: URL 是事实来源); app-boot 随后把地址栏洗成裸
   /tesla (时间链接 ?range=/?from=&to= 的筛选语义 3.3.0 下线, 直接洗掉)。 */
{
  const qs = new URLSearchParams(location.search);
  const f = shellState.filters.charging || (shellState.filters.charging = {});
  if (["fast", "slow"].includes(qs.get("type"))) f.type = qs.get("type");
  if (["recorded", "missing"].includes(qs.get("cost"))) f.cost = qs.get("cost");
  const segs = (qs.get("region") || "").split("/").map(x => x.trim()).filter(Boolean);
  if (segs.length && segs.length <= 3 && segs.every(x => x.length <= 30))
    f.region = segs.join("/");   // 脏参数丢弃 (1~3 段, 每段 ≤30 字)
  saveShell();
}

/** 切车: 状态先落, 再通知订阅方 (整体刷新当前视图)。 */
function setCar(carId) {
  if (shellState.carId === carId) return;
  shellState.carId = carId;
  saveShell();
  CAR_CHANGE_FNS.forEach(fn => fn(carId));
}

/* ---------- 上次停的视图 (music.lastRoute 同思路, 单壳只记一层) ---------- */
function saveLastView(key) {
  try { localStorage.setItem("tesla.lastView", key); }
  catch (_error) { /* 隐私模式存不进就算了 */ }
}
function readLastView() {
  try { return localStorage.getItem("tesla.lastView") || ""; }
  catch (_error) { return ""; }
}
