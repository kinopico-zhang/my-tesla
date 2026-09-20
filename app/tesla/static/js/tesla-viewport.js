// tesla-viewport — 固定壳的键盘病防治 (music 1.8.16 七轮诊疗的结论移植,
// 去 HUD/回传): 文档锁死 (html/body overflow:hidden) 的壳在 iOS 独立模式
// 下, 键盘收起那一下 WebKit 会把"还原高度"记成半路值 → 底部黑带。治法 =
// 键盘期间解锁文档 (focusin 拆锁 + 给真高度; focusout 迟几拍回锁清账),
// 让让位滚动落在合法文档上、收键走苹果百测的还原路径。
//   ① unlock/lift: 焦点一进输入框立刻拆文档锁 (抢在键盘起手之前), 文档
//      滚位/视口偏移有脏账当场归零;
//   ② ViewportDoctor: 满高基准 (localStorage 跨重启, 转屏重立) + 冻矮
//      判定 (焦点不在输入框 + 比满高矮 12px + 定住 0.7s), settled() 供
//      弹层关闭时让路键盘收起 (P6 账号弹层用)。
"use strict";
/* exported ViewportDoctor */

const ViewportDoctor = (() => {
  const vv = window.visualViewport;
  // 只有独立模式 iPhone 会病: 浏览器 Safari 工具栏自己收放, innerHeight
  // 天生会动, 满高基准立不住; 安卓 interactive-widget 布局自己缩, 是正常。
  const patient = () => window.matchMedia("(display-mode: standalone)").matches
    && (/iP(hone|ad|od)/.test(navigator.userAgent)
        || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1));
  const landscape = () => window.matchMedia("(orientation: landscape)").matches;
  const typing = () => {               // 键盘开着的唯一可靠信号: 焦点在输入框
    const el = document.activeElement;
    return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA"
      || el.isContentEditable);
  };

  /* ---------- ① 键盘期间解锁文档 (music-global-events.js 同法) ---------- */
  let kbFull = 0;
  function lift() {
    // 键盘收干净了才回锁 (focusout 的补拍会赶在键盘动画半路喊 lift)
    if (kbFull && window.innerHeight >= kbFull - 12) {
      kbFull = 0;
      const root = document.documentElement;
      root.style.overflow = ""; root.style.height = "";
      document.body.style.height = ""; document.body.style.minHeight = "";
      root.style.removeProperty("--kb-full");
    }
    // 文档永不滚是本应用铁律 (固定壳): 焦点不在输入框里就归零复位
    if (!typing() && (window.scrollX || window.scrollY
      || (vv && (vv.offsetLeft || vv.offsetTop)))) window.scrollTo(0, 0);
  }
  document.addEventListener("focusin", event => {
    const el = event.target;
    if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA"
      && !el.isContentEditable)) return;
    if (!patient()) return;                    // 桌面/安卓的账不这么记
    if (kbFull) return;                        // 键盘已开着 (焦点换了个框): 不重复拆
    kbFull = window.innerHeight;
    const root = document.documentElement;
    root.style.setProperty("--kb-full", `${kbFull}px`);
    root.style.overflow = "auto";              // 拆文档锁: 让位起手那一滚
    root.style.height = "auto";                // 必须落在可滚文档上
    document.body.style.height = "auto";
    document.body.style.minHeight = `${kbFull}px`;   // 层内撑住真高度
    setTimeout(() => {   // 650ms 没见矮 (实体键盘/起手被拦): 当无事回锁
      if (kbFull && window.innerHeight >= kbFull - 40) lift();
    }, 650);
  });
  document.addEventListener("focusout", () => {
    // 键盘收走的收尾经常一声事件都不响: 焦点一离开输入框就迟几拍各补一次
    setTimeout(lift, 350);
    setTimeout(lift, 900);
    setTimeout(lift, 1800);
  });
  lift();
  addEventListener("pageshow", lift);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) lift();
  });

  /* ---------- ② 冻矮监测 (music-viewport-doctor 去屏显/回传) ---------- */
  let seenLandscape = landscape();
  let full = window.innerHeight;
  try {
    const saved = JSON.parse(localStorage.getItem("tesla.fullInner") || "null");
    if (saved && saved.landscape === seenLandscape) full = Math.max(full, saved.height || 0);
  } catch (_error) { /* 隐私模式读不了就只信开局值 */ }
  function noteFull() {
    if (window.innerHeight <= full) return;
    full = window.innerHeight;
    try {
      localStorage.setItem("tesla.fullInner",
        JSON.stringify({ height: full, landscape: seenLandscape }));
    } catch (_error) { /* 存不进就算了, 内存里那份还在 */ }
  }
  const sick = () => full - window.innerHeight > 12;   // 冻矮: 比满高矮一截

  let freezeTimer = 0, freezeSnap = -1;
  function check() {
    if (!patient()) return;
    const nowLandscape = landscape();
    if (nowLandscape !== seenLandscape) {
      seenLandscape = nowLandscape;
      full = window.innerHeight;       // 转屏: 满高按新方向重立
    }
    noteFull();
    if (window.innerHeight >= full - 12) {   // 健在 (真回满): 清账
      freezeSnap = -1;
      clearTimeout(freezeTimer);
      return;
    }
    if (typing()) {                          // 键盘还开着: 矮是应该的
      freezeSnap = -1;
      clearTimeout(freezeTimer);
      return;
    }
    if (freezeSnap !== window.innerHeight) { // 值定住 0.7s 才算实锤
      freezeSnap = window.innerHeight;
      clearTimeout(freezeTimer);
      freezeTimer = setTimeout(() => {
        freezeSnap = -1;
        /* 冻矮实锤时的自救 = 文档已经解锁过 (focusin 拆的锁), lift() 清账;
           music 的 HUD/回传壳不带, 定住了就静默待愈 */
        if (patient() && !typing() && sick()) lift();
      }, 700);
    }
  }
  if (vv) {
    vv.addEventListener("resize", check);
    vv.addEventListener("scroll", check);
  }
  document.addEventListener("focusout", () => {
    setTimeout(check, 350);
    setTimeout(check, 900);
    setTimeout(check, 1800);
  });
  addEventListener("pageshow", check);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) check();
  });
  setInterval(check, 1500);   // 冻矮后一声事件不响: 慢心跳兜底

  function settled() {
    if (!patient()) return !vv || vv.height >= window.innerHeight - 12;
    return window.innerHeight >= full - 12;  // 高度真回满才算键盘收稳
  }
  check();
  return { settled, check };
})();
