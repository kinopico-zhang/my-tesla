// trips-playback-overlays.js — 播放 (5/13): 轨迹图层 —— 未来的不上图, 历史
// 的按速度染色随车头生长 (speedSpans 复用定格视图同一批线对象: 走到哪截到
// 哪, 收尾铺回全量, 定格零跳变), 车头圆点 + 车头连线 (buildTrackOverlays),
// 断档步头部位置与蓝实线沿道路延伸 (headPos/gapGrow; 道路前缀裁剪在
// TrackAnimation.routePrefix), 断档虚线占位与道路路径替换 (addGap, 迈过对
// 岸才上图 = gapSettle; 登记即入队匀速发, 关掉的弹层照常归档)。
// 由 trips.js 按域拆出 (结构化重构; 2026-09-21 用户点名改造: 「未来的轨迹
// 不用显示, 历史的轨迹用红绿色标记速度」「不要使用白色」—— 旧的淡底全程
// 线 + 白色进程线退场)。
/* global TrackUtil, TrackAnimation, mapLib, TripPlayback, tripMap, routeCache,
   routeBetween, routeLooksWrong, routeGapCtx, postGapFill, queueWireGap */
/* exported speedSpans, buildTrackOverlays, headPos, addGap,
   histStep, histClear, gapSettle, gapGrow */
"use strict";
/* 速度色 span: 一段同色折线 + 它在 pts 里的下标区间 [start, end] (相邻 span
   共享端点, 与 TrackUtil.speedLines 的分段一一对应)。播放期走到哪 setPath
   截到哪再上图 (未来的整段不上图); 收尾定格直接铺回全量 —— 历史与定格是
   同一批对象同一套色, 收尾不会跳变。color 留在对象上: 车头连线跟它取色。 */
function speedSpans(slice, base) {
  const spans = [];
  let at = base;
  for (const run of TrackUtil.speedLines(slice)) {
    const full = run.pts.map(mapLib.gcj);
    spans.push({
      line: mapLib.polyline({
        path: full, strokeColor: run.color,
        // 播放期加粗一号 (用户点名「动态的线条粗一点, 明显一点」): 不钉的话
        // 引擎默认只 2; 收尾定格收回 4 (session.finish)
        strokeWeight: 6,
        // 不透明 (用户点名「划过的线不要半透明效果」): 不钉的话高德默认
        // strokeOpacity 0.9, 地图道路/地名从粗线底下透出来; 实况驾驶线/
        // 足迹选中线早就钉了 1, 这里是漏网的
        strokeOpacity: 1,
        // 换色处两段共享端点, 但 lineCap 默认 butt 在转角各留一个楔形缺口
        // (定格后的速度色轨迹一节节断开) —— 圆头端帽补上, 段间无缝
        lineJoin: "round", lineCap: "round", zIndex: 50,
      }),
      full, start: at, end: at + run.pts.length - 1, drawn: -1, on: false,
      color: run.color,
    });
    at += run.pts.length - 1;
  }
  return spans;
}

function buildTrackOverlays(pts, it, path) {
  // 服务端检出过断档 (it.gaps, 原始密度口径) 就按下标切; 旧载荷退回客户端
  // 检测 (splitSegments) —— 抽稀后的自适应阈值分不清采样间距与真实断档
  const segs = Array.isArray(it.gaps)
    ? TripPlayback.sliceAtGaps(pts, it.gaps, it.seg_starts)
    : TripPlayback.splitSegments(pts, it.seg_starts);
  // span 的 pts 下标区间: segs 元素是 pts 的切片 (点同引用), 逐段 indexOf
  // 找段基; 段内各 run 依次铺满 (共享端点) —— 与 speedLines 输出对齐
  const spans = [];
  let from = 0;
  for (const seg of segs) {
    const base = Math.max(from, pts.indexOf(seg[0], from));
    from = base;
    spans.push(...speedSpans(seg, base));
  }
  const allLines = spans.map(sp => sp.line);   // 定格全集 (断档虚线随时加进来, 收尾上图)
  const head = mapLib.circleMarker({
    center: path[0], radius: 7, strokeColor: "rgba(10,10,12,.55)", strokeWeight: 2.5,
    fillColor: "#e5484d", fillOpacity: 1, zIndex: 100,
  });
  tripMap.add(head);
  /* 车头连线 (用户设计, 2026-09-22): 线尾 (最后画到图的点) → 车头当前插值
     位, 每帧两点 setPath —— 节流窗内线尾停在旧点、步内车头又在两点间走,
     这两段「线追不上车头」的缝由它补上, 肉眼上轨迹永远连着车头; 颜色跟
     轨迹最后一段同色 (hist.color 随 span 推进更新)。 */
  const tail = mapLib.polyline({
    path: [path[0], path[0]],
    strokeColor: spans.length ? spans[0].color : "#3987e5",
    strokeWeight: 6, strokeOpacity: 1,
    lineJoin: "round", lineCap: "round", zIndex: 60,
  });
  tripMap.add(tail);
  return { segs, spans, allLines, head, tail };
}

