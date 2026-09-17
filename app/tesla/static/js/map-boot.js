// map-boot.js — 足迹地图页 (4/5): 数据刷新 (轨迹+汇总并发拉取) 与地图启动
// boot: 高德配置加载/事件触发诊断/矢量地名补渲染/手势拦截。
// 由 map.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 map.html
// 里的顺序加载, 跨模块引用走全局); 底座在 map-page.js, 轨迹绘制在
// map-tracks-render.js, 细化在 map-tracks-refine.js, 筛选 UI 与收尾在
// map-filters.js (末尾 boot() 调用在彼处)。
/* global $, diag, PAGE_V, getJSON, loadAMap, showLoading, showError, trackParams,
          renderStats, renderTracks, probeRefine, scheduleProbe,
          scheduleRefine, map: writable, mapReady: writable, overlays */
/* exported refresh, boot */
"use strict";
async function refresh(first) {
  $("#error").hidden = true;
  showLoading(true, first ? "正在加载轨迹…" : "正在更新…");
  try {
    const p = trackParams();
    const [t, s] = await Promise.all([
      getJSON("/tesla/map/api/tracks" + p),
      getJSON("/tesla/map/api/summary" + p),
    ]);
    renderStats(s);
    await renderTracks(t.tracks);   // 分块绘制, 结束时自行收起加载层
    if (!t.tracks.length) showError("该时间段没有行驶轨迹");
  } catch (e) {
    showError(e.message);
    showLoading(false);
  }
}

async function boot() {
  try {
    // 加时间戳穿透浏览器缓存 (旧响应可能缓存了 amap_key: null)
    const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
    diag("config_ok", { has_key: !!cfg.amap_key, has_scode: !!cfg.security_code, v: PAGE_V });
    if (!cfg.amap_key) {
      $("#keyhint").hidden = false;
      return;
    }
    await loadAMap(cfg.amap_key, cfg.security_code);
    diag("amap_script_loaded", { ver: (window.AMap && AMap.version) || "?" });
    map = new AMap.Map("map", {
      mapStyle: cfg.style || "amap://styles/dark", zoom: 11, center: [114.05, 22.55],
    });
    map.on("complete", () => {
      mapReady = true; diag("map_complete");
      /* 矢量样式数据异步加载: 首帧不画地名, 到货后补几拍重渲染 (首次打开
         一两秒地名才出现的原因), setFeatures 同值重设 = 只触发重渲染 */
      const nudge = () => { if (map.getFeatures) map.setFeatures(map.getFeatures()); };
      setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);
    });
    // iOS Safari 会把双指缩放劫持成整页缩放: 拦截私有 gesture 事件, 手势只给高德
    for (const ev of ["gesturestart", "gesturechange"]) {
      document.getElementById("map").addEventListener(ev, e => e.preventDefault());
    }
    // 事件触发诊断 (每类前 N 次上报) + 手势中预判亮提示
    const evtN = {};
    const trackEvt = (name, val, times = 1) => {
      evtN[name] = (evtN[name] || 0) + 1;
      if (evtN[name] <= times) diag("evt_" + name, val || {});
    };
    map.on("zoomstart", () => { trackEvt("zoomstart"); scheduleProbe(); });
    map.on("zoomchange", () => { trackEvt("zoomchange", { z: Math.round(map.getZoom() * 10) / 10 }, 10); scheduleProbe(); });
    map.on("mapmove", () => { trackEvt("mapmove"); scheduleProbe(); });
    map.on("dragging", () => { trackEvt("dragging"); scheduleProbe(); });
    map.on("zoomend", () => { trackEvt("zoomend", { z: Math.round(map.getZoom() * 10) / 10 }, 15); probeRefine(); scheduleRefine(); });
    map.on("moveend", () => { trackEvt("moveend"); probeRefine(); scheduleRefine(); });
    diag("map_created");
    setTimeout(() => {
      if (!mapReady) {
        diag("map_incomplete_15s", { amap: !!window.AMap });
        showLoading(true, "地图引擎初始化未完成…已自动上报诊断, 请反馈给管理员");
      }
    }, 15000);
    await refresh(true);
    diag("boot_done", { tracks: overlays.length });
  } catch (e) {
    diag("boot_error", { msg: String(e && e.message || e).slice(0, 300) });
    if (e.message !== "未登录") showError(e.message);
  }
}
