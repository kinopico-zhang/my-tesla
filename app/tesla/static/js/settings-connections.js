// settings-connections.js — 软件设置页 (1/3): 页面底座 ($/esc/toast/api) +
// 现值载入 + TeslaMate 连接配置与高德 Key/地图样式保存。
// 由 settings.js 按域拆出 (结构化重构, 声明顺序与语义不变), 经典脚本按
// settings.html 里的顺序加载。
/* exported $, esc, toast, api, loadSettings */
"use strict";
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

let toastTimer = null;
function toast(msg, isErr) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", !!isErr);
  el.hidden = false;
  requestAnimationFrame(() => el.classList.add("on"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove("on");
    setTimeout(() => { el.hidden = true; }, 250);
  }, isErr ? 3500 : 1800);
}

async function api(path, opts) {
  const r = await fetch(path, Object.assign({ cache: "no-store" }, opts));
  if (r.status === 401) { location.replace("/login"); throw new Error("未登录"); }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error((body && body.detail) || `${r.status} ${r.statusText}`);
  return body;
}

/* ---------- 载入现值 ---------- */
async function loadSettings() {
  const s = await api("/tesla/api/settings");
  $("#tm-host").value = s.tmdb.host;
  $("#tm-port").value = s.tmdb.port;
  $("#tm-user").value = s.tmdb.user;
  $("#tm-name").value = s.tmdb.name;
  $("#tm-pass").value = "";
  $("#tm-pass").placeholder = s.tmdb.password_set ? "已设置 · 留空保持" : "未设置";
  $("#amap-now").textContent = s.amap.key_masked || "未设置";
  $("#amap-code").placeholder = s.amap.security_code_set ? "已设置 · 留空保持" : "未设置";
  const st = s.amap.style || "amap://styles/dark";
  const sel = $("#amap-style");
  const known = [...sel.options].some(o => o.value === st);
  sel.value = known ? st : "custom";       // 预设外 (自定义 ID) → 自定义档回填
  $("#amap-style-custom-row").hidden = sel.value !== "custom";
  if (!known) $("#amap-style-custom").value = st;
}

/* ---------- TeslaMate: 保存并实测 (真打一枪数据接口, 而不只 SELECT 1) ---------- */
$("#tm-save").addEventListener("click", async () => {
  const btn = $("#tm-save");
  btn.disabled = true; btn.textContent = "连接中…";
  try {
    await api("/tesla/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tmdb_host: $("#tm-host").value.trim(),
        tmdb_port: $("#tm-port").value.trim(),
        tmdb_user: $("#tm-user").value.trim(),
        tmdb_password: $("#tm-pass").value,
        tmdb_name: $("#tm-name").value.trim(),
      }),
    });
    await loadSettings();
    try {   // 再打一个真实数据接口, 确认业务查询也通
      await api("/tesla/trips/api/regions");
      toast("已保存 · 数据库连接正常");
    } catch { toast("已保存, 但数据查询失败, 请检查配置", true); }
  } catch (err) {
    toast(`保存失败: ${err.message}`, true);
  } finally {
    btn.disabled = false; btn.textContent = "保存并连接";
  }
});

/* ---------- 高德 Key / 地图样式 ---------- */
$("#amap-style").addEventListener("change", () => {
  $("#amap-style-custom-row").hidden = $("#amap-style").value !== "custom";
});
$("#amap-save").addEventListener("click", async () => {
  const btn = $("#amap-save");
  btn.disabled = true;
  try {
    await api("/tesla/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amap_key: $("#amap-key").value.trim(),
        amap_security_code: $("#amap-code").value,
        amap_style: $("#amap-style").value === "custom"
          ? $("#amap-style-custom").value.trim() : $("#amap-style").value,
      }),
    });
    $("#amap-key").value = ""; $("#amap-code").value = "";
    await loadSettings();
    toast("已保存, 刷新地图页生效");
  } catch (err) {
    toast(`保存失败: ${err.message}`, true);
  } finally {
    btn.disabled = false;
  }
});
