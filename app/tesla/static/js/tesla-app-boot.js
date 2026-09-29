// tesla-app-boot — 壳冷启 (最后加载): 关浏览器滚动恢复 → 洗地址栏成裸
// /tesla (URL 参数已在各壳模块加载期消费: 充电筛选归 tesla-shell, 足迹
// 驾驶员/充电地图度量在各自视图; 行程深链 ?id=/?ids= 与旧页路由 302 带来
// 的 ?view= 在这先抠出来再洗 —— 旧时间链接 ?range=/?from=&to= 的筛选语义
// 3.3.0 下线, 参数直接被洗掉) → 接线抽屉/筛选条/车辆切换 → 换车订阅
// (当前视图整体刷新) → 定初始视图 (?view= 优先, 行程深链直进, 再重放上次
// 视图, 缺省状态页)。
"use strict";
/* global bootDrawer, bindFilterBar, bootCarSwitcher, navigate, refreshCurrent,
          onCarChange, readLastView, VIEWS, openByKey */

if ("scrollRestoration" in history) history.scrollRestoration = "manual";
/* 深链先于洗参抠出 (replaceState 一洗 location.search 就空了): 2.0 分享
   链接 /tesla/trips?id=X 经 302 变 /tesla?view=trips&id=X, 进壳不丢;
   不认识的 ?view= 当没有 (脏参数不炸) */
const bootQs = new URLSearchParams(location.search);
const tripKey = (bootQs.get("id") || bootQs.get("ids") || "").trim();
const viewParam = (bootQs.get("view") || "").trim();
if (location.search || location.hash)
  history.replaceState(null, "", "/tesla");   // 洗掉旧链接带来的参数 (零历史条目)

onCarChange(() => refreshCurrent());      // 换车: 一次性整体切换 (用户定案)

/* Esc 剥层顺序依赖挂载顺序: 详情链 (视图脚本加载期已挂) → 抽屉 → 筛选弹层
   —— 每层关了自己就 stopImmediatePropagation, 一层 Esc 只关一层。 */
bootDrawer();
bindFilterBar();
bootCarSwitcher();

const lastView = readLastView();
navigate(VIEWS[viewParam] ? viewParam
  : tripKey ? "trips" : (VIEWS[lastView] ? lastView : "live"));
if (tripKey) openByKey(tripKey);   // 深链: 列表照常后台拉, 弹层直接开
