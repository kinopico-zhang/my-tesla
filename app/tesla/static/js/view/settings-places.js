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
// v9 (2026-10-17): 页首加「地点显示」卡 —— 三界面模板 (行程起终点/充电
// 地点/常用地点), 服务端渲染 + 防抖预览 + 专用端点保存 (语义见下方卡块)。
// v10 (2026-10-18 用户点名「每个都表示什么含义要说清楚 + 用选择代替填
// 空」): 模板手填退役 —— 部件与整条格式全改点选。部件一枚一义 (上行变量
// 名 + 下行一行小字含义), 点一下插进「蓝框」目标框的光标处 —— 点部件会
// 收起键盘 (focus 跑掉), 目标得自己记 (最后点过的框, .ptpl-target 常亮
// 蓝边与 :focus 同色); 整条格式点一下直接替换目标框 (空值 = 回默认);
// 预览进页就跑一次 (不再是冷启动空块)。
// v11 (2026-10-18 用户点名「回删名称的时候, 应该以最小单元来删除」): 删
// 除键认单元 —— 光标贴着完整 {变量} / " · " 一下整删 (逐字抠既费手又留
// 半截变量, 渲染成原样文字); 没贴着完整单元交回原生逐字符 (手打中途改
// 错不受影响), 选区/组合键 (Ctrl+删除删词)/输入法组字不拦, 前删 Delete
// 同口径对称。
// v12 (2026-10-18 用户点名「把下面的选项做成键盘, 当用户把光标放进去的
// 时候, 就弹出来的自定义键盘, 替换标准键盘。输入的时候, 下面时时刻刻
// 显示具体的例子」): 键盘化 —— 三框 inputmode=none 挡掉系统软键盘, 聚
// 焦即开卡内键盘 (整条/部件/间隔/删除/收起), 失焦即收; 键区 pointerdown
// preventDefault 叫焦点留在框里 (键永远不抢焦点, :focus 蓝框即目标, 三
// 框间切换不闪), preventDefault 后 :active 不一定吃, 按下态自己铺; 预览
// 搬进键盘常驻 —— 输入全程看得见具体例子, 正在编辑的那行描蓝。
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

// ---- 地点显示模板 (2026-10-17 用户点名「在设置界面, 可以设置各个界面
// 显示地点的模板」; 2026-10-18 二改「用选择代替填空」, 三改「做成键盘,
// 替换标准键盘, 输入时下面时时刻刻显示具体的例子」): 三界面各一条, 渲
// 染单一源在服务端 (place_naming 的 render_place), 这里只搬运 —— 改动
// (键入/手输) 停 300ms POST preview 换预览行 (预览住进键盘常驻, 样例 =
// 缓存里组件最全的一条地名, 进页先预取, 开键盘即亮), 保存走专用端点:
// 主设置保存把空串当「保持现值」(密码语义), 模板的空串是合法值 (= 回
// 默认), 两家语义不同不能合一个接口。
const PTPL_KEYS = [["trips", "行程起终点"], ["charging", "充电地点"],
                   ["places", "常用地点"]];
// 整条格式速选: [键面文字, 模板原文] —— 点一下替换目标框, 空串 = 回默认
const PTPL_PRESETS = [["默认显示", ""], ["区 · 地点", "{区} · {POI}"],
                      ["市 · 区", "{市} · {区}"], ["完整地址", "{推荐}"]];
// 部件键: [键面, 含义, 插入文本] —— 含义即「每个都表示什么」的答案 (一
// 行小字随键走, 键面窄, 措辞比 v10 的钮面收紧); 插入文本缺省 = 键面原文
const PTPL_VARS = [
  ["{名字}", "地点名"], ["{省}", "省份"], ["{市}", "城市"], ["{区}", "区县"],
  ["{镇}", "街道/镇"], ["{路}", "道路"], ["{门牌}", "门牌号"],
  ["{POI}", "附近地点"], ["{推荐}", "完整地址"]];
// 间隔键与动作键 (键盘末行): 动作键第三段是 data-act —— back = 按最小
// 单元删 (v11 口径), close = 收键盘 (失焦即收的主动入口)
const PTPL_SEPS = [["·", "间隔", " · "], ["空格", "间隔", " "]];
const PTPL_ACTS = [["删除", "按单元", "back"], ["收起", "关键盘", "close"]];
let ptplTimer = 0;
let ptplCloseTimer = 0;   // 收键盘缓一拍: 三框间换焦点 blur 先到, 别闪
let ptplTarget = null;    // 正在编辑的框 (聚焦驱动 —— 键区不抢焦点, 键入
//                        期间焦点恒在框里; 失焦 = 真去了别处 = 收)

function ptplBody() {
  return JSON.stringify({
    trips: $("#ptpl-trips").value.trim(),
    charging: $("#ptpl-charging").value.trim(),
    places: $("#ptpl-places").value.trim(),
  });
}

