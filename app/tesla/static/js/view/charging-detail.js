// view/charging-detail.js — 充电记录视图 (壳版 4/6): 详情底部弹层 —— 开合/
// 下滑关闭/Escape 分层关闭 + 详情渲染 (统计区两行六格: 电量×2+续航增加 /
// 总价+每度价格+充电时间 / 电量与充电曲线合并成一张双轴图, 档位切换只换
// 右轴那条线)。
// 曲线档位 (功率/电压/电流) 由后端下发 —— 车辆快充不回报电压电流 (死字段),
// 有真数据的档才出按钮, 只剩功率时整条档位条都不渲染。
// 壳版差异: 元素 id 与导出名加 chg- 前缀 (壳里多视图并存, #sheet/#backdrop
// 留给行程页, closeSheet 在充电地图/足迹地图也各有一份); chartText/tooltipStyle
// 同理 (充电统计页也有一份); echarts 按需注入 (loadEcharts, 壳不默认拖图表库)。
/* global $, esc, num, money, fmtCardDate, fmtPlace, fmtMinAxis, fmtDur,
          getJSON, detailCache, loadEcharts, bindSheetDrag, bindSheetSettle,
          chgCloseAlert, TESLA_MARK */
/* exported chgOpenSheet, chgSheetBody, chgAlertBd, chgAlInput,
            chgSheetOpen, chgCurrentDetailId, chgChartText, chgTooltipStyle */
"use strict";
/* ============================ 详情图表样式 (统计图表卡在充电统计页) ============================ */
const chgChartText = { axis: "#898781", ink: "#c3c2b7" };
const chgTooltipStyle = {
  backgroundColor: "rgba(28,28,30,.95)", borderWidth: 0, padding: [7, 10],
  textStyle: { color: "#f5f5f7", fontSize: 12 },
};

/* ============================ 详情 Sheet ============================ */
const chgSheet = $("#chg-sheet"), chgBackdrop = $("#chg-backdrop"), chgSheetBody = $("#chg-sheet-body");
const chgAlertBd = $("#chg-alert-bd"), chgAlInput = $("#chg-al-input");
let chPw, pwMode = "kw", chgSheetOpen = false, chgCurrentDetailId = null;
const PW_SERIES = {
  kw:       { name: "功率", color: "#3987e5", unit: "kW", key: "kw" },
  voltage:  { name: "电压", color: "#9085e9", unit: "V",  key: "voltage" },
  current:  { name: "电流", color: "#d95926", unit: "A",  key: "current" },
};

function chgOpenSheet(id) {
  chgSheetOpen = true;
  chgSheet.classList.add("on"); chgBackdrop.classList.add("on");
  chgSheetBody.innerHTML = `<div class="spin"></div>`;
  loadDetail(id);
}
function chgCloseSheet() {
  chgSheetOpen = false; chgCurrentDetailId = null;
  chgSheet.classList.remove("on"); chgBackdrop.classList.remove("on");
  if (chPw) chPw.dispose(); chPw = null;
}
chgBackdrop.addEventListener("click", chgCloseSheet);
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if (!chgAlertBd.hidden) chgCloseAlert();
  else if (chgSheetOpen) chgCloseSheet();
  else return;                          // 没关任何层: 放行给后注册的层
  e.stopImmediatePropagation();         // 一层一关 (2026-10-02 全弹窗「从哪来
                                        // 回哪去」): 别再串关筛选气泡/抽屉
});

/* 下滑关闭 (tesla-sheet-drag 壳级, iOS 安全规矩见彼处注释): 把手点一下
   也关; 信息区与正文 (统计格/费用条/图表/地址 —— 用户点名没有下滑事件
   的控件全补上; 正文一屏装下, 不欠滚动) 拖下收起, 点一下不关, 费用条/
   档位钮照常点。✕ 已撤 (用户点名): 关闭就这几条路 —— 任意处下滑、
   点蒙层、Esc。 */
bindSheetDrag(chgSheet, $("#chg-grab-zone"), chgCloseSheet, true);
bindSheetDrag(chgSheet, $("#chg-sheet .sheet-head"), chgCloseSheet, false);
bindSheetDrag(chgSheet, chgSheetBody, chgCloseSheet, false);
bindSheetSettle(chgSheet, "on");   // 视口折腾后强制废弃旧栅格 (7556 壳层丢失的保险)

