// trips-playback-session.js — 播放 (7/13): playTrack —— 播放会话对象 s
// (zoomTick/apply/seek/append/finish/replay/restart: 会话方法互相咬合,
// 不再下拆) 与数据准备 (GCJ 转换/能耗曲线/播放节拍/时长)。图层与断档在
// trips-playback-overlays.js, 实时读数与帧循环在 trips-playback-loop.js,
// 下拆函数接 ctx/env 上下文 (调用点现取闭包值, 流式追加后不读旧值)。
// 由 trips.js 按域拆出 (结构化重构; 2026-09-21 用户点名改造播放画法:
// 未来的不上图, 历史速度色随头生长 —— 旧的淡底全程 + 白色进程线退场)。
/* global $, mapLib, TrackUtil, TripPlayback, TrackAnimation, tripMap, tripMsg,
   curSess: writable, animRaf: writable, anim: writable, rec, stopRecExport,
   holdScreenAwake, releaseScreenAwake, followZoomOn: writable,
   followZoomCur: writable, zoomShown: writable, zoomApplied: writable,
   zoomLastT: writable, speedZoom, zoomEaseStart, pbToggle, pbSeek, ICON_REPLAY,
   FIT_AVOID, buildTrackOverlays, speedSpans, headPos, addGap, queueWireGap,
   histStep, histClear, gapSettle, gapGrow, setLive, setOfficial, resetPlaybar,
   setSegTitle, frameLoop, startSession, stopAnim */
/* exported anim, playTrack */
"use strict";
/* 播放轨迹动画。more=true 表示轨迹还会通过 append 追加 (合并轨迹流式
   下载边下边播): 播到当前末尾时停在原地等数据, 全部到齐后调用方关掉 more。
   defer=true 起播推迟 (2026-09-27 用户点名弹层三页独立): 只备数据与图层,
   会话挂 curSess 立即可读 (行驶数据/行驶统计两页拿它画图, 不等地图预载),
   anim 仍空着 —— 播放态入口 (控制条/跳过/录制) 读 anim, 加载期照旧空转;
   预载收尾调用方点 s.begin() 才起播 (帧循环/断档登记/视角跟随)。 */
