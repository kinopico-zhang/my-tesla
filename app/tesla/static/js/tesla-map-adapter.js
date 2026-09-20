// tesla-map-adapter.js — 地图引擎适配层: 高德 / OpenStreetMap 双服务商。
// 服务商在设置页切 (存自有库, /tesla/map/api/config 下发), 默认高德。四个
// 地图视图 (足迹/充电地图/实时/轨迹弹层) 统一经 mapLib 建图建层: 高德路径
// 零开销直通原生 AMap 对象 (行为与单服务商时代逐字节一致); OSM 路径用
// vendor/ 本地自带的 Leaflet 1.9.4 包一层「说高德方言」的垫片 —— 视图代码
// 不懂服务商, 只会一套 AMap 式调用 (setFitView/setZoomAndCenter/setPath/
// setDataSet/...)。坐标口径也归这管: 高德渲染要 GCJ-02, OSM 用原始 WGS-84,
// 视图统一喂 WGS-84 点、经 mapLib.gcj() 转渲染坐标。
// 高德路径规划 (断档补路 + 高速费估价) 没有免费 OSM 等价物: OSM 下降级为
// null —— 断档保持直线虚线占位, 高速费不估 (chip 藏掉, 不误导)。
// WebGL 保留缓冲补丁 (导出视频要 drawImage 地图画布, 上下文属性建时即定)
// 挪到这: 页面加载即装, 任何视图先后起地图都赶在画布上下文创建之前。
/* global GCJ02, getJSON, L */
/* exported mapLib */
"use strict";

