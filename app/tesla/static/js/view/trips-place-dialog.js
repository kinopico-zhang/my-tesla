// view/trips-place-dialog.js — 常用地点改名弹层 (壳级, 2026-09-30 用户点名
// 「点击地点名称, 可以弹出修改地点名称对话框, 对话框上一个 inputbox,
// 下面是具体的地点位置地图」): 行程统计点柱名/柱身打开 (设置页管理列表
// 与组详情层先后改走自己的路, 2026-10-05 起唯此一入口)。上输入框 (没改
// 过名空着当占位, 改过名预填别名; 留空保存 = 还原
// 原名), 下小地图 (组内各停车点全画出 —— v3 用户点名「如果一个地点,
// 包含多个地方, 那么打开地图, 就要显示多个地点」, spots 逐点 .place-pin
// 自绘圆点并收进视野; 单点/旧数据退回 lat/lng, WGS-84 → GCJ-02, mapLib
// 懒建一次复用; 自绘圆点 —— 默认高德针依赖 SDK 图标资源, 自绘与全站标记
// 语言一致且必显示; 没坐标/没地图 Key 整块藏起不拦改名)。保存走
// /trips/api/stats/place-alias (places = 统计行 raws 原样回传, 并组多名
// 一起改), 存完回调重拉 —— 谁开的层谁刷新自己的数据。收层三路: 把手下
// 拉 (bindSheetDrag) / 点蒙版 / Esc, 各自一层。
// v4 (2026-10-02, 用户点名「弹出的地图太小了」+「用 inputbox 和下拉菜单
// 合一的控件, 可以选择已经存在的名字」): 地图定高约半屏 (CSS); 输入框
// 右缘 ▾ 出已有名字名单, 按输入现值过滤, 点选 = 填入输入框 —— 保存即
// 别名同名, 两组并成同一个地点。开层预拉名单, 保存成功作废重拉。
// v5→v6 (2026-10-05): 组详情层标题行「改名」一度也开这层, 存完回调带上
// 存的名 (cb(alias)) —— 图表/管理页的旧回调不带参照旧。同日晚详情层改
// 就地内联输入 (用户点名「改名没必要再弹一个框」), 这层只剩行程统计
// 柱名/柱身一个入口, cb(alias) 的带名路留着备用。
/* global $, toast, sendJSON, getJSON, esc, layerMotion, ViewportDoctor,
          bindSheetDrag, bindSheetSettle, mapLib */
/* exported openPlaceDialog, closePlace */
"use strict";

let placeRow = null;    // 当前编辑的统计行 (name/trips/lat/lng/raws/spots)
let placeSaved = null;  // 存完回调 (开层的视图重拉自己的数据)
let placeMap = null;    // 小地图实例 (懒建一次)
let placeMarkers = [];  // 停车点标记们 (换地点先清旧点)
let placeNames = null;  // 已有名字名单 (null = 没拉过; 保存成功置回 null 重拉)

function openPlaceDialog(row, onSaved) {
  placeRow = row;
  placeSaved = onSaved || null;
  const aliased = !row.raws.includes(row.name);
  $("#place-hint").textContent =
    `${row.name} · 停过 ${row.trips} 次` +
    (row.raws.length > 1 ? ` (并组 ${row.raws.length} 个地名)` : "");
  $("#place-input").value = aliased ? row.name : "";
  $("#place-input").placeholder = aliased ? "留空 = 还原原名" : "给这个地点起个名";
  placePopsHide();          // 上次残留的名单不带到新地点
  placeLoadNames();         // 预拉已有名单 (点 ▾ / 聚焦时多半已到手)
  $("#place-backdrop").classList.add("show");
  $("#place-sheet").classList.add("show");
  layerMotion();
  placeSyncMap();
}

