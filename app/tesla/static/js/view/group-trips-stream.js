// view/group-trips-stream.js — 弹层第四页「详细行程」(3.10.0) 2/3: 流 —
// 行渲染 (进入即多选态: 钩 = 分组成员, 组内行默认全钩, 组外行无钩;
// 点行打/撤钩与「取消/确定」落定在 group-trips-marks), 默认窗口 = 组内
// 全部 (id 升序 = 落库序 = 出发序, 时间正序), 两端拉动加载组外候选
// (顶部下拉 prepend 视口钉原首行, 尾部触底 IO + 首屏不满链式续载)。
/* global $, esc, num, fmtCardDate, fmtDur, getJSON, toast, bindGestures,
          PRELOAD_PX */
/* exported gtrStart, gtrLoadBefore, gtrRefreshRows, gtrGroup, gtrSel, gtrResetSel */
"use strict";

const GTR_PAGE = 24;    // 两端拉动一次拉多少条组外候选

let gtrGid = null;      // 当前分组 (挂页时 gtrStart 带来)
let gtrStream = [];     // 已加载行程 (id 升序), 与 #gtr-list 子元素一一对应
let gtrGroup = null;    // 当前分组条目 (成员端点判定用)
let gtrSel = new Set(); // 钩集 (行程 id): 进入 = 组内全部, 点行增删 (marks 侧)
let gtrMoreB = false, gtrMoreA = false;   // 两端还有没有组外候选 (服务端口径)
let gtrBusy = false;    // 一次只跑一个加载 (下拉/触底/重试并发防抖)

/* 复位钩集回服务端原样 (挂页/重拉/取消都走这) */
function gtrResetSel() {
  gtrSel = new Set(gtrStream.filter(x => x.in_group).map(x => x.id));
}

/* 起终点短地名: trips-list-page 的 shortPlace 是顶层裸名 (经典脚本 =
   全局), 撞名各自覆盖, 这里改名复制保口径 (市 · 最小行政级, 地名不混
   入; 解析不出链退回整串) */
function gtrShortPlace(region, full) {
  const seg = (region || "").split(" · ").filter(Boolean);
  const pp = seg.length >= 3 ? seg.slice(-2) : seg.slice(-1);
  return pp.length ? pp.join(" · ") : full;
}

function gtrRow(it) {
  const el = document.createElement("article");
  const on = gtrSel.has(it.id);
  el.className = "card-t gtr-row" + (on ? " in" : "");
  el.dataset.id = it.id;
  // 起终点整行: 模板渲染的优先 (设置页「地点显示」, 与行程列表同口径),
  // 没模板/渲染空走本地拼装
  const fromP = it.from_place || gtrShortPlace(it.from_region, it.from);
  const toP = it.to_place || gtrShortPlace(it.to_region, it.to);
  el.innerHTML = `
    <div class="ct-top">
      <span class="ct-date">${esc(fmtCardDate(it.start))}</span>
      <span class="pick" aria-hidden="true"></span>
    </div>
    <div class="ct-cells">
      <div class="ct-cell"><div class="lb">里程</div>
        <div class="val">${it.km != null ? num(it.km) + "<small>km</small>" : "—"}</div></div>
      <div class="ct-cell"><div class="lb">时长</div><div class="val">${fmtDur(it.min)}</div></div>
      ${it.kwh != null ? `<div class="ct-cell"><div class="lb">总电耗</div>
        <div class="val">${num(it.kwh)}<small>kWh</small></div></div>` : ""}
    </div>
    <div class="ct-addr mq-line"><span class="mq-run"><i class="dot f"></i>${esc(fromP)}<span class="arr">→</span><i class="dot t"></i>${esc(toP)}</span></div>`;
  return el;
}

/* 起终点行超宽滚动: trips-list-page 同款, 量宽限本视图 (藏着量不出宽,
   跳过不挂; 转屏后重量防抖) */
function gtrMarquee() {
  for (const line of $("#gtr-list").querySelectorAll(".mq-line")) {
    const run = line.querySelector(".mq-run");
    run.classList.remove("marquee");
    if (!line.clientWidth) continue;
    const over = run.scrollWidth - line.clientWidth;
    if (over <= 2) continue;
    run.style.setProperty("--mq-dx", `${-over}px`);
    run.style.setProperty("--mq-dur", `${Math.max(8, over / 18)}s`);
    run.classList.add("marquee");
  }
}
addEventListener("resize", () => setTimeout(gtrMarquee, 200));