function ptplKick() {     // 改动停 300ms 再换预览 (键入/手输共用一条防抖)
  clearTimeout(ptplTimer);
  ptplTimer = setTimeout(ptplPreview, 300);
}

function ptplMark() {   // 预览里正在编辑的那行描蓝 (跟着焦点走, 纯本地)
  const cur = ptplTarget ? ptplTarget.id.slice(5) : "";   // "ptpl-trips" → "trips"
  for (const ln of $("#ptpl-preview").querySelectorAll(".ptpl-line[data-k]"))
    ln.classList.toggle("ptpl-on", ln.dataset.k === cur);
}

function ptplOpen() {   // 聚焦即开: 键盘面板 + 预览立刻亮 (不坐防抖)
  clearTimeout(ptplCloseTimer);
  const kb = $("#ptpl-kb");
  kb.hidden = false;
  kb.scrollIntoView({ block: "nearest" });   // 面板别开出屏幕外
  ptplMark();
  ptplPreview();
}

function ptplClose() {  // 失焦即收 —— 缓一拍: 紧接着的 focus (三框间切换) 会取消
  clearTimeout(ptplCloseTimer);
  ptplCloseTimer = setTimeout(() => {
    $("#ptpl-kb").hidden = true;
    ptplTarget = null;
  }, 0);
}

function ptplInsert(txt) {   // 插进目标框光标处 (选中段一并换掉), 光标跟到插完尾后
  const el = ptplTarget;
  const at = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? at;
  if (el.value.length + txt.length - (end - at) > 80) {
    toast("格式太长了 (最多 80 字)");   // 与服务端上限同数, 超了也存不进
    return;
  }
  el.value = el.value.slice(0, at) + txt + el.value.slice(end);
  const next = at + txt.length;
  try { el.setSelectionRange(next, next); }   // 老内核不吃: 光标留末尾不碍事
  catch { /* setSelectionRange 不支持 */ }
  ptplKick();
}

// 删除认的最小单元 (v11): 完整闭合的 {变量} 与间隔键落的 " · " 原样
const PTPL_UNIT_VAR = /\{[^{}]*\}$/;   // 回删: 光标前整段闭合变量
const PTPL_UNIT_FWD = /^\{[^{}]*\}/;   // 前删 (Delete) 同口径: 光标后整段
const PTPL_UNIT_SEP = " · ";           // 间隔 (连两侧空格一起走)

function ptplUnitLen(el, back) {
  // 光标贴着的完整单元长度 (0 = 没贴着): 物理删除键与键盘删除键共用;
  // 有选区不按单元删 (交回原生删选区)
  const at = el.selectionStart, end = el.selectionEnd;
  if (at === null || at !== end) return 0;
  if (back) {
    const head = el.value.slice(0, at);
    return PTPL_UNIT_VAR.exec(head)?.[0].length
        ?? (head.endsWith(PTPL_UNIT_SEP) ? PTPL_UNIT_SEP.length : 0);
  }
  const tail = el.value.slice(at);
  return PTPL_UNIT_FWD.exec(tail)?.[0].length
      ?? (tail.startsWith(PTPL_UNIT_SEP) ? PTPL_UNIT_SEP.length : 0);
}

function ptplCut(el, len, back) {   // 删 len 字 (back = 往左), 光标落切口
  const at = el.selectionStart;
  const cut = back ? at - len : at;
  el.value = el.value.slice(0, cut) + el.value.slice(cut + len);
  try { el.setSelectionRange(cut, cut); }   // 老内核不吃: 光标留末尾不碍事
  catch { /* setSelectionRange 不支持 */ }
  ptplKick();
}

