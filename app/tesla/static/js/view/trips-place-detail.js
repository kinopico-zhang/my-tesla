// view/trips-place-detail.js — 常用地点组详情页 (壳级, 2026-10-04 用户点名
// 「常用地点管理, 点击一个名称, 就弹出一个页面, 页面上面是地图, 页面下面
// 是真实地点列表, 点击列表的 item, 地图切换到这个位置」): 上半小地图把组
// 内各真实地点逐点画出 (.place-pin 自绘圆点, 收进视野), 下半列表 = 组的
// details (各带次数与各自坐标); 点行 = 地图居中放大到那一点 + 行/圆点选中
// 高亮; 行左滑出删除 (tesla-swipe-delete, 红钮弹原生 confirm 二次确认,
// 2026-10-04 用户报武装式没看见「点好多次才删掉」) —— 删的是 raw 原名
// (统计里该地址停车不再计数, 组次数缩), 删完回调重拉: 组还在就地换新行
// 重铺, 组删空了收层。坐标 WGS-84 → GCJ-02 (mapLib.gcj),
// 地图懒建一次复用 (换组清旧点); 没坐标的行点不出位置 (toast), 没地图 Key
// 地图整块藏起不拦列表。收层三路: 左缘右拖跟手推出 / 返回钮 / Esc, 各自
// 一层。v1 接 3.4.0 的原地展开 (plc-subs) 班 —— 展开改成开层。v3
// (2026-10-04 用户报「下滑退出的区域很小」): 标题/提示行/列表整片都能拖下
// 收层 (充电详情正文同款), 地图不绑 —— 竖向平移是地图的地盘。v4 (同日
// 用户点名「次数统一另起一行」): 次数块行收进名字块 (与管理页一个长相)。
// v5 (2026-10-05 用户点名「编辑按钮去掉吧, 单击打开的界面, 就可以编辑名
// 称」): 标题行挂「改名」(#placed-rename), 行上左滑的编辑钮退役。
// v6 (同日晚用户点名「改名没必要再弹一个框, 直接把 textbox 改成
// inputbox」): 点「改名」标题就地翻成输入框 (#placed-input, 驾驶员行内
// 改名 .drv-input 同款), 「改名」钮翻「保存」+ 旁添「取消」; Enter 存 /
// Esc 弃 / 留空存 = 还原原名 (没改过名的组留空存 = 不改)。保存走
// place-alias (places = raws 原样回传), 存完 placedChanged(存的名) 重拉
// 回传新行 —— 找到就地续开, 找不到 (留空还原分裂成多组) 收层回管理列表。
// v7 (同日晚续): 提示行整行退役 (用户点名删; 行为说明住更新日志, 管理
// 页长提示段 2026-10-04 同例), 拖拽收层区同步撤 .hint 死选择器。
// v8 (2026-10-05 晚用户点名「常用地点左滑删除去掉吧, 如果这个地点是重命名
// 的, 点击展开后, 最下面添加一个红色的删除按钮, 点击删除, 需要二次确
// 认」): 解除编组从管理页行上左滑搬进本层底部红钮 (#placed-del) —— 只给
// 改过名的组显 (组名不在原名列表里), confirm 二次确认后走空 alias 还原
// 路; 删完必收层 (这组已不存在), 管理列表由 placedChanged 回调重拉。
// v9 (2026-10-06 用户点名「不从底下弹窗, 而是从右侧滑入窗口, 全屏, 弹出
// 后, 在屏幕左侧滑动推出。弹入弹出要有动画效果, 要跟手」): 底部弹窗改
// 全屏右滑页 —— translateX(100%) 藏 / show 滑入 (抽屉同曲线), 蒙版/把手/
// 整片下拉收层 (bindSheetDrag) 退役; 左缘 .placed-edge 竖条 (iOS 返回
// 手势位) + 返回钮都能右拖跟手推出 (bindPlacedDrag: 松手过 1/3 屏或右甩
// 惯性才收, 否则原位弹回), 左上角添返回钮, Esc 照旧。
// v10 (同日用户点名「地图下面的地点列表太丑了」): 列表行改圆角小卡
// (v20 css), 次数挪出名字块到右缘同行 —— 单行卡, 名字过长省略号。
/* global $, esc, sendJSON, toast, layerMotion, ViewportDoctor, bindSheetSettle,
          mapLib, bindSwipeDelete */
/* exported openPlaceDetail, closePlaceDetail */
"use strict";

let placedRow = null;      // 当前组统计行 (name/trips/details)
let placedChanged = null;  // 删完回调 (开层的视图重拉, 回传新行; null = 组没了)
let placedMap = null;      // 小地图实例 (懒建一次)
let placedMarkers = [];    // 真实地点圆点们 (换组/换选中清旧重画)
let placedSel = -1;        // 选中行 (点行跳地图后高亮, -1 无)

