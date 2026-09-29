// view/groups-page.js — 行程分组视图 (壳版): 分组存自有库 (trips 的
// api/groups), 打开 = 合并弹层直接开 (openMerged 带分组名 —— 弹层已升
// 壳级, 分组页自己当宿主, 背后停在分组列表不再闪行程轨迹; sheetFrom 记
// 来源供关弹层跳回)。创建入口在行程列表 (长按多选 → 存为分组), 本视图
// 只管浏览/打开/改名/删除。卡片样式对齐行程列表 (card-t 同一套,
// 2026-09-22 用户点名「大致一样」)。
// 旧版 (js/groups.js) 的 $/esc/toast/页签菜单/顶栏刷新/登出上移壳模块。
/* global $, esc, num, toast, registerView, bindGestures, openMerged,
          bumpOpenSeq, closeTrip, hideSheet, curKey, rec, stopRecExport,
          sheetFrom: writable */
/* exported gpLoad, sheetFrom */   // sheetFrom 只写不读 (记弹层宿主), exported 豁免
"use strict";

let groups = [];      // 列表当前数据 (渲染 + 委托处理器查用)

/* 卡片结构仿行程卡 (card-t): 顶行名字 + 段数 pill, 中段统计格 (里程/跨度),
   底行改名/删除 —— 整卡可点开, 按钮拦住各自的事。 */
function rowHTML(g) {
  return `<div class="gp-item card-t" data-gid="${g.id}" data-ids="${g.ids.join(",")}">` +
    `<div class="ct-top"><span class="gp-name">${esc(g.name)}</span>` +
    `<span class="gp-count">${g.n} 段</span></div>` +
    `<div class="ct-cells">` +
    `<div class="ct-cell"><div class="lb">里程</div>` +
    `<div class="val">${g.km != null ? num(g.km) + "<small>km</small>" : "—"}</div></div>` +
    (g.span ? `<div class="ct-cell"><div class="lb">跨度</div>` +
      `<div class="val gp-span">${esc(g.span)}</div></div>` : "") +
    `</div>` +
    `<div class="gp-acts"><button class="gp-act gp-rename">改名</button>` +
    `<button class="gp-act gp-del">删除</button></div></div>`;
}

function render() {
  $("#gp-spin").hidden = true;
  $("#gp-empty").hidden = groups.length > 0;
  $("#gp-count-badge").textContent = groups.length ? `${groups.length} 组` : "";
  $("#gp-list").innerHTML = groups.map(rowHTML).join("");
}

async function gpLoad() {
  $("#gp-errbox").hidden = true;
  $("#gp-spin").hidden = false;
  try {
    const r = await fetch("/tesla/trips/api/groups");
    if (r.status === 401) { location.replace("/login"); return; }
    if (!r.ok) throw new Error(`${r.status}`);
    groups = await r.json();
  } catch {
    groups = [];
    $("#gp-spin").hidden = true;
    $("#gp-errbox").hidden = false;
  }
  render();
}

/* 行点击委托: 整卡点开 (弹层直接开在分组页头上, sheetFrom 记来源供地址栏
   镜像 view=groups; 关弹层停在原列表不刷新, 2026-09-25 用户点名);
   改名行内编辑; 删除二次确认 (3s 内再点才删)。
   行内重渲染会脱链事件目标 —— 委托先判 isConnected (与行程页同一坑)。 */
$("#gp-list").addEventListener("click", async e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;
  const item = t.closest(".gp-item");
  if (!item) return;
  const gid = +item.dataset.gid;
  const group = groups.find(g => g.id === gid);
  if (t.closest(".gp-del")) {
    const btn = t.closest(".gp-del");
    if (!btn.classList.contains("arm")) {          // 第一次点: 挂起 3s
      btn.classList.add("arm"); btn.textContent = "确认删除";
      setTimeout(() => { btn.classList.remove("arm"); btn.textContent = "删除"; }, 3000);
      return;
    }
    try {
      const r = await fetch(`/tesla/trips/api/groups/${gid}`, { method: "DELETE" });
      if (r.status === 401) { location.replace("/login"); return; }
      if (!r.ok) throw new Error(`${r.status}`);
      groups = groups.filter(g => g.id !== gid);
      render();
      toast("已删除分组");
    } catch { toast("删除失败"); }
  } else if (t.closest(".gp-rename")) {
    item.innerHTML =
      `<div class="gp-edit"><input class="gp-input" value="${esc(group.name)}" maxlength="30">` +
      `<button class="gp-act gp-ok">确定</button>` +
      `<button class="gp-act gp-no">取消</button></div>`;
    const inp = item.querySelector(".gp-input");
    inp.focus(); inp.select();
  } else if (t.closest(".gp-ok")) {
    const name = item.querySelector(".gp-input").value.trim();
    if (!name) { toast("名字不能为空"); return; }
    try {
      const r = await fetch(`/tesla/trips/api/groups/${gid}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (r.status === 401) { location.replace("/login"); return; }
      if (!r.ok) throw new Error(`${r.status}`);
      group.name = name;
      render();
    } catch { toast("改名失败"); }
  } else if (t.closest(".gp-no")) {
    render();
  } else {
    if (item.querySelector(".gp-input")) return;   // 行内改名中: 点卡别误开
    /* 合并弹层直接开 (壳级, 零历史条目): 分组页自己当宿主 —— 背后停在
       分组列表 (不再跳行程视图闪「行程轨迹」, 2026-09-22 用户实报);
       裸逗号键 openMerged 自行识别 (旧版裸写, 编码成 %2C 会被截断);
       整个分组条目随键传入 (带汇总, 弹层数字带一开就显数, 2026-09-23
       用户点名「加载完地图才显示」), 分组名当弹层标题, sheetFrom 记来源 */
    sheetFrom = "groups";
    openMerged(item.dataset.ids, null, group);
  }
});

$("#gp-list").addEventListener("keydown", e => {
  if (!(e.target instanceof Element)) return;
  if (e.key === "Enter" && e.target.classList.contains("gp-input")) {
    e.preventDefault();
    e.target.closest(".gp-item").querySelector(".gp-ok").click();
  } else if (e.key === "Escape") {
    render();            // 行内改名的输入框: Esc 放弃
  }
});

$("#gp-retry").addEventListener("click", gpLoad);

/* 手势: 列表滚动器在顶下拉刷新 */
const gpScroll = $("#gp-scroll");
bindGestures(gpScroll, { drawer: true, ptr: true, onRefresh: gpLoad });

let gpBooted = false;
registerView("groups", {
  title: "行程分组",
  el: $("#view-groups"),
  show() { if (!gpBooted) { gpBooted = true; gpLoad(); } },
  /* 分组页也是弹层宿主 (壳级 sheet): 离开要收干净 —— 与行程视图 hide 同
     一套 (掐在途打开与流式下载 / 导出录制 / 弹层含地址栏镜像); sheetFrom
     先清, 主动换页不拽回; 多选态是行程页的事, 这里没有 */
  hide() {
    bumpOpenSeq();
    sheetFrom = null;
    if (rec) stopRecExport(true);
    if (curKey != null) closeTrip();
    else if ($("#sheet").classList.contains("show")) hideSheet();
  },
  refresh: gpLoad,
});
