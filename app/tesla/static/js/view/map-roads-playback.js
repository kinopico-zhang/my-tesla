// view/map-roads-playback.js — 足迹地图 (壳版 6/5): 时间回放条 (2026-10-01
// 用户点名重做「去掉放大缩小按钮, 地图下方改成播放按钮加进度条, 可以播放
// 暂停, 调整进度。播放的时候, 视角实时变化, 要框住所有路径, 并且视角尽可
// 能大」)。状态机: fpPlaying = 回放态 (正常渲染整链看它让路), playPaused =
// 走带态; [▶/‖][进度条] 一条 (同日再点名: 挪到地图卡外下方, 控件
// 照行程详情播放条一家的 .playbar/.pb-btn/.pb-seek 样式) —— ▶ 点一下开演,
// 再点暂停/续播, 放完停在尾再点从头重放。✕ 钮 2026-10-02 用户点名退役
// (「不需要x按钮」), 退场 = 放完自动收/切视图/切后台。任何正常重渲
// 染 (换筛选/同步) 都是对回放的否决: renderTracks 入口反调 fpPlayExit(false)。
// 2026-10-02 两处: (1) 回放的色走累计口径 —— 同一条路越走越热 (越来越黄,
// 累计在 map-roads-render 的 playStat 一族); (2) 进视图自动开播一回: 首次
// 同步收尾/回视图且数据就绪即 fpPlayAuto (用户点名「打开行程地图没有自动
// 播放, 要点击一下才行。自动播放的时候可以用来加载数据」—— 回放窗口兼
// 作加载动画), 一场页面生命周期只此一回; 切走视图/切后台 (iOS 冻结前页
// 先转 hidden) 整场收掉, 解冻回来是静止热力图; 走带遇大帧间隔 (漏网冻
// 结) 停在原地等人点。
// 同日再点名「任何时候, 切换驾驶员都重播」: map-filters 置旗 (fpPlayArm) →
// map-boot 消费 —— 同步先铺新筛选 (入口否决收旧场) 再 fpPlayRestart 从头播。
// 同日性能批 (用户报「足迹地图很卡」): 钮/浮标/滑杆/两格改节流刷屏
// (PLAY_UI_MS/PLAY_STAT_MS —— 60fps 全量刷是白烧), DOM 引用进点时取一次;
// 图标同值不重写 (innerHTML 重挂会整棵重建 SVG, 120ms 一闪也是频闪的一路)。
// 同日两修开局镜头: 先报「刚开始播放视角不对, 很多轨迹在地图外面」——
// 撑框即跳 (并集戳出上次框 15% 跨度立刻 setBounds immediately) 追上走带
// 高峰; 后报「启动播放的时候频闪, 感觉视角打架」—— 跳变帧级多级、又与
// 定时器动画互相打断, 整体退役改指数补间 (playCam 每帧向目标走 12%),
// 大步目标化成连续小步, 收敛且目标没动不重发。
// 正常层藏而不拆 (2026-10-01 用户报「播放完之后怎么又加载一遍」—— 收场整
// 版重画 1986 条线太重): 进场只把正常折线 hide(), 收场 show() 瞬时亮回;
// 进场时整版渲染在途 (tracksRendering) 的快照不完整, 收场退回整版重建兜底。
// 2026-10-04 兜底也撤明画 (用户报「播放完又播放了一遍」: 早开播把正常层跳
// 过后, 首开收场必走兜底, 整版渐进重画 + 收尾 setFitView 看着就是第二遍回
// 放): 兜底改暗铺 —— 回放终帧顶屏占位 (终色与终态同口径), 正常层分块藏
// 着铺, 铺完一帧换装 (renderTracks 的 hidden 模式), 重画全程不可见; 换装对
// 账要读 renderGen, 它只写不读的 exported 豁免随之退役。
// 顶部两格联动 (同日用户点名「播放的时候, 上面的里程和时间也联动」): 已画
// 程的 km/min 实时累计写格, 收场还原服务端汇总口径 (fpRestoreStats)。
// 镜头跟框: 已画程的并集 bbox (t.gbb 本就是 GCJ 渲染坐标) 每程并一点,
// playCam 指数补间框住全部已走的路 (= 框住它的最大倍率); 拖进度整段分帧
// 重铺 (seekGen 作废在途批)。
/* global $, diag, mapLib, map, mapReady, fpVisibleTracks, makeRoadLines,
          roadLegend, renderTracks, fpPlaying, overlays, fpViewOn,
          roadPlayReset, roadPlayMerge, roadPlayBump, roadPlayEnd,
          writeStats, fpRestoreStats, tracksRendering,
          fpPlaying: writable, renderGen: writable */