function playTrack(pts, ts, it, zoom = 14, more = false, defer = false) {
  stopAnim();
  if (curSess) curSess.alive = false;
  const gcj = mapLib.gcj;                          // WGS-84 → 渲染坐标 (服务商归适配层管)
  const path = pts.map(gcj);                    // 全量坐标转换一次, 逐帧只切片
  let N = path.length;                          // 流式追加会变长
  const cum = TrackUtil.cumDistKm(pts);         // 播放中的实时里程
  /* 逐点能耗模型 (滚阻 + 风阻·v², 全程定标到整体 kWh): 快段每公里贵一点,
    停车不走就不耗, 收尾自然落回整体值 —— 曲线与流式追加步在 trip-playback.js */
  const ecum = TripPlayback.energyCurve(pts, cum);
  const vt = TrackAnimation.animTimes(pts, ts);      // 播放节拍: 每点累计行驶秒
  let dur = TripPlayback.animDurMs(N, cum[N - 1]);
  /* 流式节拍锚 (2026-09-25 用户点名「随着轨迹动态加载, 时间的流逝逐渐变
     快, 播放过程中流逝速度要一样」): dur 原先每次 append 按已载入的 N/km
     重算, 播放头推进速率 = 已载行驶秒/dur 随追加一路漂移 (首段短就被 3s
     底数拖慢, 211km 后 300s 封顶又随加载线性加快)。改为开播一次定死:
     汇总头先于首段到达, it.km/it.min 就是全程量 —— dur 冻结在全程档;
     pace = 全程行驶秒/全程播放时长 (每播放毫秒推进的行驶秒) 恒定, 播放头
     位置由 playT×pace 给出绝对行驶秒, 经 animAt 的比例映射换下标, 映射
     上限 mapDur = 已载行驶秒/pace 随 append 延长 —— vt 只在头部之后的
     未来侧生长, 头原地不动, 速率从头到尾一个值。非流式 mapDur 恒等于
     dur (行为不变); 流收尾 (more=false) 帧循环把 dur 校准到真实末点,
     pace 仍不动。 */
  let mapDur = dur;
  let pace = 0;
  if (more) {
    const kmFull = it.km > cum[N - 1] ? it.km : cum[N - 1];
    dur = TripPlayback.animDurMs(N, kmFull);   // 全程里程的档 (点数项仍按已知 N, 里程项占主导)
    const vtFull = it.min > 0 ? it.min * 60    // 全程累计行驶秒 (= Σ 行程时长, ts 同口径)
      : (cum[N - 1] > 0 && kmFull > cum[N - 1] ? vt[N - 1] * kmFull / cum[N - 1]
         : vt[N - 1]);                          // 汇总缺时长: 按里程比推
    pace = vtFull / dur;
    if (pace > 0 && vt[N - 1] > 0) mapDur = vt[N - 1] / pace;
  }
  const { segs, spans, allLines, head, tail } = buildTrackOverlays(pts, it, path);
  let tailColor = spans.length ? spans[0].color : "#3987e5";   // 连线当前色 (跟 hist.color 走)
  /* 合并轨迹的段界与段首时刻 (副标题实时跟播, setSegTitle): 整包缓存重开
     时随 it 到齐; 流式播放先只有首段 ([0] + it.seg_t0s), 后续段 append
     逐段登记。单条行程不启用 (null), apply 里跳过 */
  const segStarts = it.merged && Array.isArray(it.seg_starts) && it.seg_starts.length
    ? it.seg_starts.slice() : (it.merged ? [0] : null);
  const segT0s = it.merged
    ? (Array.isArray(it.seg_t0s) && it.seg_t0s.length ? it.seg_t0s.slice() : [it.start])
    : null;

  /* 播放中: 里程/时长/车速/功耗实时跳动; 收尾停在整体值, 标签换回整体口径 */
  $("#sh-spd-lb").textContent = "车速";
  $("#sh-pw-lb").textContent = "功耗";
  // power 的单位是 kW (TeslaMate positions.power 原生单位, 实测全库
  // -176~+254kW —— 当年按瓦读把它误判成「常年 ~0 的垃圾数据」, 功耗格
  // 从上线起就没亮过; 2026-09-22 动态页功率曲线挂不上牵出来纠正)。
  // 全 ~0 的行程 (车真没报) 不亮格, 不然一直显示 0.0kW 像是坏了
  let hasPower = pts.some(p => Math.abs(p[3] || 0) > 0.5);   // 追加段可能点亮
  $("#sh-cell-pw").hidden = !hasPower;          // 没有可用的功耗数据就不占格子

  const splices = [];   // 已解析的断档路由 [{aIdx, bIdx, route, rcum}] 按 aIdx 升序

  /* ts/it/cum/ecum 挂进会话: 统计页 (trips-sheet-stats) 只读 curSess 拿
     数据 (defer 起的会话预载没完也早已可读), 不进播放循环 —— 流式追加推
     的就是这几个数组, 引用不换, 追加自动可见 */
  const s = {
    pts, ts, it, cum, ecum, N, dur, vt, mapDur, playT: 0, speed: 1, paused: false, seeking: false,
    finished: false, alive: true, begun: false, lastIdx: -1, lastFrac: -1, gapDrawAt: 0,
    /* 历史速度线播放态 (overlays.speedSpans 建): 走到哪截到哪 (~8fps 时间
       节流, drawAt); color 是线尾当前色 (车头连线跟它取色); gaps 是断档
       播放态 (overlays.addGap 登记): 未走到不上图, wire 是懒规划闭包 */
    hist: { spans, done: 0, drawAt: 0,
            color: spans.length ? spans[0].color : "#3987e5" }, gaps: [],
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
      const zt = speedZoom(TripPlayback.windowMeanSpeed(vt, pts, s.playT, mapDur));
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
      const pos = headPos({ splices, path, pts }, idx, frac);   // 断档步沿道路/匀加速走过去
      const va = pts[idx][2] || 0, vb = idx + 1 < N ? (pts[idx + 1][2] || 0) : va;
      const v = va + (vb - va) * frac;         // 车速 = 匀加速的瞬时速度 (τ 线性)
      head.setCenter(pos);
      head.setOptions({ fillColor: TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(v)] });
      tripMap.setCenter(pos, true);            // 视角紧贴头部 (immediately=不排队动画)
      s.lastV = v;                             // 当前车速 (视角基线按钮重锚用)
      if (idxNew) {
        /* 断档登记即入队规划 (addGap), 这里只剩迈过对岸的转正 —— 懒规划的
           提前量按行驶秒算过, 分组把几十小时压进 300s 后 10 行驶秒只剩几十
           毫秒墙钟, 规划永远赶不上车头 (2026-09-22 撤) */
        for (const g of s.gaps) if (!g.settled && idx >= g.bIdx) gapSettle(g);
        histStep(s, idx);                      // 历史速度线推到 idx (回退自清重走)
      } else if (frac > 0 && cum[idx + 1] - cum[idx] >= TrackUtil.MIN_GAP_KM) {
        // 断档步内推进: 蓝实线跟着头部往对岸长 (有道路沿道路), 节流 ~8fps
        if (Date.now() - s.gapDrawAt > 120) {
          s.gapDrawAt = Date.now();
          const g = s.gaps.find(x => x.aIdx <= idx && idx < x.bIdx);
          if (g) gapGrow({ splices, path, pts }, g, idx, frac, pos);
        }
      }
      /* 合并轨迹副标题实时跟播 (2026-09-25 用户点名「时间要实时变, 跟着
         轨迹的运动」): 段序跟段界, 段内时刻 = 段首 t0 + 段首起行驶秒 (ts
         段内是原始时间戳差, 红灯停车都在内, 服务端 merged_track_segments
         直测), 步内按 frac 插值同 setLive 口径 —— 播放/拖进度/重播都过
         apply, 一处接线全覆盖。流式追加期未来段的界已登记 (append 先于
         播放头到), 顺扫取段序即可; 写前与 DOM 现值比对 (setSegTitle) */
      if (segStarts && ts[idx] != null) {
        let k = 0;                           // idx 落进的段序 (段界升序, 顺扫即得)
        for (let j = 1; j < segStarts.length; j++) if (idx >= segStarts[j]) k = j;
        const st = segStarts[k];
        const tb = idx + 1 < N && ts[idx + 1] != null ? ts[idx + 1] : ts[idx];
        setSegTitle(it, k, segT0s[k] || it.start,
                    ts[idx] + (tb - ts[idx]) * frac - ts[st]);
      }
      /* 车头连线 (用户设计): 线尾 (最后画到图的点) → 车头插值位, 每帧两点
         setPath —— 节流窗与步内插值两段「线追不上车头」的缝都由它补上;
         断档步内尾端收到岸边 (蓝实线沿道路长, 不叠一根弦线); 颜色跟轨迹
         最后一段同色 (hist.color, span 推进时更新) */
      const gIn = s.gaps.find(x => x.aIdx <= idx && idx < x.bIdx);
      tail.setPath([path[s.hist.done], gIn ? path[idx] : pos]);
      if (tailColor !== s.hist.color) {
        tailColor = s.hist.color;
        tail.setOptions({ strokeColor: tailColor });
      }
      setLive({ pts, ts, cum, ecum, it, N, more: s.more }, idx, frac);
    },
    seek(frac) {                // 0..1: 拖进度条/外部跳转统一入口, 立即生效
      s.playT = Math.min(Math.max(frac, 0), 1) * dur;
      if (s.more && s.playT > mapDur) s.playT = mapDur;   // 流式: 没下的段拖不进去, 顶到已载末尾
      const p = TrackAnimation.animAt(vt, s.playT, mapDur);   // 滑窗无状态, 跳完即就位
      s.apply(p.idx, p.frac);
    },
    /* 流式追加一段 (见 loadMergedStream): 索引只增不改, 速度线/断档/里程
       全部延伸; 播放头存绝对行驶秒 (pace 开播定死), 追加只在头部之后的
       未来侧延长 vt —— 头原地不动、速率不变, 无需重锚 (原先按已载比例
       重锚且 dur 每段按已载量重算, 速率逐段漂移 = 2026-09-25 用户报的
       「时间越播越快」)。
       gapPairs 是服务端检出的断档对 [[a, b, drive_id], ...] (全量累计下标,
       服务端按已发段偏移过, 直接用); 旧载荷没有则退回客户端检测。
       t0 是该段起始时刻 (副标题跟播的锚点, 段界也在这登记)。 */
    append(segPts, segTs, gapPairs, t0) {
      if (!s.alive || s.finished || !segPts.length) return;
      const startIdx = pts.length;
      if (segStarts) { segStarts.push(startIdx); segT0s.push(t0); }   // 新段起点登记
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
      mapDur = pace > 0 && vt[N - 1] > 0 ? vt[N - 1] / pace : mapDur;   // 映射上限随已载末尾延长
      s.mapDur = mapDur; s.N = N;       // 进度条/seek 读对象快照 (dur 冻结在全程档不动)
      // 新段速度 span + 段内断档; 一律不上图 —— 追加进来的是未来, 走到再亮
      // (用户点名)。服务端断档按下标切 (段内下标 = 全量 - startIdx), 段内
      // 补路服务端已拼好, 显式对里只剩没存档的真洞
      const hasPairs = Array.isArray(gapPairs);
      const segSegs = hasPairs
        ? TripPlayback.sliceAtGaps(segPts,
            gapPairs.map(p => [p[0] - startIdx, p[1] - startIdx]))
        : TrackUtil.splitGaps(segPts);
      for (const seg of segSegs) {
        const fresh = speedSpans(seg, startIdx + segPts.indexOf(seg[0]));
        s.hist.spans.push(...fresh);
        allLines.push(...fresh.map(sp => sp.line));
      }
      if (hasPairs)
        for (const p of gapPairs)
          if (p[0] >= startIdx && p[1] < pts.length && p[1] > p[0])
            addGap({ gcj, it, s, splices, pts, allLines },
                   { pts: [pts[p[0]], pts[p[1]]], did: p[2] }, p[0], p[1]);
      else
        for (const g of TrackUtil.gapsBetween(segSegs))
          addGap({ gcj, it, s, splices, pts, allLines }, g,
                 startIdx + segPts.indexOf(g.pts[0]), startIdx + segPts.indexOf(g.pts[1]));
      // 段间边界 (上一段尾 → 本段头, 停车挪位): 距离阈值同 gapsBetween
      for (const g of TrackUtil.gapsBetween([[pts[startIdx - 1]], segPts]))
        addGap({ gcj, it, s, splices, pts, allLines }, g, startIdx - 1, startIdx);
      // 新段可能带来真实量级的功耗数据 (kW, 见会话头部单位注)
      if (!hasPower && segPts.some(p => Math.abs(p[3] || 0) > 0.5)) {
        hasPower = true;
        $("#sh-cell-pw").hidden = false;
      }
      if (s.waiting) { s.waiting = false; tripMsg(null, false); }
      // 播放头不重锚: 位置是绝对行驶秒 (pace 开播定死), mapDur 延长只放开
      // 上限 —— 头在屏幕上原地不动, 时间流逝速率也原地不变
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
      // 兜底: 断档登记时就该入队了 (addGap), 这里补发漏网的 (防御性, 惯例
      // 上不会再有; 匀速发防高德限流, 见 trips-gap-routing.queueWireGap)
      for (const g of s.gaps) if (g.wire && !g.wired) queueWireGap(g);
      // 定格 = 全量速度线 + 断档虚线: 播放期截短的铺回全量, 撤掉播放态,
      // 全集一次上图 (历史与定格同一批对象, 无跳变), 拉远看全局;
      // 播放期的加粗 (6) 同步收回常轨 4 —— 定格就是打开弹层的默认观感
      for (const sp of s.hist.spans) {
        if (sp.on && sp.drawn < sp.end) sp.line.setPath(sp.full);
        sp.line.setOptions({ strokeWeight: 4 });
      }
      histClear(s);
      tripMap.remove(head);
      tripMap.remove(tail);   // 车头连线只在播放期存在 (定格 = 全量线, 无缝可补)
      tripMap.add(allLines);
      tripMap.setFitView(allLines, false, FIT_AVOID);      // 避让补环宽, 整轨收进可视区
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
      s.playT = 0; s.paused = false; s.lastIdx = -1; s.lastFrac = -1;
      s.waiting = false;
      tripMap.remove(allLines);   // 定格全集撤下: 未来的重新藏起, 走到再亮
      for (const sp of s.hist.spans) sp.line.setOptions({ strokeWeight: 6 });   // 重走再加粗
      histClear(s);               // 保险 (finish 已清过); 历史线从头重走
      head.setCenter(path[0]);
      head.setOptions({ fillColor: TrackUtil.SPEED_COLORS[TrackUtil.speedBucket(pts[0][2] || 0)] });
      tripMap.add(head);
      tail.setPath([path[0], path[0]]);   // 连线跟着重走 (色由 apply 里跟 hist.color 同步)
      tripMap.add(tail);
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
  /* 数据会话即刻挂上 (anim 是播放态, 归 begin): 行驶数据/统计两页读
     curSess 拿数据, 地图预载没完它们也照画 —— 三页各管各的数据 */
  curSess = s;
  if (defer) {
    s.begin = () => {
      if (s.begun || curSess !== s) return;   // 双点 / 晚归 (换行程·关弹层后) 不接
      s.begun = true;
      anim = s;
      startSession(s, { gcj, it, splices, pts, allLines, segs, path, zoom });
    };
  } else {
    anim = s;
    startSession(s, { gcj, it, splices, pts, allLines, segs, path, zoom });
  }
  return s;
}