function openPlaceDetail(row, onChanged) {
  placedRow = row;
  placedChanged = onChanged || null;
  placedSel = -1;
  renderPlacedTitle();
  renderPlacedList();
  const sheet = $("#placed-sheet");
  sheet.style.transform = "";            // 拖拽残留清干净, 滑入从右缘起
  sheet.classList.remove("dragging");
  sheet.classList.add("show");
  layerMotion();
  placedSyncMap();
}

function renderPlacedTitle() {
  placedExitEdit();                                // 重铺标题必是开层/存完: 编辑态清零
  $("#placed-title").textContent = `${placedRow.name} · 停过 ${placedRow.trips} 次`;
  // 底部删除钮只给改过名的组 (v8): 标题重铺的三路 (开层/存完/删点刷新)
  // 都会过这, 顺手同步 —— 留空还原后的组没改过名了, 钮跟着收
  $("#placed-foot").hidden = placedRow.raws.includes(placedRow.name);
}

function renderPlacedList() {   // 组内真实地点 (次数降序, 后端排好)
  // 注意 wrap 的 </div> 不能漏: 漏了各 wrap 俄套 (块流年代 3.4.1 起就漏着,
  // 平铺横线行看不出; v20 列表改 flex+gap 只认直接子孩, 一漏就露馅 ——
  // 间隔全丢/首行吞全列表), 2026-10-06 浏览器验证当场抓到补上
  $("#placed-list").innerHTML = (placedRow.details || []).map((d, i) =>
    `<div class="swipe-wrap placed-item" data-i="${i}">` +
    `<div class="placed-row${i === placedSel ? " on" : ""}">` +
    `<span class="placed-name">${esc(d.name)}</span>` +
    `<span class="plc-n">${d.trips} 次</span>` +
    `<button type="button" class="swipe-del">删除</button></div></div>`).join("");
}

function placedPoints() {   // 有坐标的真实地点 (带 details 下标: 选中对得上)
  return ((placedRow && placedRow.details) || [])
    .map((d, i) => ({ d, i }))
    .filter(r => r.d.lat != null && r.d.lng != null);
}

function placedDrawMarkers() {   // 清旧点重画 (选中那个 .sel 反色)
  placedMarkers.forEach(m => placedMap.remove(m));
  placedMarkers = placedPoints().map(r => mapLib.marker({
    position: mapLib.gcj([r.d.lng, r.d.lat]),
    zIndex: 130, offset: mapLib.pixel(-9, -9),   // 圆点几何心对准位置
    content: `<div class="place-pin${r.i === placedSel ? " sel" : ""}"></div>` }));
  placedMarkers.forEach(m => placedMap.add(m));
}

async function placedSyncMap() {   // 地图跟当前组走 (一个坐标都没有整块藏)
  const box = $("#placed-map");
  const rows = placedPoints();
  if (!placedRow || !rows.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  try {
    await mapLib.ready();
    const first = mapLib.gcj([rows[0].d.lng, rows[0].d.lat]);
    if (!placedMap) {              // 懒建: 层已显, 画布有尺寸
      placedMap = mapLib.createMap(box, { zoom: 16, center: first });
    }
    placedDrawMarkers();
    if (rows.length > 1) placedMap.setFitView(placedMarkers, false, [36, 36, 36, 36]);
    else placedMap.setCenter(first);
  } catch (_e) {
    box.hidden = true;             // 没 Key/引擎失败: 藏地图, 列表照常
  }
}

// 点列表行: 地图切到这个位置 (用户原话), 行文字变蓝 + 对应圆点反色高亮
$("#placed-list").addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const item = t.closest(".placed-item");
  if (!item) return;
  const d = placedRow && placedRow.details[+item.dataset.i];
  if (!d) return;
  if (d.lat == null || d.lng == null) {
    toast("这个地点没有坐标, 地图上画不出");
    return;
  }
  placedSel = +item.dataset.i;
  $("#placed-list").querySelectorAll(".placed-row").forEach(r =>
    r.classList.toggle("on", r.parentElement === item));
  if (placedMap) {
    try {
      placedMap.setZoomAndCenter(16, mapLib.gcj([d.lng, d.lat]));
      placedDrawMarkers();
    } catch (_e) { /* 引擎失败静默: 列表高亮照给 */ }
  }
});

