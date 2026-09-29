// trips-playback-loop.js — 播放 (6/13): 播放循环 —— 实时里程/电耗/车速/
// 功耗 (setLive) 与收尾整体口径 (setOfficial), 控制条复位, 帧循环 (seek/
// 暂停/流式等待) 与开播编排 startSession (断档首查 + 保活 + 起跑)。
// 由 trips.js 按域拆出 (结构化重构: 提取的函数体逐字节未动; setLive/
// setOfficial 接 env 上下文 (调用点现取闭包值, 流式追加后不读旧值),
// frameLoop 的 dur/vt 改读 s.dur/s.mapDur/s.vt (流式追加会延长 mapDur,
// 参数快照会过期; 2026-09-25 起流式 dur 冻结在全程档, mapDur 是播放头
// 绝对行驶秒 → playT 的映射上限, 见 trips-playback-session 的节拍锚);
// 经典脚本按 trips.html 里的顺序加载, 跨模块引用走全局), playTrack 在
// trips-playback-session.js。
/* global $, num, fmtDur, fmtDurLive, TripPlayback, TrackUtil, TrackAnimation,
   mergedSub, tripMsg, pbSeek, pbToggle, pbSpeed, ICON_PAUSE, anim, animRaf: writable,
   tripMap, zoomEaseStart, holdScreenAwake, addGap */
/* exported animRaf, setLive, setOfficial, playbarPending, resetPlaybar,
   frameLoop, startSession */
"use strict";
const setLive = (env, idx, frac) => {   // frac: 该步内进度 (断档中也在走)
  const { pts, ts, cum, ecum, it, N, more } = env;
  const last = idx + 1 >= N;
  const stepKm = last ? 0 : cum[idx + 1] - cum[idx];
  const va = pts[idx][2] || 0, vb = last ? va : (pts[idx + 1][2] || 0);
  const v = va + (vb - va) * frac;            // 车速两端线性插值 (断档推算模型)
  $("#sh-km").innerHTML = '<span class="n">' + (cum[idx] + stepKm * frac).toFixed(1) + "</span><small>km</small>";
  /* 总电耗/平均电耗按能耗模型随轨迹累积 (快段每公里贵, 停车不耗),
     收尾 setOfficial 定格回整体值 */
  if (it.kwh != null && ecum[N - 1] > 0) {
    const eNow = TripPlayback.fracValue(ecum, idx, frac);   // 末步夹紧
    /* 流式追加期 (分组/多选合并, 2026-09-23 用户实报十一云南游五位数):
       定标分母 ecum[N-1] 只盖已载段, 而 it.kwh 是全组总电耗 —— 直接除
       会把首段的实时平均电耗顶到数万 Wh/km。按已载里程占官方总里程先
       折算; 全载完 (more=false) 或整包缓存比例恒 1, 收尾落回整体值 */
    const scale = more && it.km > cum[N - 1] ? cum[N - 1] / it.km : 1;
    const kwhNow = it.kwh * scale * eNow / ecum[N - 1];
    /* 恒带一位小数 (2026-09-25 用户点名「总电耗这个动态数字一直加一个.0,
       这样就不会抖动了」): num() 会把 12.0 剪成 12, 播放中数值在 12↔12.3
       间跳, 定宽盒里居中的数字串宽一变数字就左右挪; toFixed(1) 恒宽不抖 */
    $("#sh-kwh").innerHTML = '<span class="n">' + kwhNow.toFixed(1) + "</span><small>kWh</small>";
    const kmNow = cum[idx] + stepKm * frac;
    if (it.wh_per_km != null && kmNow > 0)
      $("#sh-avg").innerHTML = '<span class="n">' + num(kwhNow / kmNow * 1000, 0) + "</span><small>Wh/km</small>";
  }
  const ta = ts[idx] || 0, tb = last ? ta : (ts[idx + 1] || ta);
  $("#sh-dur").innerHTML = '<span class="n">' + fmtDurLive(ta + (tb - ta) * frac) + "</span>";
  $("#sh-spd").innerHTML = '<span class="n">' + Math.round(v) + "</span><small>km/h</small>";
  const pa = pts[idx][3], pb = last ? pa : pts[idx + 1][3];   // kW: 正=放电 负=回收
  const pw = pa == null && pb == null ? null :
    pa == null ? pb : pb == null ? pa : pa + (pb - pa) * frac;
  $("#sh-pw").innerHTML = '<span class="n">' + (pw == null ? "—" :
    pw.toFixed(1)) + "</span><small>kW</small>";   // 同款恒一位 (防抖), 不再剪 .0
};

const setOfficial = env => {
  const { it, pts, ts, hasPower } = env;
  $("#sh-km").innerHTML = '<span class="n">' + num(it.km) + "</span><small>km</small>";
  /* 恒一位与 setLive/开弹层 (fillSheetHeader) 同宽, 定格不跳格 */
  if (it.kwh != null)
    $("#sh-kwh").innerHTML = '<span class="n">' + Number(it.kwh).toFixed(1) + "</span><small>kWh</small>";
  if (it.wh_per_km != null)
    $("#sh-avg").innerHTML = '<span class="n">' + num(it.wh_per_km, 0) + "</span><small>Wh/km</small>";
  $("#sh-dur").innerHTML = '<span class="n">' + fmtDur(it.min) + "</span>";
  $("#sh-spd-lb").textContent = "最高车速";
  $("#sh-spd").innerHTML = '<span class="n">' + (it.speed_max != null ? it.speed_max : "—") + "</span><small>km/h</small>";
  $("#sh-pw-lb").textContent = "平均功耗";
  const mp = hasPower ? TrackUtil.meanPowerKw(pts, ts) : null;
  $("#sh-pw").innerHTML = '<span class="n">' + (mp == null ? "—" :
    mp.toFixed(1)) + "</span><small>kW</small>";
  /* 副标题的动态段序 (播放中「第 x/N 段行程 · 该段日期」) 收尾定格换回
     静态整组口径 —— 定格是全局观感, 停在「第 N 段」半路收场反而突兀 */
  if (it.merged) $("#sh-time").textContent = mergedSub(it);
};

