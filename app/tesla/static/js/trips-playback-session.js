// trips-playback-session.js — 播放 (7/13): playTrack —— 播放会话对象 s
// (zoomTick/apply/seek/append/finish/replay/restart: 会话方法互相咬合,
// 不再下拆) 与数据准备 (GCJ 转换/能耗曲线/播放节拍/时长)。图层与断档在
// trips-playback-overlays.js, 实时读数与帧循环在 trips-playback-loop.js,
// 下拆函数接 ctx/env 上下文 (调用点现取闭包值, 流式追加后不读旧值)。
// 由 trips.js 按域拆出 (结构化重构: 除调用点改传上下文外代码逐字节未动,
// 经典脚本按 trips.html 里的顺序加载, 跨模块引用走全局)。
/* global $, GCJ02, TrackUtil, TripPlayback, TrackAnimation, tripMap, tripMsg,
   curSess: writable, animRaf: writable, anim: writable, rec, stopRecExport,
   holdScreenAwake, releaseScreenAwake, followZoomOn: writable,
   followZoomCur: writable, zoomShown: writable, zoomApplied: writable,
   zoomLastT: writable, speedZoom, zoomEaseStart, pbToggle, pbSeek, ICON_REPLAY,
   FIT_AVOID, buildTrackOverlays, speedLineOverlays, headPos, routePrefix,
   addGap, setLive, setOfficial, resetPlaybar, frameLoop, startSession, stopAnim */
/* exported anim, playTrack */
"use strict";
/* 播放轨迹动画。more=true 表示轨迹还会通过 append 追加 (合并轨迹流式
   下载边下边播): 播到当前末尾时停在原地等数据, 全部到齐后调用方关掉 more。 */
