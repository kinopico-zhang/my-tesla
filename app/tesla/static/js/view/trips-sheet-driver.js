// trips-sheet-driver.js — 轨迹弹层 (10/13): 弹层头部汇总 (单条/合并/占位),
// 驾驶员标注选单 (弹层头部纯文字按钮 + 卡片右上角 pill 直选小选单, 设置页
// 驾驶员表)。高速费估价链已撤 (用户点名先去掉: 自动估价/chip 全下线,
// 后端 /toll 接口与存量照留, 要恢复接回即可)。
/* global $, esc, num, parseLocal, fmtTime, fmtFullDate, fmtFullStamp,
   shiftStamp, fmtDur, getJSON, postJSON, driversCache: writable, openSeq,
   sheetTrip, items, listEl, renderCard, marqueeCards, toast */
/* exported fillSheetHeader, fillSheetHeaderPending, mergedSub, setSegTitle,
   setupDriverPicker, openDrvPick */
"use strict";
/* 弹层头部汇总 (日期/时长/里程/最高速/功耗): 单条来自卡片数据, 合并来自
   流式首行或整包缓存; 合并数据没到时先用占位, 到了再填 */
function fillSheetHeader(it) {
  if (it.gname) {    // 分组 (分组页打开): 名字当主标题, 副标题只留起始日期+时刻
    $("#sh-date").textContent = it.gname;
    $("#sh-time").textContent = mergedSub(it);
  } else if (it.merged) {    // 合并多段: 跨天给日期区间 (同年省后段年份), 同天照常; 时间列前缀段数
    const d1 = parseLocal(it.start), d2 = parseLocal(it.end);
    const md = d => `${d.getMonth() + 1}月${d.getDate()}日`;
    $("#sh-date").textContent = d1.toDateString() === d2.toDateString()
      ? fmtFullDate(it.start)
      : (d1.getFullYear() === d2.getFullYear()
         ? `${d1.getFullYear()}年${md(d1)} – ${md(d2)}`
         : `${d1.getFullYear()}年${md(d1)} – ${d2.getFullYear()}年${md(d2)}`);
    $("#sh-time").textContent = mergedSub(it);
  } else {
    // 日期带年份, 时刻并进左边同一串 (用户点名); 时刻只显出发 (范围太长)
    $("#sh-date").textContent = fmtFullDate(it.start);
    $("#sh-time").textContent = fmtTime(it.start);
  }
  $("#sh-km").innerHTML = '<span class="n">' + num(it.km) + "</span><small>km</small>";
  $("#sh-dur").innerHTML = '<span class="n">' + fmtDur(it.min) + "</span>";
  $("#sh-spd-lb").textContent = "最高车速";
  $("#sh-spd").innerHTML = '<span class="n">' + (it.speed_max != null ? it.speed_max : "—") + "</span><small>km/h</small>";
  // 总电耗/平均电耗格常显 (用户点名「那就显示NaN好了」): 数据缺席 (换算系
  // 数缺失/里程不足 1km) 显 — 占位, 不再整格藏起来 —— 格子忽隐忽现, 用户
  // 以为页坏了。num(null) 本身就给 —, 这里显式分叉只为不带 kWh 单位;
  // 有数时恒带一位小数 (2026-09-25 播放抖动同口径, 见 playback-loop)
  $("#sh-kwh").innerHTML = it.kwh == null
    ? "—" : '<span class="n">' + Number(it.kwh).toFixed(1) + "</span><small>kWh</small>";
  $("#sh-avg").innerHTML = it.wh_per_km == null
    ? "—" : '<span class="n">' + num(it.wh_per_km, 0) + "</span><small>Wh/km</small>";
  // 功耗格同款常显 (2026-09-25 用户点名「数字你可以没有, 但是那个灰色的
  // 块要提前出现」): 开弹层就亮格显 — 占位 (数字播放开始才有) —— 原先整格
  // 藏着, 点播放那一刻才蹦出来, 还把总电耗/平均电耗挤得挪一格; 真没功耗
  // 数据的行程开播时才收格 (session 门槛照旧, 只作用在真没数据的行程)
  $("#sh-cell-pw").hidden = false;
  $("#sh-pw-lb").textContent = "平均功耗";
  $("#sh-pw").textContent = "—";
}

/* 合并弹层副标题的静态口径 (打开时/播放收尾定格用): 分组名下显整组起始
   日期+时刻 (2026-09-25 用户点名星期让位给具体时:分), 非分组的合并显出发
   时刻 (主标题已带日期) —— 播放中由 setSegTitle 动态接管, 收尾 setOfficial
   再换回这 */
function mergedSub(it) {
  return it.n + " 段行程 · " + (it.gname ? fmtFullStamp(it.start) : fmtTime(it.start));
}

/* 播放中副标题: 第几段 + 当前点日期+时刻 (2026-09-25 用户点名「随着播放
   动态的变化, 显示第 x 段行程, 年月日」+「星期改成具体的小时和分钟」+
   「时间要实时变, 跟着轨迹的运动」) —— 播放会话每帧调 (trips-playback
   -session 的 apply, 播放/拖进度/重播统一走那), elapsed = 段首起的行驶秒,
   段首时刻平移它即当前点墙钟 (shiftStamp, 段内 ts 是原始时间戳差, 停车
   红灯都在内); t0 缺席 (旧载荷/老缓存) 回退整组 start */
