// login.js — 由 login.html 内联脚本抽出 (位置/顺序/语义不变), 供 lint 与测试
// 同一张登录页服务全站: 账号层的 /login 和应用 scope 内的 /tesla/login
// (scope 收窄后会话过期 302 不再越界)。
"use strict";
const form = document.getElementById("form");
const errEl = document.getElementById("err");
const btn = document.getElementById("btn");
const card = document.getElementById("card");
const passInput = document.getElementById("pass");
const eyeBtn = document.getElementById("eye");

// 本登录页属于哪个应用 (账号层的 /login → 空串, HTML 默认就是 My Tesla)
function appRoot() {
  return location.pathname.replace(/\/login\/?$/, "");
}

const APP_TITLES = { "/tesla": "My Tesla" };

// 应用内的登录页换上应用自己的名字 (标题/卡片), 账号层的保持 HTML 默认
(function applyAppName() {
  const name = APP_TITLES[appRoot()];
  if (!name) return;
  document.title = "登录 · " + name;
  const h1 = document.querySelector("h1");
  if (h1) h1.textContent = name;
})();

// 登录完去哪: 优先 next 参数 (会话过期 302 带来的原地址; 只认当前应用
// scope 内的站内路径, 防站外跳)。应用内登录页没带 next 就回应用主页;
// 账号层登录页回上次停留的 Tesla 页 (主屏 App 里会话过期重新登录 /
// Safari 书签进来都适用), 白名单外回充电记录页。
function pickNext() {
  const root = appRoot();
  const next = new URLSearchParams(location.search).get("next") || "";
  const inRoot = next.startsWith("/") && !next.startsWith("//") &&
    (root === "" || next === root || next.startsWith(root + "/"));
  if (inRoot) return next;
  if (root) return root;
  let last = null;
  try { last = localStorage.getItem("mytesla-last-page"); } catch (e) {}
  return last && /^\/(tesla\/(charging|stats|chargemap|map|trips|groups|live|settings|changelog))(\?|$)/.test(last)
    ? last : "/tesla/charging";
}

// 查看密码: 明文 ↔ 密文, 图标同步切换
eyeBtn.addEventListener("click", () => {
  const show = passInput.type === "password";
  passInput.type = show ? "text" : "password";
  eyeBtn.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  // hidden 属性对 SVG 不生效 (UA 的 [hidden]{display:none} 只管 HTML 命名空间),
  // 两个眼睛曾因此并排显示, 必须动 style.display
  document.getElementById("eye-open").style.display = show ? "none" : "";
  document.getElementById("eye-slash").style.display = show ? "" : "none";
});

form.addEventListener("submit", async e => {
  e.preventDefault();
  errEl.textContent = "";
  btn.disabled = true;
  try {
    const r = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user: document.getElementById("user").value,
        password: document.getElementById("pass").value,
      }),
    });
    if (r.ok) {
      location.replace(pickNext());
      return;
    }
    // 优先展示后端给出的原因 (账号密码错误 / 尝试次数过多…), 兜底按状态码
    const d = await r.json().catch(() => null);
    let msg;
    if (d && d.detail) msg = String(d.detail);
    else if (r.status === 401) msg = "账号或密码错误";
    else if (r.status === 429) msg = "尝试次数过多, 请稍后再试";
    else if (r.status === 404) msg = "登录接口不存在, 服务可能未更新";
    else msg = `登录失败 (HTTP ${r.status})`;
    errEl.textContent = msg;
    card.classList.remove("shake");
    void card.offsetWidth;
    card.classList.add("shake");
  } catch (e) {
    errEl.textContent = "网络错误, 请重试";
  }
  btn.disabled = false;
});
document.getElementById("user").focus();