async function loadDetail(id) {
  let d;
  try {
    d = detailCache.get(id) || await getJSON(`/tesla/charging/api/sessions/${id}`);
    detailCache.set(id, d);
  } catch (e) {
    chgSheetBody.innerHTML = `<div class="err-box"><p>加载失败: ${esc(e.message)}</p></div>`;
    return;
  }
  if (!chgSheetOpen) return;
  chgCurrentDetailId = id;
  const rangeGain = d.end_rated_range != null && d.start_rated_range != null
    ? d.end_rated_range - d.start_rated_range : null;
  const pwTabs = d.curve.tabs;                 // 有真数据的档 (kw 恒在)
  if (!pwTabs.includes(pwMode)) pwMode = "kw"; // 上次的档这次没有 → 折回功率
  /* 快慢充标签钉右上角与日期同行 (用户点名); Tesla 官方桩的文字标立到
     pill 左边 (2026-09-27 用户点名「tesla 的tag是额外的tag, 该是快充和
     慢充还是要打对应的 tag」+「换个位置, 快慢充一直在右上角」: pill 常驻
     最右, 字标退居其左, 与列表卡同款白字不套底); 地点行与列表同款
     只留最小两段 (fmtPlace), 整链在底部地址行, 线缆/类型留在下面的标签行 */
  const shCls = d.is_fast ? "tag-fast" : "tag-slow";
  const shLb = d.is_fast ? "快充" : "慢充";
  $("#chg-sh-tag").innerHTML =
    (d.tesla_supercharger
      ? `<span class="tesla-mark" aria-label="Tesla 超充">${TESLA_MARK}</span>` : "") +
    `<span class="tag ${shCls}">${shLb}</span>`;
  $("#chg-sh-date").textContent = fmtCardDate(d.start);
  $("#chg-sh-loc").textContent = fmtPlace(d);
  $("#chg-sh-row").innerHTML =
    (d.cable ? `<span class="tag tag-slow" style="color:var(--ink-2);background:var(--surface-2)">${esc(d.cable)}</span>` : "") +
    (d.charger_type ? `<span class="tag tag-slow" style="color:var(--ink-2);background:var(--surface-2)">${esc(d.charger_type)}</span>` : "");
  /* 统计区只留曲线里没有的 (用户点名: 电量变化/峰值功率看图就有):
     第一行三格 = 两口径电量 + 续航增加; 第二行也是三格 = 总价 (可点补录)
     + 每度价格 + 充电时间 —— 2026-09-29 追点「总价这个框改到1格宽,
     多出来的位置加一个充电时间」: 总价从占两格收成一格, 时长当初撤掉
     (看图就有) 这次点名要回, 改口充电时间住末格, 「1时44分」与行程页
     同口径 (fmtDur) —— 整个详情一屏装下不用滚 */
  chgSheetBody.innerHTML = `
    <div class="st-grid">
      <div class="st"><div class="lb">充入电量</div><div class="val">${num(d.energy_added)}<small> kWh</small></div></div>
      <div class="st"><div class="lb">表计电量</div><div class="val">${num(d.energy_used)}<small> kWh</small></div></div>
      <div class="st"><div class="lb">续航增加</div><div class="val">${rangeGain != null ? "+" + num(rangeGain, 0) : "—"}<small> km</small></div></div>
      <div class="st st-cost" id="st-cost-tile"><div class="lb">总价</div><div class="val${d.cost == null ? " red" : ""}" id="st-cost-val">${d.cost != null ? money(d.cost) : "未记费用"}</div></div>
      <div class="st"><div class="lb">每度价格</div><div class="val" id="st-price-val">${d.price_per_kwh != null ? "¥" + d.price_per_kwh.toFixed(3) : "—"}</div></div>
      <div class="st"><div class="lb">充电时间</div><div class="val">${fmtDur(d.duration_min)}</div></div>
    </div>
    <div class="sh-chart-title">
      <span>充电曲线</span>
      ${pwTabs.length > 1 ? `<div class="mini-seg" id="pw-seg">` +
        pwTabs.map(k => `<button data-v="${k}"${k === pwMode ? ' class="on"' : ""}>${PW_SERIES[k].name}</button>`).join("") + `</div>` : ""}
    </div>
    <div id="chart-pw"></div>
    <div class="sh-addr">${esc(d.address || "")}${d.outside_temp != null ? ` · 平均气温 ${num(d.outside_temp, 0)}°C` : ""}</div>`;

  const pwSeg = $("#pw-seg");                  // 只剩一档时没有档位条
  if (pwSeg) pwSeg.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    pwSeg.querySelector(".on").classList.remove("on"); b.classList.add("on");
    pwMode = b.dataset.v; renderPwChart(d);
  });

  requestAnimationFrame(async () => {
    let ec;
    try { ec = await loadEcharts(); }             // 按需注入; 弹层已关就不画了
    catch (_e) { return; }
    if (!chgSheetOpen) return;
    chPw = ec.init($("#chart-pw"));
    renderPwChart(d);
  });
}

