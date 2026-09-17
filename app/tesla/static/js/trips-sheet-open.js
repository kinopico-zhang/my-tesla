// trips-sheet-open.js — 轨迹弹层 (11/13): 打开弹层 —— 单条 (卡片数据/单条
// 接口) 与合并流式 (边下边播, 整包缓存), 建图与事件接管 (手动缩放锁定
// 视角), 播放前预载编排 (矢量扫路/栅格瓦片)。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局); 头部/驾驶员/高速费在
// trips-sheet-driver.js, 关弹层与地址栏深链在 trips-sheet-close.js
// (后加载, 调用时才解析)。
/* global $, getJSON, urlTripKey, listURL, mergedCache, amapStyle, ensureAMap,
   tripMsg, openSeq: writable, curKey: writable, sheetTrip: writable,
   tripMap: writable, trackCache, skipAnim, anim, followZoomOn: writable,
   zoomUserLock: writable, zoomUserZoom: writable, followZoom, tileTemplate,
   preloadTiles, preloadVectorTrack, TrackUtil, playTrack, hideSheet,
   fillSheetHeader, fillSheetHeaderPending, setupDriverPicker, autoCalcToll */
/* exported openTrip, loadMergedStream, sheetTrip, followZoomOn, zoomUserZoom */
"use strict";
async function openTrip(it, fromUrl) {
  curKey = it.merged ? (it.mergeKey || it.ids.join(",")) : String(it.id);
  if (!fromUrl && urlTripKey() !== curKey)
    history.pushState({ k: curKey }, "", listURL(curKey));
  const seq = ++openSeq;
  sheetTrip = it.merged ? null : it;   // 驾驶员标注只对单条行程有意义
  const cached = it.merged ? mergedCache.get(it.mergeKey) : null;
  if (cached) Object.assign(it, cached);   // 合并整包缓存命中: 数据齐了直接播
  if (it.pts || !it.merged) fillSheetHeader(it);   // 单条: 字段随卡片/接口齐, 直接填
  else fillSheetHeaderPending();                   // 合并流式: 数据在路上, 占位
  setupDriverPicker(it, seq);
  $("#sheet").classList.add("show");
  $("#backdrop").classList.add("show");
  tripMsg("正在加载轨迹…", true);

  try {
    await ensureAMap();
    if (seq !== openSeq) return;

    if (!tripMap) {
      tripMap = new AMap.Map("trip-map", { mapStyle: amapStyle, zoom: 11 });
      // iOS Safari 双指缩放劫持成页面缩放: 拦掉, 手势只给地图
      for (const ev of ["gesturestart", "gesturechange"])
        document.getElementById("trip-map").addEventListener(ev, e => e.preventDefault());
      tripMap.on("click", skipAnim);   // 播放中点一下 = 跳过, 直接收尾拉远
      /* 播放中按车速自动变焦 (慢速拉近/高速拉远) 的用户接管: 听地图容器上的
         缩放类输入 (滚轮/双击/双指)。不用 zoomend 数值比对 —— 变焦改成动画
         过渡后, 动画期间 getZoom 一直是中间值, 自己的 zoomend 和用户的
         分不开; 而程序化 setZoom 不会触发这些输入事件, 听输入是确定性的 */
      const zoomTakeover = () => {
        followZoomOn = false;
        zoomUserLock = true;                 // 手动接管 = 视角锁定, 换行程也保持
        zoomUserZoom = tripMap.getZoom();
      };
      // 锁定期间自动变焦已停, 播放中缩放只来自用户手势 —— 持续记录用户档位
      tripMap.on("zoomend", () => {
        if (zoomUserLock && anim && !anim.finished) zoomUserZoom = tripMap.getZoom();
      });
      const mapEl = document.getElementById("trip-map");
      mapEl.addEventListener("wheel", zoomTakeover, { passive: true });
      mapEl.addEventListener("dblclick", zoomTakeover);
      mapEl.addEventListener("touchstart", e => {
        if (e.touches.length >= 2) zoomTakeover();   // 双指 = 捏合缩放
      }, { passive: true });
    }
    /* 高德矢量样式数据是异步加载的: 首帧渲染时标注规则还没到, 地名不画;
       数据到货后要一次重渲染才补画 (同一轨迹第二次进入就有地名的原因)。
       开弹层后延时补几拍 —— setFeatures 同值重设 = 只触发重渲染, 不动视角 */
    const nudgeLabels = () => {
      if (tripMap && tripMap.getFeatures) tripMap.setFeatures(tripMap.getFeatures());
    };
    setTimeout(nudgeLabels, 1500);
    setTimeout(nudgeLabels, 5000);
    setTimeout(nudgeLabels, 12000);
    tripMap.clearMap();

    if (it.merged && !it.pts) {   // 合并轨迹流式: 汇总 → 首段开播 → 逐段追加
      await loadMergedStream(it, seq);
      return;
    }
    let c = it.pts ? it : trackCache.get(it.id);   // 合并整包: 数据随 it 一起来
    if (!c) {
      c = await getJSON(`/tesla/trips/api/${it.id}/track`);
      trackCache.set(it.id, c);
    }
    if (seq !== openSeq) return;
    if (!it.merged && it.toll == null)
      autoCalcToll(it, c.pts, seq);   // 不 await: 估价不挡播放

    /* 播放前把沿途瓦片刷进缓存 (跟随倍率按里程), 播放不再一路补图白屏;
       矢量模式没有可抄的瓦片 URL, 改扫路预取 (见 preloadVectorTrack) */
    const zoom = followZoom(TrackUtil.cumDistKm(c.pts).pop() || 0);
    const tpl = await tileTemplate();
    if (tpl) await preloadTiles(c.pts, zoom, tpl,
      p => tripMsg(`正在预载地图 ${p}%`, true));
    else await preloadVectorTrack(c.pts, c.ts || [], zoom,
      p => tripMsg(`正在预载地图 ${p}%`, true), seq);
    if (seq !== openSeq) return;
    tripMsg(null, false);
    playTrack(c.pts, c.ts || [], it, zoom);   // 动态播放: 起点跑向终点, 视角跟随, 结束后拉远全局
  } catch (e) {
    if (seq !== openSeq) return;
    if (fromUrl && it.merged) { hideSheet(); throw e; }   // 坏合并深链: 让 openByKey 抹参回列表
    tripMsg(String(e.message || e), false);   // 卡片打开等: 弹层里亮出错误
  }
}

