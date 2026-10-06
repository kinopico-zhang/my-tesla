// view/settings-account.js — 账号设置独立页 (2026-09-27 从数据来源页拆出,
// 设置组首位; 3.3.0 时账号卡曾住数据来源页顶部, 更早住抽屉底部): 三张卡
// (2026-10-05 二改, 用户点名「账号名改成 inline edit box / 改名·改密·退出
// 分三个 panel / 说明行去掉」) —— ① 账号名: 名字行点「改名」就地翻输入框
// (地点详情 #placed-input 同款: 预填全选, Enter 存, Esc 弃, 没动过不打
// 接口); ② 修改密码; ③ 登出。今晨更早的一版表单还住底部弹层 #acct-sheet
// (已退役)。
/* global $, toast, getJSON, sendJSON, bindGestures, registerView */
"use strict";

let acctAdmin = false;      // 徽章回显: 编辑态藏, 退出编辑按此复原

/* ① 账号名 —— 行内编辑 (改名的确定/取消 = .drv-ok/.drv-act 胶囊) */
function nameEnterEdit() {
  const inp = $("#me-name-input");
  inp.value = $("#acct-name").textContent;
  inp.hidden = false;
  $("#me-name-cancel").hidden = false;
  $("#acct-name").hidden = true;
  $("#acct-badge").hidden = true;
  const btn = $("#me-name-save");
  btn.textContent = "保存";
  btn.classList.add("drv-ok");
  inp.focus();
  inp.select();                       // 预填全选: 敲字即整名替换
}

function nameExitEdit() {
  $("#me-name-input").hidden = true;
  $("#me-name-cancel").hidden = true;
  $("#acct-name").hidden = false;
  $("#acct-badge").hidden = !acctAdmin;
  const btn = $("#me-name-save");
  btn.textContent = "改名";
  btn.classList.remove("drv-ok");
}

async function nameSave() {
  const btn = $("#me-name-save");
  if (btn.disabled) return;           // 在途: 连点/连按回车不双发
  const val = $("#me-name-input").value.trim();
  if (val === $("#acct-name").textContent) { nameExitEdit(); return; }   // 没动
  btn.disabled = true;
  try {
    const me = await sendJSON("/api/account/name", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: val }),
    });
    $("#acct-name").textContent = me.name;
    toast("名称已改");
    nameExitEdit();
  } catch (err) {
    toast(`改名失败: ${err.message}`);   // 名字被占/不合规矩: 服务器的话直说
  } finally {
    btn.disabled = false;
  }
}

$("#me-name-save").addEventListener("click", () => {
  if ($("#me-name-input").hidden) nameEnterEdit();
  else nameSave();
});
$("#me-name-cancel").addEventListener("click", nameExitEdit);
$("#me-name-input").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); nameSave(); }
  else if (e.key === "Escape") { e.stopPropagation(); nameExitEdit(); }   // 一层 Esc 关一层
});

/* ② 修改密码 (错口令/两次不一致当场报, 成功三字段清空) */
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

/* ③ 登出 + 名字/徽章加载 (/api/me 填, 进视图/下拉刷新都重拉 —— 别处
   改名后这里跟着新) */
async function acctCardLoad() {
  const me = await getJSON("/api/me");
  $("#acct-name").textContent = me.name;
  acctAdmin = !!me.is_admin;
  $("#acct-badge").hidden = !acctAdmin;
}
acctCardLoad().catch(() => { /* 拉不到: 三卡只留表单与登出钮 */ });
$("#logout").addEventListener("click", () => {
  fetch("/api/logout", { method: "POST" }).finally(() => { location.href = "/login"; });
});

/* 手势: 滚动器在顶下拉刷新 (与设置组另三页同款) */
bindGestures($("#acct-scroll"), { drawer: true, ptr: true, onRefresh: acctCardLoad });
registerView("settings-account", {
  title: "账号设置",
  el: $("#view-settings-account"),
  show: acctCardLoad,
  refresh: acctCardLoad,
});