/* exported fpPlayExit, fpPlayAuto, fpPlayRestart */
// fpPlayExit 给 renderTracks 出口钩; fpPlayAuto 给 map-boot 同步收尾 /
// map-filters 回视图; fpPlayRestart 给 map-boot 换驾驶员点名重播
"use strict";
const PLAY_TOTAL_MS = 36000;    // 全量回放的目标时长 (程少自动放慢)
const PLAY_MAX_PER_FRAME = 6;   // 播放单帧最多补的程数
const PLAY_SEEK_CHUNK = 80;     // 拖进度整段重铺: 单帧最多铺的程数
const PLAY_CAM_EASE = 0.12;     // 跟框指数补间: 每帧向目标走的份额 (连续小步)
const PLAY_UI_MS = 120;         // 钮/浮标/滑杆刷屏节流 (60fps 全量刷是白烧)
const PLAY_STAT_MS = 240;       // 顶部两格联动节流 (innerHTML 解析不便宜)
// 播放钮图标 (行程播放条同款 SVG, trips-playback-bar 同源): 空闲态的 ▶ 由
// app.html 内联初值给, JS 只管换 播放中 ↔ 暂停
const FP_ICON_PLAY = '<svg viewBox="0 0 24 24" width="13" height="13"><path d="M7.5 4.6v14.8L20 12z" fill="currentColor"/></svg>';
const FP_ICON_PAUSE = '<svg viewBox="0 0 24 24" width="13" height="13"><path d="M6.6 4.8h4.1v14.4H6.6zM13.3 4.8h4.1v14.4h-4.1z" fill="currentColor"/></svg>';
let playList = [];              // 回放清单快照 (fpVisibleTracks, 日期升序)
let playIdx = 0;                // 已画到第几程
let playLines = [];             // 回放层折线 (收场撤)
let playBBox = null;            // 已画程并集 bbox [x0,y0,x1,y1] (GCJ 渲染坐标)
let playRaf = 0;                // 播放走带 rAF (0 = 停)
let playSeekRaf = 0;            // 拖进度重铺 rAF (非 0 = 重铺占线)
let playStepMs = 60;            // 每程占的毫秒 (按清单长度摊 36 秒)
let playT0 = 0;                 // 走带起点 (续播按当前进度回拨)
let playPaused = true;          // 走带态 (进回放态默认停在 0)
let seekGen = 0;                // 重铺代号 (新一次拖动作废在途批)
let seekDragging = false;       // 滑杆拖动中 (UI 不抢滑杆位置/标签)
let playCam = null;             // 镜头框 (渲染坐标): 跟框补间的自家态
let playLastStep = 0;           // 走带上帧时刻 (>1s 间隔 = 冻结/后台解冻)
let playAutoDone = false;       // 本场页面生命周期已自动开播过 (只此一回)
let playKm = 0, playMin = 0;    // 联动累计: 已画程的里程/时长 (顶部两格)
let playLayerOk = false;        // 进场时正常层完整 (否则收场整版重建兜底)
let playUiAt = 0, playStatAt = 0;   // 上次刷屏时刻 (节流)
const playBtn = $("#fp-play"), playDateChip = $("#fp-play-date"),
      playSeekBar = $("#fp-seek");

function fpPlayReveal(t) {      // 画一程 + 并进跟框 bbox / 联动累计 / 热力累计
  const up = roadPlayMerge(t);  // 先并累计: 本程自己的线起画就是并后的档
  const lines = makeRoadLines(t, true);   // live 口径: 色读走到此刻为止
  if (lines.length) { map.add(lines); playLines.push(...lines); }
  roadPlayBump(up);             // 早先画的线升档重染 (同一格又热了一档)
  playKm += t.km || 0;
  playMin += t.min || 0;
  if (t.gbb)
    playBBox = playBBox
      ? [Math.min(playBBox[0], t.gbb[0]), Math.min(playBBox[1], t.gbb[1]),
         Math.max(playBBox[2], t.gbb[2]), Math.max(playBBox[3], t.gbb[3])]
      : t.gbb.slice();
}

