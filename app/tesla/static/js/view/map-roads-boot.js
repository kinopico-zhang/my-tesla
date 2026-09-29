// view/map-roads-boot.js — 足迹地图「走过的路」同步与格合并 (壳版 5/5 之
// 前的道路层): 拟合结果 (服务端 drive_roads, 只回有几何的行: ok 证实 +
// guess 推断) 存本地库 fp_roads, 按清单对账 (rv 算法版不符清库; rn 点数
// 或拟合态 s 变了重下 —— worker 会把 guess 重拟合成 ok, 几何没变只有态
// 变, 不盯住 s 手机就一直画旧虚线)。roadRebuild 把当前筛选内逐程的格序
// 列合并成全局计数 roadCells
// (格键 → packStat) 与最重格计数 roadMax —— 渲染层按它上连续热力色阶
// (对数刻度, 1 次 → roadMax 次); 换筛选只重算这步, 不再请求。
// 次数计数只从已证实段来 (roadCellsOf 剔推断层: 可能走过 ≠ 走过)。
// 冻结线: 下载每 25 行让一帧 / 合并每 200 程让一帧 (iOS 长任务整页冻结,
// 2026-09-24 viewport-doctor 实证), 配方同 map-boot.js 的 50 帧。
/* global diag, RoadsGrid, ROAD_FMT_V, manifest, manifestIdx, localDb,
          fpRowVisible, fpRoadAll, fpRoadPut, fpRoadDelete, fpRoadClear,
          appendIfVisible, showLoading, showProgress, roadBandSync,
          redrawRoads, roadLegend, map, overlays,
          roadsById: writable, roadCellsById: writable, roadCells: writable,
          roadMax: writable */
/* exported fpRoadsSync, roadDownload, roadRebuild */
"use strict";
const raf = () => new Promise(r => requestAnimationFrame(r));

function roadAsTrack(row, r) {   // 道路行补渲染层要的字段 (原地补, 单一对象身份)
  row.km = row.km || 0;
  row.s = r ? r.s : 0;           // 清单的拟合态: 落库随行存, 对账盯它重下
  row.date = r ? r.t : "";       // 清单行的日期/时长 (详情卡口径, 免得客户端再存)
  row.min = r ? r.m : 0;
  return row;
}

function roadCellsOf(row) {   // 已证实段的格序列 (推断层不进计数, 见 rowSpans)
  const pts = row.pts || [];
  const cells = [];
  for (const s of RoadsGrid.rowSpans(pts, row.g || [])) {
    const c = RoadsGrid.cellsForFlat(pts.slice(s[0], s[1]));
    for (let i = 0; i < c.length; i++) cells.push(c[i]);   // 长数组不 spread
  }
  return cells;
}

function mergeCells(keys, dateStr) {   // 一程的格序列并进全局计数 (含本程折返重走)
  const day = RoadsGrid.dayOrdOf(dateStr);
  const per = new Map();               // 本程内每格次数 (有序连续去重后仍可重复进格)
  for (const k of keys) per.set(k, (per.get(k) || 0) + 1);
  for (const [k, c] of per) {
    const old = roadCells.get(k) || 0;
    const nc = RoadsGrid.cellCount(old) + c;
    if (nc > roadMax) roadMax = nc;   // 色阶上限跟最重计数走 (图例右端/插值)
    roadCells.set(k, RoadsGrid.packStat(
      nc, Math.max(RoadsGrid.cellDay(old), day)));
  }
}