/* 电量与所选曲线合一张图 (用户点名): 左轴电量 % (绿), 右轴功率/电压/电流
   随档换色; 两轴刻度各染各的曲线色、轴顶各标轴义 (用户点名), 横轴截到
   曲线终点不空尾巴; 换档只换右轴那条线 */
function renderPwChart(d) {
  if (!chPw) return;
  const s = PW_SERIES[pwMode], cv = d.curve, vals = cv[s.key];
  const yMax = Math.max(...vals, 1);
  const xMax = cv.minutes.length ? cv.minutes[cv.minutes.length - 1] : null;
  chPw.setOption({
    animationDuration: 250,
    grid: { left: 6, right: 6, top: 26, bottom: 0, containLabel: true },   // 顶距给轴名留位
    tooltip: { ...chgTooltipStyle, trigger: "axis",
               axisPointer: { type: "cross", lineStyle: { color: "#898781" },
                              crossStyle: { color: "#5a5a5e" } },
               formatter: ps => {
                 const i = ps[0].dataIndex;
                 return `${fmtMinAxis(ps[0].axisValue)} · 电量 <b>${cv.soc[i]}%</b><br/>` +
                        `${s.name} <b>${vals[i]} ${s.unit}</b>` +
                        (cv.energy[i] != null ? `<br/>累计 ${num(cv.energy[i])} kWh` : "");
               } },
    xAxis: { type: "value", min: 0, max: xMax,
             axisLine: { show: false }, axisTick: { show: false },
             axisLabel: { color: chgChartText.axis, fontSize: 10, formatter: fmtMinAxis },
             splitLine: { lineStyle: { color: "#2c2c2a" } } },
    yAxis: [
      { type: "value", min: 0, max: 100,
        name: "电量 %", nameGap: 8,              // 轴义标在轴顶 (用户点名)
        nameTextStyle: { color: "#1fa349", fontSize: 10, fontWeight: 600, align: "left" },
        splitLine: { lineStyle: { color: "#2c2c2a" } },
        axisLabel: { color: "#1fa349", fontSize: 10, formatter: "{value}%" } },  // 刻度跟电量曲线同色
      { type: "value", min: 0, max: Math.ceil(yMax * 1.08),
        name: `${s.name} ${s.unit}`, nameGap: 8, // 换档跟着换 (功率 kW/电压 V/电流 A)
        nameTextStyle: { color: s.color, fontSize: 10, fontWeight: 600, align: "right" },
        splitLine: { show: false },
        axisLabel: { color: s.color, fontSize: 10 } },
    ],
    series: [
      { type: "line", yAxisIndex: 0, data: cv.minutes.map((t, i) => [t, cv.soc[i]]),
        showSymbol: false, sampling: "lttb",
        lineStyle: { color: "#1fa349", width: 2 }, itemStyle: { color: "#1fa349" },
        areaStyle: { color: "rgba(31,163,73,.10)" } },
      { type: "line", yAxisIndex: 1, data: cv.minutes.map((t, i) => [t, vals[i]]),
        showSymbol: false, sampling: "lttb",
        lineStyle: { color: s.color, width: 2 }, itemStyle: { color: s.color } },
    ],
  }, { replaceMerge: ["series"] });
}