function fpPlayFit() {           // 镜头框住已走的全部路 (= 框住它的最大倍率)
  if (!map || !playBBox) return;
  const [x0, y0, x1, y1] = playBBox;
  // 四周留 2% 呼吸 (窄框保底 0.003°)。t.gbb 本就是渲染坐标 (gbbOf 已转过
  // GCJ-02), 直接进框 —— 再转一次等于几百米的双重偏移
  const mx = Math.max((x1 - x0) * 0.02, 0.003), my = Math.max((y1 - y0) * 0.02, 0.003);
  const tgt = [x0 - mx, y0 - my, x1 + mx, y1 + my];
  if (playCam) {
    // 指数补间: 每帧向目标走 12%, 大步目标化成连续小步 —— 撑框即跳的帧级
    // 多级跳变 + 定时器动画被跳变中途打断 (用户报「启动播放的时候频闪,
    // 感觉视角打架」) 一并退役。收敛 (差 < 1e-5° ≈ 1m) 且目标没动就不重发,
    // 引擎重渲染不白烧
    let live = false;
    for (let i = 0; i < 4; i++) {
      const d = (tgt[i] - playCam[i]) * PLAY_CAM_EASE;
      if (Math.abs(d) > 1e-5) live = true;
      playCam[i] += d;
    }
    if (!live) return;
  } else playCam = tgt.slice();   // 开场/拖进度落位: 一步到位 (人点过的要立刻有响应)
  map.setBounds(mapLib.bounds(playCam), true);   // 即时到补间位 (自带动画会和补间打架)
}

function fpPlayUI(force) {       // 钮/浮标/滑杆 一并刷 (走带每帧调, 节流)
  const now = performance.now();
  if (!force && now - playUiAt < PLAY_UI_MS) return;
  playUiAt = now;
  const n = playList.length;
  // 图标同值不重写: innerHTML 重挂会整棵重建 SVG, 120ms 一闪也是频闪的一路
  // (innerHTML 读回会被序列化改写, 拿 dataset 记账才比得准)
  const ic = playPaused ? "play" : "pause";
  if (playBtn.dataset.ic !== ic) {
    playBtn.dataset.ic = ic;
    playBtn.innerHTML = playPaused ? FP_ICON_PLAY : FP_ICON_PAUSE;   // 行程播放条同款
    playBtn.setAttribute("aria-label", playPaused ? "按时间顺序回放走过的路" : "暂停回放");
  }
  const chip = playDateChip;
  chip.hidden = !fpPlaying;
  chip.textContent = n
    ? ((playIdx > 0 && playList[playIdx - 1].date)
         ? playList[playIdx - 1].date + " · " : "") + playIdx + " / " + n
    : "";
  if (seekDragging) return;     // 拖动中: 滑杆位置与标签 input 预览说了算
  const bar = playSeekBar;
  const frac = n ? playIdx / n : 0;
  bar.value = String(Math.round(frac * 1000));
  bar.style.setProperty("--pb", (frac * 100).toFixed(1) + "%");   // 与 .pb-seek 同变量
}

function fpPlayStats(force) {    // 联动: 顶部两格随已画程累计 (与汇总同一排版)
  const now = performance.now();
  if (!force && now - playStatAt < PLAY_STAT_MS) return;
  playStatAt = now;
  writeStats({ distance_km: playKm, duration_min: playMin });
}

function fpPlayEnter() {        // 进回放态: 正常层只藏不拆 (收场瞬时亮回),
  fpPlaying = true;             // 图例让位浮标, 摆在 0
  playPaused = true;
  renderGen++;                  // 先作废在途渲染/换画 (同步块内无帧可插队)
  // 渲染在途或正常层还没铺 (早开播) 都算不完整 → 收场退回整版重建
  playLayerOk = !tracksRendering && overlays.length > 0;
  if (overlays.length) for (const o of overlays) o.hide();
  playList = fpVisibleTracks();
  playIdx = 0;
  playBBox = playCam = null;     // 镜头从头框起
  playKm = 0; playMin = 0;
  roadPlayReset();              // 热力累计清零: 色从冷起, 越走越热
  playStepMs = Math.min(220, Math.max(16, PLAY_TOTAL_MS / Math.max(1, playList.length)));
  roadLegend(false);
  fpPlayUI(true);
  fpPlayStats(true);
  diag("fp_play_enter", { n: playList.length, ms: Math.round(playStepMs) });
}

