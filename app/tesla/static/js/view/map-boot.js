// view/map-boot.js — 足迹地图视图 (壳版 4/5): 同步 fpSync 与地图启动 fpBoot
// (首进视图才跑, 由 view/map-filters.js 的 registerView 调)。
// fpSync: 拉全量清单 → 对账浏览器本地库 (IndexedDB, 点数不符重下/多余
// 删掉/格式版本不符清库) → 本地已有的先整批画 (首屏不等网络) → 缺的按
// 50 条一批流式下载 (NDJSON 边下边画, 地图跟着新轨迹扩大, 加载层进度条)
// → 汇总行。换筛选/下拉刷新/抽屉刷新都走 fpSync (清单现拉, 驾驶员标注
// 也就跟着新鲜); 同步中再触发会排一轮, 不并发。
// 引擎装载收口到 tesla-map-adapter 的 mapLib (服务商可切, 高德/OSM 同一套
// 调用); 旧版 (js/map-boot.js) 的 boot() 改名 fpBoot, 只换画布 id (#fp-map)。
/* global $, diag, PAGE_V, FP_FMT_V, getJSON, mapLib, showLoading, showError,
          showProgress, trackParams, renderStats, renderTracks,
          appendIfVisible, scheduleRefine, fpLocalOpen, fpLocalAll, fpLocalPut,
          fpLocalDelete, fpLocalClear, fpVisibleTracks, overlays,
          manifest: writable, manifestIdx: writable, allById: writable,
          localDb: writable, map: writable, mapReady: writable */
/* exported fpSync, fpBoot */
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
  showLoading(true, "正在同步轨迹…");
  if (localDb === undefined) localDb = await fpLocalOpen();   // 不可用 → null (内存模式)
  const man = await getJSON("/tesla/map/api/tracks/manifest?_=" + Date.now());
  let stored = new Map();
  if (man.v !== FP_FMT_V) {          // 轨迹格式变了: 本地库整体作废重下
    diag("fp_fmt_v", { v: man.v, mine: FP_FMT_V });
    await fpLocalClear(localDb);
  } else {
    stored = await fpLocalAll(localDb);
  }
  manifest = man;
  manifestIdx = new Map(man.tracks.map(r => [r.id, r]));
  // 对账: 清单里没有的删, 点数不符的也重下 (轨迹本体被改过/半截写入)
  const keep = new Map(), drop = [];
  for (const [id, s] of stored) {
    const r = manifestIdx.get(id);
    if (r && s.pts && s.pts.length === r.n * 2) keep.set(id, s);
    else drop.push(id);
  }
  if (drop.length) fpLocalDelete(localDb, drop);
  allById = keep;
  const need = man.tracks.filter(r => !keep.has(r.id));
  const statsP = getJSON("/tesla/map/api/summary" + trackParams()).then(renderStats);
  if (keep.size) await renderTracks(fpVisibleTracks());   // 本地已有先画, 首屏不等网络
  if (need.length) await fpDownload(need);                // 缺的流式下载: 边下边画
  await statsP;
  if (!fpVisibleTracks().length) showError("该时间段没有行驶轨迹");
  showLoading(false);
  diag("fp_synced", { rows: manifest.tracks.length, have: allById.size, need: need.length });
}

async function fpDownload(need) {   // 分批流式下载: 一条一条画 + 进度条 + 视野跟随
  const total = need.length;
  showLoading(true, "正在下载轨迹 0 / " + total + "…");
  let done = 0, lastFit = 0;
  const CHUNK = 50;    // 与服务端单次上限 (200) 留余量, 一批一请求
  for (let i = 0; i < need.length; i += CHUNK) {
    const resp = await fetch("/tesla/map/api/tracks/stream?ids=" +
      need.slice(i, i + CHUNK).map(r => r.id).join(","));
    if (!resp.ok || !resp.body) throw new Error("轨迹下载失败 (" + resp.status + ")");
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {   // NDJSON: 一行一条全精度轨迹, 逐行解析, 不等整包
      const st = await reader.read();
      if (st.done) break;
      buf += dec.decode(st.value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        if (!line) continue;
        const t = JSON.parse(line);
        allById.set(t.id, t);
        fpLocalPut(localDb, t);       // 落本地库 (不可用时自动跳过)
        appendIfVisible(t);           // 下载一条画一条 (当前筛选可见才画)
        done++;
      }
      showProgress(done, total);
      const now = Date.now();
      if (now - lastFit > 500 && overlays.length) {   // 视野跟着新轨迹扩大 (节流免动画)
        lastFit = now;
        map.setFitView(overlays, true, [40, 40, 40, 40]);
      }
    }
  }
  map.setFitView(overlays, false, [40, 40, 40, 40]);   // 收尾终态视野
  scheduleRefine();                                    // 已在 13 级以上则立即细化
}

async function fpBoot() {
  try {
    await mapLib.ready();   // 配置 + 引擎脚本 (高德要 Key, OSM 免 Key 开箱即用)
    diag("config_ok", { engine: mapLib.version(), v: PAGE_V });
    map = mapLib.createMap("fp-map", { zoom: 11, center: [114.05, 22.55] });
    map.on("complete", () => {
      mapReady = true; diag("map_complete");
      /* 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染 (首次打开
         一两秒地名才出现的原因), setFeatures 同值重设 = 只触发重渲染
         (OSM 栅格没有这层, 垫片不实现 getFeatures, 守卫自动跳过) */
      const nudge = () => { if (map.getFeatures) map.setFeatures(map.getFeatures()); };
      setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);
    });
    // iOS Safari 会把双指缩放劫持成整页缩放: 拦截私有 gesture 事件, 手势只给地图
    for (const ev of ["gesturestart", "gesturechange"]) {
      document.getElementById("fp-map").addEventListener(ev, e => e.preventDefault());
    }
    // 事件触发诊断 (每类前 N 次上报); 缩放/平移稳定后本地细化
    const evtN = {};
    const trackEvt = (name, val, times = 1) => {
      evtN[name] = (evtN[name] || 0) + 1;
      if (evtN[name] <= times) diag("evt_" + name, val || {});
    };
    map.on("zoomstart", () => trackEvt("zoomstart"));
    map.on("zoomchange", () => trackEvt("zoomchange", { z: Math.round(map.getZoom() * 10) / 10 }, 10));
    map.on("mapmove", () => trackEvt("mapmove"));
    map.on("dragging", () => trackEvt("dragging"));
    map.on("zoomend", () => { trackEvt("zoomend", { z: Math.round(map.getZoom() * 10) / 10 }, 15); scheduleRefine(); });
    map.on("moveend", () => { trackEvt("moveend"); scheduleRefine(); });
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
