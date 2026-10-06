// tesla-swipe-delete — My Tesla 列表行左滑露出操作钮 (iOS 同款): 拖拽揭示/
// 松手判定/尾随 click 吞除。移植自 My Music 的 music-swipe-delete (1.8.110
// 收尾版, iPhone 生产验证过), 与业务零耦合, 只认 .swipe-wrap 结构。
// 与 music 版的适配差 (照搬时会咬人的两处, 都记在这):
// 1) 行容器不限 button —— 这边行是 div (.plc-row/.placed-row), CSS 选择器
//    放宽到 "> :first-child" (music 版是 ".swipe-wrap > button:first-child");
// 2) 与 tesla-gesture 的仲裁: 左划在 bindGestures 里 mode="done" 直接交
//    还系统 (不 preventDefault), 这里用 pointer 事件另起炉灶不冲突;
//    右划是抽屉手势的地盘, 这里只认左移照旧。
// 3) 删除钮的二次确认走原生 window.confirm (2026-10-04 从武装式改回
//    music 路线: 钮上变「确认删除」3s 的武装式没被用户看见, 连点好多次才
//    删掉 —— 对话框躲不掉): 消费方在 onDelete 里弹框, 取消/失败正常
//    返回, 没被抽走的行就地收起; 删成了 reload 后旧行早被抽走
//    (isConnected = false), 收尾是空操作。
// v3 (2026-10-04 用户点名「改名按钮去掉, 改成左滑显示编辑按钮」): 行尾操
//    作钮从单枚删除扩成面板 —— .swipe-actions 里「编辑」「删除」按序排
//    (改过名的组两枚, 没改过名的只编辑); 揭示宽度按面板实测 (双钮 144 /
//    单钮 72), 橡皮筋与过半判定跟着面板宽走。详情层还是裸 .swipe-del 单
//    钮 —— 面板缺省时那枚钮自己就是面板 (兼容路); bindSwipeDelete 第三参
//    onEdit 可缺省。
// v4 (2026-10-04 驾驶员页跟进): onEdit 多收一个被点的钮 (第二参) —— 驾驶
//    员的面板里「设为默认」「改名」都是编辑类, 消费方按钮分派; 地点页/详
//    情层不收这个参, 不受影响。
"use strict";
/* exported bindSwipeDelete */

// ------------------------------------------------------------ 左滑操作
// .swipe-wrap 的行左滑露出操作面板 (iOS 同款): 横向拖动跟手, 竖向让给
// 滚动 (行 touch-action: pan-y); 松手过半开/不过半弹回。一次只开一行,
// 点别处/滚动/滑另一行都收起, 开着的行点一下也是收起。
// 只认左移: 右移是抽屉/系统边缘返回的地盘, 这里一抢 (setPointerCapture)
// 抽屉就跟到一半被掐弹回。尾随 click 的吞法: 标记在新按下时清, 松手后
// 设备不补发 click 也不至于粘住吞掉下一次真点击。
const SWIPE_REVEAL = 72;             // 单枚操作钮宽度 (px); 面板宽按实测
let swipeOpenWrap = null;            // 开着的行 (null = 全收)
let swipeDrag = null;                // 拖拽进行中 {wrap,row,reveal,startX,startY,base,horizontal,offset,moved}
let swipeSuppressClick = false;      // 松手前横移过: 尾随的 click 吞掉

/** 行尾的操作面板: #plc-list 的行是 .swipe-actions 面板 (编辑+删除);
    详情层还是裸 .swipe-del 单钮 —— 面板缺省时那枚钮自己就是面板。 */
function swipePanel(wrap) {
  return wrap.querySelector(".swipe-actions") || wrap.querySelector(".swipe-del");
}

/** 移操作面板 + 顺手挂 revealed (行不动, 面板从右缘滑上来): x=0 面板藏
    在右缘外, x=-面板宽 全开 (可多拖 24px 橡皮筋); --veil (0→1) 喂纱的
    浓度 = 拖开的比例, 拖多少显多少。收起 (x=0) 时清行内样式而不是写 0:
    藏态交回 CSS 基线 (translateX(100%) / --veil 缺省 0), 行内样式永远
    压着样式表。 */
function setSwipeTransform(wrap, x) {
  const panel = swipePanel(wrap);
  const reveal = panel && panel.offsetWidth ? panel.offsetWidth : SWIPE_REVEAL;
  if (panel) panel.style.transform = x ? `translateX(${reveal + x}px)` : "";
  if (x) wrap.style.setProperty("--veil", String(Math.min(1, -x / reveal)));
  else wrap.style.removeProperty("--veil");
  wrap.classList.toggle("revealed", x < 0);
}

function closeSwipeRow() {
  if (!swipeOpenWrap) return;
  if (swipeOpenWrap.isConnected && swipePanel(swipeOpenWrap)) {
    setSwipeTransform(swipeOpenWrap, 0);
  }
  swipeOpenWrap = null;
}

