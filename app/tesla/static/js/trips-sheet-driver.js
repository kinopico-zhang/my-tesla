// trips-sheet-driver.js — 轨迹弹层 (10/13): 弹层头部汇总 (单条/合并/占位),
// 驾驶员标注选单 (设置页驾驶员表), 高速费估价 (等距途经点驾车规划,
// 高德返回 tolls)。
// 由 trips.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按 trips.html
// 里的顺序加载, 跨模块引用走全局); 打开弹层在 trips-sheet-open.js。
/* global $, esc, num, parseLocal, fmtTime, fmtCardDate, fmtDur, getJSON,
   postJSON, driversCache: writable, openSeq, sheetTrip, items, listEl,
   renderCard, toast, toGcj */
/* exported fillSheetHeader, fillSheetHeaderPending, setupDriverPicker,
   autoCalcToll */
"use strict";
/* 弹层头部汇总 (日期/时长/里程/最高速/功耗): 单条来自卡片数据, 合并来自
   流式首行或整包缓存; 合并数据没到时先用占位, 到了再填 */
function fillSheetHeader(it) {
  if (it.merged) {    // 合并多段: 跨天给日期区间, 同天照常; 时间列前缀段数
    const d1 = parseLocal(it.start), d2 = parseLocal(it.end);
    $("#sh-date").textContent = d1.toDateString() === d2.toDateString()
      ? fmtCardDate(it.start).replace(/ \d\d:\d\d$/, "")
      : (d1.getMonth() + 1) + "月" + d1.getDate() + "日 – " + (d2.getMonth() + 1) + "月" + d2.getDate() + "日";
    $("#sh-time").textContent = it.n + " 段行程 · " + fmtTime(it.start) + " – " + fmtTime(it.end);
  } else {
    $("#sh-date").textContent = fmtCardDate(it.start).replace(/ \d\d:\d\d$/, "");
    $("#sh-time").textContent = (it.end ? fmtTime(it.start) + " – " + fmtTime(it.end) : "");
  }
  $("#sh-km").innerHTML = '<span class="n">' + num(it.km) + "</span><small>km</small>";
  $("#sh-dur").innerHTML = '<span class="n">' + fmtDur(it.min) + "</span>";
  $("#sh-spd-lb").textContent = "最高车速";
  $("#sh-spd").innerHTML = '<span class="n">' + (it.speed_max != null ? it.speed_max : "—") + "</span><small>km/h</small>";
  $("#sh-cell-kwh").hidden = it.kwh == null;
  $("#sh-kwh").innerHTML = it.kwh == null ? "—" : '<span class="n">' + num(it.kwh) + "</span><small>kWh</small>";
  $("#sh-cell-avg").hidden = it.wh_per_km == null;
  $("#sh-avg").innerHTML = it.wh_per_km == null
    ? "—" : '<span class="n">' + num(it.wh_per_km, 0) + "</span><small>Wh/km</small>";
  $("#sh-pw-lb").textContent = "平均功耗";
  $("#sh-pw").textContent = "—";
}

/* 合并数据在路上: 弹层先开 (阻断其他操作), 头部占位 */
function fillSheetHeaderPending() {
  $("#sh-date").textContent = "连续轨迹";
  $("#sh-time").textContent = "正在下载…";
  $("#sh-km").textContent = "—";
  $("#sh-dur").textContent = "—";
  $("#sh-spd").textContent = "—";
  $("#sh-cell-kwh").hidden = true;
  $("#sh-cell-avg").hidden = true;
  $("#sh-pw").textContent = "—";
}

/* ---------- 弹层驾驶员标注: 未标 = 默认驾驶员兜底, 没配驾驶员整行不显示 ---------- */
async function setupDriverPicker(it, seq) {
  const pick = $("#sh-drv-pick");
  pick.hidden = true;                             // 先藏, 数据到位再亮
  if (!it.merged) {                               // 合并多段: 驾驶员标注不适用
    if (driversCache === undefined) {
      try { driversCache = await getJSON("/tesla/api/drivers"); }
      catch { driversCache = null; }
    }
    if (seq !== openSeq) return;                  // 弹层已切走, 结果作废
    if (driversCache && driversCache.length > 0) {
      const def = driversCache.find(d => d.is_default);
      $("#sh-drv-sel").innerHTML =
        `<option value="">${def ? `未指定 · 默认${esc(def.name)}` : "未指定"}</option>` +
        driversCache.map(d => `<option value="${d.id}">${esc(d.name)}</option>`).join("");
      $("#sh-drv-sel").value = it.driver_id != null ? String(it.driver_id) : "";
      pick.hidden = false;
    }
  }
  fillTollChip(it);
  metaRowSync();
}