/* 合并轨迹流式加载 (NDJSON): 首行汇总填弹层头, 之后每行一段 —— 第一段
   到了就开播, 后续段到了追加, 不等整包下完 (38 段的轨迹要好几秒)。首段
   未到时显示已耗时/已收字节; 全部到齐存 mergedCache, 重开同一条秒开。 */
async function loadMergedStream(it, seq) {
  const key = it.mergeKey;
  const res = await fetch(`/tesla/trips/api/merged_stream?ids=${key}`);
  if (res.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const reader = res.body.getReader(), dec = new TextDecoder();
  const t0 = performance.now();
  const allPts = [], allTs = [], segStarts = [];
  let buf = "", got = 0, msgAt = 0, sess = null, segsGot = 0, segsTotal = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    got += value.length;
    buf += dec.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      const d = JSON.parse(line);
      if (d.summary) {                    // 首行: 汇总 → 弹层头 (segs = 有点数的段数)
        Object.assign(it, d.summary);
        segsTotal = d.segs || it.n;
        fillSheetHeader(it);
      } else if (d.pts && d.pts.length) {
        if (seq !== openSeq) { reader.cancel().catch(() => {}); return; }   // 弹层已换
        segsGot++;
        if (!sess) {
          /* 首段开播前扫路预取 (矢量; 栅格走下面的后台抄 URL 预载):
             环形前瞻容器管播放中的连续前瞻, 这里把开场几秒 + 首段走廊
             先灌进缓存, 后续段边播边由环带覆盖 */
          await preloadVectorTrack(d.pts, d.ts, followZoom(it.km || 0),
            p => tripMsg(`正在预载地图 ${p}%`, true), seq);
          if (seq !== openSeq) { reader.cancel().catch(() => {}); return; }   // 扫路中弹层已换
          tripMsg(null, false);
          sess = playTrack(d.pts, d.ts, it, followZoom(it.km || 0), true);
        } else {
          sess.append(d.pts, d.ts);
        }
        segStarts.push(allPts.length);
        allPts.push(...d.pts);
        allTs.push(...d.ts);
        // 新一段的沿途瓦片后台预载 (不挡播放)
        tileTemplate().then(tpl => {
          if (tpl) preloadTiles(d.pts, followZoom(it.km || 0), tpl, () => {});
        });
      }
    }
    if (!sess && performance.now() - msgAt > 300) {   // 首段未到: 已耗时 + 已收字节
      msgAt = performance.now();
      tripMsg(`正在下载轨迹 · ${((performance.now() - t0) / 1000).toFixed(0)}s · ${(got / 1048576).toFixed(1)}MB`, true);
    }
  }
  if (seq !== openSeq) return;
  if (sess) sess.more = false;            // 流结束: 播到头就收尾
  if (allPts.length >= 2)
    mergedCache.set(key, { n: it.n, ids: it.ids, date: it.date, start: it.start,
      end: it.end, km: it.km, min: it.min, speed_max: it.speed_max,
      from: it.from, to: it.to, pts: allPts, ts: allTs, seg_starts: segStarts });
  if (!sess) throw new Error("这些行程没有轨迹数据");
  if (segsGot < segsTotal) tripMsg(`轨迹下载中断, 已播 ${segsGot}/${segsTotal} 段`, false);
}
