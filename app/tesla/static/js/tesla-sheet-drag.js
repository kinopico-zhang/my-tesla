// tesla-sheet-drag — 底部弹层下拉关闭 (壳级共用): 把"拖着跟手、松手回弹、
// 拉过 90px 才算关"绑到弹层的可拖区 —— 把手 (点一下也关) + 上部展示
// 信息区 (点一下不关, 那里还有 ✕ / 下拉框等控件; 用户点名信息区下滑
// 也能收起); 充电详情正文一屏装下, 正文区整片也绑上 (用户点名: 没有
// 下滑事件的控件全补上)。四张明细弹层共用: 充电详情 / 行程 / 充电地图
// / 足迹。
// 轴向仲裁 (2026-09-27 用户点名「左右滑会被判定下滑」): 8px slop 内弹层
// 纹丝不动; 横向占优 = 横滑 (弹层分页切页 / 地图平移), 解绑交还原生;
// 明确向下 (dy > 2|dx|) 才接管关闭拖拽 —— 斜向未定继续观察不动。横滑
// 分支绝不碰样式 (当天二轮实报「左滑不动」: 仲裁窗口内改祖先样式会掐
// 死原生滚动起手, 剥 settle 留的 inline none 同样是改); 接管过的
// (moved) 松手才清。
// 不用 setPointerCapture: iOS Safari 对 touch 指针 capture 会当场
// pointercancel (手指一动事件就被系统收走, 2026-09-13 用户实测拉不动),
// move/up 挂 window 级 —— 不捕获手指出界照样收, 各端行为一致。
"use strict";
/* exported bindSheetDrag, bindSheetSettle */

/* 弹层闲置层降级 (IMG_7556 定案): 弹层开着时若以非 none 的 transform 闲
   置 (translateY(0) 也算), iOS 折腾完键盘/工具栏/切卡后, 这种独立合成层
   会留旧栅格 —— 弹层的背景/圆角/描边整块不画, 只剩子层在飘, 底下露纯黑。
   两道保险: ① CSS 侧开态写 transform:none (开着=回主渲染树, 闭↔开照样
   按 identity 插值出滑入滑出); ② 这里在视口折腾过后 (visualViewport
   resize / 回前台) 给开着的弹层过一遍微变换+回 none, 强制废弃已烂的栅
   格。bindSheetSettle 每弹层一次, openClass 各家不同 (on/show)。 */
function bindSheetSettle(sheet, openClass) {
  const open = () => sheet.classList.contains(openClass);
  const resettle = () => {
    if (!open()) return;
    sheet.style.transform = "translateY(0.01px)";   // 真改一次样式才作废旧栅格
    void sheet.offsetWidth;
    sheet.style.transform = "none";
  };
  let t = 0;
  const soon = () => { clearTimeout(t); t = setTimeout(resettle, 300); };
  if (window.visualViewport) window.visualViewport.addEventListener("resize", soon);
  addEventListener("pageshow", soon);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) soon(); });
  // 收起瞬间清掉闲置态的 inline none, 不然它压住类里的 translateY(105%),
  // 关闭滑出动画不出, 弹层赖在屏上
  new MutationObserver(() => {
    if (!open() && sheet.style.transform === "none") sheet.style.transform = "";
  }).observe(sheet, { attributes: true, attributeFilter: ["class"] });
}

const SHEET_DRAG_SLOP = 8;   // 轴向判定门槛 (px), 与手势仲裁 GESTURE_SLOP 同尺

function bindSheetDrag(sheet, zone, onClose, tapCloses) {
  let x0 = 0, y0 = null, dy = 0, axis = "", moved = false;
  function detach() {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", release);
    window.removeEventListener("pointercancel", release);
  }
  function move(e) {
    if (y0 == null) return;
    const dx = e.clientX - x0, vy = e.clientY - y0;
    if (!axis) {
      if (Math.abs(dx) < SHEET_DRAG_SLOP && Math.abs(vy) < SHEET_DRAG_SLOP) return;
      if (Math.abs(dx) > Math.abs(vy)) {          // 横滑: 交还原生 (分页切页/地图平移)
        axis = "x"; detach();                     // 弹层从没动过, 无需弹回 —— 也不
        return;                                   // 碰样式: iOS 手势仲裁窗口内改祖
      }                                           // 先样式会把原生滚动的起手掐死
      if (vy > Math.abs(dx) * 2) axis = "y";      // (2026-09-27 用户实报弹层里左滑
      else return;                                // 不动, 几次才成 —— 剥 settle 留的
    }                                             // inline none 同样是改样式)
    dy = Math.max(0, vy);      // 只往下拖有效, 往上顶不抬层
    moved = true;
    sheet.style.transition = "none";
    sheet.style.transform = `translateY(${dy}px)`;
  }
  function release() {
    detach();
    if (y0 == null) return;
    if (moved) { sheet.style.transition = ""; sheet.style.transform = ""; }
    if (dy > 90) onClose();                // 拉过 90px = 明确想关; 否则弹回
    y0 = null; axis = "";
  }
  zone.addEventListener("pointerdown", e => {
    x0 = e.clientX; y0 = e.clientY; dy = 0; axis = ""; moved = false;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
  });
  // 捕获段吞拖完的 click (拖过 8px 不算点击): 否则回弹动画结束瞬间跟来的
  // click 会打着 ✕ / 下拉框把刚弹回的弹层又关掉; tapCloses 的把手点一下也关
  zone.addEventListener("click", e => {
    if (dy > 8) { e.stopImmediatePropagation(); e.preventDefault(); dy = 0; return; }
    if (tapCloses) onClose();
  }, true);
}
