// view/trips-sheet-close.js — 轨迹弹层 (壳版 13/13): 收尾 —— 关弹层
// (hideSheet/closeTrip), 深链入口 openByKey (壳冷启把 ?id=/?ids= 消费后由
// tesla-app-boot 调), 弹层下拉拖拽关闭。
// 旧版 (js/trips-sheet-close.js) 的 popstate 同步 / history.back 删 —— 壳是
// 零历史条目内存路由; cameFromGroups 以 sheetFrom 复活 (只管地址栏镜像
// view=groups —— 2026-09-22 起分组页自己当宿主, 视图没换过, 关弹层不需要
// 跳回; 2026-09-25 用户点名把关闭时的同键 navigate (原地刷新列表) 去掉)。
// 文件名沿用旧名 (命名普查按 basename 折叠)。
/* global $, getJSON, bindSheetDrag, bindSheetSettle, openMerged, openTrip,
          stopAnim, curSess: writable, sheetTrip: writable,
          curKey: writable, sheetFrom: writable, VIEWS, currentView */
/* exported hideSheet, openByKey, sheetTrip, sheetFrom */   // sheetFrom 只写不读 (深链记宿主/关闭清空, 读方在镜像), exported 豁免
"use strict";
/* ---------- 深链入口: 壳冷启消费 ?id=/?ids= 后调用 (分享链接直开) ---------- */
async function openByKey(key) {
  /* 手里没有卡片数据, 单条走单条接口, 合并走合并接口 (失败 → 洗掉参数)。
     合并键两种形式: "首-尾" (现行) / 逗号 (旧链)。深链落在分组页
     (?view=groups&ids=, 分组页打开时镜像的): 宿主是分组页, 按 groups 记
     来源 —— 关弹层/镜像口径与实机打开一致 */
  if (currentView() === VIEWS.groups) sheetFrom = "groups";
  try {
    if (/[-,]/.test(key)) {   // 必须 await: 流式失败要
      /* 合并深链: 先取轻量汇总 (服务端只查 drives, 不碰轨迹点), 弹层带数
         开 —— 2026-09-23 的 info 直填盖住了分组/多选, 深链重开 (刷新/分享/
         PWA 重开) 手里没卡片数据还在全程占位, 2026-09-24 用户再报「加载
         地图时平均电耗空着, 过一会儿才出来」。取不到 (坏链/超时) 照旧无
         info 占位, 错误收场交给后面的流式。 */
      let info = null;
      try { info = await getJSON(`/tesla/trips/api/merged_summary?ids=${key}`); }
      catch { info = null; }
      await openMerged(key, true, info);
    }
    else openTrip(await getJSON(`/tesla/trips/api/sessions/${key}`), true);  // rethrow 到这抹参
  } catch (_e) {
    hideSheet();
    history.replaceState(null, "", "/tesla");   // 坏链接 → 洗掉行程参数
  }
}

function hideSheet() {
  stopAnim();
  if (curSess) { curSess.alive = false; curSess = null; }
  $("#sheet").classList.remove("show");
  $("#backdrop").classList.remove("show");
  sheetTrip = null;
}

/* 零历史条目: 关弹层只把地址栏镜像回裸壳地址 (打开时 replaceState 过
   /tesla?view=trips&id=); 不动历史栈。分组页打开的 (sheetFrom) 关完停在
   原列表 —— 2026-09-22 起分组页自己当宿主, 打开时视图没换, 这里也不再
   navigate 回分组 (同键 navigate = 原地刷新列表, 每次关弹层都转圈重拉,
   2026-09-25 用户点名去掉)。 */
function closeTrip() {
  const key = curKey;
  hideSheet();
  curKey = null;
  sheetFrom = null;
  if (key != null) history.replaceState(null, "", "/tesla");
}

$("#backdrop").addEventListener("click", closeTrip);
/* 下滑关闭 (tesla-sheet-drag 壳级, iOS 安全规矩见彼处注释): 把手点一下
   也关; 上部信息区 (日期时长/驾驶员/统计格) 与左滑过去的动态页/统计页
   (各自三张图卡, 纯展示无控件 —— 统计页 2026-09-27 用户点名漏了) 拖下
   收起, 点一下不关。播放条与地图不在此列 —— 那是控件区。动态/统计页
   在横滑分页里: 横滑切页由 tesla-sheet-drag 的轴向仲裁让给原生 snap
   (横向占优即解绑弹回), 横滑切页与下拉关闭互不抢手势。 */
bindSheetDrag($("#sheet"), $("#grab"), closeTrip, true);
for (const z of document.querySelectorAll(
  "#sheet .sh-head, #sheet .sh-cells, #sheet .tp-stats, #sheet .tp-hist"))
  bindSheetDrag($("#sheet"), z, closeTrip, false);
bindSheetSettle($("#sheet"), "show");   // 视口折腾后强制废弃旧栅格 (7556 同保险)
