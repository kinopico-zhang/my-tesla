// view/settings-map.js — 地图设置视图 (P6, 拆自旧设置页的高德卡): 两张卡
// 各配一把高德 Key (类型不同不能混用) —— 「地图显示」卡 Web端(JS API) 型,
// 浏览器渲染/轨迹/断档补路用; 「足迹道路拟合」卡 Web服务 型, 服务端把轨迹
// 拟合到实际道路用 (worker 每轮现读, 保存即踢)。2026-09-25 用户点名「地图
// 只保留高德」, 服务商切换整组退役。样式预设外的值 (自定义样式 ID) 落
// 「自定义…」档回填。旧版底座 ($/esc/toast/api) 在 settings-connections.js,
// 壳版由 tesla-common 接管; TeslaMate 卡拆去 view/settings-db.js。
/* global $, toast, getJSON, sendJSON, mapLib, bindGestures, registerView */
"use strict";

let mapStylePrev = "amap://styles/dark";
const curStyle = () => $("#amap-style").value === "custom"
  ? $("#amap-style-custom").value.trim() : $("#amap-style").value;

async function mapSetLoad() {
  const s = await getJSON("/tesla/api/settings");
  $("#amap-now").textContent = s.amap.key_masked || "未设置";
  $("#amap-web-now").textContent = s.amap.web_key_masked || "未设置";
  $("#amap-code").placeholder = s.amap.security_code_set ? "已设置 · 留空保持" : "未设置";
  const st = s.amap.style || "amap://styles/dark";
  const sel = $("#amap-style");
  const known = [...sel.options].some(o => o.value === st);
  sel.value = known ? st : "custom";       // 预设外 (自定义 ID) → 自定义档回填
  $("#amap-style-custom-row").hidden = sel.value !== "custom";
  if (!known) $("#amap-style-custom").value = st;
  mapStylePrev = curStyle();
}

$("#amap-style").addEventListener("change", () => {
  $("#amap-style-custom-row").hidden = $("#amap-style").value !== "custom";
});

$("#amap-save").addEventListener("click", async () => {
  const btn = $("#amap-save");
  // 高德 Key 绑在引擎脚本 URL 上, 页内换不净 (要整页刷新); 其余配置都能热换
  const keyChanged = $("#amap-key").value.trim() !== "";
  const touched = curStyle() !== mapStylePrev
    || keyChanged || $("#amap-code").value !== "";
  btn.disabled = true;
  try {
    await sendJSON("/tesla/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amap_key: $("#amap-key").value.trim(),
        amap_security_code: $("#amap-code").value,
        amap_style: curStyle(),
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
      : "已切换地图样式, 打开地图即生效");
    await mapSetLoad();
  } catch (err) {
    toast(`保存失败: ${err.message}`);
  } finally {
    btn.disabled = false;
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
