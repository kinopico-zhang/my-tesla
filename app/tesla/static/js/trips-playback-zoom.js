// trips-playback-zoom.js — 播放 (4/13): 随速变焦 —— 滑窗均速 → 曲线档 →
// 迟滞带 → 指数缓动, 用户手动缩放即锁定 (换行程/重播保持用户档), 播放条
// +/- 基线按钮平移整条曲线 (localStorage 记住)。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局); 曲线/滑窗/迟滞纯逻辑在
// trip-playback.js。
/* global $, TripPlayback, tripMap, curSess */
/* exported followZoomOn, followZoomCur, zoomUserLock, zoomUserZoom, zoomShown,
   zoomApplied, zoomLastT, zoomBias, speedZoom, zoomEaseStart */
"use strict";
/* 播放视角随车速缩放: 慢速拉近看细节, 高速拉远看全局。速度先过滑动窗取
   均值再喂曲线 —— 堵车走走停停时瞬时速度高频打摆, 直接喂视角跟着频繁
   拉近拉远, 看得人头晕。窗口开在播放时间轴上 (过去 2s + 预看 5s, 倍速下
   观感不漂移), 均值天然领先当前车速约 1.5s —— 减速刚起势视角就开始拉近,
   不等车停稳了才反应 (旧版墙钟回看 8s, 慢下来后还要拖好几秒才动)。
   窗口均值连续值 (46km/h 一档, 12.5~15.3 夹紧)
   目标档取整, 带 ±0.6 迟滞带 —— 档位边界的速度抖动 (等灯起步) 不至于来回
   打摆; 实际档位每帧指数缓动逼近目标 (帧率无关)。缓动必须自己做: AMap 的
   动画 setZoom 会被逐帧 setCenter 打成爬行 (实测 3s 只挪 0.1 档), 而立即档
   设小数是保真的 (逐帧 setCenter 下 set 14.12 → 读回 14.12)。用户接管见
   建图处的输入事件监听 —— 接管即视角锁定 (zoomUserLock), 换行程/重播都
   保持用户档位不再自动变焦, 播放条 +/- 基线按钮恢复自动。 */
let followZoomOn = false, followZoomCur = 0;    // 开关 / 目标档 (迟滞簿记)
let zoomUserLock = false, zoomUserZoom = 0;  // 手动视角锁定 + 用户档位 (页会话内)
let zoomShown = 0, zoomApplied = 0, zoomLastT = 0;   // 缓动值 / 已下发值 / 上帧时刻
let zoomBias = 0;   // 视角基线: 随速变焦整条曲线平移 (±2.5, 0.5 步进, localStorage 记住)
try {
  zoomBias = TripPlayback.clampZoomBias(parseFloat(localStorage.getItem("trip-zoom-bias")) || 0);
} catch { /* 无痕模式等 localStorage 不可用 → 当 0 */ }
const speedZoom = v => TripPlayback.speedZoom(v, zoomBias);   // 曲线/滑窗/迟滞在 trip-playback.js

/* 开播/重播: 视角中心与档位都直接到位, 开场不做缓动过渡 (只限最开始,
   之后速度档变化仍逐帧缓动)。档位取整 —— AMap 对小数档会在设置后
   1~2s 自动吸附到最近整数, 开场静止期最容易踩中。
   用户手动缩放过 (zoomUserLock) 则保持用户档位: 只把中心跟到新车头。 */
function zoomEaseStart(zoom) {
  if (zoomUserLock) {
    const z = Math.round(zoomUserZoom || tripMap.getZoom());
    followZoomOn = false;
    followZoomCur = z;
    tripMap.setZoom(z, true);
    zoomShown = zoomApplied = z;
    zoomLastT = performance.now();
    return;
  }
  zoom = Math.round(zoom);
  followZoomOn = true;
  followZoomCur = zoom;
  tripMap.setZoom(zoom, true);
  zoomShown = zoomApplied = zoom;
  zoomLastT = performance.now();
}

/* 视角基线加减: 整条慢近快远曲线跟着平移 (不动曲线形状)。手动缩放接管过
   (followZoomOn=false, 视角锁定) 时按它 = 恢复自动变焦 (锁定解除), 从当前
   档缓动到新目标。播放结束后按无效果 (缓动循环已停), 重播照常。 */
function bumpZoomBias(d) {
  const next = TripPlayback.clampZoomBias(zoomBias + d);
  if (next === zoomBias) return;
  zoomBias = next;
  try { localStorage.setItem("trip-zoom-bias", String(zoomBias)); } catch { /* 同上 */ }
  $("#pb-zval").textContent = zoomBias > 0 ? `+${zoomBias}` : String(zoomBias);
  if (!followZoomOn) {
    followZoomOn = true;                     // 重新接管: 从当前档缓动到新目标
    zoomUserLock = false;                    // 手动锁定解除, 恢复随速变焦
    zoomShown = zoomApplied = tripMap.getZoom();
    zoomLastT = performance.now();
  }
  followZoomCur = Math.round(speedZoom(curSess ? curSess.lastV : 0));
}
$("#pb-zout").addEventListener("click", () => bumpZoomBias(-0.5));
$("#pb-zin").addEventListener("click", () => bumpZoomBias(0.5));
$("#pb-zval").textContent = zoomBias > 0 ? `+${zoomBias}` : String(zoomBias);
