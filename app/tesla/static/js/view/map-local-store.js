// view/map-local-store.js — 足迹地图本地库 (IndexedDB): 全精度轨迹存在
// 浏览器里, 下次打开按清单对账 (点数不符重下 / 多余删掉), 只增量下载新
// 轨迹。记录就是服务端 MapTrack 原样 {id, car_id, date, km, min, pts}。
// 安全上下文 (https / localhost) 才有 indexedDB, 私有模式等场景会打不开
// —— 打不开统一返回 null, 调用方退化为内存模式 (当次会话全功能, 只是
// 不跨会话); 所有失败都静默 resolve, 本地库是加速器, 绝不挡渲染。
/* exported fpLocalOpen, fpLocalAll, fpLocalPut, fpLocalDelete, fpLocalClear */
"use strict";
const FP_DB = "mytesla", FP_STORE = "fp_tracks";

function fpLocalOpen() {   // → Promise<IDBDatabase | null> (失败/不可用 = null)
  return new Promise(resolve => {
    if (!("indexedDB" in self)) return resolve(null);
    let req;
    try { req = indexedDB.open(FP_DB, 1); }
    catch { return resolve(null); }
    let done = false;
    const fail = () => {
      if (done) return;
      done = true;
      try { req.result && req.result.close(); } catch { /* 没起来过 */ }
      resolve(null);
    };
    req.onupgradeneeded = () => {   // 建库/升级: 只有一个键值仓
      if (!req.result.objectStoreNames.contains(FP_STORE))
        req.result.createObjectStore(FP_STORE, { keyPath: "id" });
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

function fpLocalAll(db) {   // 全量记录 → Map(id → track) (增量对账的基准)
  return new Promise(resolve => {
    if (!db) return resolve(new Map());
    try {
      const req = db.transaction(FP_STORE, "readonly")
        .objectStore(FP_STORE).getAll();
      req.onsuccess = () =>
        resolve(new Map((req.result || []).map(r => [r.id, r])));
      req.onerror = () => resolve(new Map());
    } catch { resolve(new Map()); }
  });
}

function fpLocalPut(db, track) {   // 存一条 (fire-and-forget, 失败不影响本次)
  if (!db) return;
  try {
    db.transaction(FP_STORE, "readwrite").objectStore(FP_STORE).put(track);
  } catch { /* 私有模式偶发 QuotaExceeded: 静默 */ }
}

function fpLocalDelete(db, ids) {   // 删一批 (清单里已不存在的轨迹)
  if (!db || !ids.length) return;
  try {
    const st = db.transaction(FP_STORE, "readwrite").objectStore(FP_STORE);
    for (const id of ids) st.delete(id);
  } catch { /* 静默 */ }
}

function fpLocalClear(db) {   // 整仓清空 (轨迹格式版本不符, 全量重下)
  if (!db) return;
  try {
    db.transaction(FP_STORE, "readwrite").objectStore(FP_STORE).clear();
  } catch { /* 静默 */ }
}
