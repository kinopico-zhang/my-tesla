// link-delivery — My Home 门厅的链接送达: 复制优先 (HTTP 无异步剪贴板时走
// execCommand 退化路), 拷贝整个被拒时拉系统分享面板兜底。
// 拆自 accounts.js (结构化重构: 代码逐字节未动, 按 accounts.html 里的顺序加载, 跨模块引用走全局)。
"use strict";
/* exported copyText, deliverLink */

/* HTTP 环境没有异步剪贴板 API (isSecureContext=false), 退化用 execCommand。
   iOS Safari 要求: 同一手势内先 focus 再选中再拷贝, 元素还得留在视口里
   (完全透明/移出屏幕会被拒绝建立选区)。旧版三处全踩 —— 对 textarea 用
   Range 选 (它没有 DOM 子节点, 选不中), 没 focus, 还 opacity:0 移出屏幕,
   iOS Safari 一直复制落空 (2026-09-13 用户抓到)。 */
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(text); return true; } catch (_e) { /* 落回 */ }
  }
  let ok = false;
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.readOnly = true;   // 只读: 聚焦不弹 iOS 键盘
  ta.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;"
    + "opacity:.01;pointer-events:none";
  document.body.appendChild(ta);
  ta.focus({ preventScroll: true });          // 必须先聚焦, 选区才建立
  ta.setSelectionRange(0, text.length);
  try { ok = document.execCommand("copy"); } catch (_e) { ok = false; }
  ta.blur();
  ta.remove();
  if (ok) return true;
  // 再试老路: contenteditable + Range 选区 (更老的 iOS 只认这种)
  const div = document.createElement("div");
  div.contentEditable = "true";
  div.textContent = text;
  div.style.cssText = "position:fixed;top:0;left:0;opacity:.01;pointer-events:none";
  document.body.appendChild(div);
  const range = document.createRange();
  range.selectNodeContents(div);
  const sel = getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  try { ok = document.execCommand("copy"); } catch (_e) { ok = false; }
  sel.removeAllRanges();
  div.remove();
  return ok;
}

/* 链接送出去: 复制优先; iOS Safari 在 HTTP 下拷贝这条路可能整个被拒,
   拉起系统分享面板兜底 (面板里就有「拷贝」, 还能直接发给家人)。
   返回 copied / shared / cancelled / failed。 */
async function deliverLink(link) {
  if (await copyText(link)) return "copied";
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ text: "My Home 注册邀请:", url: link });
      return "shared";
    } catch (_e) { return "cancelled"; }   // 用户自己关了面板
  }
  return "failed";
}
