// view/settings-account.js — 账号弹层 (P6): 抽屉账号行点开, 改名称/改密码
// (旧设置页的账号卡搬进底部弹层; 「关于」卡不搬 —— 更新日志已是抽屉导航项)。
// 弹层带输入框, 关层要让路键盘: 先 blur 交还焦点, ViewportDoctor.settled()
// 没回满 (键盘还在收) 前迟几拍再拆层, 最多 1.2s —— 固定壳文档解锁期
// (tesla-viewport) 的收键还原必须发生在层还撑着时 (music push-panes 同法,
// 防底部黑带)。旧版的顶栏刷新/登出/启动载入不搬 (抽屉接管)。
/* global $, toast, getJSON, sendJSON, layerMotion, ViewportDoctor, closeDrawer */
/* exported openAcct, closeAcct */
"use strict";

function openAcct() {
  closeDrawer();                       // 弹层从抽屉账号行来: 先收抽屉 (z 在弹层上)
  $("#acct-backdrop").classList.add("show");
  $("#acct-sheet").classList.add("show");
  layerMotion();
  acctLoad();
}

function closeAcct() {
  const t = document.activeElement;
  if (t instanceof HTMLElement) t.blur();   // 先交还焦点, 键盘起收
  const start = Date.now();
  const teardown = () => {
    $("#acct-backdrop").classList.remove("show");
    $("#acct-sheet").classList.remove("show");
    layerMotion();
  };
  const wait = () => {   // settled() 没回满: 键盘没收稳不拆层 (最多等 1.2s)
    if (ViewportDoctor.settled() || Date.now() - start > 1200) teardown();
    else setTimeout(wait, 80);
  };
  wait();
}

async function acctLoad() {
  const me = await getJSON("/api/me");
  $("#me-name").textContent = me.name;
}

$("#me-name-save").addEventListener("click", async () => {
  const btn = $("#me-name-save");
  btn.disabled = true;
  try {
    const me = await sendJSON("/api/account/name", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("#me-name-input").value.trim() }),
    });
    $("#me-name").textContent = me.name;
    $("#acct-name").textContent = me.name;    // 抽屉账号行同步
    $("#me-name-input").value = "";
    toast("名称已改");
  } catch (err) {
    toast(`改名失败: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

$("#me-pass-save").addEventListener("click", async () => {
  const btn = $("#me-pass-save");
  if ($("#me-new-pass").value !== $("#me-new-pass2").value) {
    toast("两次输入的新密码不一致");
    return;
  }
  btn.disabled = true;
  try {
    await sendJSON("/api/account/password", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        old_password: $("#me-old-pass").value,
        new_password: $("#me-new-pass").value,
      }),
    });
    $("#me-old-pass").value = ""; $("#me-new-pass").value = ""; $("#me-new-pass2").value = "";
    toast("密码已改");
  } catch (err) {
    toast(`改密失败: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

/* 接线: 抽屉账号行点开; 点蒙版/Esc 收 (Esc 只在本弹层开着时拦, 一层 Esc 关一层) */
$("#acct-row").addEventListener("click", openAcct);
$("#acct-backdrop").addEventListener("click", closeAcct);
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !$("#acct-sheet").classList.contains("show")) return;
  closeAcct();
  e.stopImmediatePropagation();
});
