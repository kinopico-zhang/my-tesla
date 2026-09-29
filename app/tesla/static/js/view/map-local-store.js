// view/map-local-store.js — 足迹地图本地库 (IndexedDB): 只存「走过的路」
// 拟合结果 (服务端 drive_roads 的 ok 行), 记录是 RoadStreamRow 补上渲染
// 字段后的原样 {id, km, date, min, pts}; 下次打开按清单对账 (rn 点数
// 不符重下), 只增量下载新路。2026-09-29 原始轨迹层退役: v3 起只剩
// fp_roads 仓, 旧库 (v1 轨迹仓 / v2 双仓) 升上来顺手删掉 fp_tracks
// 释放空间 —— 全精度点位不再进手机。
// 安全上下文 (https / localhost) 才有 indexedDB, 私有模式等场景会打不开
// —— 打不开统一返回 null, 调用方退化为内存模式 (当次会话全功能, 只是
// 不跨会话); 所有失败都静默 resolve, 本地库是加速器, 绝不挡渲染。
/* exported fpLocalOpen, fpRoadAll, fpRoadPut, fpRoadDelete, fpRoadClear */
"use strict";
const FP_DB = "mytesla", FP_ROADS = "fp_roads";

function fpLocalOpen() {   // → Promise<IDBDatabase | null> (失败/不可用 = null)
  return new Promise(resolve => {
    if (!("indexedDB" in self)) return resolve(null);
    let req;
    try { req = indexedDB.open(FP_DB, 3); }
    catch { return resolve(null); }
    let done = false;
    const fail = () => {
      if (done) return;
      done = true;
      try { req.result && req.result.close(); } catch { /* 没起来过 */ }
      resolve(null);
    };
    req.onupgradeneeded = () => {   // v3: 只剩道路仓 (旧库的 fp_tracks 删掉释放空间)
      if (!req.result.objectStoreNames.contains(FP_ROADS))
        req.result.createObjectStore(FP_ROADS, { keyPath: "id" });
      if (req.result.objectStoreNames.contains("fp_tracks"))
        req.result.deleteObjectStore("fp_tracks");
    };
    req.onsuccess = () => {
      if (done) return;
      done = true;
      resolve(req.result);
    };
    req.onerror = fail;
    req.onblocked = fail;   // 旧标签页占着连接: 不无限等
    setTimeout(fail, 3000);
  });
}

function fpRoadAll(db) {   // 全量道路记录 → Map(id → row)
  return new Promise(resolve => {
    if (!db) return resolve(new Map());
    try {
      const req = db.transaction(FP_ROADS, "readonly")
        .objectStore(FP_ROADS).getAll();
      req.onsuccess = () =>
        resolve(new Map((req.result || []).map(r => [r.id, r])));
      req.onerror = () => resolve(new Map());
    } catch { resolve(new Map()); }
  });
}

function fpRoadPut(db, row) {   // 存一条 (fire-and-forget, 失败不影响本次)
  if (!db) return;
  try {
    db.transaction(FP_ROADS, "readwrite").objectStore(FP_ROADS).put(row);
  } catch { /* 私有模式偶发 QuotaExceeded: 静默 */ }
}

function fpRoadDelete(db, ids) {   // 删一批 (清单里已不再是 ok 的程)
  if (!db || !ids.length) return;
  try {
    const st = db.transaction(FP_ROADS, "readwrite").objectStore(FP_ROADS);
    for (const id of ids) st.delete(id);
  } catch { /* 静默 */ }
}

function fpRoadClear(db) {   // 道路算法版本不符: 整仓清空重下
  if (!db) return;
  try {
    db.transaction(FP_ROADS, "readwrite").objectStore(FP_ROADS).clear();
  } catch { /* 静默 */ }
}
