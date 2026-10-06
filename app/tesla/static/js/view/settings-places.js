// view/settings-places.js — 常用地点管理 (2026-09-30 用户点名「在设置页面
// 上, 也加一个常用地点管理」; 2026-10-04 左滑删除; 2026-10-04 用户点名
// 「点击一个名称, 就弹出一个页面: 上面是地图, 下面是真实地点列表, 点列表
// 的 item 地图切换到这个位置」): 全量列出常去地点 (旧版只列最常 12 + 榜外
// 改过名的), 点组行开组详情层 (trips-place-detail: 上地图下真实地点列表,
// 点行地图跳那, 行左滑删单点); 底部「已删除」分区带恢复钮 (详情层里藏掉的
// 真实地点)。
// v7 (2026-10-05 用户点名「编辑按钮去掉吧, 单击打开的界面, 就可以编辑名
// 称」+「页面的响应速度太慢了, 改成异步的方式」): ① 行上左滑「编辑」钮
// 退役 —— 改名住进组详情层标题行 (#placed-rename, 那边接线), 没改过名
// 的组行连左滑面板一起干净; ② locations 聚合要汇总全部行程 (实测 1-6
// 秒), 页面异步化 —— 首拉亮加载态 (空态不诈胡), 再次进页旧列表先顶后台
// 换新, 数据没变 (签名同) 连重铺都省 (滚动位置不跳), 几百组首批 80 根先
// 见面其余 rAF 跟进, 不再一拍堵死主线程。
// v8 (2026-10-05 晚用户点名「常用地点左滑删除去掉吧」+「不显示原名,
// 显示是几个地点的汇总」): 行上左滑整链退役 —— 解除编组的删除搬进详情层
// 底部红钮 (#placed-del, 那边接线); 原名小字行退役, 并进多处的组改报
// 「N 个地点的汇总」, 单点组不带小字 (跟没改过名的组一个长相)。
// 列表数据 = 行程统计的 locations 接口原样 (别名/并组/坐标都在行里)。
/* global $, esc, getJSON, sendJSON, toast, bindGestures, registerView,
           openPlaceDetail */
"use strict";
let plcRows = [];
let plcGen = 0;    // 拉取/铺排代际: 后发的赢 (进页重拉叠下拉刷新不串台)
let plcSig = "";   // 上次铺排的数据签名: 没变化不重铺 (滚动位置不跳)

function rowHtml(r) {
  // v8: 行只管点开 (左滑面板整链退役), 并进多处的组名字下报一行
  // 「N 个地点的汇总」—— 改名前叫什么对用的人没意义, 报组里几处才有用
  const n = (r.details || []).length;
  return `<div class="plc-item">` +
    `<div class="plc-g" data-name="${esc(r.name)}">` +
    `<div class="plc-row">` +
    `<div class="plc-name">${esc(r.name)}` +
    (n > 1 ? `<span class="plc-sum">${n} 个地点的汇总</span>` : "") +
    `<span class="plc-n">${r.trips} 次</span></div>` +
    `<span class="plc-go">›</span></div>` +
    `</div></div>`;
}

function renderPlaces() {
  $("#plc-empty").hidden = plcRows.length > 0;
  const list = $("#plc-list");
  list.innerHTML = "";
  // 分批铺 (全量 500+ 组一次性 innerHTML 堵主线程一拍): 首批 80 根同步
  // 先见面, 其余 rAF 跟进; 途中有更新一轮开跑 (plcGen 变) 就停笔让位
  const gen = plcGen;
  let i = 0;
  const step = () => {
    if (gen !== plcGen) return;
    list.insertAdjacentHTML("beforeend",
      plcRows.slice(i, i + 80).map(rowHtml).join(""));
    i += 80;
    if (i < plcRows.length) requestAnimationFrame(step);
  };
  step();
}

async function loadPlaces() {
  // 已删除名单与列表同拉 (底部恢复区的数据源); 组内真实地点 details
  // 在详情层用 (locations 行里就带着, 管理页/统计页同一个形状)。
  // 异步化: 没旧数据亮加载态, 有旧数据先顶着, 拉到再换 (gen 防过期串台)
  const gen = ++plcGen;
  if (!plcRows.length) {
    $("#plc-empty").hidden = true;
    $("#plc-loading").hidden = false;
  }
  try {
    const [all, hidden] = await Promise.all([
      getJSON("/tesla/trips/api/stats/locations"),
      getJSON("/tesla/trips/api/stats/place-hidden"),
    ]);
    if (gen !== plcGen) return;
    plcRows = all;
    $("#plc-hid-sec").hidden = hidden.length === 0;
    $("#plc-hid-list").innerHTML = hidden.map(name =>
      `<div class="plc-hid-row"><div class="plc-name">${esc(name)}</div>` +
      `<button type="button" class="drv-act plc-restore">恢复</button></div>`).join("");
    const sig = JSON.stringify(all);
    if (sig !== plcSig) { plcSig = sig; renderPlaces(); }
  } catch (err) {
    toast(`常用地点加载失败: ${err.message}`);
  } finally {
    if (gen === plcGen) $("#plc-loading").hidden = true;
  }
}

// 行点击 (冒泡层): 点行体 = 开组详情层 (改名/解除编组删除都在那边, 行上
// 没有别的控件了)。hint = 详情层改名存下的新名 (按它找新行就地续开; 留空
// 还原分裂成多组时找不到 = 收层), 不带 = 删点路, 按旧名找
$("#plc-list").addEventListener("click", e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const g = t.closest(".plc-g");
  if (!g) return;
  const idx = [...$("#plc-list").children].indexOf(g.parentElement);
  if (idx < 0 || !plcRows[idx]) return;
  const row = plcRows[idx];
  openPlaceDetail(row, async hint => {
    await loadPlaces();
    return plcRows.find(r => r.name === (hint ?? row.name)) || null;
  });
});

// 已删除分区: 恢复 = 删隐藏行, 统计里原样回来
$("#plc-hid-list").addEventListener("click", async e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.closest(".plc-restore")) return;
  const name = t.closest(".plc-hid-row").querySelector(".plc-name").textContent;
  try {
    await sendJSON("/tesla/trips/api/stats/place-hide", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ places: [name], hidden: false }),
    });
  } catch (err) {
    toast(`恢复失败: ${err.message}`);
  }
  await loadPlaces();
});

bindGestures($("#plc-scroll"), { drawer: true, ptr: true, onRefresh: loadPlaces });
registerView("settings-places", {
  title: "常用地点",
  el: $("#view-settings-places"),
  show: loadPlaces,    // 每次进来都拉 (统计页那边改了名这里要跟着新; 没变
                       // 不重铺, 旧列表原样顶着 —— v7 异步化)
  refresh: loadPlaces,
});