const mapLib = (() => {
  let provider = "amap";                    // amap | osm (ready() 后才准)
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

  /* ---------- 引擎启动: 拉配置 → 按服务商装脚本 ---------- */
  function ready() {
    if (readyP) return readyP;
    readyP = (async () => {
      // 加时间戳穿透浏览器缓存 (旧响应可能缓存了 amap_key: null)
      const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
      provider = cfg.provider === "osm" ? "osm" : "amap";
      if (provider === "amap") {
        if (!cfg.amap_key) {
          const e = new Error("未配置高德地图 Key (设置 → 地图设置, 或改用 OpenStreetMap)");
          e.noKey = true;
          throw e;
        }
        if (cfg.style) styleV = cfg.style;
        if (cfg.security_code) window._AMapSecurityConfig = { securityJsCode: cfg.security_code };
        // HeatMap 插件随主脚本带上 (充电地图要用; 其他视图多载一个插件无感)
        await injectScript("https://webapi.amap.com/maps?v=2.0&plugin=AMap.HeatMap&key="
          + encodeURIComponent(cfg.amap_key));
      } else {
        if (window.L) return;
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = "/tesla/static/vendor/leaflet.css";
        document.head.appendChild(link);
        await injectScript("/tesla/static/vendor/leaflet.js");
        await injectScript("/tesla/static/vendor/leaflet-heat.js");   // 热力 (充电地图)
      }
    })();
    readyP.catch(() => { readyP = null; });   // 失败可重试
    return readyP;
  }
  function reset() { readyP = null; }         // 设置页换服务商后调, 下次 ready 重读配置

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

  /* ================= OSM (Leaflet) 垫片: 说高德方言 ================= */

  // 瓦片: Carto 家的 OSM 数据深色底图 (免 Key, 与 App 深色风格一致);
  // crossOrigin 给视频导出的画布合成留路 (drawImage 跨源图会污染画布)
  const OSM_TILES = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png";

  // 高德 zIndex (1..120) → 专属 pane (叠在默认 overlay 层之上, 序与高德一致;
  // 热力画布在默认 overlay 层, 任何矢量线都盖它之上, 挑选圈不被热力糊脸)
  const PANES = [1, 2, 50, 80, 90, 99, 100, 120];
  const paneName = z => "mlz" + z;

  const toLL = p => [p[1], p[0]];            // [lng, lat] → Leaflet [lat, lng]
  const manyToLL = pts => pts.map(toLL);
  const px2 = (x, y) => ({ getX: () => x, getY: () => y });   // 高德 Pixel 形状

  // 高德描边选项 → Leaflet 样式 (strokeStyle/dasharray 合成 dashArray)
  function styleOpts(o) {
    const s = {};
    if (o.strokeColor != null) s.color = o.strokeColor;
    if (o.strokeOpacity != null) s.opacity = o.strokeOpacity;
    if (o.strokeWeight != null) s.weight = o.strokeWeight;
    if (o.strokeStyle === "dashed")
      s.dashArray = (o.strokeDasharray || [10, 10]).join(",");
    if (o.fillColor != null) s.fillColor = o.fillColor;
    if (o.fillOpacity != null) s.fillOpacity = o.fillOpacity;
    return s;
  }

  class LPoly {   // AMap.Polyline 垫片
    constructor(o) {
      this._ll = L.polyline(manyToLL(o.path || []), Object.assign(
        { lineJoin: o.lineJoin, lineCap: o.lineCap, pane: paneName(o.zIndex || 0) },
        styleOpts(o)));
    }
    setPath(pts) { this._ll.setLatLngs(manyToLL(pts)); }
    setOptions(o) { this._ll.setStyle(styleOpts(o)); }
    on(ev, fn) { this._ll.on(ev, () => fn()); }   // 点击回调不读事件对象 (现有用法)
    getBounds() { return this._ll.getBounds(); }
  }

  class LCircle {   // AMap.CircleMarker 垫片 (bubble 语义 = 点击穿给地图)
    constructor(o) {
      this._ll = L.circleMarker(toLL(o.center), Object.assign(
        { radius: o.radius, pane: paneName(o.zIndex || 0), interactive: false },
        styleOpts(o)));
    }
    setCenter(p) { this._ll.setLatLng(toLL(p)); }
    setOptions(o) { this._ll.setStyle(styleOpts(o)); }
    getBounds() { return this._ll.getBounds(); }
  }

  class LMark {   // AMap.Marker 垫片 (offset 像素锚 → divIcon iconAnchor)
    constructor(o) {
      const off = o.offset || px2(0, 0);
      this._ll = L.marker(toLL(o.position), {
        icon: L.divIcon({ className: "ml-marker", html: o.content,
                          iconSize: null, iconAnchor: [-off.getX(), -off.getY()] }),
        zIndexOffset: o.zIndex || 0, interactive: false,
      });
    }
    setPosition(p) { this._ll.setLatLng(toLL(p)); }
  }

  class LMap {   // AMap.Map 垫片
    constructor(el, opts) {
      const c = (opts && opts.center) || [114.05, 22.55];
      this._m = L.map(el, {
        center: toLL(c), zoom: (opts && opts.zoom) != null ? opts.zoom : 11,
        zoomControl: false, zoomSnap: 0, preferCanvas: true,   // 分数级缩放 + 画布渲染 (视频导出要 drawImage)
      });
      L.tileLayer(OSM_TILES, { maxZoom: 19, crossOrigin: true,
        attribution: "© OpenStreetMap · © CARTO" }).addTo(this._m);
      for (const z of PANES) {
        this._m.createPane(paneName(z));
        this._m.getPane(paneName(z)).style.zIndex = 400 + z;
      }
      this._group = L.layerGroup().addTo(this._m);   // 全部覆盖物走它 (clearMap 用)
    }
    on(ev, fn) {
      const name = { complete: "load", zoomchange: "zoom", mapmove: "move", dragging: "drag" }[ev] || ev;
      this._m.on(name, e => {
        if (ev !== "click") return fn(e);
        const pt = this._m.latLngToContainerPoint(e.latlng);   // 高德事件形状 (充电地图就近取点用)
        fn({ pixel: px2(pt.x, pt.y), lnglat: { lng: e.latlng.lng, lat: e.latlng.lat } });
      });
    }
    getZoom() { return this._m.getZoom(); }
    setZoom(z, imm) { this._m.setZoom(z, { animate: !imm }); }
    zoomIn() { this._m.zoomIn(); }
    zoomOut() { this._m.zoomOut(); }
    getCenter() { const c = this._m.getCenter(); return { lng: c.lng, lat: c.lat }; }
    setCenter(p, imm) { this._m.panTo(toLL(p), { animate: !imm }); }
    setZoomAndCenter(z, p, imm) { this._m.setView(toLL(p), z, { animate: !imm }); }
    setFitView(list, imm, avoid) {   // avoid 高德序 [上, 下, 右, 左] → Leaflet 两角
      let b = null;
      for (const o of list || []) {
        const gb = o.getBounds ? o.getBounds() : null;
        if (gb) b = b ? b.extend(gb) : gb;
      }
      if (!b) return;
      const a = avoid || [0, 0, 0, 0];
      this._m.fitBounds(b, {
        paddingTopLeft: [a[3], a[0]], paddingBottomRight: [a[2], a[1]],
        animate: !imm,
      });
    }
    add(x) { for (const l of [].concat(x)) this._group.addLayer(l._ll); }
    remove(x) { for (const l of [].concat(x)) this._group.removeLayer(l._ll); }
    clearMap() { this._group.clearLayers(); }
    destroy() { this._m.remove(); }
    getBounds() {
      const b = this._m.getBounds();
      const sw = b.getSouthWest(), ne = b.getNorthEast();
      return { southwest: { lng: sw.lng, lat: sw.lat }, northeast: { lng: ne.lng, lat: ne.lat } };
    }
    lngLatToContainer(p) { const pt = this._m.latLngToContainerPoint(toLL(p)); return px2(pt.x, pt.y); }
    getResolution() {   // 米/像素 (中心纬度处的墨卡托分辨率)
      const c = this._m.getCenter();
      return 156543.03392 * Math.cos(c.lat * Math.PI / 180) / Math.pow(2, this._m.getZoom());
    }
  }

  /* ================= 统一工厂: 高德直通, OSM 走垫片 ================= */

  function createMap(el, opts) {
    if (provider === "amap")
      return new AMap.Map(el, { mapStyle: styleV, zoom: opts.zoom, center: opts.center });
    return new LMap(el, opts);
  }
  const polyline = o => provider === "amap" ? new AMap.Polyline(o) : new LPoly(o);
  const circleMarker = o => provider === "amap" ? new AMap.CircleMarker(o) : new LCircle(o);
  const marker = o => provider === "amap" ? new AMap.Marker(o) : new LMark(o);
  const pixel = (x, y) => provider === "amap" ? new AMap.Pixel(x, y) : px2(x, y);
  function heatMap(m, o) {
    if (provider === "amap") return new AMap.HeatMap(m, o);
    // leaflet.heat: 梯度键值格式与高德同款 (0.2/0.45/.../1); 强度 = count/max
    const layer = L.heatLayer([], { radius: o.radius, gradient: o.gradient,
      minOpacity: .12, maxZoom: 17 }).addTo(m._m);
    return {
      setDataSet(ds) {
        const max = ds.max || 1;
        layer.setLatLngs(ds.data.map(d => [d.lat, d.lng, (d.count || 0) / max]));
      },
    };
  }

  /* 渲染坐标: 高德要 GCJ-02, OSM 用原始 WGS-84 (视图侧统一喂 WGS-84) */
  const gcj = p => provider === "amap" ? GCJ02.wgs84ToGcj02(p[0], p[1]) : [p[0], p[1]];

  /* 高德驾车规划 (断档补路 + 高速费估价): OSM 无免费等价物 → null 降级 */
  function drivingSearch(aGcj, bGcj, wps) {
    return new Promise(resolve => {
      if (provider !== "amap" || !window.AMap) return resolve(null);
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

  function version() {
    return provider === "amap"
      ? ((window.AMap && AMap.version) || "?")
      : ("Leaflet " + (window.L ? L.version : "?"));
  }

  const api = {
    ready, reset,
    // 服务商标记: 读 provider (ready() 后才准; 调用侧都在建图后用)
    get isAmap() { return provider === "amap"; },
    get isOsm() { return provider === "osm"; },
    style: () => styleV,
    version,
    createMap, polyline, circleMarker, marker, pixel, heatMap,
    gcj, drivingSearch,
  };
  return api;
})();