function setSegTitle(it, k, t0, elapsed) {
  const txt = (it.n ? `第 ${k + 1}/${it.n} 段行程` : `第 ${k + 1} 段行程`)
            + " · " + fmtFullStamp(shiftStamp(t0 || it.start, elapsed));
  const el = $("#sh-time");
  if (el.textContent !== txt) el.textContent = txt;   // 分钟/段序没滚不重排
}

/* 合并数据在路上: 弹层先开 (阻断其他操作), 头部占位; 分组名已经知道,
   先亮名字再等数据 (用户点名名字置顶) */
function fillSheetHeaderPending(it) {
  $("#sh-date").textContent = it && it.gname ? it.gname : "连续轨迹";
  $("#sh-time").textContent = "正在下载…";
  $("#sh-km").textContent = "—";
  $("#sh-dur").textContent = "—";
  $("#sh-spd").textContent = "—";
  $("#sh-kwh").textContent = "—";
  $("#sh-avg").textContent = "—";
  // 功耗格常显 (2026-09-25): 合并数据在路上也先亮灰格占位, 不等播放
  $("#sh-cell-pw").hidden = false;
  $("#sh-pw-lb").textContent = "平均功耗";
  $("#sh-pw").textContent = "—";
}

/* ---------- 弹层驾驶员标注: 未标 = 未指定兜底, 没配驾驶员整行不显示 ---------- */
async function setupDriverPicker(it, seq) {
  const btn = $("#sh-drv-btn");
  btn.hidden = true;                             // 先藏, 数据到位再亮
  if (!it.merged) {                               // 合并多段: 驾驶员标注不适用
    if (driversCache === undefined) {
      try { driversCache = await getJSON("/tesla/api/drivers"); }
      catch { driversCache = null; }
    }
    if (seq !== openSeq) return;                  // 弹层已切走, 结果作废
    if (driversCache && driversCache.length > 0) {
      syncDrvBtn(it);                             // 纯文字: 名字 / 未指定
      btn.hidden = false;
    }
  }
}

/* 头部按钮文案与标注同步 (弹层打开时 + 标注写库后就地刷新);
   未标只写「未指定」—— 默认驾驶员的名字去底部选单里看 */
function syncDrvBtn(it) {
  $("#sh-drv-btn").textContent = it.driver_id != null ? it.driver : "未指定";
}

/* ---------- 标注写库 + 双入口就地更新 (弹层按钮 / 卡片小选单共用) ---------- */
async function assignDriver(it, driverId) {
  const upd = await postJSON(`/tesla/trips/api/${it.id}/driver`,
                             { driver_id: driverId });
  Object.assign(it, upd);                       // 弹层条目就地更新
  if (it === sheetTrip) syncDrvBtn(it);         // 头部纯文字按钮跟着刷新
  const card = items.find(x => x.id === upd.id);   // 列表条目 (分享直开时可能还没加载)
  if (card && card !== it) Object.assign(card, upd);
  const el = listEl.querySelector(`.card-t[data-id="${upd.id}"]`);
  if (el && card) el.replaceWith(renderCard(card));
  marqueeCards();                               // 换的新卡要重量起终点行
  toast(driverId == null ? "已清除标注" : `已标注为 ${upd.driver}`);
}

/* 头部驾驶员 = 纯文字按钮 (用户点名: 不框椭圆胶囊, 点击切换): 弹的是
   卡片右上角 pill 同一张底部选单 (iOS 动作单样式) */
$("#sh-drv-btn").addEventListener("click", () => {
  if (sheetTrip) openDrvPick(sheetTrip);
});

/* ---------- 卡片驾驶员直选 (用户点名: 点右上角 pill 弹小选单, 不用进详情) ---------- */
let drvPickTarget = null;

async function openDrvPick(it) {
  if (driversCache === undefined) {
    try { driversCache = await getJSON("/tesla/api/drivers"); }
    catch { driversCache = null; }
  }
  if (!driversCache || !driversCache.length) {
    toast("还没添加驾驶员 (设置 → 驾驶员)");
    return;
  }
  const def = driversCache.find(d => d.is_default);
  const cur = it.driver_id;
  $("#drv-pop-list").innerHTML =
    `<button type="button" class="drv-pop-row${cur == null ? " on" : ""}" data-id="">` +
    (def ? `未指定 · 默认${esc(def.name)}` : "未指定") + "</button>" +
    driversCache.map(d =>
      `<button type="button" class="drv-pop-row${cur === d.id ? " on" : ""}" data-id="${d.id}">` +
      esc(d.name) + "</button>").join("");
  drvPickTarget = it;
  $("#drv-pop").hidden = false;
}

function closeDrvPop() {
  drvPickTarget = null;
  $("#drv-pop").hidden = true;
}

$("#drv-pop-list").addEventListener("click", async e => {
  const btn = e.target.closest(".drv-pop-row");
  if (!btn || !drvPickTarget) return;
  const it = drvPickTarget;
  closeDrvPop();
  try { await assignDriver(it, btn.dataset.id === "" ? null : +btn.dataset.id); }
  catch (err) { toast(`标注失败: ${err.message}`); }
});
$("#drv-pop").addEventListener("click", e => {   // 点蒙版收 (选单卡自身不算)
  if (e.target === e.currentTarget) closeDrvPop();
});
$("#drv-pop-x").addEventListener("click", closeDrvPop);
