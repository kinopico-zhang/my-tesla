// settings-account.js — 软件设置页 (3/3): 账号自助 (改名称/改密码) +
// 页面收尾 (顶栏刷新 / 退出登录 / 启动载入)。收尾块放本文件 (最后加载):
// 启动时要调的 loadSettings/loadDrivers 都在前两个文件里, 顶层立即执行
// 只能等它们都就位。
// 由 settings.js 按域拆出 (结构化重构, 声明顺序与语义不变); 底座
// ($/toast/api) 在 settings-connections.js。
/* global $, toast, api, loadSettings, loadDrivers */
"use strict";
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
