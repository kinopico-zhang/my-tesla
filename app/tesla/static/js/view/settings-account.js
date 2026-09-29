// view/settings-account.js — 账号设置独立页 (2026-09-27 从数据来源页拆出,
// 设置组首位; 3.3.0 时账号卡曾住数据来源页顶部, 更早住抽屉底部):
// 改名称/改密码的底部弹层 + 页上账号卡 (名字/管理员徽章, /api/me 填,
// 每次进视图/下拉刷新都重拉) + 登出钮。弹层带输入框, 关层要让路键盘:
// 先 blur 交还焦点, ViewportDoctor.settled() 没回满 (键盘还在收) 前迟几拍
// 再拆层, 最多 1.2s —— 固定壳文档解锁期 (tesla-viewport) 的收键还原必须
// 发生在层还撑着时 (music push-panes 同法, 防底部黑带)。旧版的顶栏刷新/
// 启动载入不搬。
/* global $, toast, getJSON, sendJSON, layerMotion, ViewportDoctor,
          bindSheetDrag, bindSheetSettle, bindGestures, registerView */
/* exported openAcct, closeAcct */
"use strict";

function openAcct() {
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
    $("#acct-name").textContent = me.name;    // 账号卡同步
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

/* 接线: 账号卡「改名称 / 改密码」点开; 点蒙版/Esc 收 (Esc 只在本弹层开着
   时拦, 一层 Esc 关一层) */
$("#acct-row").addEventListener("click", openAcct);
$("#acct-backdrop").addEventListener("click", closeAcct);
document.addEventListener("keydown", e => {
  if (e.key !== "Escape" || !$("#acct-sheet").classList.contains("show")) return;
  closeAcct();
  e.stopImmediatePropagation();
});
/* 把手拖拽收层 + 视口折腾重画: 与其他明细弹层同款 (壳级 tesla-sheet-drag) */
bindSheetDrag($("#acct-sheet"), $("#acct-sheet .grab"), closeAcct, true);
bindSheetSettle($("#acct-sheet"), "show");

/* 页上账号卡 (3.3.0 从抽屉账号行搬来): 加载期填名字/管理员徽章; 登出走
   /api/logout 清 cookie 回登录页 */
async function acctCardLoad() {
  const me = await getJSON("/api/me");
  $("#acct-name").textContent = me.name;
  if (me.is_admin) $("#acct-badge").hidden = false;
  $("#acct-row").hidden = false;
}
acctCardLoad().catch(() => { /* 拉不到: 账号卡只留登出钮 */ });
$("#logout").addEventListener("click", () => {
  fetch("/api/logout", { method: "POST" }).finally(() => { location.href = "/login"; });
});

/* 手势: 滚动器在顶下拉刷新 (与设置组另三页同款); 进视图重拉 (别处改名后
   这里跟着新) */
bindGestures($("#acct-scroll"), { drawer: true, ptr: true, onRefresh: acctCardLoad });
registerView("settings-account", {
  title: "账号设置",
  el: $("#view-settings-account"),
  show: acctCardLoad,
  refresh: acctCardLoad,
});