/* 高速费 chip: 算过的才显示 (¥0 也是"算过" = 没走收费路) */
function fillTollChip(it) {
  const chip = $("#sh-toll");
  if (it.merged || it.toll == null) { chip.hidden = true; return; }
  chip.hidden = false;
  chip.textContent = it.toll > 0
    ? `高速 ¥${Number.isInteger(it.toll) ? it.toll : it.toll.toFixed(1)}` +
      (it.toll_km ? ` · ${Math.round(it.toll_km)}km` : "")
    : "无高速费";
}

function metaRowSync() {   // 驾驶员选择和高速费 chip 都藏了才整行藏
  $("#sh-drv").hidden = $("#sh-drv-pick").hidden && $("#sh-toll").hidden;
}

/* ---------- 高速费估价: 沿轨迹途经点驾车规划, 高德返回 tolls ---------- */
const TOLL_WAYPOINTS = 14;   // 途经点数 (高德单次驾车规划限 16, 留裕量)

/* 起终点 + 等距途经点把规划钉在实际走过的路上, 否则估的是"高德以为你
   会走的路"。tolls=0 也是有效结果 (没走收费路); 规划失败返回 null。 */
function calcTripToll(pts) {
  return new Promise(resolve => {
    if (!pts || pts.length < 2) return resolve(null);
    const n = pts.length;
    const gcj = i => toGcj([pts[i][0], pts[i][1]]);
    const wps = [];
    for (let k = 1; k <= TOLL_WAYPOINTS; k++)
      wps.push(gcj(Math.round(k * (n - 1) / (TOLL_WAYPOINTS + 1))));
    AMap.plugin("AMap.Driving", () => {
      try {
        const policy = AMap.DrivingPolicy && AMap.DrivingPolicy.LEAST_DISTANCE != null
          ? AMap.DrivingPolicy.LEAST_DISTANCE : 2;
        new AMap.Driving({ policy }).search(gcj(0), gcj(n - 1), wps, (status, result) => {
          if (status !== "complete" || !result.routes || !result.routes.length)
            return resolve(null);
          const r = result.routes[0];
          const roads = {};   // 同名收费路段合并 (按路名)
          for (const st of r.steps)
            if (st.tolls > 0 && st.toll_road)
              roads[st.toll_road] = (roads[st.toll_road] || 0) + st.tolls;
          resolve({
            tolls: r.tolls || 0,
            toll_km: Math.round((r.tolls_distance || 0) / 100) / 10,
            distance: r.distance || 0,
            roads: Object.keys(roads).map(rd => ({ road: rd, tolls: roads[rd] })),
          });
        });
      } catch { resolve(null); }
    });
  });
}

/* 打开还没算过的行程时顺手估一次, 成功即回传存库 (以后打开不再算)。 */
async function autoCalcToll(it, pts, seq) {
  const est = await calcTripToll(pts);
  if (!est || seq !== openSeq) return;
  it.toll = est.tolls;
  it.toll_km = est.toll_km;
  fillTollChip(it);
  metaRowSync();
  try {
    await postJSON(`/tesla/trips/api/${it.id}/toll`, {
      tolls: est.tolls, toll_km: est.toll_km,
      distance: est.distance, roads: est.roads,
    });
    const card = items.find(x => x.id === it.id);
    if (card && card !== it) { card.toll = est.tolls; card.toll_km = est.toll_km; }
  } catch { /* 存失败无所谓: 下次打开再估 */ }
}

$("#sh-drv-sel").addEventListener("change", async () => {
  const it = sheetTrip;
  if (!it) return;
  const sel = $("#sh-drv-sel");
  const driverId = sel.value === "" ? null : +sel.value;
  try {
    const upd = await postJSON(`/tesla/trips/api/${it.id}/driver`,
                               { driver_id: driverId });
    Object.assign(it, upd);                       // 弹层条目就地更新
    const card = items.find(x => x.id === upd.id);   // 列表条目 (分享直开时可能还没加载)
    if (card && card !== it) Object.assign(card, upd);
    const el = listEl.querySelector(`.card-t[data-id="${upd.id}"]`);
    if (el && card) el.replaceWith(renderCard(card));
    toast(driverId == null ? "已清除标注" : `已标注为 ${upd.driver}`);
  } catch (err) {
    toast(`标注失败: ${err.message}`);
    sel.value = it.driver_id != null ? String(it.driver_id) : "";
  }
});
