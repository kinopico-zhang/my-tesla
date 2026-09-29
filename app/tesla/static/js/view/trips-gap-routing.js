// trips-gap-routing.js — 播放 (3/13): 断档补路 —— 高德驾车规划求真实道路
// 路径 (距离优先), 病态路线判别 (端点吸附对向车道规划出掉头环线) 与上下文
// 重规划, 规划成功回传自有库存档 (下次服务端直接下发拼好的连续轨迹),
// 匀速补路队列 (分组合并一次上百个断档, 并发全发必撞限流; 关掉的弹层
// 排队尾巴照样发 —— 只为归档, 且给活会话让路)。
// 规划收口到 mapLib.drivingSearch (失败/不可用 → null, 调用方
// 保持直线虚线占位); 坐标换算走 mapLib.gcj (高德 GCJ-02)。
/* global mapLib, GCJ02, TrackUtil */
/* exported routeCache, routeBetween, toGcj, postGapFill, routeLooksWrong,
   routeGapCtx, queueWireGap */
"use strict";
/* 断档两点间的真实道路路径 (高德驾车规划 · 距离优先/最短路程):
   返回 gcj 路径数组, 失败/没路返回 null, 调用方回退直线。 */
const routeCache = new Map();   // "driveId:aIdx-bIdx" → gcj 路径 (只缓存成功)
function routeBetween(aGcj, bGcj) {
  return mapLib.drivingSearch(aGcj, bGcj).then(r => (r && r.route.length >= 2) ? r.route : null);
}

const toGcj = p => mapLib.gcj(p);

/* 匀速补路队列: 每个断档登记进来就排上 (addGap), 350ms 一个匀速发 —— 单
   条行程断档寥寥; 分组合并一次上百个, 并发全发必撞高德限流 (3~4 个紧挨着
   都偶发)。wired 在入队时即置位 (防重排/重发)。发的时候活会话优先: 关掉
   的弹层留着的尾巴 (规划结果只用来归档, 不再上图) 给新打开的让路, 没有
   活会话的活儿再按序清尾巴 —— 否则关一个 123 洞的分组紧接着开新行程,
   新行程的断档要排 40 多秒的队。 */
const wireQueue = [];
let wireBusy = false;
function queueWireGap(rec) {
  if (!rec || rec.wired || !rec.wire) return;
  rec.wired = true;
  wireQueue.push(rec);
  if (wireBusy) return;
  wireBusy = true;
  (function pump() {
    setTimeout(() => {
      let i = wireQueue.findIndex(r => r.sess && r.sess.alive);
      if (i < 0) i = 0;
      wireQueue.splice(i, 1)[0].wire();
      if (wireQueue.length) pump();
      else wireBusy = false;
    }, 350);
  })();
}

/* 规划成功的断档补路回传服务端: 存进 app 自有库 (TeslaMate 原库只读不动),
   之后轨迹接口直接下发服务端拼好的连续轨迹, 前端不再重新规划。
   高德路线是 GCJ, 转回 WGS 上传; 端点 g.pts 本就是 WGS 采样点, 服务端按
   最近点锚定。回传失败无所谓 —— 下次播放这个断档还在, 会再规划再传。
   合并流的断档带所属段 id (g.did, 服务端 gaps 三元组), 归档到段自己头上。 */
function postGapFill(it, g, route) {
  const did = g.did != null ? g.did : it.id;
  if (typeof did !== "number") return;
  fetch("/tesla/trips/api/gap_fill", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      drive_id: did,
      a: g.pts[0].slice(0, 2), b: g.pts[1].slice(0, 2),
      path: route.map(p => GCJ02.gcj02ToWgs84(p[0], p[1])),
    }),
  }).catch(() => {});
}

/* 断档补路的方向校验: 高德把断档端点吸附到对向车道时, 会规划出先朝反方向
   绕一大圈再回来的路 (实测 0.25km 的断档被规划成 3.6km 掉头环线, 起步方向
   与行驶方向差 176°)。判"病态": 绕行超直线 3 倍, 或起步方向背离断档前行
   驶方向 110° 以上。 */
function routeLooksWrong(route, g, pts, aIdx) {
  if (!route || route.length < 2) return true;
  const straight = TrackUtil.ptDistKm(g.pts[0], g.pts[1]);
  if (TrackUtil.cumDistKm(route)[route.length - 1] > straight * 3 + 0.15) return true;
  if (aIdx > 0) {
    const approach = TrackUtil.bearingDeg(pts[aIdx - 1], pts[aIdx]);
    const start = TrackUtil.bearingDeg(route[0], route[Math.min(2, route.length - 1)]);
    const diff = Math.abs(approach - start);
    if (Math.min(diff, 360 - diff) > 110) return true;
  }
  return false;
}

/* 病态路线的修正: 用断档前后各 3 个真实轨迹点做起终点重新规划 —— 起终点
   落在实际行驶的车道上, 不会吸附到对向; 再按最近点把结果裁剪回 a..b 段。 */
function routeGapCtx(pts, g, aIdx, bIdx) {
  const i0 = aIdx - 3, i1 = bIdx + 3;
  if (i0 < 0 || i1 >= pts.length) return Promise.resolve(null);   // 断档贴着轨迹首尾, 没有上下文
  const aG = toGcj(g.pts[0]), bG = toGcj(g.pts[1]);
  return routeBetween(toGcj(pts[i0]), toGcj(pts[i1])).then(ext => {
    if (!ext || ext.length < 2) return null;
    let s0 = 0, d0 = Infinity;                    // 先定位离 a 最近的点
    for (let i = 0; i < ext.length; i++) {
      const d = TrackUtil.ptDistKm(ext[i], aG);
      if (d < d0) { d0 = d; s0 = i; }
    }
    let s1 = s0, d1 = Infinity;                   // 再在 a 之后定位 b (顺序约束防裁剪坍缩)
    for (let i = s0; i < ext.length; i++) {
      const d = TrackUtil.ptDistKm(ext[i], bG);
      if (d < d1) { d1 = d; s1 = i; }
    }
    if (d0 > 0.15 || d1 > 0.15) return null;      // 延伸路线没贴着断档两端, 不可信
    /* 首尾用精确的断档端点, 中间只取两个最近点之间的路线点: 最近点本身
       可能落在端点后方几十米 (路线点稀疏), 带上会出现起步回头的小折返 */
    const slice = [aG, ...ext.slice(s0 + 1, s1), bG];
    if (TrackUtil.cumDistKm(slice)[slice.length - 1] > TrackUtil.ptDistKm(g.pts[0], g.pts[1]) * 3 + 0.15)
      return null;                                // 裁出来还是绕, 放弃
    return slice;
  });
}