function fpPlayStep() {         // 走带: 按时间目标补程 (单帧封顶防卡)
  playRaf = 0;
  if (!fpPlaying || !map) return;
  const now = performance.now();
  if (now - playLastStep > 1000) {   // 大帧间隔 = 冻结/后台解冻且漏了
    fpPlayPause();                   // visibilitychange: 停在原地等人点, 不快进
    return;
  }
  playLastStep = now;
  const target = Math.min(playList.length,
                          1 + Math.floor((now - playT0) / playStepMs));
  let drawn = 0;
  while (playIdx < target && drawn < PLAY_MAX_PER_FRAME) {
    fpPlayReveal(playList[playIdx++]);
    drawn++;
  }
  fpPlayUI();
  fpPlayStats();
  fpPlayFit();
  if (playIdx >= playList.length) { fpPlayExit(true); return; }   // 放完: 瞬时亮回
  playRaf = requestAnimationFrame(fpPlayStep);
}

function fpPlayResume() {       // 续播: 走带起点按当前进度回拨
  if (playSeekRaf || !fpPlaying || !map) return;   // 重铺占线: 这一拍不接
  playPaused = false;
  if (playIdx >= playList.length) { fpPlayExit(true); return; }
  const now = performance.now();
  playT0 = now - playIdx * playStepMs;
  playLastStep = now;           // 走带钟基线重置 (暂停多久都不算大帧间隔)
  if (!playRaf) playRaf = requestAnimationFrame(fpPlayStep);
  fpPlayUI(true);
}

function fpPlayPause() {
  playPaused = true;
  if (playRaf) { cancelAnimationFrame(playRaf); playRaf = 0; }
  fpPlayUI(true);
}

function fpPlaySeek(frac, autoplay) {   // 拖进度: 整段分帧重铺到 want 程为止
  const want = Math.max(0, Math.min(playList.length,
                                    Math.round(frac * playList.length)));
  seekGen++;
  if (playRaf) { cancelAnimationFrame(playRaf); playRaf = 0; }
  if (map && playLines.length) map.remove(playLines);
  playLines = [];
  playBBox = playCam = null;
  playKm = 0; playMin = 0;
  playIdx = 0;
  roadPlayReset();              // 重铺从零累计: 色跟着重铺进度一起冷起
  const gen = seekGen;
  (function step() {
    if (gen !== seekGen || !fpPlaying || !map) return;
    const end = Math.min(playIdx + PLAY_SEEK_CHUNK, want);
    while (playIdx < end) fpPlayReveal(playList[playIdx++]);
    fpPlayUI();
    fpPlayStats();
    fpPlayFit();
    if (playIdx < want) playSeekRaf = requestAnimationFrame(step);
    else { playSeekRaf = 0; if (autoplay && playIdx < playList.length) fpPlayResume(); }
  })();
}

function fpPlayExit(restore) {  // 收场: 撤回放层; restore = 放完/✕ → 回正常层
  const n = playIdx;
  fpPlaying = false;
  playPaused = true;
  seekGen++;
  roadPlayEnd();                // 热力累计与重染索引撤 (索引攥着线对象, 不清会漏)
  playLastStep = 0;             // 走带钟归零 (下场从 enter 重新起)
  if (playRaf) { cancelAnimationFrame(playRaf); playRaf = 0; }
  if (playSeekRaf) { cancelAnimationFrame(playSeekRaf); playSeekRaf = 0; }
  // 回放层撤线分两路 (2026-10-04 修「播放完又播放了一遍」): 正常层完整
  // (playLayerOk)/否决路照旧现在撤; 兜底路 (正常层没铺过 —— 早开播的首开
  // 常态) 把终帧押后撤, 暗铺期间顶屏占位, 铺完一帧换装
  const hold = restore && map && mapReady && !playLayerOk && playLines.length > 0;
  if (!hold && map && playLines.length) map.remove(playLines);
  const stale = hold ? playLines : [];
  playLines = [];
  playList = [];
  playBBox = playCam = null;
  playKm = 0; playMin = 0;
  seekDragging = false;
  fpPlayUI(true);               // 钮回 ▶, 浮标收起, 滑杆归 0
  fpRestoreStats();             // 顶部两格还原服务端汇总口径
  if (restore && map && mapReady) {
    if (playLayerOk) {
      for (const o of overlays) o.show();   // 瞬时亮回 (不再整版重画一遍)
      roadLegend(true);
    } else {
      // 兜底重铺改暗铺: 原来收场整版重画, 分块渐进冒线 + 收尾 setFitView ——
      // 跟回放一个视觉语言, 用户看着就是又播了一遍 (10-01「播完又加载一
      // 遍」同病, 当时靠藏而不拆修的正是层已在的收场; 10-02 打开即开播后
      // 首开的正常层根本没铺, 收场必走这兜底, 老症状换个形态回来了)。
      // 回放终色与终态同口径 (makeRoadLines), 占位与换装零色差; 被更新的
      // 渲染顶掉 (换筛选等) 就只撤占位 —— 接管者自会重画
      renderTracks(fpVisibleTracks(), true).then(gen => {
        if (map && stale.length) map.remove(stale);
        if (gen === renderGen && overlays.length) {   // 没被顶掉才换装
          for (const o of overlays) o.show();
          roadLegend(true);
        }
      });
    }
  }
  diag("fp_play_exit", { shown: n, restore: !!restore,
                         layer: restore ? (playLayerOk ? "show" : "swap") : "veto" });
}

