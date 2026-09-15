// ESLint 9 扁平配置 —— 前端门禁 (与后端 pylint/mypy 对齐, 由 run_tests.sh 与 CI 调用)。
// node_modules 不进 git (CI 用 npm ci 安装); 注意: `...js.configs.recommended`
// 只带 name/rules 等键, 块内若再写 `rules:` 会整体覆盖展开结果
// (recommended 悄悄失效过), 必须 `...js.configs.recommended.rules`。
import js from "@eslint/js";
import globals from "globals";

// 页面脚本通用规则: recommended 全量 + 允许函数提升引用 (事件驱动组织)
const pageScript = {
  ...js.configs.recommended,
  rules: {
    ...js.configs.recommended.rules,
    "no-use-before-define": ["error", { functions: false, classes: false }],
    // 经典脚本的 catch 静默吞错是常态 (fetch 失败已有兜底展示)
    "no-unused-vars": ["error", { caughtErrors: "none" }],
    "no-empty": ["error", { allowEmptyCatch: true }],
  },
};

export default [
  // 不检查: 高德/echarts 第三方压缩包、venv、数据目录
  { ignores: ["app/tesla/static/echarts.min.js", ".venv/**", "data/**", "node_modules/**"] },

  // Tesla 应用 (app/tesla/static): 按脚本分层声明跨文件全局 (定义者与
  // 使用者分开, 避免同文件 no-redeclare)。加载顺序: 纯逻辑 UMD 模块
  // (gcj02/trackutil/format/trip-playback) → 页面脚本; 行程页再多一层
  // trips-list (列表/筛选) 在 trips (弹层/播放) 之前。
  {
    files: ["app/tesla/static/gcj02.js",
            "app/tesla/static/trackutil.js",
            "app/tesla/static/format.js",
            "app/tesla/static/trip-playback.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        module: "readonly",        // UMD 尾巴: node 测试路径走 module.exports
        require: "readonly",       // trip-playback.js 依赖同目录 trackutil.js
      },
    },
  },
  {
    // gcj02 参考实现的常量 (PI/EE) 本就超出 double 精度, 逐位照抄别四舍五入
    files: ["app/tesla/static/gcj02.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser, module: "readonly" },
    },
    rules: { ...pageScript.rules, "no-loss-of-precision": "off" },
  },
  {
    files: ["app/tesla/static/lastpage.js",
            "app/tesla/static/groups.js",
            "app/tesla/static/settings.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser },
    },
  },
  {
    files: ["app/tesla/static/map.js",
            "app/tesla/static/chargemap.js",
            "app/tesla/static/live.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        AMap: "readonly",                 // 高德 JS API 全局命名空间
        _AMapSecurityConfig: "writable",  // 高德安全密钥配置 (页面赋值)
        GCJ02: "readonly",                // gcj02.js 先加载
        TrackUtil: "readonly",            // trackutil.js 先加载 (map/live)
      },
    },
  },
  {
    files: ["app/tesla/static/index.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        FormatUtil: "readonly",     // format.js 先加载 (顶部解构)
        GCJ02: "readonly",
        echarts: "readonly",        // echarts.min.js 先于页面脚本加载
      },
    },
  },
  {
    files: ["app/tesla/static/stats.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        FormatUtil: "readonly",
        echarts: "readonly",
      },
    },
  },
  {
    files: ["app/tesla/static/trips-list.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        FormatUtil: "readonly",
        // trips.js 后于本脚本加载: 这些是弹层入口, 事件回调触发时早已就绪
        openTrip: "readonly", openMerged: "readonly",
      },
    },
  },
  {
    files: ["app/tesla/static/trips.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        AMap: "readonly",
        _AMapSecurityConfig: "writable",
        GCJ02: "readonly",
        TrackUtil: "readonly",      // trackutil.js 先加载
        TripPlayback: "readonly",   // trip-playback.js 先加载
        FormatUtil: "readonly",     // format.js 先加载
        // trips-list.js 先于本脚本加载 (经典脚本, 顶层声明进全局):
        // 列表状态与渲染函数, 弹层在事件回调里引用
        state: "readonly", items: "readonly", listEl: "readonly",
        trackCache: "readonly", renderCard: "readonly",
        listURL: "readonly", toast: "readonly", esc: "readonly",
        $: "readonly", getJSON: "readonly", postJSON: "readonly",
        loadMore: "readonly", urlTripKey: "readonly",   // 地址栏深链 (trips-list)
        // trips-list.js 顶部解构声明的格式化名, 本页直接沿用 (不重复声明)
        fmtCardDate: "readonly", fmtDur: "readonly", num: "readonly",
        driversCache: "writable",      // let 声明的共享缓存, 本页也写 (拉驾驶员表)
      },
    },
  },

  // 账号层 (app/static): 登录/注册/账号管理的页面脚本
  {
    files: ["app/static/*.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser },
    },
  },

  // 前端单元测试 (node:test, ESM)
  {
    files: ["tests/js/*.mjs"],
    ...js.configs.recommended,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.node },
    },
  },
];
