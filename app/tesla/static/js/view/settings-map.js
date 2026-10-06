// view/settings-map.js — 地图设置视图 (P6, 拆自旧设置页的高德卡): 两张卡
// 各配一把高德 Key (类型不同不能混用) —— 「地图显示」卡 Web端(JS API) 型,
// 浏览器渲染/轨迹/断档补路用; 「足迹道路拟合」卡 Web服务 型, 服务端把轨迹
// 拟合到实际道路用 (worker 每轮现读, 保存即踢)。2026-09-25 用户点名「地图
// 只保留高德」, 服务商切换整组退役; 2026-10-05 地图样式选择整链退役
// (用户点名「不允许用户选择」, 固定幻影黑住适配层), 同日两轮说明行改版:
// 长说明先删, 换一行获取方式, 已填的 key 在框里显掩码 (住 placeholder,
// 留空仍 = 保持现值)。旧版底座 ($/esc/toast/api) 在 settings-connections.js,
// 壳版由 tesla-common 接管; TeslaMate 卡拆去 view/settings-db.js。
// v12 (2026-10-06 用户点名「地图设置界面, 添加两个测试按钮」): 两张卡各
// 配一枚「测试」。
// v13 (同日追点「测试正常只显示正常就行了, 只有测试正常才能保存」): 测试
// 改测「框里的候选」—— Web端走适配层 mapLib.probeKey 在独立 iframe 里装
// 引擎建小图 (Key/安全码钉在引擎脚本上, 与本页引擎互不沾, 不用先保存也
// 不用刷新页面), Web服务把候选 POST 给服务端打一次逆地理; 通过只报
// 「正常」, 输入一变作废重测, 测试通过才解锁保存 (v12 的「测已保存值/
// 未保存先拦」旧路退役 —— 那路与保存闸死循环)。
/* global $, toast, getJSON, sendJSON, mapLib, bindGestures, registerView */
"use strict";

async function mapSetLoad() {
  const s = await getJSON("/tesla/api/settings");
  // 已填的 key 在框里显掩码 (2026-10-05 用户点名「中间几位用 * 掩掉」):
  // 住 placeholder —— 留空提交仍是「保持现值」, 掩码串不会被打包存成新 key
  $("#amap-key").placeholder = s.amap.key_masked
    ? `${s.amap.key_masked} · 留空保持` : "未设置";
  $("#amap-code").placeholder = s.amap.security_code_set ? "已设置 · 留空保持" : "未设置";
  $("#amap-web-key").placeholder = s.amap.web_key_masked
    ? `${s.amap.web_key_masked} · 留空保持` : "未设置";
}

/* 保存闸状态: 候选测试通过了才 true (输入一变作废) —— 两个保存钮的
   finally 读它决定回锁还是留开, 声明得走在保存钮前面 */
let amapOk = false, webOk = false;

$("#amap-save").addEventListener("click", async () => {
  const btn = $("#amap-save");
  // 高德 Key 绑在引擎脚本 URL 上, 页内换不净 (要整页刷新); 安全码能热换
  const keyChanged = $("#amap-key").value.trim() !== "";
  const touched = keyChanged || $("#amap-code").value !== "";
  btn.disabled = true;
  try {
    await sendJSON("/tesla/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amap_key: $("#amap-key").value.trim(),
        amap_security_code: $("#amap-code").value,
      }),
    });
    $("#amap-key").value = ""; $("#amap-code").value = "";
    if (touched) {
      /* 免刷新生效 (你问的「为什么改地图要刷新页面」): 配置只在引擎启动时
         读一次, 而足迹/充电地图/轨迹弹层的地图实例是常驻的, 带着旧引擎 ——
         以前只能整页刷新。现在 reset 重读配置 + ready() 预热新引擎, swap
         事件让常驻实例自毁, 下次进各视图自动重建 (实时页本来就每次重建) */
      mapLib.reset();
      try { await mapLib.ready(); } catch { /* 预热失败: 进地图页时各视图的错误兜底接管 */ }
      dispatchEvent(new CustomEvent("maplib:swap"));
    }
    toast(!touched ? "已保存"
      : keyChanged ? "已保存; 高德 Key 换了刷新一次页面才生效 (Key 绑在地图引擎上)"
      : "已保存, 打开地图即生效");
    await mapSetLoad();
  } catch (err) {
    toast(`保存失败: ${err.message}`);
  } finally {
    btn.disabled = !amapOk;           // 保存闸: 测试通过才开着 (存败候选没变)
  }
});

