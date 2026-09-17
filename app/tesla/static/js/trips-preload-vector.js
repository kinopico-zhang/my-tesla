// trips-preload-vector.js — 播放 (9/13): 矢量扫路预载 —— 遮罩下把主图相机
// 沿路线扫一遍灌引擎瓦片缓存 (开场到位 + 慢网兜底; 播放中的连续前瞻由
// 环形前瞻容器负责, 见 CSS #trip-map)。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局); 栅格瓦片预载在 trips-preload-tiles.js。
/* global TrackAnimation, TrackUtil, TripPlayback, tripMap, toGcj, speedZoom,
   zoomUserLock, zoomUserZoom, openSeq, VECTOR_PRELOAD_STEP_MS,
   VECTOR_PRELOAD_CAP_MS, VECTOR_PRELOAD_STEP_FRAC, VECTOR_PRELOAD_BRACKET_MS,
   FIT_AVOID */
/* exported preloadVectorTrack */
"use strict";
async function preloadVectorTrack(pts, ts, openZoom, onProgress, seq) {
  const N = pts.length;
  if (N < 2 || !tripMap) return;
  let cv = null;   // 首次建图 WebGL 就绪有延迟 (流式路径没等过): 轮询一小会儿
  for (let i = 0; i < 6 && !(cv = document.querySelector("#trip-map canvas")); i++)
    await new Promise(r => setTimeout(r, 250));
  if (!cv) return;   // 栅格 (有自己的抄 URL 预载) 或未就绪: 放弃, 播放照常
  const vt = TrackAnimation.animTimes(pts, ts);
  const vtTotal = vt[vt.length - 1] || 0;
  if (vtTotal <= 0) return;
  const cum = TrackUtil.cumDistKm(pts);
  const dur = TripPlayback.animDurMs(N, cum[N - 1]);
  /* 该点处播放会用的档位: 与 zoomTick 同口径 (过去2s+预看5s 滑窗均速);
     视角锁定时播放全程一个档, 扫路也整条按用户档 */
  let hystZoom = Math.round(openZoom);   // 迟滞状态机初值 = 开场档 (zoomTick 同款)
  /* 曲线档 (无迟滞): 播放缓动的终点原料, 也是跨界预取的目标档 */
  const curveZoomAt = i => {
    if (zoomUserLock) return Math.round(zoomUserZoom || tripMap.getZoom());
    return speedZoom(TripPlayback.windowMeanSpeed(vt, pts, dur * vt[i] / vtTotal, dur));
  };
  const zoomAt = i => {   // 迟滞档 (zoomTick 同款 ±0.6 带: 纯 round 会在档位
    // 边界与播放分道, 过渡带的瓦片谁都没拉过)
    hystZoom = TripPlayback.hysteresisZoom(curveZoomAt(i), hystZoom);
    return hystZoom;
  };
  const alive = () => seq === openSeq;
  const dwell = () => new Promise(r => setTimeout(r, VECTOR_PRELOAD_STEP_MS));
  const visit = async (z, p) => {
    tripMap.setZoomAndCenter(z, p, true);
    await dwell();
  };
  /* 跨界预取: 矢量瓦片只在偶数档取数 (dbg83 实测全程只有 z10/12/14), 播放
     缓动跨过档位边界那刻要整层换瓦片 —— 新档没缓存时底图拿旧档数据兜底,
     地名却要等新档数据到 (真机上 = 变焦时文字消失)。迟滞端着旧档、曲线已
     漂向新档的过渡步, 把曲线档也顺带扫一眼 (瓦片请求随相机事件即发, 不等
     渲染, 短驻留就够), 翻转点两侧两带瓦片都提前在手 */
  const visitBracket = async (z, p) => {
    tripMap.setZoomAndCenter(z, p, true);
    await new Promise(r => setTimeout(r, VECTOR_PRELOAD_BRACKET_MS));
  };
  const mapW = document.getElementById("trip-map").clientWidth || 390;
  const t0 = performance.now();
  await visit(Math.round(openZoom), toGcj(pts[0]));   // 开场档先到位 (zoomEaseStart 同款)
  if (alive()) onProgress(5);
  let idx = 0, km = 0;
  while (idx < N - 1 && performance.now() - t0 < VECTOR_PRELOAD_CAP_MS && alive()) {
    await visit(zoomAt(idx), toGcj(pts[idx]));
    const zTarget = Math.round(curveZoomAt(idx));   // 曲线正漂向的档
    if (zTarget !== hystZoom) await visitBracket(zTarget, toGcj(pts[idx]));
    if (!alive()) return;
    onProgress(Math.min(95, 5 + Math.round(km / (cum[N - 1] || 1) * 90)));   // 单调 5→95
    let mpp = 200;   // 米/px 回落值: 步距偏大 = 少扫几步, 不致命
    try { mpp = tripMap.getResolution() || 200; } catch { /* 老版本缺这个接口 */ }
    km += VECTOR_PRELOAD_STEP_FRAC * mapW * mpp / 1000;   // 步距 ~85% 容器宽
    while (idx < N - 1 && cum[idx] < km) idx++;
  }
  /* 收尾一步: 整轨拉远视野 (finish() 同款避让边距, 补环宽), 定格时
     整张全局图的数据也已在手。隐形折线只为供出范围, 用完即删 */
  if (alive()) {
    const stride = Math.max(1, Math.floor(N / 4000));
    const path = [];
    for (let i = 0; i < N; i += stride) path.push(toGcj(pts[i]));
    const whole = new AMap.Polyline({ path, strokeOpacity: 0, zIndex: 1 });
    tripMap.add(whole);
    /* 直跳 (immediately): 动画式会被紧随的开播抢镜, 收尾档瓦片 (含
       contain_range 低层父级) 拉不满, 播完拉远时还得现场补 */
    tripMap.setFitView([whole], true, FIT_AVOID);
    await dwell();
    tripMap.remove(whole);
    onProgress(100);
  }
}