/* 待播复位: 进度归零 + 暂停钮 (起播是自动的, 图标落在"将播/正在播"态)。
   弹层一开就摆出来 (用户点名: 加载地图时控制按钮别跟着等) —— 也顺手
   清掉上一条的残留 (播完的重播钮/拖过的进度), 不闪旧画面 */
function playbarPending() {
  pbSeek.value = 0;
  pbSeek.style.setProperty("--pb", "0%");
  pbToggle.innerHTML = ICON_PAUSE;
  pbToggle.setAttribute("aria-label", "暂停");
}
function resetPlaybar() {
  playbarPending();
  $("#playbar").hidden = false;
  $("#pb-zoom").hidden = false;   // 视角基线 ± 挪去地图右下角了, 显隐仍随播放条
}

function frameLoop(s) {
  let lastNow = 0;
  (function frame(now) {
    if (anim !== s || s.finished) return;    // 会话已停止/替换, 或已收尾
    // 帧间隔钳制 [0, 100ms]: Chrome 的 rAF 时间戳可能比上一帧还早 (见
    // trackutil.animAt 注释); 切后台回来会有超大间隔 —— 都不该让播放头跳跃
    const dt = Math.max(0, Math.min(now - lastNow, 100));
    lastNow = now;
    /* 流式收尾校准: 开播的全程行驶秒取自汇总头的 Σ行程时长 (it.min), 与
       真实 vt 末点差着红灯压缩/断档推算几个点 —— more 关掉那帧把 dur 对
       到真实末点 (mapDur), 进度条 100% 与真实收尾重合; pace 不动, 速率
       不变 (2026-09-25 用户点名「时间的流逝速度一样, 不要变」)。非流式
       mapDur 恒等于 dur, 这里天然空转 */
    if (!s.more && s.mapDur !== s.dur) s.dur = s.mapDur;
    const cap = s.more ? Math.min(s.dur, s.mapDur) : s.dur;   // 流式顶在已载末尾
    if (!s.paused && !s.seeking)
      s.playT = Math.min(s.playT + dt * s.speed, cap);
    if (s.waiting && s.playT < cap) {        // 拖回已载区间: 撤「等待后续轨迹」
      s.waiting = false;
      tripMsg(null, false);
    }
    const p = TrackAnimation.animAt(s.vt, s.playT, s.mapDur);   // 按行驶秒 → 步 + 步内进度
    s.apply(p.idx, p.frac);
    s.zoomTick();                           // 随速变焦缓动 (暂停也推进)
    pbSeek.value = Math.round(s.playT / s.dur * 1000);   // 分母: 全程时长 (流式=真实全程进度)
    pbSeek.style.setProperty("--pb", (s.playT / s.dur * 100).toFixed(1) + "%");
    if (s.playT >= cap) {
      if (!s.more) { s.finish(); return; }   // 播完自动收尾 (控制条留着重播)
      if (!s.waiting) {                      // 流式还没下完: 停在末尾等追加
        s.waiting = true;
        tripMsg("等待后续轨迹…", true);
      }
    }
    animRaf = requestAnimationFrame(frame);
  })(performance.now());
}

function startSession(s, env) {
  const { gcj, it, splices, pts, allLines, segs, path, zoom } = env;
  /* 服务端检出过断档 (it.gaps) → 直接按下标登记断档对 (did 随对归档回传,
     登记即入队规划), 段起点处的跨段跳变 (停车挪位, 服务端逐段检测看不见)
     按 gapsBetween 同一道距离阈值补登记 —— 与 buildTrackOverlays 的切段口径
     一致, 不会重不会漏。旧载荷退回客户端检测 (splitGaps + gapsBetween)。 */
  if (Array.isArray(it.gaps)) {
    const gapCtx = { gcj, it, s, splices, pts, allLines };
    for (const p of it.gaps)
      if (p[0] >= 0 && p[1] < pts.length && p[1] > p[0])
        addGap(gapCtx, { pts: [pts[p[0]], pts[p[1]]], did: p[2] }, p[0], p[1]);
    for (const st of it.seg_starts || [])
      if (st > 0 && st < pts.length
          && TrackUtil.ptDistKm(pts[st - 1], pts[st]) >= TrackUtil.MIN_GAP_KM)
        addGap(gapCtx, { pts: [pts[st - 1], pts[st]] }, st - 1, st);
  } else {
    const gapCtx = { gcj, it, s, splices, pts, allLines };   // addGap 上下文 (append 里的调用点同款)
    for (const g of TrackUtil.gapsBetween(segs))
      addGap(gapCtx, g, pts.indexOf(g.pts[0]), pts.indexOf(g.pts[1]));
  }
  resetPlaybar();
  pbSpeed.textContent = "1×";
  tripMap.setCenter(path[0], true);            // 中心与档位都直接到位 (开场不缓动)
  zoomEaseStart(zoom);
  holdScreenAwake();                           // 开播保活 (禁止熄屏)
  frameLoop(s);
}
