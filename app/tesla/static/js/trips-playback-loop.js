// trips-playback-loop.js — 播放 (6/13): 播放循环 —— 实时里程/电耗/车速/
// 功耗 (setLive) 与收尾整体口径 (setOfficial), 控制条复位, 帧循环 (seek/
// 暂停/流式等待) 与开播编排 startSession (断档首查 + 保活 + 起跑)。
// 由 trips.js 按域拆出 (结构化重构: 提取的函数体逐字节未动; setLive/
// setOfficial 接 env 上下文 (调用点现取闭包值, 流式追加后不读旧值),
// frameLoop 的 dur/vt 改读 s.dur/s.vt (追加会重算时长, 参数快照会过期);
// 经典脚本按 trips.html 里的顺序加载, 跨模块引用走全局), playTrack 在
// trips-playback-session.js。
/* global $, num, fmtDur, fmtDurLive, TripPlayback, TrackUtil, TrackAnimation,
   tripMsg, pbSeek, pbToggle, pbSpeed, ICON_PAUSE, anim, animRaf: writable,
   tripMap, zoomEaseStart, holdScreenAwake, addGap */
/* exported animRaf, setLive, setOfficial, resetPlaybar, frameLoop, startSession */
"use strict";
const setLive = (env, idx, frac) => {   // frac: 该步内进度 (断档中也在走)
  const { pts, ts, cum, ecum, it, N } = env;
  const last = idx + 1 >= N;
  const stepKm = last ? 0 : cum[idx + 1] - cum[idx];
  const va = pts[idx][2] || 0, vb = last ? va : (pts[idx + 1][2] || 0);
  const v = va + (vb - va) * frac;            // 车速两端线性插值 (断档推算模型)
  $("#sh-km").innerHTML = '<span class="n">' + (cum[idx] + stepKm * frac).toFixed(1) + "</span><small>km</small>";
  /* 总电耗/平均电耗按能耗模型随轨迹累积 (快段每公里贵, 停车不耗),
     收尾 setOfficial 定格回整体值 */
  if (it.kwh != null && ecum[N - 1] > 0) {
    const eNow = TripPlayback.fracValue(ecum, idx, frac);   // 末步夹紧
    const kwhNow = it.kwh * eNow / ecum[N - 1];
    $("#sh-kwh").innerHTML = '<span class="n">' + num(kwhNow) + "</span><small>kWh</small>";
    const kmNow = cum[idx] + stepKm * frac;
    if (it.wh_per_km != null && kmNow > 0)
      $("#sh-avg").innerHTML = '<span class="n">' + num(kwhNow / kmNow * 1000, 0) + "</span><small>Wh/km</small>";
  }
  const ta = ts[idx] || 0, tb = last ? ta : (ts[idx + 1] || ta);
  $("#sh-dur").innerHTML = '<span class="n">' + fmtDurLive(ta + (tb - ta) * frac) + "</span>";
  $("#sh-spd").innerHTML = '<span class="n">' + Math.round(v) + "</span><small>km/h</small>";
  const pa = pts[idx][3], pb = last ? pa : pts[idx + 1][3];   // W: 正=放电 负=回收
  const pw = pa == null && pb == null ? null :
    pa == null ? pb : pb == null ? pa : pa + (pb - pa) * frac;
  $("#sh-pw").innerHTML = '<span class="n">' + (pw == null ? "—" :
    (pw / 1000).toFixed(1).replace(/\.0$/, "")) + "</span><small>kW</small>";
};

const setOfficial = env => {
  const { it, pts, ts, hasPower } = env;
  $("#sh-km").innerHTML = '<span class="n">' + num(it.km) + "</span><small>km</small>";
  if (it.kwh != null) $("#sh-kwh").innerHTML = '<span class="n">' + num(it.kwh) + "</span><small>kWh</small>";
  if (it.wh_per_km != null)
    $("#sh-avg").innerHTML = '<span class="n">' + num(it.wh_per_km, 0) + "</span><small>Wh/km</small>";
  $("#sh-dur").innerHTML = '<span class="n">' + fmtDur(it.min) + "</span>";
  $("#sh-spd-lb").textContent = "最高车速";
  $("#sh-spd").innerHTML = '<span class="n">' + (it.speed_max != null ? it.speed_max : "—") + "</span><small>km/h</small>";
  $("#sh-pw-lb").textContent = "平均功耗";
  const mp = hasPower ? TrackUtil.meanPowerW(pts, ts) : null;
  $("#sh-pw").innerHTML = '<span class="n">' + (mp == null ? "—" :
    (mp / 1000).toFixed(1).replace(/\.0$/, "")) + "</span><small>kW</small>";
};

function resetPlaybar() {
  pbSeek.value = 0;
  pbSeek.style.setProperty("--pb", "0%");
  pbToggle.innerHTML = ICON_PAUSE;
  pbToggle.setAttribute("aria-label", "暂停");
  $("#playbar").hidden = false;
}

function frameLoop(s) {
  let lastNow = 0;
  (function frame(now) {
    if (anim !== s || s.finished) return;    // 会话已停止/替换, 或已收尾
    // 帧间隔钳制 [0, 100ms]: Chrome 的 rAF 时间戳可能比上一帧还早 (见
    // trackutil.animAt 注释); 切后台回来会有超大间隔 —— 都不该让播放头跳跃
    const dt = Math.max(0, Math.min(now - lastNow, 100));
    lastNow = now;
    if (!s.paused && !s.seeking)
      s.playT = Math.min(s.playT + dt * s.speed, s.dur);
    const p = TrackAnimation.animAt(s.vt, s.playT, s.dur);   // 按行驶秒 → 步 + 步内进度
    s.apply(p.idx, p.frac);
    s.zoomTick();                           // 随速变焦缓动 (暂停也推进)
    pbSeek.value = Math.round(s.playT / s.dur * 1000);
    pbSeek.style.setProperty("--pb", (s.playT / s.dur * 100).toFixed(1) + "%");
    if (s.playT >= s.dur) {
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
  const gapCtx = { gcj, it, s, splices, pts, allLines };   // addGap 上下文 (append 里的调用点同款)
  for (const g of TrackUtil.gapsBetween(segs))
    addGap(gapCtx, g, pts.indexOf(g.pts[0]), pts.indexOf(g.pts[1]));
  resetPlaybar();
  pbSpeed.textContent = "1×";
  tripMap.setCenter(path[0], true);            // 中心与档位都直接到位 (开场不缓动)
  zoomEaseStart(zoom);
  holdScreenAwake();                           // 开播保活 (禁止熄屏)
  frameLoop(s);
}
