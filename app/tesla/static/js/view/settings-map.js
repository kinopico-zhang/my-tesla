// view/settings-map.js — 地图设置视图 (P6, 拆自旧设置页的高德卡): 服务商
// (高德/OpenStreetMap, 用户点名可切换) + Key/安全码/地图样式现值载入与保存。
// 选 OSM 时 Key/样式整组收起 (不用 Key); 样式预设外的值 (自定义样式 ID) 落
// 「自定义…」档回填。旧版底座 ($/esc/toast/api) 在 settings-connections.js,
// 壳版由 tesla-common 接管; TeslaMate 卡拆去 view/settings-db.js。
/* global $, toast, getJSON, sendJSON, mapLib, bindGestures, registerView */
"use strict";

let mapProviderPrev = "amap";   // 载入时的服务商: 保存时对比, 换过要让适配层重读配置

const PROVIDER_HINTS = {
  amap: "高德: 国内瓦片快, 轨迹/热力/断档补路全功能; 需要上面填的 Web 端 Key。",
  osm: "OpenStreetMap: 不用 Key 开箱即用, 坐标系原生 WGS-84; 底图来自国际社区, 国内访问可能偏慢, 断档补路退化为虚线直连。",
};
function syncProviderRows() {
  const osm = $("#map-provider").value === "osm";
  $("#amap-rows").hidden = osm;
  $("#map-provider-hint").textContent = PROVIDER_HINTS[$("#map-provider").value] || "";
}

async function mapSetLoad() {
  const s = await getJSON("/tesla/api/settings");
  mapProviderPrev = s.amap.provider || "amap";
  $("#map-provider").value = s.amap.provider || "amap";
  syncProviderRows();
  $("#amap-now").textContent = s.amap.key_masked || "未设置";
  $("#amap-code").placeholder = s.amap.security_code_set ? "已设置 · 留空保持" : "未设置";
  const st = s.amap.style || "amap://styles/dark";
  const sel = $("#amap-style");
  const known = [...sel.options].some(o => o.value === st);
  sel.value = known ? st : "custom";       // 预设外 (自定义 ID) → 自定义档回填
  $("#amap-style-custom-row").hidden = sel.value !== "custom";
  if (!known) $("#amap-style-custom").value = st;
}

$("#map-provider").addEventListener("change", syncProviderRows);
$("#amap-style").addEventListener("change", () => {
  $("#amap-style-custom-row").hidden = $("#amap-style").value !== "custom";
});

$("#amap-save").addEventListener("click", async () => {
  const btn = $("#amap-save");
  btn.disabled = true;
  try {
    await sendJSON("/tesla/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        map_provider: $("#map-provider").value,
        amap_key: $("#amap-key").value.trim(),
        amap_security_code: $("#amap-code").value,
        amap_style: $("#amap-style").value === "custom"
          ? $("#amap-style-custom").value.trim() : $("#amap-style").value,
      }),
    });
    $("#amap-key").value = ""; $("#amap-code").value = "";
    const providerNow = $("#map-provider").value;
    if (providerNow !== mapProviderPrev) {
      /* 换服务商: 适配层作废缓存的配置 (还没起过地图的话下次现读新的);
         已起过的地图实例是旧引擎, 要整页刷新才换得干净 */
      mapLib.reset();
      mapProviderPrev = providerNow;
      toast("已切换地图服务商, 刷新页面后生效");
    } else {
      toast("已保存, 刷新地图页生效");
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
