// register.js — 凭邀请注册: 进页先验邀请链接, 提交创建账号并自动登录
"use strict";
const form = document.getElementById("form");
const errEl = document.getElementById("err");
const btn = document.getElementById("btn");
const card = document.getElementById("card");
const passInput = document.getElementById("pass");
const eyeBtn = document.getElementById("eye");

const invite = new URLSearchParams(location.search).get("invite") || "";

// 查看密码: 明文 ↔ 密文, 图标同步切换 (SVG 的显隐必须动 style.display,
// hidden 属性对 SVG 不生效 —— 登录页曾因此两个眼睛并排显示)
eyeBtn.addEventListener("click", () => {
  const show = passInput.type === "password";
  passInput.type = show ? "text" : "password";
  eyeBtn.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  document.getElementById("eye-open").style.display = show ? "none" : "";
  document.getElementById("eye-slash").style.display = show ? "" : "none";
});

const fail = msg => {
  errEl.textContent = msg;
  card.classList.remove("shake");
  void card.offsetWidth;
  card.classList.add("shake");
};

(async () => {   // 进页先验邀请: 坏链接直接说原因, 不让用户白填一表
  if (!invite) {
    fail("缺少邀请参数, 请从管理员发的链接进入");
    btn.disabled = true;
    return;
  }
  try {
    const r = await fetch(`/api/invite-status?invite=${encodeURIComponent(invite)}`);
    if (!r.ok) {
      const d = await r.json().catch(() => null);
      fail((d && d.detail) || "邀请链接不可用");
      btn.disabled = true;
    }
  } catch (_e) {
    errEl.textContent = "网络错误, 稍后重试";   // 离线不拦表单, 提交时再报
  }
})();

form.addEventListener("submit", async e => {
  e.preventDefault();
  errEl.textContent = "";
  const name = document.getElementById("name").value.trim();
  const password = passInput.value;
  if (password !== document.getElementById("pass2").value) {
    fail("两次输入的密码不一致");
    return;
  }
  btn.disabled = true;
  try {
    const r = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite, name, password }),
    });
    if (r.ok) {                    // 注册即登录, 直接进门厅挑应用
      location.replace("/");
      return;
    }
    const d = await r.json().catch(() => null);
    fail((d && d.detail) || `注册失败 (HTTP ${r.status})`);
  } catch (_e) {
    fail("网络错误, 请重试");
  }
  btn.disabled = false;
});
document.getElementById("name").focus();
