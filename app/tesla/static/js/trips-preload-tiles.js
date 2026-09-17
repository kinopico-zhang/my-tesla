// trips-preload-tiles.js — 播放 (8/13): 栅格瓦片预载 —— 从地图 DOM 抄真实
// 瓦片 URL 当模板, 沿途头瓦片 ±1 圈用 Image() 刷进 HTTP 缓存; 跟随倍率按
// 里程取档 (followZoom)。矢量渲染没有瓦片 img, 抄不到就静默跳过。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局)。
/* global TrackAnimation, toGcj, zoomBias */
/* exported followZoom, tileTemplate, preloadTiles */
"use strict";
/* ---------- 播放前预载沿途瓦片 ----------
   跟随播放时瓦片按需拉取, 长途一路白屏补图。先用 Image() 把沿途瓦片刷进
   HTTP 缓存 (与地图自身请求同 URL 直接命中); 高德若是矢量渲染 (DOM 里没有
   瓦片 img) 抄不到模板, 或瓦片请求超时, 都静默跳过, 照常播放。 */
const TILE_HOSTS = ["webrd01", "webrd02", "webrd03", "webrd04"];

/* 跟随倍率按里程: 260km 的路线跟 15 级视口基本"没在动", 放到 12 级看得出走线。
   基线平移同步生效 (预载瓦片的倍率跟实际开播档一致) */
function followZoom(km) {
  return Math.max(10.5, Math.min(18.5,
    (km < 20 ? 14 : km < 80 ? 13 : km < 200 ? 12 : 11) + zoomBias));
}

/* 从地图 DOM 抄一张真实瓦片 URL 当模板 (lang/style/scale 跟实际渲染走, 高德改版不用跟)。
   首次建图时初始瓦片还没进 DOM, 轮询等一小会儿; 矢量渲染是 canvas 没有瓦片
   img (请求走另一套接口), 预载无意义 → 放弃, 不浪费请求。
   抄到一次就缓存 (流式逐段预载共用, 风格/倍率不会变)。 */
let tileTplCache = null;
async function tileTemplate() {
  if (tileTplCache) return tileTplCache;
  for (let i = 0; i < 12; i++) {
    const img = document.querySelector("#trip-map img[src*='appmaptile']");
    if (img) return tileTplCache = img.src;
    if (document.querySelector("#trip-map canvas")) return null;
    await new Promise(r => setTimeout(r, 250));
  }
  return null;
}

function tileUrl(tpl, x, y, z) {
  return tpl
    .replace(/([?&]x=)\d+/, "$1" + x)
    .replace(/([?&]y=)\d+/, "$1" + y)
    .replace(/([?&]z=)\d+/, "$1" + z)
    .replace(/webrd0\d/, TILE_HOSTS[(x + y) % 4]);   // 轮换子域, 不打爆单台
}

/* 沿途每点的头瓦片 ±1 圈 (跟随视口约 2×3 张), 去重后上限 360 张 */
function preloadTiles(pts, z, tpl, onProgress) {
  const tiles = new Set();
  const step = Math.max(1, Math.floor(pts.length / 1500));
  for (let i = 0; i < pts.length; i += step) {
    const g = toGcj(pts[i]);
    const t = TrackAnimation.lngLatToTile(g[0], g[1], z);
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++) tiles.add((t[0] + dx) + "," + (t[1] + dy));
  }
  const urls = [...tiles].slice(0, 360).map(k => {
    const [x, y] = k.split(",").map(Number);
    return tileUrl(tpl, x, y, z);
  });
  if (!urls.length) return Promise.resolve();
  let done = 0;
  return new Promise(resolve => {
    const timer = setTimeout(resolve, 8000);   // 最多等 8s, 没到的照常按需补
    const tick = () => {
      done++;
      onProgress(Math.round(done / urls.length * 100));
      if (done >= urls.length) { clearTimeout(timer); resolve(); }
    };
    urls.forEach(u => { const im = new Image(); im.onload = im.onerror = tick; im.src = u; });
  });
}
