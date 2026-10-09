// setup.js — 首启引导: 三步全走完才能进应用, 不允许跳过。第一步建管理
// 员 (注册即登录, 后续接口都带会话); 带数据源/地图步骤的部署 (My Home /
// My Tesla) 顺路配 TeslaMate 与高德 Key, 一步变体 (My Money / My Music)
// 建完即完成。起步步数由 /api/setup-status 的 missing 决定 —— 中途退出
// 的续走 (管理员已在, 从缺口步接着); 完成跳转读 body 的 data-done;
// 步骤按 DOM 现状收集, 同一份脚本服务两种页面。
"use strict";
const card = document.getElementById("card");
const doneUrl = document.body.dataset.done || "/";
const forms = ["form1", "form2", "form3"]
  .map(id => document.getElementById(id)).filter(Boolean);

const fail = (form, msg) => {
  form.querySelector(".err").textContent = msg;
  card.classList.remove("shake");
  void card.offsetWidth;
  card.classList.add("shake");
};

const showStep = index => {
  forms.forEach((form, i) => { form.hidden = i !== index; });
  const steps = document.getElementById("steps");
  if (steps) {
    Array.from(steps.children).forEach((li, i) => {
      li.classList.toggle("active", i === index);
      li.classList.toggle("done", i < index);
    });
  }
  const first = forms[index] && forms[index].querySelector("input");
  if (first) first.focus();
};

const finish = () => {
  forms.forEach(form => { form.hidden = true; });
  const steps = document.getElementById("steps");
  if (steps) Array.from(steps.children).forEach(li => li.classList.add("done"));
  document.getElementById("done").hidden = false;
  setTimeout(() => location.replace(doneUrl), 1200);
};

const advance = index => {
  if (index + 1 >= forms.length) { finish(); return; }
  showStep(index + 1);
  if (index + 1 === 1) prefillSettings();
};

// 查看密码: 明文 ↔ 密文, 图标同步切换 (SVG 的显隐必须动 style.display,
// hidden 属性对 SVG 不生效)
document.getElementById("eye").addEventListener("click", () => {
  const passInput = document.getElementById("su-pass");
  const show = passInput.type === "password";
  passInput.type = show ? "text" : "password";
  document.getElementById("eye").setAttribute(
    "aria-label", show ? "隐藏密码" : "显示密码");
  document.getElementById("eye-open").style.display = show ? "none" : "";
  document.getElementById("eye-slash").style.display = show ? "" : "none";
});

// 第一步: 建立第一个管理员 (409 = 别的设备已完成初始化, 去登录页)
forms[0].addEventListener("submit", async e => {
  e.preventDefault();
  const btn = forms[0].querySelector(".btn");
  const password = document.getElementById("su-pass").value;
  if (password !== document.getElementById("su-pass2").value) {
    fail(forms[0], "两次输入的密码不一致");
    return;
  }
  btn.disabled = true;
  try {
    const r = await fetch("/api/setup-admin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("su-name").value.trim(),
        password,
      }),
    });
    if (r.ok) { advance(0); return; }
    if (r.status === 409) { location.replace("/login"); return; }
    const d = await r.json().catch(() => null);
    fail(forms[0], (d && d.detail) || `创建失败 (HTTP ${r.status})`);
  } catch (_e) {
    fail(forms[0], "网络错误, 请重试");
  }
  btn.disabled = false;
});

// 进入数据源步骤时拉现值: 输入框预填 (掩码/密码只给 placeholder, 留空=保持)
async function prefillSettings() {
  try {
    const r = await fetch("/tesla/api/settings", { cache: "no-store" });
    if (!r.ok) return;
    const d = await r.json();
    const t = d.tmdb || {};
    const fill = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value || "";
    };
    fill("tm-host", t.host); fill("tm-port", t.port);
    fill("tm-user", t.user); fill("tm-name", t.name);
    const pass = document.getElementById("tm-pass");
    if (pass) pass.placeholder = t.password_set ? "已设置, 留空保持" : "未设置";
    const a = d.amap || {};
    const key = document.getElementById("amap-key");
    if (key) key.placeholder = a.key_masked ? `现值 ${a.key_masked}, 留空保持` : "未设置";
    const code = document.getElementById("amap-code");
    if (code) code.placeholder = a.security_code_masked ? `现值 ${a.security_code_masked}, 留空保持` : "未设置";
  } catch (_e) { /* 拉不到现值不挡流程, 空表单照填 */ }
}

// 第二步 (有则存在): TeslaMate 连接, 保存自动验证 (失败服务端已回滚可重试)
if (forms[1]) {
  forms[1].addEventListener("submit", async e => {
    e.preventDefault();
    const btn = forms[1].querySelector(".btn");
    btn.disabled = true;
    try {
      const v = id => document.getElementById(id).value.trim();
      const r = await fetch("/tesla/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tmdb_host: v("tm-host"), tmdb_port: v("tm-port"),
          tmdb_user: v("tm-user"), tmdb_password: v("tm-pass"),
          tmdb_name: v("tm-name"),
        }),
      });
      if (r.ok) { advance(1); return; }
      const d = await r.json().catch(() => null);
      fail(forms[1], (d && d.detail) || `保存失败 (HTTP ${r.status})`);
    } catch (_e) {
      fail(forms[1], "网络错误, 请重试");
    }
    btn.disabled = false;
  });
}

// 第三步 (有则存在): 高德 Key + 安全码 (留空=保持现值)
if (forms[2]) {
  forms[2].addEventListener("submit", async e => {
    e.preventDefault();
    const btn = forms[2].querySelector(".btn");
    btn.disabled = true;
    try {
      const v = id => document.getElementById(id).value.trim();
      const r = await fetch("/tesla/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amap_key: v("amap-key"), amap_security_code: v("amap-code"),
        }),
      });
      if (r.ok) { advance(2); return; }
      const d = await r.json().catch(() => null);
      fail(forms[2], (d && d.detail) || `保存失败 (HTTP ${r.status})`);
    } catch (_e) {
      fail(forms[2], "网络错误, 请重试");
    }
    btn.disabled = false;
  });
}

// 起步步数: 管理员没建 → 从头; 建过 (中途退出的续走) → 从第一个缺口步
// 接着 (服务端只对「管理员在 + 有会话」的访客放行续走, 缺口步的表单一定
// 在场)。查不到状态就从第一步走 —— 保存接口会给出真实的缺口。
(async () => {
  let start = 0;
  try {
    const r = await fetch("/api/setup-status", { cache: "no-store" });
    const d = r.ok ? await r.json() : null;
    const missing = (d && d.missing) || [];
    if (!missing.includes("account"))
      start = missing.includes("teslamate") ? 1 : 2;
  } catch (_e) { /* 网络坏掉: 从第一步走 */ }
  showStep(Math.min(start, forms.length - 1));
  if (start >= 1) prefillSettings();
})();