async function fpRoadsSync(man) {   // 道路层对账 → 待下清单 (本地就绪的已建好索引)
  let stored = new Map();
  if (man.rv !== ROAD_FMT_V) {      // 算法版本变了: 本地道路库整体作废重下
    diag("road_fmt_v", { rv: man.rv, mine: ROAD_FMT_V });
    await fpRoadClear(localDb);
  } else {
    stored = await fpRoadAll(localDb);
  }
  roadsById = new Map();
  roadCellsById = new Map();
  const keep = new Map(), drop = [];
  for (const [id, s] of stored) {
    const r = manifestIdx.get(id);
    // 清单里不再是 s===1|3 (worker 重拟合失败/清单刷新)、rn 不符或拟合态
    // 变了 (guess→ok: 点数不变, 只有虚线变实线) → 重下
    if (r && (r.s === 1 || r.s === 3) && s.pts &&
        s.pts.length === r.rn * 2 && s.s === r.s)
      keep.set(id, s);
    else drop.push(id);
  }
  if (drop.length) fpRoadDelete(localDb, drop);
  for (const [id, s] of keep) {
    roadAsTrack(s, manifestIdx.get(id));
    roadsById.set(id, s);
    roadCellsById.set(id, roadCellsOf(s));
  }
  return man.tracks.filter(r => (r.s === 1 || r.s === 3) && !keep.has(r.id));
}

async function roadDownload(need) {   // 分批流式下载道路: 边下边建格边画 (配方同整版渲染)
  const total = need.length;
  const max0 = roadMax;               // 起步时的色阶上限 (收尾比对: 变了要重铺色)
  showLoading(true, "正在下载走过的路 0 / " + total + "…");
  let done = 0, lastFit = 0, sinceYield = 0;
  const liveFit = total <= 200;   // 小补量才中途重定视野 (大批量的风暴, 见下)
  const CHUNK = 50;    // 与服务端单次上限 (200) 留余量, 一批一请求
  for (let i = 0; i < need.length; i += CHUNK) {
    const resp = await fetch("/tesla/map/api/roads/stream?ids=" +
      need.slice(i, i + CHUNK).map(r => r.id).join(","));
    if (!resp.ok || !resp.body) throw new Error("道路下载失败 (" + resp.status + ")");
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {   // NDJSON: 一行一条拟合路径, 逐行解析, 不等整包
      const st = await reader.read();
      if (st.done) break;
      buf += dec.decode(st.value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        if (!line) continue;
        const parsed = JSON.parse(line);
        const row = roadAsTrack(parsed, manifestIdx.get(parsed.id));
        fpRoadPut(localDb, row);       // 落本地库 (不可用时自动跳过)
        roadsById.set(row.id, row);
        const cells = roadCellsOf(row);
        roadCellsById.set(row.id, cells);
        const r = manifestIdx.get(row.id);
        if (r && fpRowVisible(r)) {    // 只有当前筛选的程才进全局计数/上屏
          mergeCells(cells, r.t);
          appendIfVisible(row);
        }
        done++;
        if (++sinceYield >= 25) { sinceYield = 0; await raf(); }   // 冻结线 1
      }
      showProgress(done, total);
      const now = Date.now();
      /* 中途重定视野只留给小补量 (增量几条): 全量重下 1800 程时每 500ms
         一次即时 setFitView, 每次都触发全图重渲染 —— 2026-09-29 手机端
         实测「疯狂刷新+黑屏」即此 (主线程打满地图不刷帧), 大批量只收尾一次 */
      if (liveFit && now - lastFit > 500 && overlays.length) {
        lastFit = now;
        map.setFitView(overlays, true, [40, 40, 40, 40]);
      }
    }
  }
  map.setFitView(overlays, false, [40, 40, 40, 40]);   // 收尾终态视野
  roadBandSync();                                      // 档位对齐当前缩放 (下载期可能变焦)
  if (roadMax !== max0) {   // 新路抬了色阶上限: 先画的线色阶过期, 分块重铺
    redrawRoads();          // (只比上限: 上限没动的档间微调留待下次整版渲染)
    roadLegend(true);
  }
}

async function roadRebuild() {   // 当前筛选的逐程格合并 → 全局计数 (换筛选只重算这步)
  roadCells = new Map();
  roadMax = 0;                  // 色阶上限随合并重建 (mergeCells 里跟进)
  if (!manifest) return;
  let n = 0;
  for (const row of manifest.tracks) {
    const cells = roadCellsById.get(row.id);
    if (!cells || !fpRowVisible(row)) continue;
    mergeCells(cells, row.t);
    if (++n % 200 === 0) await raf();   // 冻结线 2
  }
}
