// tesla-map-adapter.js — 地图引擎层: 高德单服务商 (2026-09-25 用户点名
// 「地图只保留高德」, 更早的多服务商切换整链退役 —— 官方源/国内镜像/
// 本地瓦片垫片全拆, 退役棘轮见 test_map_adapter)。四个地图视图 (足迹/
// 充电地图/实时/轨迹弹层) 统一经 mapLib 建图建层, 直通原生 AMap 对象;
// 坐标口径也归这管: 高德渲染要 GCJ-02, 视图统一喂 WGS-84 点、经
// mapLib.gcj() 转渲染坐标。高德驾车规划 (断档补路 + 高速费估价) 同在这层。
// WebGL 保留缓冲补丁 (导出视频要 drawImage 地图画布, 上下文属性建时即定)
// 挪到这: 页面加载即装, 任何视图先后起地图都赶在画布上下文创建之前。
/* global GCJ02, getJSON */
/* exported mapLib */
"use strict";

const mapLib = (() => {
  let styleV = "amap://styles/dark";        // 高德样式 (config 下发, 设置页可换)
  let readyP = null;                        // 单飞: 配置 + 引擎脚本只装一次

  function injectScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("地图脚本加载失败, 请检查网络"));
      document.head.appendChild(s);
    });
  }

  /* ---------- 引擎启动: 拉配置 → 装高德脚本 ---------- */
  function ready() {
    if (readyP) return readyP;
    readyP = (async () => {
      // 加时间戳穿透浏览器缓存 (旧响应可能缓存了 amap_key: null)
      const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
      if (!cfg.amap_key) {
        const e = new Error("未配置高德地图 Key (设置 → 地图设置)");
        e.noKey = true;
        throw e;
      }
      if (cfg.style) styleV = cfg.style;
      if (cfg.security_code) window._AMapSecurityConfig = { securityJsCode: cfg.security_code };
      // 引擎已装过就不重装 (免刷新换样式/安全码的前提; Key 换了仍要整页刷新才换得净)
      if (window.AMap) return;
      // HeatMap 插件随主脚本带上 (充电地图要用; 其他视图多载一个插件无感)
      await injectScript("https://webapi.amap.com/maps?v=2.0&plugin=AMap.HeatMap&key="
        + encodeURIComponent(cfg.amap_key));
    })();
    readyP.catch(() => { readyP = null; });   // 失败可重试
    return readyP;
  }
  function reset() { readyP = null; }         // 设置页换样式/安全码后调, 下次 ready 重读配置

  /* ---------- WebGL 保留绘图缓冲: 导出视频要 drawImage 地图画布拿内容,
     高德默认建的上下文没开 preserveDrawingBuffer —— 合成器取走画面后缓冲
     即清空, drawImage 只能拿到黑帧 (dbg90 实测)。上下文属性建时即定, 页面
     加载就装 (任何地图实例创建之前)。 ---------- */
  (function patchGLKeepBuffer() {
    const orig = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, attrs) {
      if (type === "webgl" || type === "webgl2" || type === "experimental-webgl")
        attrs = Object.assign({ antialias: true }, attrs, { preserveDrawingBuffer: true });
      return orig.call(this, type, attrs);
    };
  })();

  /* ================= 高德直通工厂 (视图不碰原生对象, 换实现只动这) ====== */

  function createMap(el, opts) {
    return new AMap.Map(el, { mapStyle: styleV, zoom: opts.zoom, center: opts.center });
  }
  const polyline = o => new AMap.Polyline(o);
  const circleMarker = o => new AMap.CircleMarker(o);
  const marker = o => new AMap.Marker(o);
  const pixel = (x, y) => new AMap.Pixel(x, y);
  const heatMap = (m, o) => new AMap.HeatMap(m, o);

  /* 渲染坐标: 高德要 GCJ-02 (视图侧统一喂 WGS-84) */
  const gcj = p => GCJ02.wgs84ToGcj02(p[0], p[1]);

  /* 高德驾车规划 (断档补路 + 高速费估价); 不可用/失败 → null, 调用方降级
     (断档虚线直连占位, 高速费 chip 藏掉不误导) */
  function drivingSearch(aGcj, bGcj, wps) {
    return new Promise(resolve => {
      if (!window.AMap) return resolve(null);
      AMap.plugin("AMap.Driving", () => {
        try {
          const policy = AMap.DrivingPolicy && AMap.DrivingPolicy.LEAST_DISTANCE != null
            ? AMap.DrivingPolicy.LEAST_DISTANCE : 2;
          const dr = new AMap.Driving({ policy });
          const cb = (status, result) => {
            if (status !== "complete" || !result.routes || !result.routes.length)
              return resolve(null);
            const r = result.routes[0];
            const route = [];
            for (const st of r.steps) for (const p of st.path) route.push([p.lng, p.lat]);
            if (route.length < 2) return resolve(null);
            const roads = {};   // 同名收费路段合并 (按路名)
            for (const st of r.steps)
              if (st.tolls > 0 && st.toll_road)
                roads[st.toll_road] = (roads[st.toll_road] || 0) + st.tolls;
            resolve({
              route,
              tolls: r.tolls || 0,
              toll_km: Math.round((r.tolls_distance || 0) / 100) / 10,
              distance: r.distance || 0,
              roads: Object.keys(roads).map(rd => ({ road: rd, tolls: roads[rd] })),
            });
          };
          if (wps && wps.length) dr.search(aGcj, bGcj, wps, cb);
          else dr.search(aGcj, bGcj, cb);
        } catch { resolve(null); }
      });
    });
  }

  function version() { return (window.AMap && AMap.version) || "?"; }

  const api = {
    ready, reset,
    style: () => styleV,
    version,
    createMap, polyline, circleMarker, marker, pixel, heatMap,
    gcj, drivingSearch,
  };
  return api;
})();