function fpPlayAuto() {        // 自动开播一回: 首次同步收尾/回视图且数据就绪
  // (map-boot 的 fpSyncOnce 尾 + map-filters 的 show 各调一次; 数据没就绪
  //  不烧名额 —— playAutoDone 只在真播上才置)。视图不在前台/已在放/没得放
  //  都不起 —— 人看着地图才值得开演。返真 = 本拍真开播了 (map-boot 拿去
  //  决定铺层让不让路: 只让路本拍起播的, 早就在放的不护 —— 换筛选踩进来
  //  要收播重铺, 见 map-boot)
  if (playAutoDone || fpPlaying || !fpViewOn || !map || !mapReady) return false;
  if (!fpVisibleTracks().length) return false;
  playAutoDone = true;
  fpPlayEnter();
  fpPlayResume();
  diag("fp_play_auto", { n: playList.length });
  return true;
}

function fpPlayRestart() {      // 换驾驶员点名重播: 新清单从头播 (map-boot 调;
  // 前置条件它包了: 数据已在本地 + 引擎已起, 且新筛选已整版铺好 —— 收场
  // 瞬时亮回, 不会亮回旧驾驶员的线)
  playAutoDone = true;          // 真播了: 自动开播名额一并花掉 (切走再回不自播)
  fpPlayEnter();
  fpPlayResume();
  diag("fp_play_restart", { n: playList.length });
}

/* ---------- 接线 ---------- */
$("#fp-play").addEventListener("click", () => {
  if (!map || !mapReady) return;
  if (!fpPlaying) {
    if (!fpVisibleTracks().length) return;   // 空筛选没得放
    fpPlayEnter();                           // (enter 再取一次快照, 同拍一致)
    fpPlayResume();
  } else if (playPaused) {
    if (playIdx >= playList.length) fpPlaySeek(0, true);   // 放完再点: 从头重放
    else fpPlayResume();
  } else fpPlayPause();
});
$("#fp-seek").addEventListener("input", () => {   // 拖动中: 走带先停, 只预览标签
  seekDragging = true;   // 先占位: 空闲首拖要进回放态, enter 的 UI 刷别抢滑杆
  if (!fpPlaying && map && mapReady && fpVisibleTracks().length) fpPlayEnter();
  if (!playList.length) return;
  if (playRaf) fpPlayPause();
  const bar = playSeekBar;
  const frac = +bar.value / 1000;
  bar.style.setProperty("--pb", (frac * 100).toFixed(1) + "%");   // 与 .pb-seek 同变量
  const t = playList[Math.min(playList.length - 1, Math.floor(frac * playList.length))];
  if (t) {
    const chip = playDateChip;
    chip.hidden = false;
    chip.textContent = t.date || "";
  }
});
$("#fp-seek").addEventListener("change", () => {  // 松手: 提交进度 (整段重铺)
  seekDragging = false;
  if (!fpPlaying) {   // 空闲态直接点滑杆 (input 没进过回放态的兜底)
    if (!map || !mapReady || !fpVisibleTracks().length) return;
    fpPlayEnter();
  }
  fpPlaySeek(+$("#fp-seek").value / 1000, !playPaused);
});
addEventListener("maplib:swap", () => { if (fpPlaying) fpPlayExit(false); });
// 切后台/锁屏 (iOS 冻结前页先转 hidden): 整场收掉 —— 解冻回来不会自己接着
// 播 (2026-10-02 用户报「打开足迹地图就自动开始播放」: 冻结时播放在途, 解冻
// rAF 续跑, 看着就像自己开播了)。走带钟的大间隔停播是它漏网时的二保
document.addEventListener("visibilitychange", () => {
  if (document.hidden && fpPlaying) fpPlayExit(true);
});