function gtrRender() {
  $("#gtr-list").innerHTML = "";
  for (const it of gtrStream) $("#gtr-list").appendChild(gtrRow(it));
  $("#gtr-top").hidden = !gtrMoreB;    // 两端提示行: 还有候选才亮, 拉空即收
  $("#gtr-top").textContent = "下拉加载更早的行程";
  $("#gtr-tail").hidden = !gtrMoreA;
  $("#gtr-tail").textContent = "上拉加载更后的行程";
  gtrMarquee();
}

/* 默认窗口: 组内全部 (挂页/重试都走这), 复位钩集与两端候选旗标 */
async function gtrLoad() {
  if (gtrBusy || !gtrGid) return;
  gtrBusy = true;
  gtrStream = []; gtrGroup = null;
  $("#gtr-errbox").hidden = true;
  $("#gtr-spin").hidden = false;
  try {
    const d = await getJSON(`/tesla/trips/api/groups/${gtrGid}/trips`);
    gtrGroup = d.group;
    gtrStream = d.items;
    gtrMoreB = d.has_more_before;
    gtrMoreA = d.has_more_after;
    gtrResetSel();   // 进入即多选: 组内全部起钩
    gtrRender();
  } catch {
    $("#gtr-errbox").hidden = false;
  }
  $("#gtr-spin").hidden = true;
  gtrBusy = false;
}

/* 顶部下拉: 加载更前的组外候选, 头前插入后按增量回补 scrollTop ——
   视口钉在原首行不跳 (prepend 掉高度差就会闪滚) */
async function gtrLoadBefore() {
  if (gtrBusy || !gtrMoreB || !gtrStream.length) return;
  gtrBusy = true;
  const sc = $("#gtr-scroll");
  const h0 = sc.scrollHeight;
  try {
    const d = await getJSON(
      `/tesla/trips/api/groups/${gtrGid}/trips?before=${gtrStream[0].id}&limit=${GTR_PAGE}`);
    gtrStream = d.items.concat(gtrStream);   // 服务端给 id 升序, 直接头前接
    gtrMoreB = d.has_more_before;
    gtrRender();
    sc.scrollTop += sc.scrollHeight - h0;
  } catch {
    toast("加载失败");
  }
  gtrBusy = false;
}

/* 尾部触底: 加载更后的组外候选; 首屏没填满 (哨兵还在预载区里 IO 不再
   触发) 链式续载直到哨兵滚出预载区 (充电/行程列表同款) */
async function gtrLoadAfter() {
  if (gtrBusy || !gtrMoreA || !gtrStream.length) return;
  gtrBusy = true;
  let ok = false;
  try {
    const d = await getJSON(
      `/tesla/trips/api/groups/${gtrGid}/trips?after=${gtrStream[gtrStream.length - 1].id}&limit=${GTR_PAGE}`);
    gtrStream = gtrStream.concat(d.items);
    gtrMoreA = d.has_more_after;
    gtrRender();
    ok = true;
  } catch {
    toast("加载失败");
  }
  gtrBusy = false;
  if (ok && gtrMoreA &&
      $("#gtr-tail").getBoundingClientRect().top < innerHeight + PRELOAD_PX)
    gtrLoadAfter();
}

/* 哨兵常驻: 页藏起 (display:none) 不相交, 不会偷跑 */
new IntersectionObserver(es => {
  if (es[0].isIntersecting) gtrLoadAfter();
}, { rootMargin: PRELOAD_PX + "px" }).observe($("#gtr-tail"));

/* 就地翻行: 只重画钩态不符的行 (选/未选类), 其余已加载行原样保留 ——
   分页拉的页不丢, 不整页重拉 */
function gtrRefreshRows() {
  for (const el of [...$("#gtr-list").children]) {
    const it = gtrStream.find(x => x.id === +el.dataset.id);
    if (it && el.classList.contains("in") !== gtrSel.has(it.id))
      el.replaceWith(gtrRow(it));
  }
  gtrMarquee();
}

/* 挂页 (trips-sheet-stats 的 gtrPageSync 调, 弹层开着分组行程): 复位
   钩集与已加载窗口, 拉组内全部 */
function gtrStart(gid) {
  if (gid == null) return;
  gtrGid = gid;
  gtrLoad();
}

/* 重试 (错误盒) 与手势: 竖滑滚列表 / 顶部到顶下拉加载更早; 横滑让给分
   页器原生滚页 (drawer 关 —— 弹层里没有抽屉手势), 方向锁仲裁各认各的 */
$("#gtr-retry").addEventListener("click", () => gtrLoad());
bindGestures($("#gtr-scroll"), { drawer: false, ptr: true,
  onRefresh: () => gtrLoadBefore() });
