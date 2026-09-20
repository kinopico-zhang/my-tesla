// view/settings-db.js — 数据来源视图 (P6, 拆自旧设置页的 TeslaMate 卡):
// 现值载入 + 保存并实测 (真打一枪数据接口, 而不只 SELECT 1)。旧版底座
// ($/esc/toast/api) 在 settings-connections.js, 壳版由 tesla-common 的
// getJSON/sendJSON/toast 接管; 地图卡拆去 view/settings-map.js (旧页
// 一文件两卡, 壳里按抽屉导航拆成两个视图, 新 basename)。
/* global $, toast, getJSON, sendJSON, bindGestures, registerView */
"use strict";

/* 现值载入: 每次进视图都拉 (设置对象 db/map 两个视图共用, 对面改过不读到旧值) */
async function dbLoad() {
  const s = await getJSON("/tesla/api/settings");
  $("#tm-host").value = s.tmdb.host;
  $("#tm-port").value = s.tmdb.port;
  $("#tm-user").value = s.tmdb.user;
  $("#tm-name").value = s.tmdb.name;
  $("#tm-pass").value = "";
  $("#tm-pass").placeholder = s.tmdb.password_set ? "已设置 · 留空保持" : "未设置";
}

/* TeslaMate: 保存并实测 (改完立即换库重连, 连不上后端自动回滚) */
$("#tm-save").addEventListener("click", async () => {
  const btn = $("#tm-save");
  btn.disabled = true; btn.textContent = "连接中…";
  try {
    await sendJSON("/tesla/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tmdb_host: $("#tm-host").value.trim(),
        tmdb_port: $("#tm-port").value.trim(),
        tmdb_user: $("#tm-user").value.trim(),
        tmdb_password: $("#tm-pass").value,
        tmdb_name: $("#tm-name").value.trim(),
      }),
    });
    await dbLoad();
    try {   // 再打一个真实数据接口, 确认业务查询也通
      await getJSON("/tesla/trips/api/regions");
      toast("已保存 · 数据库连接正常");
    } catch { toast("已保存, 但数据查询失败, 请检查配置"); }
  } catch (err) {
    toast(`保存失败: ${err.message}`);
  } finally {
    btn.disabled = false; btn.textContent = "保存并连接";
  }
});

bindGestures($("#db-scroll"), { drawer: true, ptr: true, onRefresh: dbLoad });
registerView("settings-db", {
  title: "数据来源",
  el: $("#view-settings-db"),
  show: dbLoad,   // 无 boot 一次性态: 每次进来都拉现值 (对面视图可能改过)
  refresh: dbLoad,
});
