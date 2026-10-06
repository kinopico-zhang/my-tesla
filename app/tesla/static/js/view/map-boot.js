// view/map-boot.js — 足迹地图视图 (壳版 4/5): 同步 fpSync 与地图启动 fpBoot
// (首进视图才跑, 由 view/map-filters.js 的 registerView 调)。
// fpSync: 拉全量清单 → 道路层对账本地库 (IndexedDB: rv 算法版不符清库 /
// rn 点数或拟合态 s 不符重下) → 当前筛选的格计数 → 本地已有的先整批画
// (首屏不等网络) → 缺的按 50 条一批流式下载「走过的路」(NDJSON 边下边
// 画, 小补量时地图跟着新路扩大; 加载进度条 2026-09-29 拆 —— 与图例重
// 叠, 边下边画本就增量展示) → 汇总行 (summary 端点的
// 筛选口径, 平移/缩放不动它 —— 2026-09-29 用户点名与充电地图不联动)。
// 2026-09-29 起只画「走过的路」(用户点名「只显示走过的路就行了, 不需要
// 显示每一条轨迹」): 原始轨迹不再下载, 没拟合到的程等 worker 拟合好
// 再出现。换筛选/下拉刷新都走 fpSync (清单现拉, 驾驶员标注也就跟着
// 新鲜); 同步中再触发会排一轮, 不并发。
// 2026-10-02 自动开播提前到格合并后 (用户报「打开行程足迹没有自动播放」):
// 回放兼作加载动画, 路一就绪就播, 不等整版铺线; 本拍起播才让铺层让路
// (收场 rebuild 兜底)。换驾驶员点名重播 (同日点名「任何时候, 切换驾驶员
// 都重播」): 先铺新筛选再从头播; 其余同步在放不护, renderTracks 照旧否决
// 收场重铺 (同日报「筛选后视角不跟新筛选」)。
// 引擎装载收口到 tesla-map-adapter 的 mapLib (高德单服务商, 2026-09-25
// 调用); 旧版 (js/map-boot.js) 的 boot() 改名 fpBoot, 只换画布 id (#fp-map)。
/* global $, diag, PAGE_V, getJSON, mapLib, showError,
          trackParams, renderStats, renderTracks,
          fpLocalOpen, fpVisibleTracks, overlays, scheduleRoadZoom,
          fpPlayAuto, fpPlayRestart, fpViewOn,
          roadsViewportSync,
          fpRoadsSync, roadDownload, roadRebuild, roadsById,
          manifest: writable, manifestIdx: writable, localDb: writable,
          map: writable, mapReady: writable */
/* exported fpSync, fpBoot, manifestIdx, fpPlayArm */
// manifestIdx 只写不读 (道路层在别的文件读); fpPlayArm 只在 map-filters 被调
// —— 都靠 exported 豁免 (no-unused-vars)
"use strict";
let fpSyncing = false, fpAgain = false;   // 同步互斥: 进行中再触发 → 排一轮
let playArm = false;   // 点名重播旗: 换驾驶员置 (fpPlayArm), 下一轮同步消费
function fpPlayArm() { playArm = true; }   // 换驾驶员置旗: 那一轮同步从头重播

async function fpSync() {   // 清单对账 + 增量下载 + 渲染 (所有刷新入口)
  if (!map) return;         // 地图还没起来 (视图没进过/配置缺 Key): 不空转
  if (fpSyncing) { fpAgain = true; return; }
  fpSyncing = true;
  try {
    await fpSyncOnce();
  } catch (e) {   // 数据同步失败只亮错误层, 不炸调用方 (下拉刷新/chip 都裸调)
    diag("sync_fail", { msg: String(e && e.message || e).slice(0, 200) });
    if (e.message !== "未登录") showError(e.message);
  } finally {
    fpSyncing = false;
    if (fpAgain) { fpAgain = false; fpSync(); }   // 期间又触发过: 补一轮
  }
}

