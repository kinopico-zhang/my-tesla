/* lastpage.js (上次停留页跳转) 的 node --test 单元测试。
   它是立即执行的 IIFE, 直接读写全局 (location/storage/document/...),
   node 没有这些 —— 用桩替换 globalThis 再执行源码, 桩上捕捉行为:
   跳转目标 / 记录的最终地址 / 挂上的 visibilitychange 监听。 */
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const KEY = "mytesla-last-page", LAUNCH = "mytesla-launch-marked";

/* node 22+ 内置了只读 navigator, 无法覆盖 —— navigator.standalone 的
   老式判定分支只在可覆盖的运行时 (门禁用的宿主 node 18) 执行 */
let canOverrideNavigator = false;
try {
  Object.defineProperty(globalThis, "navigator",
                        { value: {}, configurable: true });
  canOverrideNavigator = true;
  delete globalThis.navigator;
} catch { /* 内置 navigator 不可覆盖 */ }

function runPage(opts = {}) {
  const calls = { replace: null, visibility: null };
  const lsData = new Map(Object.entries(opts.localStorage || {}));
  const ssData = new Map(Object.entries(opts.sessionStorage || {}));
  const mkStore = (data, broken) => ({
    getItem: broken ? () => { throw new Error("blocked"); }
      : k => (data.has(k) ? data.get(k) : null),
    setItem: broken ? () => { throw new Error("blocked"); }
      : (k, v) => data.set(k, v),
  });
  const page = {
    location: {
      pathname: opts.pathname ?? "/tesla/map",
      search: opts.search ?? "",
      replace: url => { calls.replace = url; },
    },
    sessionStorage: mkStore(ssData, opts.sessionStorageBroken),
    localStorage: mkStore(lsData, opts.localStorageBroken),
    document: {
      hidden: false,
      addEventListener: (ev, fn) => {
        if (ev === "visibilitychange") calls.visibility = fn;
      },
    },
    matchMedia: () => ({ matches: !!opts.standaloneMatch }),
  };
  const saved = {};
  for (const [name, stub] of Object.entries(page)) {
    saved[name] = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { value: stub, configurable: true });
  }
  if (canOverrideNavigator) {
    Object.defineProperty(globalThis, "navigator",
      { value: { standalone: opts.navigatorStandalone }, configurable: true });
  }
  const require = createRequire(import.meta.url);
  const module_path = path.join(
    path.dirname(fileURLToPath(import.meta.url)), "..", "..",
    "app", "tesla", "static", "js", "lastpage.js");
  delete require.cache[require.resolve(module_path)];   // 每个用例重跑一遍 IIFE
  const teardown = () => {
    for (const [name, desc] of Object.entries(saved)) {
      if (desc) Object.defineProperty(globalThis, name, desc);
      else delete globalThis[name];
    }
    if (canOverrideNavigator) delete globalThis.navigator;
  };
  try {
    require(module_path);
  } finally {
    /* keepGlobals: 用例还要在跑完后调 visibility 监听 (闭包运行时才查全局),
       拆桩的时机交给用例 (teardown()) */
    if (!opts.keepGlobals) teardown();
  }
  return { calls, lsData, ssData, page, teardown };
}

test("非白名单路径: 整段不动作 (不记录不监听不跳)", () => {
  const { calls, lsData, ssData } = runPage({ pathname: "/tesla/login" });
  assert.equal(lsData.size, 0);
  assert.equal(ssData.size, 0);
  assert.equal(calls.visibility, null);
  assert.equal(calls.replace, null);
});

test("白名单页正常换页 (同会话): 记录 path+search, 不跳", () => {
  const { calls, lsData } = runPage({
    pathname: "/tesla/trips", search: "?id=5",
    sessionStorage: { [LAUNCH]: "1" },
  });
  assert.equal(lsData.get(KEY), "/tesla/trips?id=5");
  assert.equal(calls.replace, null);
});

test("冷启动 + 主屏全屏 App + 上次在别的页: replace 跳回", () => {
  const { calls, lsData, ssData } = runPage({
    localStorage: { [KEY]: "/tesla/settings" }, standaloneMatch: true,
  });
  assert.equal(calls.replace, "/tesla/settings");
  assert.equal(lsData.get(KEY), "/tesla/map");   // 新页也记上
  assert.equal(ssData.get(LAUNCH), "1");         // 会话标记已写
});

test("冷启动 + navigator.standalone (老式 iOS 判定) 也算全屏 App", t => {
  if (!canOverrideNavigator) return t.skip("navigator 不可覆盖 (node 内置)");
  const { calls } = runPage({
    navigatorStandalone: true, localStorage: { [KEY]: "/tesla/live" },
  });
  assert.equal(calls.replace, "/tesla/live");
});

test("上次就是本页 (含筛选参数): 不跳", () => {
  const { calls } = runPage({
    search: "?id=9", localStorage: { [KEY]: "/tesla/map?id=9" },
    standaloneMatch: true,
  });
  assert.equal(calls.replace, null);
});

test("上次地址不在白名单 (localStorage 脏数据): 不跳, 照常记录", () => {
  const { calls, lsData } = runPage({
    localStorage: { [KEY]: "https://evil.example/x" }, standaloneMatch: true,
  });
  assert.equal(calls.replace, null);
  assert.equal(lsData.get(KEY), "/tesla/map");
});

test("Safari 页内访问 (非 standalone): 只记录不跳", () => {
  const { calls, lsData } = runPage({
    localStorage: { [KEY]: "/tesla/live" },
  });
  assert.equal(calls.replace, null);
  assert.equal(lsData.get(KEY), "/tesla/map");
});

test("隐私模式 sessionStorage 不可用: 整段放弃 (防回弹循环)", () => {
  const { calls, lsData } = runPage({ sessionStorageBroken: true });
  assert.equal(lsData.size, 0);           // record 都没执行
  assert.equal(calls.visibility, null);   // 监听也没挂
  assert.equal(calls.replace, null);
});

test("localStorage 读写被禁 (隐私模式残页): 读当空, 写静默吞掉", () => {
  const { calls, lsData } = runPage({
    localStorageBroken: true, standaloneMatch: true,
  });
  assert.equal(calls.replace, null);      // saved 读失败当 null → 不跳
  assert.equal(lsData.size, 0);           // record 的写也被 try 吞掉
});

test("切后台 (visibilitychange) 重记最终停留地址 (弹层深链靠它捕捉)", () => {
  const r = runPage({ pathname: "/tesla/trips", search: "?id=12", keepGlobals: true });
  try {
    assert.equal(typeof r.calls.visibility, "function");
    assert.equal(r.lsData.get(KEY), "/tesla/trips?id=12");
    r.page.location.search = "?id=13";    // 弹层开了另一条 (只动 URL 不重载)
    r.page.document.hidden = false;
    r.calls.visibility();                 // 回前台: 不重记
    assert.equal(r.lsData.get(KEY), "/tesla/trips?id=12");
    r.page.document.hidden = true;
    r.calls.visibility();                 // 切后台: 重记
    assert.equal(r.lsData.get(KEY), "/tesla/trips?id=13");
  } finally {
    r.teardown();   // 监听闭包运行时才查全局, 拆桩必须等用例做完
  }
});