// 任何滚动 (列表/页面) 都把开着的行收起来 —— 绑在 document 捕获层,
// scroll 不冒泡, 绑容器收不到祖先的滚动。
document.addEventListener("scroll", closeSwipeRow, true);

function bindSwipeDelete(container, onDelete, onEdit) {
  container.addEventListener("pointerdown", (event) => {
    swipeSuppressClick = false;                  // 新按下 = 上一手势翻篇
    if (swipeDrag) {                             // 出界松手没收到 up: 兜底归位
      swipeDrag.wrap.classList.remove("swiping");
      setSwipeTransform(swipeDrag.wrap, swipeDrag.base);
      swipeDrag = null;
    }
    const wrap = event.target.closest(".swipe-wrap");
    if (!wrap || !wrap.contains(event.target)) { closeSwipeRow(); return; }
    if (event.target.closest(".swipe-del, .swipe-edit")) return;  // 操作钮: 点按即触发
    if (swipeOpenWrap && swipeOpenWrap !== wrap) closeSwipeRow();
    const panel = swipePanel(wrap);
    const reveal = panel && panel.offsetWidth ? panel.offsetWidth : SWIPE_REVEAL;
    swipeDrag = { wrap, row: wrap.firstElementChild, reveal,
                  startX: event.clientX, startY: event.clientY,
                  base: swipeOpenWrap === wrap ? -reveal : 0,
                  horizontal: null, offset: 0, moved: false };
  });
  container.addEventListener("pointermove", (event) => {
    if (!swipeDrag) return;
    const dx = event.clientX - swipeDrag.startX;
    const dy = event.clientY - swipeDrag.startY;
    if (swipeDrag.horizontal === null) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      // 只认左移; 右移/竖移都撒手 (右移归抽屉返回手势, 竖移归滚动)
      swipeDrag.horizontal = dx < 0 && Math.abs(dx) > Math.abs(dy);
      if (!swipeDrag.horizontal) { swipeDrag = null; return; }
      swipeDrag.wrap.classList.add("swiping");   // 拖动跟手, 松手才交给过渡
      try {
        swipeDrag.row.setPointerCapture(event.pointerId);  // 鼠标拖出容器也能收到 up
      } catch (_error) { /* 抓不到也能拖; 出界松手由下一次按下兜底 */ }
    }
    swipeDrag.moved = true;
    // 左移露面板 (可多拖 24px 橡皮筋), 右移最多推回 0
    swipeDrag.offset = Math.min(0, Math.max(-swipeDrag.reveal - 24,
                                            swipeDrag.base + dx));
    setSwipeTransform(swipeDrag.wrap, swipeDrag.offset);
  });
  const settle = (cancelled) => {
    const drag = swipeDrag;
    swipeDrag = null;
    if (!drag || !drag.horizontal) return;
    drag.wrap.classList.remove("swiping");       // 回位/定住交给 CSS 过渡
    if (cancelled) {                              // 浏览器接管手势 (滚动等)
      setSwipeTransform(drag.wrap, drag.base);
      if (drag.base) swipeOpenWrap = drag.wrap;
      return;
    }
    swipeSuppressClick = drag.moved;              // 拖过的松手 click 不当行点击
    if (drag.offset < -drag.reveal / 2) {
      setSwipeTransform(drag.wrap, -drag.reveal);
      swipeOpenWrap = drag.wrap;
    } else {
      setSwipeTransform(drag.wrap, 0);
      if (swipeOpenWrap === drag.wrap) swipeOpenWrap = null;
    }
  };
  container.addEventListener("pointerup", () => settle(false));
  container.addEventListener("pointercancel", () => settle(true));
  // 捕获层吃两类点击: 操作钮 (编辑/删除, 不再冒泡给行点击/展开) 和滑完
  // 松手/开着的行上的尾随 click; 冒泡层的行展开因此看不见这几下。
  container.addEventListener("click", async (event) => {
    if (swipeSuppressClick) {
      swipeSuppressClick = false;
      event.stopPropagation();
      event.preventDefault();
      return;
    }
    const act = event.target.closest(".swipe-del, .swipe-edit");
    if (act) {
      event.stopPropagation();
      event.preventDefault();
      const wrap = act.closest(".swipe-wrap");
      swipeOpenWrap = null;
      if (act.classList.contains("swipe-edit")) {
        if (onEdit) await onEdit(wrap, act);   // 编辑: 消费方开弹层/行内改名 (v4 带上被点的钮), 行就地收起
      } else {
        await onDelete(wrap);                    // 删除: confirm/请求都在消费方
      }
      // 二次确认取消/请求失败的行自动收起; 删成了 reload 后旧行早被
      // 抽走 (isConnected = false), 收尾是空操作
      if (wrap.isConnected) setSwipeTransform(wrap, 0);
      return;
    }
    if (swipeOpenWrap && swipeOpenWrap.contains(event.target)) {
      closeSwipeRow();                            // 开着的行点一下 = 收起
      event.stopPropagation();
      event.preventDefault();
    }
  }, true);
}