$("#amap-web-save").addEventListener("click", async () => {
  const btn = $("#amap-web-save");
  const changed = $("#amap-web-key").value.trim() !== "";
  btn.disabled = true;
  try {
    await sendJSON("/tesla/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amap_web_key: $("#amap-web-key").value.trim() }),
    });
    $("#amap-web-key").value = "";
    if (changed) {
      /* Web 服务 key 是 worker 每轮现读的, 踢一下立即开跑 (不用等 60s 空转轮) */
      try { await getJSON("/tesla/map/api/roads/tick"); } catch { /* worker 没起也不算保存失败 */ }
      toast("已保存, 拟合在后台跑 (足迹地图左下角图例有进度)");
    } else {
      toast("已保存");
    }
    await mapSetLoad();
  } catch (err) {
    toast(`保存失败: ${err.message}`);
  } finally {
    btn.disabled = !webOk;            // 保存闸: 测试通过才开着 (存败候选没变)
  }
});

/* ---------- 测试钮 + 保存闸 (v12 添钮, v13 追点「只有测试正常才能保存」):
   测的是「框里的候选」—— 空框回落现值, 与保存同一口径。通过只报
   「正常」; 输入一变作废 (要重测), 测试通过才解锁保存。 */
const amapGate = () => { $("#amap-save").disabled = !amapOk; };
const webGate = () => { $("#amap-web-save").disabled = !webOk; };
for (const id of ["amap-key", "amap-code"])
  $("#" + id).addEventListener("input", () => { amapOk = false; amapGate(); });
$("#amap-web-key").addEventListener("input", () => { webOk = false; webGate(); });
amapGate(); webGate();               // 进页先锁: 测过才许存

$("#amap-test").addEventListener("click", async () => {
  const btn = $("#amap-test");
  btn.disabled = true;
  amapOk = false; amapGate();        // 重测从锁起跑
  try {
    // 候选: 框里有值用框里的, 空框回落现值 (config 端点明文拿, 引擎装载
    // 走的就是它)
    let key = $("#amap-key").value.trim(), code = $("#amap-code").value;
    if (!key || !code) {
      const cfg = await getJSON("/tesla/map/api/config?_=" + Date.now());
      key = key || cfg.amap_key || "";
      code = code || cfg.security_code || "";
    }
    if (!key) { toast("测试未通过: 还没填 Key"); return; }
    // 独立 iframe 装候选引擎建小图 + 逆地理验真伪 (探针住适配层);
    // 通过时带回结论整句 (正常 / Key 有效但限流), 直接转述
    const verdict = await mapLib.probeKey(key, code);
    amapOk = true; amapGate();
    toast(verdict);
  } catch (err) {
    toast(`测试未通过: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

// Web服务候选: 结论整句由服务端给 (通过 detail 就是「正常」; 配额限流算
// 「有效但限流」, 网络不通算不过), 前端只转述
$("#amap-web-test").addEventListener("click", async () => {
  const btn = $("#amap-web-test");
  btn.disabled = true;
  webOk = false; webGate();
  try {
    const r = await sendJSON("/tesla/map/api/web-key-test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: $("#amap-web-key").value.trim() }),
    });
    if (!r.ok) { toast(`测试未通过: ${r.detail}`); return; }
    webOk = true; webGate();
    toast(r.detail);
  } catch (err) {
    toast(`测试失败: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

bindGestures($("#mapset-scroll"), { drawer: true, ptr: true, onRefresh: mapSetLoad });
registerView("settings-map", {
  title: "地图设置",
  el: $("#view-settings-map"),
  show: mapSetLoad,   // 每次进来都拉现值 (样式可能被数据来源视图那边的保存带上)
  refresh: mapSetLoad,
});