// 详情层改名 (v6 内联): 点「改名」标题就地翻输入框, 钮翻「保存」添「取消」
// —— 驾驶员行内改名同款, 不再叠地点命名弹层 (用户点名「没必要再弹一个
// 框」)。存完 placedChanged(存的名) 重拉管理列表回传新行 —— 找到就地续开
// (标题/列表/地图跟新), 找不到 (留空还原分裂成多组) 收层回管理列表
function placedEnterEdit() {
  const inp = $("#placed-input");
  const aliased = !placedRow.raws.includes(placedRow.name);
  inp.value = placedRow.name;
  inp.placeholder = aliased ? "留空保存 = 还原原名" : "留空保存 = 保持原名";
  inp.hidden = false;
  $("#placed-cancel").hidden = false;
  $("#placed-title").hidden = true;
  const btn = $("#placed-rename");
  btn.textContent = "保存";
  btn.classList.add("drv-ok");
  inp.focus();
  inp.select();                       // 预填全选: 敲字即整名替换
}

function placedExitEdit() {
  $("#placed-input").hidden = true;
  $("#placed-cancel").hidden = true;
  $("#placed-title").hidden = false;
  const btn = $("#placed-rename");
  btn.textContent = "改名";
  btn.classList.remove("drv-ok");
}