async function placeSyncMap() {   // 小地图跟当前地点走 (没坐标整块藏)
  const box = $("#place-map");
  const spots = (placeRow && placeRow.spots && placeRow.spots.length
    ? placeRow.spots : [{ lat: placeRow && placeRow.lat,
                           lng: placeRow && placeRow.lng }])
    .filter(s => s && s.lat != null && s.lng != null);
  if (!placeRow || !spots.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  try {
    await mapLib.ready();
    const pts = spots.map(s => mapLib.gcj([s.lng, s.lat]));
    if (!placeMap) {              // 懒建: 层已显, 画布有尺寸
      placeMap = mapLib.createMap(box, { zoom: 16, center: pts[0] });
    }
    placeMarkers.forEach(m => placeMap.remove(m));   // 复用: 换地点先清旧点
    placeMarkers = pts.map(p => mapLib.marker({ position: p, zIndex: 130,
      offset: mapLib.pixel(-9, -9),       // 圆点几何心对准位置
      content: '<div class="place-pin"></div>' }));
    placeMarkers.forEach(m => placeMap.add(m));
    if (pts.length > 1) placeMap.setFitView(placeMarkers, false, [36, 36, 36, 36]);
    else placeMap.setCenter(pts[0]);
  } catch (_e) {
    box.hidden = true;            // 没 Key/引擎失败: 藏地图, 改名照常
  }
}

async function placeLoadNames() {   // 已有地点名: locations 全量行的显示名 (缓存到关层)
  if (placeNames) return;           // 拉失败静默成空名单, 不拦手输
  try {
    // top=0 = 全部行瘦成名+次数 (名单只要 name; 全量 raws/details 在弱网
    // 上是白拖的 146KB)
    const all = await getJSON("/tesla/trips/api/stats/locations?top=0");
    placeNames = [...new Set(all.map(r => r.name))];
  } catch (_e) { placeNames = []; }
}

function placePopsShow() {          // 名单上屏 (按输入现值过滤; 本名除外)
  const q = $("#place-input").value.trim().toLowerCase();
  const names = (placeNames || [])
    .filter(n => !placeRow || n !== placeRow.name)
    .filter(n => !q || n.toLowerCase().includes(q)).slice(0, 80);
  const note = names.length ? "选已有名字 = 跟它并成同一个地点"
    : (placeNames || []).length ? "没有叫这个名字的地点"
                                : "已有名字没拉到, 可直接输入新名";
  $("#place-pops").innerHTML =
    `<div class="pp-note">${note}</div>` +
    names.map(n => `<button type="button" class="pp-item">${esc(n)}</button>`).join("");
  $("#place-pops").hidden = false;
  $("#place-down").classList.add("open");
}

function placePopsHide() {
  $("#place-pops").hidden = true;
  $("#place-down").classList.remove("open");
}

$("#place-save").addEventListener("click", async () => {
  if (!placeRow) return;
  const btn = $("#place-save");
  btn.disabled = true;
  try {
    const ali = $("#place-input").value.trim();
    await sendJSON("/tesla/trips/api/stats/place-alias", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ places: placeRow.raws, alias: ali }),
    });
    toast("已保存");
    placeNames = null;            // 并组刚发生过: 名单作废, 下次开层重拉
    const cb = placeSaved;
    closePlace();
    if (cb) cb(ali);              // 存完重拉 (图表/管理列表各自刷新; v6 带上
                                  // 存下的名 —— 组详情层按它找新行就地续开)
  } catch (err) {
    toast(`保存失败: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

function closePlace() {
  const t = document.activeElement;
  if (t instanceof HTMLElement) t.blur();   // 先交还焦点, 键盘起收
  placePopsHide();                          // 名单随层一起收 (蒙版/把手路径)
  const start = Date.now();
  const teardown = () => {                  // settled() 没回满不拆层 (账号弹层同法)
    $("#place-backdrop").classList.remove("show");
    $("#place-sheet").classList.remove("show");
    layerMotion();
    placeRow = null;
    placeSaved = null;
  };
  const wait = () => {
    if (ViewportDoctor.settled() || Date.now() - start > 1200) teardown();
    else setTimeout(wait, 80);
  };
  wait();
}

/* 接线: 蒙版/Esc 收 (Esc 只在本层开着时拦, 一层 Esc 关一层); 输入框回车
   直接存; 把手拖拽收层 (壳级 tesla-sheet-drag)。下拉合一 (v4): 聚焦/敲字
   过滤名单, ▾ 开合 (不抢焦点 —— focus 监听会把它再顶开), 点选项填入,
   点名单外任意处收名单 (capture: 抢在各视图自己的收层之前)。 */
$("#place-backdrop").addEventListener("click", closePlace);
$("#place-input").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); $("#place-save").click(); }
});
$("#place-input").addEventListener("focus", () => {
  if (placeRow) placeLoadNames().then(placePopsShow);
});
$("#place-input").addEventListener("input", () => {
  if (!$("#place-pops").hidden) placePopsShow();   // 名单开着才跟着过滤
});
$("#place-down").addEventListener("click", () => {
  if ($("#place-pops").hidden) placeLoadNames().then(placePopsShow);
  else placePopsHide();
});
$("#place-pops").addEventListener("click", e => {
  const b = e.target.closest("button.pp-item");
  if (!b) return;
  $("#place-input").value = b.textContent;   // 点选 = 填入 (保存即并组)
  placePopsHide();
});
document.addEventListener("pointerdown", e => {   // 点名单外任意处收名单。
  // pointerdown 不是 click: 弹层下半屏是地图, 高德画布 preventDefault 触摸
  // 后不合成 click —— 靠 click 点外永远收不起 (2026-10-02 用户实报「下拉
  // 收不起来」); pointerdown 在触摸被吞之前就已派发, 地图/把手/任意处都灵
  if (!$("#place-pops").hidden && !e.target.closest(".place-field")) placePopsHide();
}, true);
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !$("#place-sheet").classList.contains("show")) return;
  if (!$("#place-pops").hidden) placePopsHide();   // 一层 Esc 关一层: 先收名单
  else closePlace();
  e.stopImmediatePropagation();
});
bindSheetDrag($("#place-sheet"), $("#place-sheet .grab"), closePlace, true);
bindSheetSettle($("#place-sheet"), "show");
