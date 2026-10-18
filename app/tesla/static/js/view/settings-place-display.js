// view/settings-place-display.js — 地点显示 (2026-10-17 用户点名「高德给
// 的地址要完完整整的结构化地存起来, 然后在设置界面, 可以设置各个界面
// 显示地点的模板」; 起家住 settings-places 常用地点页, 2026-10-18 五改
// 后独立成页): 一界面一卡 (行程起终点/充电地点/常用地点), 卡 = 标题 +
// tag 列表输入区 + 2-3 条真实地名例子。
// v10 (同日「含义说清楚 + 用选择代替填空」): 部件点选代替手填, 一枚一义。
// v11 (同日「回删按最小单元」): 删除认 {变量}/" · " 整段。
// v12 (同日「做成键盘替换标准键盘 + 时时刻刻显示具体例子」): 三框
// inputmode=none + 卡内键盘 + 预览常驻。
// v13 (同日「地点显示要独立配置页面, 不要和常用地点放在一起」): 拆来
// 本页 (settings-places.js 只剩常用地点管理)。
// v14 (同日「一界面一卡; 输入框不是 textbox, 是 tag 列表的空间; 键盘上
// 的内容就是部件」): 文本框整链退役 —— 模板拆成最小单元的标签 ({变量}
// 蓝 / 间隔与手输残文灰), 点标签即删 (v11 的单元删除天然成立, 没有光
// 标), 键盘部件键接到标签列表末尾; 例子从键盘常驻预览改为一卡一区
// 2-3 条 (服务端渲染, 改动停 300ms 即换), 整条格式速选退役 (拼一条就
// 两三下), 清空键 = 回默认。
// 保存走专用端点: 主设置保存把空串当「保持现值」(密码语义), 模板的
// 空串是合法值 (= 回默认), 两家语义不同不能合一个接口。
/* global $, esc, getJSON, sendJSON, toast, bindGestures, registerView */
"use strict";

const PTPL_KEYS = [["trips", "行程起终点"], ["charging", "充电地点"],
                   ["places", "常用地点"]];
// 部件键: [键面, 含义] —— 含义即「每个都表示什么」的答案 (一行小字随
// 键走); 插入文本 = 键面原文 ({省} 整段带花括号)
const PTPL_VARS = [
  ["{名字}", "地点名"], ["{省}", "省份"], ["{市}", "城市"], ["{区}", "区县"],
  ["{镇}", "街道/镇"], ["{路}", "道路"], ["{门牌}", "门牌号"],
  ["{POI}", "附近地点"], ["{推荐}", "完整地址"]];
// 末行控制键: [键面, 含义, 插入文本/data-act] —— 间隔走 data-txt 同部
// 件路, 其余动作分派: back 去末尾 / clear 回默认 / close 关键盘
const PTPL_SEPS = [["·", "间隔", " · "], ["空格", "间隔", " "]];
const PTPL_ACTS = [["删除", "去末尾", "back"], ["清空", "回默认", "clear"],
                   ["收起", "关键盘", "close"]];

const PTPL_VAR_RE = /\{[^{}]*\}/;    // 单元判别 (是不是 {变量})
let ptplUnits = { trips: [], charging: [], places: [] };   // 每卡的最小单元串
let ptplActive = "";   // 正在编辑的卡 key ("" = 没在编辑)
let ptplTimer = 0;     // 改动停 300ms 再换例子 (防抖)

function ptplParse(tpl) {
  // 存的模板 → 最小单元串: {变量} 一段一段抠出来, 夹着的字面 (间隔/老
  // 数据手输的残文) 各自成段 —— 标签列表画的就是它, 删除去掉的也是它
  const out = [];
  let last = 0, m;
  const re = /\{[^{}]*\}/g;
  while ((m = re.exec(tpl))) {
    if (m.index > last) out.push(tpl.slice(last, m.index));
    out.push(m[0]);
    last = m.index + m[0].length;
  }
  if (last < tpl.length) out.push(tpl.slice(last));
  return out;
}

function ptplTagLabel(u) {
  if (PTPL_VAR_RE.exec(u)) return u.slice(1, -1);   // {省} → 省
  if (u === " · ") return "·";
  if (u === " ") return "空格";
  return u;    // 老数据手输的字面: 原样亮出来 (不藏)
}

function ptplRenderField(k) {
  const units = ptplUnits[k];
  $(`#ptpl-field-${k}`).innerHTML = units.length
    ? units.map((u, i) =>
        `<button type="button" class="ptpl-tag${PTPL_VAR_RE.exec(u) ? "" : " lit"}"` +
        ` data-i="${i}">${esc(ptplTagLabel(u))}</button>`).join("")
    : `<span class="ptpl-ghost">默认显示</span>`;
}

function ptplBody() {
  return JSON.stringify({
    trips: ptplUnits.trips.join(""),
    charging: ptplUnits.charging.join(""),
    places: ptplUnits.places.join(""),
  });
}

function ptplKick() {     // 改动停 300ms 再换例子 (所有改法共用一条防抖)
  clearTimeout(ptplTimer);
  ptplTimer = setTimeout(ptplPreview, 300);
}

function ptplChanged() {
  ptplRenderField(ptplActive);
  ptplKick();
}