/* 历史速度线推进到 idx (含): 时间节流 ~8fps (断档蓝实线同款), 但线尾落后
   车头 25 点以上强制起拍 —— 连线只是两点弦, 高速下落后太多会被拉成穿街
   过巷的长直线。速度色线是按分色 run 拆开的短对象, 每次只 setPath 车头
   所在这一段 —— 白线时代 "整条路径一次重铺太卡"的按点数攒块 (N/200)
   早就多余, 还在合并轨迹 (分组播放) 里随总点数把步长涨到几百: 线尾拖在
   车头后面追不上, 回拨/重播后更要空窗几百点才起笔 (2026-09-22 用户实报)。
   回退 (拖进度条往回拨) 先 histClear 全清重走, 节流拍一并清零 —— 清完第
   一拍立即起笔。 */
function histStep(s, idx) {
  const h = s.hist;
  if (idx < h.done) histClear(s);
  if (idx !== s.N - 1 && idx - h.done < 25 && Date.now() - h.drawAt < 120) return;   // ~8fps, 跟手
  h.drawAt = Date.now();
  h.done = idx;
  for (const sp of h.spans) {          // spans 按起点有序 (追加只往后拼)
    if (sp.start > idx) break;         // 后面的都还没走到
    const upto = Math.min(sp.end, idx);
    if (upto <= sp.drawn) continue;    // 这段早就画到这了
    sp.drawn = upto;
    if (!sp.on) { sp.on = true; tripMap.add(sp.line); }
    sp.line.setPath(sp.full.slice(0, upto - sp.start + 1));
  }
  for (let k = h.spans.length - 1; k >= 0; k--)   // 连线取色: 车头所在 span
    if (h.spans[k].start <= h.done) { h.color = h.spans[k].color; break; }
}

/* 外部重置 (拖进度条回退 / 重播): 播放期上过的历史线全撤、断档态还原,
   从头重走 —— 回退之后的「未来」重新藏起来 */
function histClear(s) {
  const h = s.hist;
  for (const sp of h.spans) {
    if (sp.on) { tripMap.remove(sp.line); sp.on = false; }
    sp.drawn = -1;
  }
  for (const g of s.gaps) {
    if (g.solid) { tripMap.remove(g.solid); g.solid = null; }
    if (g.settled) { tripMap.remove(g.line); g.settled = false; }
  }
  h.done = 0;
  h.drawAt = 0;   // 节流拍清零: 清完第一拍立即重画 (回拨/重播不空窗)
  if (h.spans.length) h.color = h.spans[0].color;   // 连线色随重走复位
}

/* 断档步的头部位置: 有道路路径沿道路走 (rcum 是它的累计里程), 没有则
   两端直线插值 —— 车按插值速度驶过, 不瞬移到对岸。断档步的弧长进度不
   随时间线性: 补出来的这段没有真实采样, 按两端速度匀加速驶过 (v0 起步
   v1 收尾, accelArc), 弦线占位同款; 正常步的真实采样自带节拍, 保持线性。 */
function headPos(ctx, idx, frac) {
  const { splices, path, pts } = ctx;
  const sp = splices.find(g => g.aIdx === idx);
  const v0 = pts[idx][2] || 0;
  const v1 = idx + 1 < pts.length ? (pts[idx + 1][2] || 0) : v0;
  if (sp) return TrackAnimation.pathPointAt(sp.route, sp.rcum,
    TrackAnimation.accelArc(frac, v0, v1));
  const a = path[idx], b = path[idx + 1];
  if (!b) return a;
  if (TrackUtil.ptDistKm(a, b) >= TrackUtil.MIN_GAP_KM)
    frac = TrackAnimation.accelArc(frac, v0, v1);
  return [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac];
}

/* 断档步内: 蓝实线跟着头部往对岸长 —— 有道路路径取道路前缀 (routePrefix,
   弧长进度与 headPos 同款匀加速), 没有就弦线连到插值头位; ~8fps 节流由
   调用方 (apply 的 else 分支) 管 */