async function placedSave() {
  if (!placedRow) return;
  const inp = $("#placed-input");
  const btn = $("#placed-rename");
  if (btn.disabled) return;            // 在途: 连点/连按回车不双发
  const aliased = !placedRow.raws.includes(placedRow.name);
  const val = inp.value.trim();
  // 没动过 / 没改过名的组清空存: 不打接口, 收编辑态原样回去
  if (val === placedRow.name || (!val && !aliased)) { placedExitEdit(); return; }
  btn.disabled = true;
  try {
    await sendJSON("/tesla/trips/api/stats/place-alias", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ places: placedRow.raws, alias: val }),
    });
    toast("已保存");
    const fresh = placedChanged ? await placedChanged(val) : null;
    if (!fresh) { closePlaceDetail(); return; }
    placedRow = fresh;
    placedSel = -1;
    renderPlacedTitle();
    renderPlacedList();
    placedSyncMap();
  } catch (err) {
    toast(`保存失败: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

$("#placed-rename").addEventListener("click", () => {
  if (!placedRow) return;
  if ($("#placed-input").hidden) placedEnterEdit();
  else placedSave();
});
$("#placed-cancel").addEventListener("click", placedExitEdit);
$("#placed-input").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); placedSave(); }
});

// 左滑删除 (真实地点行): 删 raw 原名 — 该地址停车不再计数, 组次数缩;
// 红钮弹原生 confirm 二次确认 (取消 = 模块把行收回, 列表原样)
bindSwipeDelete($("#placed-list"), async wrap => {
  const d = placedRow && placedRow.details[+wrap.dataset.i];
  if (!d) return;
  if (!window.confirm(`删除「${d.name}」?\n该地址的停车不再计入统计, ` +
      "可在管理页底部「已删除」里恢复。")) return;
  try {
    await sendJSON("/tesla/trips/api/stats/place-hide", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ places: [d.name], hidden: true }),
    });
  } catch (err) {
    toast(`删除失败: ${err.message}`);
    return;                        // 模块把行收回, 列表原样
  }
  const fresh = placedChanged ? await placedChanged() : null;
  if (fresh) {                     // 组还在: 就地换新行 (标题/列表/地图)
    placedRow = fresh;
    placedSel = -1;
    renderPlacedTitle();
    renderPlacedList();
    placedSyncMap();
  } else {
    closePlaceDetail();            // 组删空了: 收层回管理列表
  }
});

// 底部红色删除钮 (v8): 解除编组 —— 空 alias 还原路, 组里的真实地点恢复
// 原名、各自单独列出, 不进「已删除」。confirm 二次确认 (取消当没发生);
// 删完必收层 (这组已不存在), 管理列表由 placedChanged 回调重拉
$("#placed-del").addEventListener("click", async () => {
  if (!placedRow) return;
  if (!window.confirm(`删除常用地点「${placedRow.name}」?\n` +
      "这是解除编组: 组里的真实地点恢复原名, 各自单独列出。")) return;
  try {
    await sendJSON("/tesla/trips/api/stats/place-alias", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ places: placedRow.raws, alias: "" }),
    });
  } catch (err) {
    toast(`删除失败: ${err.message}`);
    return;
  }
  if (placedChanged) await placedChanged();   // 管理列表先重拉 (回传行用不上了)
  closePlaceDetail();
});

function closePlaceDetail() {
  const t = document.activeElement;
  if (t instanceof HTMLElement) t.blur();   // 先交还焦点, 键盘起收
  const sheet = $("#placed-sheet");
  // 滑出当场起走 (v9): .dragging 摘 + 内联 transform 清 + .show 摘同一拍,
  // transition 从指位/开位插值到 translateX(100%)。全屏页四边钉死不吃
  // 视口高, 键盘塌陷的视口翻腾矮不了它 —— 不用再等 settled 才动手
  sheet.classList.remove("dragging");
  sheet.style.transform = "";
  sheet.classList.remove("show");
  layerMotion();
  const start = Date.now();
  const teardown = () => {                  // settled() 没回满不拆状态 (命名弹层同法)
    placedExitEdit();                       // 编辑中途被拖/点收层: 状态清零再藏
    placedRow = null;
    placedChanged = null;
    placedSel = -1;
  };
  const wait = () => {
    if (ViewportDoctor.settled() || Date.now() - start > 1200) teardown();
    else setTimeout(wait, 80);
  };
  wait();
}

// 左缘右拖推出 (v9, 用户点名「弹出后, 在屏幕左侧滑动推出…要跟手」):
// .placed-edge 竖条 + 返回钮都能起手; move/up 挂 window 级不捕获 (iOS
// Safari 对 touch 指针 capture 当场 pointercancel —— 下拉收层同法)。slop
// 8 内不动; 竖滑/左滑不抢 (条上 touch-action:none, 原生本就无滚可滚);
// 接管后 1:1 跟手 (只往右, 开态不许拖成负)。松手: 过 1/3 屏或右甩惯性
// (vx > 0.5 且拉过 20px, 抽屉同阈) 才收层 —— closePlaceDetail 里内联
// transform 清 + .show 摘同一拍, 滑出动画从指位接着走; 不过阈原位弹回。
// 拖过 slop 抑制随后的 click (返回钮起手拖完弹回, 不当点按把层关了)
function bindPlacedDrag(els, onClose) {
  const sheet = $("#placed-sheet");
  let x0 = 0, y0 = 0, dx = 0, lastX = 0, lastT = 0, vx = 0, axis = "", swallow = false;
  let move = null, release = null, cancel = null;   // detach 要引用, 先占位再装
  const detach = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", release);
    window.removeEventListener("pointercancel", cancel);
  };
  move = e => {
    const mx = e.clientX - x0, my = e.clientY - y0;
    if (!axis) {
      if (Math.abs(mx) < 8 && Math.abs(my) < 8) return;    // slop 内不动
      if (mx <= Math.abs(my)) { detach(); return; }        // 竖滑/左滑: 不抢
      axis = "x";
      sheet.classList.add("dragging");
      swallow = true;
    }
    dx = Math.max(0, e.clientX - x0);      // 只往右: 开态不许拖成负
    sheet.style.transform = `translateX(${dx}px)`;
    const now = performance.now();
    if (now > lastT) vx = (e.clientX - lastX) / (now - lastT);
    lastX = e.clientX; lastT = now;
  };
  release = () => {
    detach();
    if (axis !== "x") return;
    sheet.classList.remove("dragging");
    const w = sheet.offsetWidth || window.innerWidth;
    if (dx > w / 3 || (vx > 0.5 && dx > 20)) onClose();
    else sheet.style.transform = "";        // 不过阈: 原位弹回
  };
  cancel = () => {                    // 系统手势/来电打断: 原位弹回
    detach();
    if (axis === "x") {
      sheet.classList.remove("dragging");
      sheet.style.transform = "";
    }
  };
  const down = e => {
    if (!sheet.classList.contains("show")) return;
    x0 = lastX = e.clientX;
    y0 = e.clientY;
    dx = 0; vx = 0; axis = "";
    lastT = performance.now();
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", cancel);
  };
  for (const el of els) el.addEventListener("pointerdown", down);
  window.addEventListener("click", e => {
    if (!swallow) return;
    swallow = false;
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
}

/* 接线: 左缘右拖跟手推出 (v9, bindPlacedDrag —— 竖条 + 返回钮起手) /
   返回钮点按 / Esc 收 (Esc 只在本层开着时拦, 一层 Esc 关一层); settle
   保险照接 (7556: 视口折腾后微变换回 none, 废掉烂栅格)。v9 起蒙版/把手/
   整片下拉收层 (bindSheetDrag) 退役 —— 全屏页没有蒙版, 收层走右滑。 */
$("#placed-back").addEventListener("click", closePlaceDetail);
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !$("#placed-sheet").classList.contains("show")) return;
  if (!$("#placed-input").hidden) placedExitEdit();   // 一层 Esc 关一层: 先弃编辑
  else closePlaceDetail();
  e.stopImmediatePropagation();
});
bindPlacedDrag(document.querySelectorAll("#placed-sheet .placed-edge, #placed-back"),
               closePlaceDetail);
bindSheetSettle($("#placed-sheet"), "show");