function ptplActivate(k) {
  // 点卡进入编辑: 键盘 (单件) 搬进这张卡 —— appendChild 搬家监听不丢,
  // 三张卡共用一副键盘, 住在正在编辑的卡里
  ptplActive = k;
  for (const [kk] of PTPL_KEYS)
    $(`#ptpl-card-${kk}`).classList.toggle("on", kk === k);
  const kb = $("#ptpl-kb");
  kb.hidden = false;
  $(`#ptpl-card-${k}`).appendChild(kb);
  kb.scrollIntoView({ block: "nearest" });   // 面板别开出屏幕外
}

function ptplClose() {   // 退出编辑 (收起键/点编辑卡外/存完/换页)
  ptplActive = "";
  $("#ptpl-kb").hidden = true;
  for (const [k] of PTPL_KEYS) $(`#ptpl-card-${k}`).classList.remove("on");
}

// 点编辑卡之外 = 退出编辑。走 click 不走 pointerdown: 滚动手势只发
// pointerdown 不发 click, 边看例子边滚屏不该把键盘收了
document.addEventListener("click", e => {
  if (!ptplActive) return;
  if (e.target instanceof Element &&
      e.target.closest(`#ptpl-card-${ptplActive}`)) return;
  ptplClose();
});

function ptplAdd(txt) {   // 部件/间隔: 接到标签列表末尾
  const arr = ptplUnits[ptplActive];
  if (arr.join("").length + txt.length > 80) {
    toast("格式太长了 (最多 80 字)");   // 与服务端上限同数, 超了也存不进
    return;
  }
  arr.push(txt);
  ptplChanged();
}

function ptplBuildKeys() {
  const key = (lb, cap, attr) =>
    `<button type="button" class="ptpl-key"${attr}>` +
    `<span class="ptpl-vlb">${esc(lb)}</span>` +
    `<span class="ptpl-vcap">${esc(cap)}</span></button>`;
  $("#ptpl-vars").innerHTML = PTPL_VARS.map(([lb, cap]) =>
    key(lb, cap, ` data-txt="${esc(lb)}"`)).join("");
  $("#ptpl-acts").innerHTML =
    PTPL_SEPS.map(([lb, cap, txt]) => key(lb, cap, ` data-txt="${esc(txt)}"`)).join("") +
    PTPL_ACTS.map(([lb, cap, act]) => key(lb, cap, ` data-act="${esc(act)}"`)).join("");
}

// 键分派 (冒泡层): 动作键 (收起/删除/清空) → 部件/间隔 (接末尾)
$("#ptpl-kb").addEventListener("click", e => {
  if (!ptplActive) return;
  const k = e.target instanceof Element && e.target.closest(".ptpl-key");
  if (!k) return;
  const act = k.dataset.act;
  if (act === "close") { ptplClose(); return; }
  if (act === "back") { ptplUnits[ptplActive].pop(); ptplChanged(); return; }
  if (act === "clear") { ptplUnits[ptplActive] = []; ptplChanged(); return; }
  ptplAdd(k.dataset.txt);
});

for (const [k] of PTPL_KEYS) {
  $(`#ptpl-field-${k}`).addEventListener("click", e => {
    // 点标签 (编辑态): 删这个标签 —— 标签就是最小单元, 点谁删谁; 没在
    // 编辑时点标签/点空白 = 进入编辑 (别顺手把人删了)
    const tag = e.target instanceof Element && e.target.closest(".ptpl-tag");
    if (tag && ptplActive === k) {
      ptplUnits[k].splice(Number(tag.dataset.i), 1);
      ptplRenderField(k);
      ptplKick();
      return;
    }
    ptplActivate(k);
  });
}

async function loadPlaceTpls() {
  try {
    const d = await getJSON("/tesla/api/place-templates");
    for (const [k] of PTPL_KEYS) {
      ptplUnits[k] = ptplParse(d[k] || "");
      ptplRenderField(k);
    }
  } catch (err) {
    toast(`地点显示模板加载失败: ${err.message}`);
  }
  ptplPreview();     // 进页预取: 例子区不空窗
}

async function ptplPreview() {
  try {
    const d = await sendJSON("/tesla/api/place-templates/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: ptplBody(),
    });
    for (const [k] of PTPL_KEYS) {
      $(`#ptpl-ex-${k}`).innerHTML = !d.rows.length
        ? `<div class="ptpl-exline">还没有地名样例 (等后台命名跑完)</div>`
        : d.rows.map(r =>
            `<div class="ptpl-exline"><span class="ptpl-src">${esc(r.sample)}</span>` +
            `<span>${esc(r[k] || "(默认显示)")}</span></div>`).join("");
    }
  } catch (err) {
    toast(`例子刷新失败: ${err.message}`);
  }
}

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
  ptplClose();   // 存完收键盘退出编辑
});

ptplBuildKeys();
bindGestures($("#ptpl-scroll"), { drawer: true, ptr: true, onRefresh: loadPlaceTpls });
registerView("settings-place-display", {
  title: "地点显示",
  el: $("#view-settings-place-display"),
  show: () => { loadPlaceTpls(); },   // 每次进页现拉 (别处改过/清过要跟着新)
  hide: ptplClose,   // 换页收键盘 (没有输入框了, 失焦这条路不存在)
  refresh: loadPlaceTpls,
});