function ptplKeyDelete(el, e, back) {
  // 物理删除键 (带事件: 组合键 Ctrl+删除删词 / 输入法组字放行原生);
  // 没贴着完整单元交回原生逐字符 (手打中途改错不受影响)
  if (e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
  const len = ptplUnitLen(el, back);
  if (!len) return;
  e.preventDefault();
  ptplCut(el, len, back);
}

function ptplBuildKeys() {
  const key = (lb, cap, attr) =>
    `<button type="button" class="ptpl-key"${attr}>` +
    `<span class="ptpl-vlb">${esc(lb)}</span>` +
    `<span class="ptpl-vcap">${esc(cap)}</span></button>`;
  $("#ptpl-presets").innerHTML = PTPL_PRESETS.map(([lb, val]) =>
    `<button type="button" class="ptpl-preset" data-val="${esc(val)}">${esc(lb)}</button>`).join("");
  $("#ptpl-vars").innerHTML = PTPL_VARS.map(([lb, cap, txt]) =>
    key(lb, cap, ` data-txt="${esc(txt ?? lb)}"`)).join("");
  $("#ptpl-seps").innerHTML =
    PTPL_SEPS.map(([lb, cap, txt]) => key(lb, cap, ` data-txt="${esc(txt)}"`)).join("") +
    PTPL_ACTS.map(([lb, cap, act]) => key(lb, cap, ` data-act="${esc(act)}"`)).join("");
}

async function loadPlaceTpls() {
  try {
    const d = await getJSON("/tesla/api/place-templates");
    for (const [k] of PTPL_KEYS) $("#ptpl-" + k).value = d[k] || "";
  } catch (err) {
    toast(`地点显示模板加载失败: ${err.message}`);
  }
  ptplPreview();     // 进页预取: 开键盘即亮, 不吃首开空窗
}

async function ptplPreview() {
  try {
    const d = await sendJSON("/tesla/api/place-templates/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: ptplBody(),
    });
    const box = $("#ptpl-preview");   // 住进键盘常驻 (显隐随面板走)
    if (!d.sample) {   // 命名还没跑过: 预览没原料, 说明白而不是空块
      box.innerHTML = `<div class="ptpl-line">还没有可用的地名样例 (等后台命名跑完再来预览)</div>`;
      return;
    }
    box.innerHTML = `<div class="ptpl-line ptpl-sample">样例: ${esc(d.sample)}</div>` +
      PTPL_KEYS.map(([k, lb]) =>
        `<div class="ptpl-line" data-k="${k}"><span class="ptpl-lb">${lb}</span>` +
        `<span>${esc(d[k] || "(默认显示)")}</span></div>`).join("");
    ptplMark();     // 行重铺了, 描蓝跟着回
  } catch (err) {
    toast(`预览失败: ${err.message}`);
  }
}

ptplBuildKeys();
for (const [k] of PTPL_KEYS) {
  const el = $("#ptpl-" + k);
  el.addEventListener("input", ptplKick);
  el.addEventListener("keydown", e => {   // 物理删除键同单元口径 (桌面还在用)
    if (e.key === "Backspace") ptplKeyDelete(el, e, true);
    else if (e.key === "Delete") ptplKeyDelete(el, e, false);
  });
  el.addEventListener("focus", () => { ptplTarget = el; ptplOpen(); });
  el.addEventListener("blur", ptplClose);
}

// 键盘面板 (冒泡层): pointerdown 掐掉「挪焦点」的默认行为 —— 焦点/光标
// 留在正编辑的框里, 键才插得进光标处, :focus 蓝框也才亮得住 (失焦即收
// 的前提); preventDefault 后 :active 不一定吃, 按下态自己铺 (.ptpl-press)
$("#ptpl-kb").addEventListener("pointerdown", e => {
  e.preventDefault();
  const k = e.target instanceof Element && e.target.closest(".ptpl-key, .ptpl-preset");
  if (k) k.classList.add("ptpl-press");
});
function ptplUnpress() {   // 指针起来/滑出取消: 按下态卸掉
  for (const k of $("#ptpl-kb").querySelectorAll(".ptpl-press"))
    k.classList.remove("ptpl-press");
}
$("#ptpl-kb").addEventListener("pointerup", ptplUnpress);
$("#ptpl-kb").addEventListener("pointercancel", ptplUnpress);

// 键分派 (冒泡层): 动作键 (收起/删除) → 整条格式 (替换) → 部件/间隔 (插
// 光标处)
$("#ptpl-kb").addEventListener("click", e => {
  if (!(e.target instanceof Element) || !ptplTarget) return;
  const k = e.target.closest(".ptpl-key, .ptpl-preset");
  if (!k) return;
  const act = k.dataset.act;
  if (act === "close") { ptplTarget.blur(); return; }   // 失焦即收 (同一条路)
  if (act === "back") {
    const len = ptplUnitLen(ptplTarget, true);
    if (len) ptplCut(ptplTarget, len, true);
    return;
  }
  if ("val" in k.dataset) {             // 整条格式: 一键替换
    ptplTarget.value = k.dataset.val;
    ptplKick();
    return;
  }
  ptplInsert(k.dataset.txt);            // 部件/间隔: 落进光标处
});

$("#ptpl-save").addEventListener("click", async () => {
  try {
    await sendJSON("/tesla/api/place-templates", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: ptplBody(),
    });
    toast("地点显示已保存");
    ptplPreview();
  } catch (err) {
    toast(`保存失败: ${err.message}`);
  }
  if (ptplTarget) ptplTarget.blur();   // 存完收键盘 (macOS 点钮不夺焦点)
});

registerView("settings-places", {
  title: "常用地点",
  el: $("#view-settings-places"),
  show: () => { loadPlaces(); loadPlaceTpls(); },   // 模板值也每次现拉 (别处
  //                                  改过/清过这里要跟着新; 列表照旧 v7 异步化)
  refresh: loadPlaces,
});
