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
//   ③ 冻矮自愈 (music 1.8.32 同法, 2026-09-21 用户点名修底部黑边): 冷开
//      时 iOS 的还原高度跨重启赖账, 带矮值整程一声事件不响、永不自愈,
//      壳矮一截底下就露黑带 —— 实锤时壳高直接钉记档的满高 (--shell-h,
//      tesla-base.css 消费), 黑带当场补回, 回满自动撤。
//   ④ 裸 Safari 的 dvh 赖账 (2026-09-21 IMG_7556 实测定案): Safari 里
//      (非独立模式) 从切卡/键盘折腾回来, 100dvh 这个单位本身会带旧值
//      不刷新 —— 布局视口明明 731, dvh 停在 438, 壳/滚动器按矮值排,
//      底下露黑带、弹层被 92dvh 压扁、独立合成层留旧栅格 (弹层壳整块
//      不画只剩子层)。独立模式有 ③ 兜; Safari 的 innerHeight 随工具栏
//      浮动, ②的满高基准立不住, 改立"探针对账": 一枚 fixed 探针量活的
//      100dvh (不吃 --shell-h), 比文档根矮超 120px (工具栏浮动 ≤90 不
//      误伤) 且定住 0.7s → 实锤, 壳高钉布局视口真值, 探针回平自动撤。
"use strict";
/* exported ViewportDoctor */

const ViewportDoctor = (() => {
  const vv = window.visualViewport;
  // 苹果触屏 (Safari 与独立模式都算): ① 的键盘拆锁两边都病, 都要治
  // (7556 就是裸 Safari 里的账); ②③ 的满高基准只有独立模式立得住
  // (Safari 工具栏自己收放, innerHeight 天生会动), 裸 Safari 走 ④ 探针。
  const appleTouch = () => (/iP(hone|ad|od)/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1));
  const patient = () => window.matchMedia("(display-mode: standalone)").matches
    && appleTouch();
  const landscape = () => window.matchMedia("(orientation: landscape)").matches;
  const typing = () => {               // 键盘开着的唯一可靠信号: 焦点在输入框
    const el = document.activeElement;
    return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA"
      || el.isContentEditable);
  };

  /* ---------- ① 键盘期间解锁文档 (music-global-events.js 同法) ---------- */
  let kbFull = 0;
  function lift(force) {
    // 键盘收干净了才回锁 (focusout 的补拍会赶在键盘动画半路喊 lift)。
    // force (1800ms 末拍): Safari 工具栏状态在键盘期间变了的话, 内高永远
    // 回不到拆锁那刻的值 —— 文档不能就这么一直敞着, 焦点不在输入框就硬锁。
    if ((force && !typing()) || (kbFull && window.innerHeight >= kbFull - 12)) {
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
    if (!appleTouch()) return;                // 桌面/安卓的账不这么记 (裸 Safari 也治)
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
    setTimeout(() => lift(true), 1800);
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

  /* ---------- ③ 冻矮自愈: 布局别信 webview 的还原高度 ----------
     满高钳在屏内 (竖屏取长边/横屏取短边): 防基线本身被瞬时值带高,
     补偿铺出屏外反而截掉底栏。 */
  const capOf = () => landscape() ? Math.min(screen.width, screen.height)
                                  : Math.max(screen.width, screen.height);
  function shellH(on, px) {   // 冻矮: 壳高钉真满高 (tesla-base.css 消费)
    const root = document.documentElement;
    if (on) root.style.setProperty(
      "--shell-h", Math.min(px != null ? px : full, capOf()) + "px");
    else root.style.removeProperty("--shell-h");
  }

  /* ---------- ④ 裸 Safari 的 dvh 赖账: 探针对账 ----------
     探针 = fixed 的一根 100dvh 标尺 (不吃 --shell-h, 钉了高也照样量真
     dvh)。文档根 (html{height:100%}) = 布局视口, 是"应然"; 探针是 dvh 的
     "实然"。两者差超 120px (工具栏浮动 ≤90 不会误伤) 且定住 0.7s → dvh
     在赖旧账, 壳高钉布局视口真值; 探针回平 (差 ≤12) 自动撤。钉着期间
     探针依旧量真 dvh, 好没好一目了然, 不会来回抖。 */
  let lieProbe = null, lieTimer = 0, lieSnap = -1, lieDeclared = false;
  function probeDvh() {
    if (!lieProbe) {
      lieProbe = document.createElement("div");
      lieProbe.style.cssText =
        "position:fixed;top:0;left:0;width:0;height:100dvh;" +
        "visibility:hidden;pointer-events:none;";
      document.body.appendChild(lieProbe);
    }
    return lieProbe.getBoundingClientRect().height;
  }
  function dvhLie() {
    if (document.hidden || typing()) {          // 键盘期矮是应该的; ① 拆锁时根高不可信
      lieSnap = -1;
      clearTimeout(lieTimer);
      return;
    }
    const gap = document.documentElement.clientHeight - probeDvh();
    if (gap <= 12) {                            // 探针回平: 赖账好了 (或从没病)
      lieSnap = -1;
      lieDeclared = false;
      clearTimeout(lieTimer);
      shellH(false);
      return;
    }
    if (lieDeclared || gap < 120 || lieSnap === gap) return;   // 已钉/浮动不当病/值没定住
    lieSnap = gap;
    clearTimeout(lieTimer);
    lieTimer = setTimeout(() => {
      lieSnap = -1;
      if (document.hidden || typing()) return;
      const root = document.documentElement;
      if (root.clientHeight - probeDvh() < 120) return;
      lieDeclared = true;
      shellH(true, root.clientHeight);   // 自愈: 壳高按布局视口钉真值
    }, 700);
  }

  let freezeTimer = 0, freezeSnap = -1;
  let declared = false;                // 实锤一次就闩住, 回满才解 (别刷屏)
  function check() {
    if (!appleTouch()) return;
    if (!patient()) { dvhLie(); return; }   // 裸 Safari: ④ 探针对账
    const nowLandscape = landscape();
    if (nowLandscape !== seenLandscape) {
      seenLandscape = nowLandscape;
      full = window.innerHeight;       // 转屏: 满高按新方向重立
    }
    noteFull();
    if (window.innerHeight >= full - 12) {   // 健在 (真回满): 清账撤补偿
      freezeSnap = -1;
      declared = false;
      clearTimeout(freezeTimer);
      shellH(false);                   // 冻矮补偿撤掉 (壳高回真 100dvh)
      return;
    }
    if (typing()) {                          // 键盘还开着: 矮是应该的
      freezeSnap = -1;
      clearTimeout(freezeTimer);
      return;
    }
    if (declared) return;
    if (freezeSnap !== window.innerHeight) { // 值定住 0.7s 才算实锤
      freezeSnap = window.innerHeight;
      clearTimeout(freezeTimer);
      freezeTimer = setTimeout(() => {
        freezeSnap = -1;
        if (!patient() || typing() || !sick()) return;
        declared = true;
        shellH(true);   // 自愈: 壳高钉真满高, 冷开冻矮当场补 (不用用户动手)
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