async function fpSyncOnce() {
  const replay = playArm; playArm = false;   // 点名重播旗本轮消费 (换驾驶员置的)
  $("#fp-error").hidden = true;
  if (localDb === undefined) localDb = await fpLocalOpen();   // 不可用 → null (内存模式)
  const man = await getJSON("/tesla/map/api/tracks/manifest?_=" + Date.now());
  manifest = man;
  manifestIdx = new Map(man.tracks.map(r => [r.id, r]));
  const roadNeed = await fpRoadsSync(man);   // 道路层对账 (本地就绪的先建索引)
  await roadRebuild();                       // 当前筛选的格计数 (渲染分桶的底)
  const statsP = getJSON("/tesla/map/api/summary" + trackParams()).then(renderStats);
  // 换驾驶员点名重播 (2026-10-02 用户点名「任何时候, 切换驾驶员都重播」):
  // 先整版铺新筛选 (在放则 renderTracks 入口的否决收旧场), 铺完新清单从头
  // 播 —— 正常层与筛选始终一致, 收场瞬时亮回。没得播 (该驾驶员没走过的
  // 路/引擎没起/人已切走) 退回常路 (空筛选的报错在下面)
  if (replay && mapReady && fpViewOn && roadsById.size && fpVisibleTracks().length) {
    await renderTracks(fpVisibleTracks());
    fpPlayRestart();
  } else {
    const autoOn = fpPlayAuto();   // 路一就绪就开播, 不等铺正常层 (2026-10-02 用户报
                                   // 「打开没有自动播放」: 铺近两千条线好几秒, 干等
                                   // 窗口里像坏了 —— 回放本就兼作加载动画; 起不来
                                   // (如引擎未就绪) 收尾再补一脚)
    // 本拍刚自动开播 → 铺层让路 (收场走回放的 rebuild 兜底)。其余同步 (下拉
    // 刷新等) 在放不护: renderTracks 入口的否决照旧收场重铺。本地已有先画,
    // 首屏不等网络
    if (roadsById.size && !autoOn) await renderTracks(fpVisibleTracks());
  }
  if (roadNeed.length) await roadDownload(roadNeed);   // 缺的流式下载: 边下边建格边画
  await statsP;
  if (!fpVisibleTracks().length) showError("该筛选下还没有走过的路");
  diag("fp_synced", { rows: manifest.tracks.length, roads: roadsById.size,
                      need: roadNeed.length });
  fpPlayAuto();   // 同步收尾再试一脚: 早场被引擎未就绪挡下时这里起 (已播过空转)
}

async function fpBoot() {
  try {
    await mapLib.ready();   // 配置 + 引擎脚本 (高德, 要 Key)
    diag("config_ok", { engine: mapLib.version(), v: PAGE_V });
    // 灰阶底图 (2026-09-30 用户点名「把地图搞灰一点, 不要有彩色, 地铁的彩色
    // 也不显示」): 足迹地图的彩色只留给走过的路的次数热力色, 底图一律无彩
    // —— 地铁线/绿地/水系全灰 (雅士灰)。别的地图 (充电地图/实时/弹层小图)
    // 照旧跟设置页的全局样式走。
    map = mapLib.createMap("fp-map", { zoom: 11, center: [114.05, 22.55],
                                       style: "amap://styles/grey" });
    map.on("complete", () => {
      mapReady = true; diag("map_complete");
      /* 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染 (首次打开
         一两秒地名才出现的原因), setFeatures 同值重设 = 只触发重渲染
         (引擎异常时守卫自动跳过, 不致命) */
      const nudge = () => { if (map && map.getFeatures) map.setFeatures(map.getFeatures()); };
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
        showError("地图引擎初始化未完成…已自动上报诊断, 请反馈给管理员");
      }
    }, 15000);
    await fpSync();
    diag("boot_done", { tracks: overlays.length });
  } catch (e) {
    diag("boot_error", { msg: String(e && e.message || e).slice(0, 300) });
    if (e.noKey) { $("#fp-keyhint").hidden = false; return; }   // 高德缺 Key: 专属引导卡
    if (e.message !== "未登录") showError(e.message);   // 引擎装载失败 (数据错误 fpSync 自己兜)
  }
}
