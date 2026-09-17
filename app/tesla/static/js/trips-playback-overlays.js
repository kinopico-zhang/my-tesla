// trips-playback-overlays.js — 播放 (5/13): 轨迹图层 —— 背景速度色线 (按段
// 识别断档) / 白色进程线 / 车头圆点 (buildTrackOverlays), 断档步头部位置与
// 白线沿道路延伸 (headPos/routePrefix), 断档虚线占位与道路路径替换 (addGap)。
// 由 trips.js 按域拆出 (结构化重构: 提取的函数体逐字节未动, 签名与调用点
// 改传 ctx 上下文, 经典脚本按 trips.html 里的顺序加载, 跨模块引用走全局);
// playTrack 编排壳在 trips-playback-session.js。
/* global TrackUtil, GCJ02, TripPlayback, TrackAnimation, tripMap, routeCache,
   routeBetween, routeLooksWrong, routeGapCtx, postGapFill */
/* exported speedLineOverlays, buildTrackOverlays, headPos, routePrefix,
   addGap */
"use strict";
// 背景全程速度线 (淡) —— 拉远后就是完整的速度色全局图
// 合并轨迹按段识别断档 (见 splitSegments), 单段照旧全局一套
const speedLineOverlays = slice => TrackUtil.speedLines(slice).map(b => new AMap.Polyline({
  path: b.pts.map(p => GCJ02.wgs84ToGcj02(p[0], p[1])),
  strokeColor: b.color, strokeOpacity: 0.28, strokeWeight: 4,
  // 换色处两段共享端点, 但 lineCap 默认 butt 在转角各留一个楔形缺口
  // (定格后的速度色轨迹一节节断开) —— 圆头端帽补上, 段间无缝
  lineJoin: "round", lineCap: "round", zIndex: 50,
}));

function buildTrackOverlays(pts, it, path) {
  const segs = TripPlayback.splitSegments(pts, it.seg_starts);
  const bgLines = [];
  for (const seg of segs) bgLines.push(...speedLineOverlays(seg));
  const allLines = [...bgLines];   // 断档虚线随时加进来 (见 addGap), 收尾拉远用
  tripMap.add(bgLines);

  const progress = new AMap.Polyline({
    path: [path[0]], strokeColor: "#f5f5f7", strokeWeight: 4.5,
    lineJoin: "round", lineCap: "round", zIndex: 80,
  });
  const head = new AMap.CircleMarker({
    center: path[0], radius: 7, strokeColor: "#fff", strokeWeight: 2.5,
    fillColor: "#e5484d", fillOpacity: 1, zIndex: 100,
  });
  tripMap.add([progress, head]);
  return { segs, bgLines, allLines, progress, head };
}

/* 断档步的头部位置: 有道路路径沿道路走 (rcum 是它的累计里程), 没有则
   两端直线插值 —— 车按插值速度驶过, 不瞬移到对岸。 */
function headPos(ctx, idx, frac) {
  const { splices, path } = ctx;
  const sp = splices.find(g => g.aIdx === idx);
  if (sp) return TrackAnimation.pathPointAt(sp.route, sp.rcum, frac);
  const a = path[idx], b = path[idx + 1];
  return b ? [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac] : a;
}

/* 断档步内白线跟着头部往对岸长: 道路路径从头到当前进度处的一段 */
function routePrefix(ctx, sp, frac) {
  const q = frac * sp.rcum[sp.rcum.length - 1];
  let i = 0;
  while (i < sp.route.length && sp.rcum[i] < q) i++;
  return sp.route.slice(0, i).concat([headPos(ctx, sp.aIdx, frac)]);
}

/* GPS 断档处 (隧道/信号丢失) 没有真实采样: 蓝色虚线沿真实道路连接,
   先画直线占位, 规划路径回来后整段替换; 规划成功的还会回传服务端存档
   (存自有库, 之后服务端直接下发拼好的连续轨迹)。 */
function addGap(ctx, g, aIdx, bIdx) {
  const { gcj, it, s, splices, pts, allLines } = ctx;
  const line = new AMap.Polyline({
    path: g.pts.map(gcj), strokeColor: "#3987e5", strokeOpacity: 0.28,
    strokeWeight: 4, strokeStyle: "dashed", strokeDasharray: [8, 8],
    // 圆头端帽: 虚线与两侧实线在断档岸边转角处衔接无缝 (同速度色线)
    lineJoin: "round", lineCap: "round", zIndex: 50,
  });
  allLines.push(line);
  tripMap.add(line);
  // 断档路径规划: 缓存命中立即换成道路线, 否则请求回来后替换 (失败保持直线);
  // 规划病态 (吸附到对向车道绕回头路) 时改用上下文重规划 (同样有缓存)
  const key = `${it.id}:${aIdx}-${bIdx}`, ctxKey = key + ":ctx";
  const applyRoute = route => {
    if (!s.alive || !route || route.length < 2) return;
    line.setPath(route);
    splices.push({ aIdx, bIdx, route, rcum: TrackUtil.cumDistKm(route) });
    splices.sort((x, y) => x.aIdx - y.aIdx);
    s.drawn = 0;      // 白线下帧重建: 跳变段改为沿道路
    postGapFill(it, g, route);   // 规划成功 → 回传存档 (只单条; 合并的服务端已拼好)
  };
  const settle = plain => {
    if (!routeLooksWrong(plain, g, pts, aIdx)) return applyRoute(plain);
    const hit = routeCache.get(ctxKey);
    if (hit) return applyRoute(hit);
    routeGapCtx(pts, g, aIdx, bIdx).then(r => {
      if (r) { routeCache.set(ctxKey, r); return applyRoute(r); }
      /* 失败重试一次: ctx 请求紧跟 3 个常规请求, 高德规划接口偶发限流 */
      setTimeout(() => {
        routeGapCtx(pts, g, aIdx, bIdx).then(r2 => {
          if (!r2) return;   // 两次都失败: 保持直线弦。绝不能放行已知病态的
                             // plain —— 1385 曾把 0.5km 隧道断档画成 37km 掉头环线
          routeCache.set(ctxKey, r2);
          applyRoute(r2);
        });
      }, 900);
    });
  };
  const hit = routeCache.get(key);
  if (hit) settle(hit);
  else routeBetween(gcj(g.pts[0]), gcj(g.pts[1]))
    .then(r => { if (r) routeCache.set(key, r); settle(r); });
}
