// chargemap-time-filters.js — 充电地图页 (3/3): 顶栏时间筛选 (快捷档 +
// 自定义日历, 连点两次选区间) 与 URL 同步 + 三视图切换 + 弹层/缩放/刷新/
// 退出收尾 + 启动 boot()。
// 由 chargemap.js 按域拆出 (结构化重构: 代码逐字节未动, 经典脚本按
// chargemap.html 里的顺序加载, 跨模块引用走全局); 底座在 chargemap-page.js,
// 热力渲染在 chargemap-heatmap.js。
/* global $, TIME_RANGES, pad, timeSel, view: writable, map, locations, boot,
          renderHeatmap, closeSheet, refresh */
"use strict";
function timeLabel() {
  if (timeSel.v === "custom")   // 自定义显示紧凑区间, 如 01/01–03/31
    return `${timeSel.from.slice(5).replace("-", "/")}–${timeSel.to.slice(5).replace("-", "/")}`;
  return TIME_RANGES.find(r => r.v === timeSel.v).lb;
}
function syncURL() {   // 筛选写进地址栏 (默认值不写, 链接保持干净)
  const u = new URL(location.href);
  if (timeSel.v === "custom") {
    u.searchParams.delete("range");
    u.searchParams.set("from", timeSel.from); u.searchParams.set("to", timeSel.to);
  } else {
    u.searchParams.delete("from"); u.searchParams.delete("to");
    if (timeSel.v === "all") u.searchParams.delete("range"); else u.searchParams.set("range", timeSel.v);
  }
  if (view === "energy") u.searchParams.delete("view"); else u.searchParams.set("view", view);
  history.replaceState(null, "", u);
}
function setTimeRange(v, skipRefresh) {
  timeSel.v = v;
  $("#time-lb").textContent = timeLabel();
  document.querySelectorAll("#time-opts button[data-v]").forEach(b =>
    b.classList.toggle("on", b.dataset.v === v));
  if (v !== "custom") $("#tm-dates").hidden = true;   // 回到快捷档, 收起日历
  syncURL();
  if (!skipRefresh) refresh(false);
}
/* ---------- 自定义日历: 同一个日历连点两次 —— 第一下起点, 第二下终点 ----------
   终点早于起点自动交换; 已有区间再点 = 重新开始选; 只点一下就确定 = 单日。 */
let calYm = "", calA = null, calB = null;    // 显示月 / 草稿起止 (ISO 日期)
const calCn = iso => { const p = iso.split("-"); return `${+p[1]}月${+p[2]}日`; };
function calRender() {
  const [y, m] = calYm.split("-").map(Number);
  $("#tm-ym").textContent = `${y}年${m}月`;
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7;   // 周一开头
  const days = new Date(y, m, 0).getDate();
  const n = new Date();
  const today = `${n.getFullYear()}-${pad(n.getMonth() + 1)}-${pad(n.getDate())}`;
  $("#tm-next").disabled = calYm >= today.slice(0, 7);     // 未来月没有数据
  let h = "";
  for (let i = 0; i < lead; i++) h += "<i></i>";
  for (let d = 1; d <= days; d++) {
    const iso = `${calYm}-${pad(d)}`;
    const cls = iso === calA || iso === calB ? "on"
      : calA && calB && iso > calA && iso < calB ? "mid" : "";
    h += `<button class="${cls}${iso === today ? " today" : ""}"
            data-d="${iso}" aria-label="${iso}">${d}</button>`;
  }
  $("#tm-cal").innerHTML = h;   // 重渲染会脱链点击目标, "点空白处收起" 的守卫兜底
  $("#tm-sel").textContent = !calA ? "点选开始日期"
    : !calB ? `已选开始 ${calCn(calA)}, 再点结束日期`
    : `${calCn(calA)} – ${calCn(calB)}`;
}
function calShift(k) {
  const [y, m] = calYm.split("-").map(Number);
  const t = new Date(y, m - 1 + k, 1);
  calYm = `${t.getFullYear()}-${pad(t.getMonth() + 1)}`;
  calRender();
}
function calOpen() {   // 打开日历: 带出已应用的自定义区间, 没有则从当月起
  calA = timeSel.from; calB = timeSel.to;
  calYm = (calA || `${new Date().getFullYear()}-${pad(new Date().getMonth() + 1)}`).slice(0, 7);
  calRender();
}
$("#tm-cal").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const d = b.dataset.d;
  if (!calA || calB) { calA = d; calB = null; }   // 新一轮: 重新选起点
  else if (d < calA) { calB = calA; calA = d; }   // 反着点: 自动交换
  else calB = d;                                  // 第二下 = 终点 (同一天 = 单日)
  calRender();
});
$("#tm-prev").addEventListener("click", () => calShift(-1));
$("#tm-next").addEventListener("click", () => calShift(1));
$("#time-opts").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || !b.dataset.v) return;   // 日历里的按钮 (日期/翻月/确定) 不走快捷档逻辑
  if (b.dataset.v === "custom") {   // 展开/收起日历, 连点两次选好再确定生效
    const box = $("#tm-dates");
    box.hidden = !box.hidden;
    if (!box.hidden) calOpen();
    return;
  }
  if (b.dataset.v === timeSel.v) return;
  $("#time-menu").removeAttribute("open");
  setTimeRange(b.dataset.v);
});
$("#tm-apply").addEventListener("click", () => {
  if (!calA) return;                // 一下都没点不生效
  $("#time-menu").removeAttribute("open");
  timeSel.from = calA;              // 只点了起点 = 单日
  timeSel.to = calB || calA;
  setTimeRange("custom");
});
$("#time-menu").addEventListener("toggle", () => {   // 重开菜单回到已应用区间
  if ($("#time-menu").open && !$("#tm-dates").hidden) calOpen();
});
setTimeRange(timeSel.v, true);

/* 三视图切换: 只换热力度量, 不重新请求数据 */
$("#view-seg").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || b.dataset.v === view) return;
  view = b.dataset.v;
  $("#view-seg .on").classList.remove("on"); b.classList.add("on");
  syncURL();
  if (map && locations.length) renderHeatmap();   // 地图没起来时记着状态, boot 后首渲染
});

$("#retry").addEventListener("click", () => refresh(false));
$("#recheck").addEventListener("click", () => location.reload());
$("#backdrop").addEventListener("click", closeSheet);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSheet(); });
$("#zin").addEventListener("click", () => map && map.zoomIn());
$("#zout").addEventListener("click", () => map && map.zoomOut());
/* 顶栏刷新: 重拉当前页数据 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  await refresh(false);
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
  location.href = "/login";
});

boot();