function gapGrow(ctx, g, idx, frac, pos) {
  const { splices, path, pts } = ctx;
  const sp = idx === g.aIdx ? splices.find(x => x.aIdx === g.aIdx) : null;
  const v0 = pts[idx][2] || 0;
  const v1 = idx + 1 < pts.length ? (pts[idx + 1][2] || 0) : v0;
  const arc = TrackAnimation.accelArc(frac, v0, v1);
  const seg = sp ? TrackAnimation.routePrefix(sp, arc, pos) : [path[g.aIdx], pos];
  if (!g.solid) {
    g.solid = mapLib.polyline({
      path: seg, strokeColor: "#3987e5", strokeWeight: 6, strokeOpacity: 1,
      lineJoin: "round", lineCap: "round", zIndex: 80,
    });
    tripMap.add(g.solid);
  } else g.solid.setPath(seg);
}

/* 迈过对岸: 蓝实线撤下, 断档虚线转正上图 (走过的断档也是历史);
   跳播/拖进度直接迈过的, 现场补规划 (虚线随后换成道路线) */
function gapSettle(g) {
  if (g.settled) return;
  if (g.wire && !g.wired) queueWireGap(g);
  if (g.solid) { tripMap.remove(g.solid); g.solid = null; }
  tripMap.add(g.line);
  g.settled = true;
}

/* GPS 断档处 (隧道/信号丢失) 没有真实采样: 蓝色虚线沿真实道路连接 (定格
   视图用), 播放期不提前上图 (未来藏起), 迈过对岸才 gapSettle; 规划成功的
   还会回传服务端存档 (存自有库, 之后服务端直接下发拼好的连续轨迹)。
   登记即入队 (queueWireGap 350ms 匀速发): 懒规划的提前量按行驶秒算, 可
   分组播放把几十小时压进 300s, 10 行驶秒只剩几十毫秒墙钟 —— 规划永远
   赶不上车头, 分组断档全程直线 (2026-09-22 用户实报); 队列匀速发不并
   发, 限流由它兜。did 是断档所属段 id (服务端 gaps 三元组, 归档回传用;
   段间跳变没有 did, 落回 it.id)。 */
function addGap(ctx, g, aIdx, bIdx) {
  const { gcj, it, s, splices, pts, allLines } = ctx;
  const line = mapLib.polyline({
    path: g.pts.map(gcj), strokeColor: "#3987e5",
    strokeWeight: 4, strokeStyle: "dashed", strokeDasharray: [8, 8],
    strokeOpacity: 1,   // 与速度色线同口径不透明 (高德默认 0.9 会透出地图)
    // 圆头端帽: 虚线与两侧实线在断档岸边转角处衔接无缝 (同速度色线)
    lineJoin: "round", lineCap: "round", zIndex: 50,
  });
  allLines.push(line);
  const rec = { aIdx, bIdx, did: g.did != null ? g.did : it.id, sess: s,
                line, solid: null, settled: false, wired: false, wire: null };
  s.gaps.push(rec);
  // 断档路径规划: 缓存命中立即换成道路线, 否则请求回来后替换 (失败保持直线);
  // 规划病态 (吸附到对向车道绕回头路) 时改用上下文重规划 (同样有缓存)
  const key = `${it.id}:${aIdx}-${bIdx}`, ctxKey = key + ":ctx";
  const applyRoute = route => {
    if (!route || route.length < 2) return;
    /* 弹层已关/已换: 图不用再动, 但照样回传归档 —— 关弹层不等 123 个
       断档的队列滴完, 没归档的下次打开还是直线 (2026-09-22: 分组一开
       一关 0 存档的根子); 队列会给活会话的断档让路 (trips-gap-routing) */
    if (!s.alive) { postGapFill(it, g, route); return; }
    line.setPath(route);   // 虚线 (定格/已转正) 与后续 gapGrow 的 routePrefix 同步换路
    splices.push({ aIdx, bIdx, route, rcum: TrackUtil.cumDistKm(route) });
    splices.sort((x, y) => x.aIdx - y.aIdx);
    postGapFill(it, g, route);   // 规划成功 → 回传存档 (单条/合并段都传, 按 did 归档)
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
  rec.wire = () => {
    const hit = routeCache.get(key);
    if (hit) settle(hit);
    else routeBetween(gcj(g.pts[0]), gcj(g.pts[1]))
      .then(r => { if (r) routeCache.set(key, r); settle(r); });
  };
  queueWireGap(rec);   // 登记即入队 (350ms 匀速发, 限流见 trips-gap-routing)
}
