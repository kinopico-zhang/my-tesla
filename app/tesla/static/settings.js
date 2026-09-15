// settings.js — 由 settings.html 内联脚本抽出 (位置/顺序/语义不变), 供 lint 与测试
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

/* ---------- 驾驶员 ---------- */
let drivers = [];

function renderDrivers() {
  $("#drv-empty").hidden = drivers.length > 0;
  $("#drv-list").innerHTML = drivers.map(d =>
    `<div class="drv-row" data-id="${d.id}">` +
    `<div class="drv-name">${esc(d.name)}${d.is_default ? '<span class="drv-badge">默认</span>' : ""}</div>` +
    (d.is_default ? "" : `<button class="drv-act set-def">设为默认</button>`) +
    `<button class="drv-act del">删除</button></div>`).join("");
}

async function loadDrivers() {
  drivers = await api("/tesla/api/drivers");
  renderDrivers();
}

$("#drv-add").addEventListener("click", async () => {
  const name = $("#drv-name").value.trim();
  if (!name) return;
  try {
    await api("/tesla/api/drivers", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    $("#drv-name").value = "";
    await loadDrivers();
  } catch (err) {
    toast(`添加失败: ${err.message}`, true);
  }
});

$("#drv-name").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); $("#drv-add").click(); }
});

$("#drv-list").addEventListener("click", async e => {
  const t = e.target;
  if (!(t instanceof Element) || !t.isConnected) return;   // 重渲染脱链防误触
  const row = t.closest(".drv-row");
  if (!row) return;
  const id = +row.dataset.id;
  const opts = {
    method: "PATCH", headers: { "Content-Type": "application/json" },
  };
  try {
    if (t.closest(".set-def")) {
      await api(`/tesla/api/drivers/${id}`, Object.assign(opts,
        { body: JSON.stringify({ is_default: true }) }));
      await loadDrivers();
    } else if (t.closest(".del")) {
      if (!confirm("删除这个驾驶员?")) return;
      await api(`/tesla/api/drivers/${id}`, { method: "DELETE" });
      await loadDrivers();
    }
  } catch (err) {
    toast(`操作失败: ${err.message}`, true);
  }
});

/* ---------- 账号 (自助改名称 / 改密码) ---------- */
async function loadMe() {
  const me = await api("/api/me");
  $("#me-name").textContent = me.name;
}

$("#me-name-save").addEventListener("click", async () => {
  const btn = $("#me-name-save");
  btn.disabled = true;
  try {
    const me = await api("/api/account/name", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("#me-name-input").value.trim() }),
    });
    $("#me-name").textContent = me.name;
    $("#me-name-input").value = "";
    toast("名称已改");
  } catch (err) {
    toast(`改名失败: ${err.message}`, true);
  } finally {
    btn.disabled = false;
  }
});

$("#me-pass-save").addEventListener("click", async () => {
  const btn = $("#me-pass-save");
  if ($("#me-new-pass").value !== $("#me-new-pass2").value) {
    toast("两次输入的新密码不一致", true);
    return;
  }
  btn.disabled = true;
  try {
    await api("/api/account/password", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        old_password: $("#me-old-pass").value,
        new_password: $("#me-new-pass").value,
      }),
    });
    $("#me-old-pass").value = $("#me-new-pass").value = $("#me-new-pass2").value = "";
    toast("密码已改");
  } catch (err) {
    toast(`改密失败: ${err.message}`, true);
  } finally {
    btn.disabled = false;
  }
});

/* 顶栏刷新: 重拉设置与司机列表 */
$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.classList.add("busy");
  try {
    await loadSettings();
  } catch (err) { toast(`设置加载失败: ${err.message}`, true); }
  await loadDrivers().catch(() => {});
  btn.classList.remove("busy");
});

$("#logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.replace("/login");
});

/* ---------- 启动 ---------- */
loadSettings().catch(err => toast(`设置加载失败: ${err.message}`, true));
loadDrivers().catch(() => {});
loadMe().catch(() => {});
