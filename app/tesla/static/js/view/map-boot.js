// view/map-boot.js — 足迹地图视图 (壳版 4/5): 同步 fpSync 与地图启动 fpBoot
// (首进视图才跑, 由 view/map-filters.js 的 registerView 调)。
// fpSync: 拉全量清单 → 道路层对账本地库 (IndexedDB: rv 算法版不符清库 /
// rn 点数或拟合态 s 不符重下) → 当前筛选的格计数 → 本地已有的先整批画
// (首屏不等网络) → 缺的按 50 条一批流式下载「走过的路」(NDJSON 边下边
// 画, 小补量时地图跟着新路扩大, 加载层进度条) → 汇总行 (summary 端点的
// 筛选口径, 平移/缩放不动它 —— 2026-09-29 用户点名与充电地图不联动)。
// 2026-09-29 起只画「走过的路」(用户点名「只显示走过的路就行了, 不需要
// 显示每一条轨迹」): 原始轨迹不再下载, 没拟合到的程等 worker 拟合好
// 再出现。换筛选/下拉刷新都走 fpSync (清单现拉, 驾驶员标注也就跟着
// 新鲜); 同步中再触发会排一轮, 不并发。
// 引擎装载收口到 tesla-map-adapter 的 mapLib (高德单服务商, 2026-09-25
// 调用); 旧版 (js/map-boot.js) 的 boot() 改名 fpBoot, 只换画布 id (#fp-map)。
/* global $, diag, PAGE_V, getJSON, mapLib, showLoading, showError,
          trackParams, renderStats, renderTracks,
          fpLocalOpen, fpVisibleTracks, overlays, scheduleRoadZoom,
          roadsViewportSync,
          fpRoadsSync, roadDownload, roadRebuild, roadsById,
          manifest: writable, manifestIdx: writable, localDb: writable,
          map: writable, mapReady: writable */
/* exported fpSync, fpBoot, manifestIdx */
// manifestIdx 只写不读 (道路层在别的文件读), exported 豁免 (no-unused-vars)
"use strict";
let fpSyncing = false, fpAgain = false;   // 同步互斥: 进行中再触发 → 排一轮

async function fpSync() {   // 清单对账 + 增量下载 + 渲染 (所有刷新入口)
  if (!map) return;         // 地图还没起来 (视图没进过/配置缺 Key): 不空转
  if (fpSyncing) { fpAgain = true; return; }
  fpSyncing = true;
  try {
    await fpSyncOnce();
  } catch (e) {   // 数据同步失败只亮错误层, 不炸调用方 (下拉刷新/chip 都裸调)
    diag("sync_fail", { msg: String(e && e.message || e).slice(0, 200) });
    if (e.message !== "未登录") showError(e.message);
    showLoading(false);
  } finally {
    fpSyncing = false;
    if (fpAgain) { fpAgain = false; fpSync(); }   // 期间又触发过: 补一轮
  }
}

async function fpSyncOnce() {
  $("#fp-error").hidden = true;
  showLoading(true, "正在同步走过的路…");
  if (localDb === undefined) localDb = await fpLocalOpen();   // 不可用 → null (内存模式)
  const man = await getJSON("/tesla/map/api/tracks/manifest?_=" + Date.now());
  manifest = man;
  manifestIdx = new Map(man.tracks.map(r => [r.id, r]));
  const roadNeed = await fpRoadsSync(man);   // 道路层对账 (本地就绪的先建索引)
  await roadRebuild();                       // 当前筛选的格计数 (渲染分桶的底)
  const statsP = getJSON("/tesla/map/api/summary" + trackParams()).then(renderStats);
  if (roadsById.size) await renderTracks(fpVisibleTracks());   // 本地已有先画, 首屏不等网络
  if (roadNeed.length) await roadDownload(roadNeed);   // 缺的流式下载: 边下边建格边画
  await statsP;
  if (!fpVisibleTracks().length) showError("该筛选下还没有走过的路");
  showLoading(false);
  diag("fp_synced", { rows: manifest.tracks.length, roads: roadsById.size,
                      need: roadNeed.length });
}

async function fpBoot() {
  try {
    await mapLib.ready();   // 配置 + 引擎脚本 (高德, 要 Key)
    diag("config_ok", { engine: mapLib.version(), v: PAGE_V });
    map = mapLib.createMap("fp-map", { zoom: 11, center: [114.05, 22.55] });
    map.on("complete", () => {
      mapReady = true; diag("map_complete");
      /* 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染 (首次打开
         一两秒地名才出现的原因), setFeatures 同值重设 = 只触发重渲染
         (引擎异常时守卫自动跳过, 不致命) */
      const nudge = () => { if (map.getFeatures) map.setFeatures(map.getFeatures()); };
      setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);
    });
    // iOS Safari 会把双指缩放劫持成整页缩放: 拦截私有 gesture 事件, 手势只给地图
    for (const ev of ["gesturestart", "gesturechange"]) {
      document.getElementById("fp-map").addEventListener(ev, e => e.preventDefault());
    }
    // 事件触发诊断 (每类前 N 次上报); 缩放收尾道路跨档换画 + 汇总重算
    const evtN = {};
    const trackEvt = (name, val, times = 1) => {
      evtN[name] = (evtN[name] || 0) + 1;
      if (evtN[name] <= times) diag("evt_" + name, val || {});
    };
    map.on("zoomstart", () => trackEvt("zoomstart"));
    map.on("zoomchange", () => trackEvt("zoomchange", { z: Math.round(map.getZoom() * 10) / 10 }, 10));
    map.on("mapmove", () => trackEvt("mapmove"));
    map.on("dragging", () => trackEvt("dragging"));
    // 缩放收尾: 道路跨档换画 + 视野增删 (高倍只画视野内);
    // 平移收尾: 视野增删 (高倍摘视野外的线、补新进视野的)。
    // 汇总三数不跟视野走 (2026-09-29 用户点名「与充电地图逻辑不一样,
    // 不用联动」): summary 端点的筛选口径就是终态, 平移/缩放不动它
    map.on("zoomend", () => {
      trackEvt("zoomend", { z: Math.round(map.getZoom() * 10) / 10 }, 15);
      scheduleRoadZoom(); roadsViewportSync();
    });
    map.on("moveend", () => { trackEvt("moveend"); roadsViewportSync(); });
    diag("map_created");
    setTimeout(() => {
      if (!mapReady) {
        diag("map_incomplete_15s", { engine: mapLib.version() });
        showLoading(true, "地图引擎初始化未完成…已自动上报诊断, 请反馈给管理员");
      }
    }, 15000);
    await fpSync();
    diag("boot_done", { tracks: overlays.length });
  } catch (e) {
    diag("boot_error", { msg: String(e && e.message || e).slice(0, 300) });
    if (e.noKey) { $("#fp-keyhint").hidden = false; return; }   // 高德缺 Key: 专属引导卡
    if (e.message !== "未登录") showError(e.message);   // 引擎装载失败 (数据错误 fpSync 自己兜)
    showLoading(false);
  }
}