function playTrack(pts, ts, it, zoom = 14, more = false) {
  stopAnim();
  if (curSess) curSess.alive = false;
  const gcj = p => GCJ02.wgs84ToGcj02(p[0], p[1]);
  const path = pts.map(gcj);                    // 全量坐标转换一次, 逐帧只切片
  let N = path.length;                          // 流式追加会变长
  const cum = TrackUtil.cumDistKm(pts);         // 播放中的实时里程
  /* 逐点能耗模型 (滚阻 + 风阻·v², 全程定标到整体 kWh): 快段每公里贵一点,
    停车不走就不耗, 收尾自然落回整体值 —— 曲线与流式追加步在 trip-playback.js */
  const ecum = TripPlayback.energyCurve(pts, cum);
  const vt = TrackAnimation.animTimes(pts, ts);      // 播放节拍: 每点累计行驶秒
  let dur = TripPlayback.animDurMs(N, cum[N - 1]);
  let growStep = Math.max(1, Math.floor(N / 200));   // 白线分块生长: 每帧全量重建太卡
  const { segs, bgLines, allLines, progress, head } = buildTrackOverlays(pts, it, path);

  /* 播放中: 里程/时长/车速/功耗实时跳动; 收尾停在整体值, 标签换回整体口径 */
  $("#sh-spd-lb").textContent = "车速";
  $("#sh-pw-lb").textContent = "功耗";
  // 这辆车的 API 上报的 power 常年 ~0 (实测全库 -94~254W, 真开车至少上万瓦),
  // 只有出现真实量级的数据才亮出功耗格, 不然一直显示 0.0kW 像是坏了
  let hasPower = pts.some(p => Math.abs(p[3] || 0) > 500);   // 追加段可能点亮
  $("#sh-cell-pw").hidden = !hasPower;          // 没有可用的功耗数据就不占格子

  const splices = [];   // 已解析的断档路由 [{aIdx, bIdx, route, rcum}] 按 aIdx 升序

  const s = {
    pts, N, dur, vt, playT: 0, speed: 1, paused: false, seeking: false,
    finished: false, alive: true, lastIdx: -1, lastFrac: -1, drawn: 0,
    lineBase: null, gapDrawAt: 0,   // 白线末次重建快照 / 断档步内延伸节流
    more, waiting: false, lastV: 0,   // more/waiting: 流式状态; lastV: 当前车速
    /* 随速变焦缓动: 每帧推进 (暂停也要把当前滑变走完, 不然卡在半路) */
    zoomTick() {
      if (!followZoomOn) return;              // 手动缩放即停 (锁定, 见 zoomUserLock)
      // dt 用 performance.now() 差 (不回退), 上限 500ms: 低帧率下钳 100ms
      // 会把缓动拖成爬行 (测试容器 ~2.5fps 实测), 真机 60fps 则恒为步进
      const now = performance.now();
      const dt = Math.min(Math.max(now - zoomLastT, 0), 500);
      zoomLastT = now;
      // 滑窗均速 (过去2s+预看5s, 领先当前车速 ~1.5s) → 曲线档 → 迟滞带
      // → 指数缓动: 三段纯逻辑都在 trip-playback.js (矢量扫路同口径)
      const zt = speedZoom(TripPlayback.windowMeanSpeed(vt, pts, s.playT, dur));
      followZoomCur = TripPlayback.hysteresisZoom(zt, followZoomCur);
      zoomShown = TripPlayback.easeZoomStep(followZoomCur, zoomShown, dt);
      if (Math.abs(zoomShown - zoomApplied) > 0.005) {   // 值变了才下发
        zoomApplied = zoomShown;
        tripMap.setZoom(zoomShown, true);
      }
    },
    apply(idx, frac = 0) {       // 播放头落到 idx 步内 frac 进度 (拖进度条也走这里)
      if (idx === s.lastIdx && frac === s.lastFrac) return;
      const idxNew = idx !== s.lastIdx;
      s.lastIdx = idx; s.lastFrac = frac;
      const pos = headPos({ splices, path }, idx, frac);   // 断档步沿道路/直线插值走过去
      const va = pts[idx][2] || 0, vb = idx + 1 < N ? (pts[idx + 1][2] || 0) : va;
      const v = va + (vb - va) * frac;         // 断档中车速两端线性插值
      head.setCenter(pos);
      head.setOptions({ fillColor: TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(v)] });
      tripMap.setCenter(pos, true);            // 视角紧贴头部 (immediately=不排队动画)
      s.lastV = v;                             // 当前车速 (视角基线按钮重锚用)
      if (idxNew) {
        if (idx < s.drawn) s.drawn = 0;         // 拖进度条回退: 白线从头重建
        if (idx - s.drawn >= growStep || idx === N - 1) {
          s.drawn = idx;
          // 断档跳变段替换成道路路径后, 白线也跟着沿道路走
          s.lineBase = TrackAnimation.splicePath(path, splices, idx);
          progress.setPath(s.lineBase);
        }
      } else if (frac > 0 && cum[idx + 1] - cum[idx] >= TrackUtil.MIN_GAP_KM) {
        // 断档步内推进: 白线跟着头部往对岸长 (有道路沿道路), 节流 ~8fps
        if (Date.now() - s.gapDrawAt > 120) {
          s.gapDrawAt = Date.now();
          const sp = splices.find(g => g.aIdx === idx);
          progress.setPath(TrackAnimation.splicePath(path, splices, idx)
            .concat(sp ? routePrefix({ splices, path }, sp, frac) : [pos]));
        }
      }
      setLive({ pts, ts, cum, ecum, it, N }, idx, frac);
    },
    seek(frac) {                // 0..1: 拖进度条/外部跳转统一入口, 立即生效
      s.playT = Math.min(Math.max(frac, 0), 1) * dur;
      const p = TrackAnimation.animAt(vt, s.playT, dur);   // 滑窗无状态, 跳完即就位
      s.apply(p.idx, p.frac);
    },
    /* 流式追加一段 (见 loadMergedStream): 索引只增不改, 速度线/断档/里程
       全部延伸; 播放头按当前 idx 重新锚定, 避免按新总量比例重算导致倒跳 */
    append(segPts, segTs) {
      if (!s.alive || s.finished || !segPts.length) return;
      const startIdx = pts.length;
      for (const p of segPts) { pts.push(p); path.push(gcj(p)); }
      for (const t of segTs) ts.push(t);
      for (let i = startIdx; i < pts.length; i++)
        cum.push(cum[i - 1] + TrackUtil.ptDistKm(pts[i - 1], pts[i]));
      for (let i = startIdx; i < pts.length; i++)
        ecum.push(ecum[i - 1] + TripPlayback.energyStep(pts, cum, i));
      for (let i = startIdx; i < pts.length; i++)   // 节拍同步延伸 (含段间边界步)
        vt.push(vt[i - 1] + TrackAnimation.animStepSec(pts[i - 1], pts[i],
                 ts.length >= pts.length ? Math.max(0, ts[i] - ts[i - 1]) : 1));
      N = pts.length;
      dur = TripPlayback.animDurMs(N, cum[N - 1]);
      growStep = Math.max(1, Math.floor(N / 200));
      s.dur = dur; s.N = N;             // 进度条 seek 用的是对象上的快照
      // 新段速度线 + 段内断档 (段内补路服务端已拼好, 这里只剩稀疏采样断档)
      const segSegs = TrackUtil.splitGaps(segPts);
      for (const seg of segSegs) {
        const lines = speedLineOverlays(seg);
        bgLines.push(...lines);
        allLines.push(...lines);
        tripMap.add(lines);
      }
      for (const g of TrackUtil.gapsBetween(segSegs))
        addGap({ gcj, it, s, splices, pts, allLines }, g,
               startIdx + segPts.indexOf(g.pts[0]), startIdx + segPts.indexOf(g.pts[1]));
      // 段间边界 (上一段尾 → 本段头, 停车挪位): 距离阈值同 gapsBetween
      for (const g of TrackUtil.gapsBetween([[pts[startIdx - 1]], segPts]))
        addGap({ gcj, it, s, splices, pts, allLines }, g, startIdx - 1, startIdx);
      // 新段可能带来真实量级的功耗数据
      if (!hasPower && segPts.some(p => Math.abs(p[3] || 0) > 500)) {
        hasPower = true;
        $("#sh-cell-pw").hidden = false;
      }
      if (s.waiting) { s.waiting = false; tripMsg(null, false); }
      // 播放头按行驶秒比例重锚 (不是下标比例), 头部在屏幕上原地不动
      if (s.lastIdx >= 0) s.playT = vt[N - 1] > 0 ? dur * vt[s.lastIdx] / vt[N - 1] : 0;
    },
    /* 收尾: 停表+拉远, 但控制条留着 (重播/拖进度仍可用);
       stopAnim 只在关弹层/换轨迹时调用。 */
    finish() {
      if (s.finished) return;
      s.finished = true;
      if (animRaf) cancelAnimationFrame(animRaf);
      animRaf = 0;
      releaseScreenAwake();               // 播完收尾, 允许熄屏
      tripMsg(null, false);
      followZoomOn = false;              // 播放结束, 随速变焦停用 (重播恢复)
      tripMap.remove([progress, head]);
      allLines.forEach(l => l.setOptions({ strokeOpacity: 1 }));  // 淡线变亮
      tripMap.setFitView(allLines, false, FIT_AVOID);      // 拉远 → 全局视角 (避让补环宽, 整轨收进可视区)
      setOfficial({ it, pts, ts, hasPower });
      pbToggle.innerHTML = ICON_REPLAY;
      pbToggle.setAttribute("aria-label", "重播");
      pbSeek.value = 1000;
      pbSeek.style.setProperty("--pb", "100%");
      if (rec) {   // 导出中: 拉远定格入镜后自动收片 (期间重开录制则别误杀)
        const r = rec;
        setTimeout(() => { if (rec === r) stopRecExport(false); }, 1200);
      }
    },
    replay() {                   // 重播: 从头再放 (播完点按钮 / 播完拖进度都会走这)
      if (!s.finished) return;
      s.finished = false;
      s.playT = 0; s.paused = false; s.lastIdx = -1; s.lastFrac = -1; s.drawn = 0;
      s.waiting = false; s.lineBase = null;
      allLines.forEach(l => l.setOptions({ strokeOpacity: 0.28 }));
      progress.setPath([path[0]]);
      head.setCenter(path[0]);
      head.setOptions({ fillColor: TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(pts[0][2] || 0)] });
      tripMap.add([progress, head]);
      tripMap.setCenter(path[0], true);        // 中心与档位都直接到位 (开场不缓动)
      zoomEaseStart(zoom);
      $("#sh-spd-lb").textContent = "车速";
      $("#sh-pw-lb").textContent = "功耗";
      resetPlaybar();
      holdScreenAwake();                  // 重播继续保活
      frameLoop(s);
    },
    restart() {             // 导出视频要整段: 播放中/暂停中也从头重放
      if (!s.finished) {    // replay 只认播完 —— 强过门槛, 且跳过 finish 的拉远定格
        if (animRaf) cancelAnimationFrame(animRaf);   // 停旧帧循环 (replay 再起新的, 别双跑)
        animRaf = 0;
        s.finished = true;
      }
      s.replay();
    },
  };
  anim = s;
  curSess = s;
  startSession(s, { gcj, it, splices, pts, allLines, segs, path, zoom });
  return s;
}
