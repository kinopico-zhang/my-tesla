// ESLint 9 扁平配置 —— 前端门禁 (与后端 pylint/mypy 对齐, 由 run_tests.sh 调用)。
// 独立仓口径: 账号层页面 (app/home/static) + Tesla 应用 (app/tesla/static/js,
// 纯逻辑 UMD 模块与页面脚本都住 js/ 子目录, 跨模块引用走全局, 头部自带
// /* global */ 与 /* exported */ 注释)。
// 注意: `...js.configs.recommended` 只带 name/rules 等键, 块内若再写 `rules:`
// 会整体覆盖展开结果 (recommended 悄悄失效过), 必须 `...js.configs.recommended.rules`。
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
  // 不检查: 压缩的第三方库 / venv / 数据目录 / node_modules (组合仓内是软链)
  { ignores: ["app/tesla/static/echarts.min.js", ".venv/**", "data/**",
              "node_modules/**"] },

  // 账号层 (app/home/static): 登录/注册/账号管理页面脚本 (经典脚本,
  // 按 html 里的顺序加载; 跨模块引用走全局, 头部自带 /* global */ 注释)
  {
    files: ["app/home/static/*.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser },
    },
  },

  // Tesla 应用 (app/tesla/static/js): 纯逻辑 UMD 模块 (gcj02/trackutil/
  // track-animation/format/trip-playback/lastpage) 与页面脚本都住 js/ 子目录
  // (结构化重构: 大页面脚本按逻辑拆成见名知意的小文件, 经典脚本按各自
  // html 里的顺序加载)。跨模块引用走全局, 每个文件头部自带 /* global */
  // (用到别处定义的) 与 /* exported */ (本文件定义、别处用的) 注释 ——
  // 配置里不再按文件列举。加载层级见各 html: UMD 纯逻辑 → 页面脚本;
  // 行程页 trips-list (列表/筛选) 在 trips (弹层/播放) 之前。
  {
    files: ["app/tesla/static/js/*.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        module: "readonly",               // UMD 尾巴: node 测试路径走 module.exports
        require: "readonly",              // UMD 模块间依赖 (track-animation/trip-playback)
        AMap: "readonly",                 // 高德 JS API 全局命名空间
        _AMapSecurityConfig: "writable",  // 高德安全密钥配置 (页面赋值)
        echarts: "readonly",              // echarts.min.js (static 根, 第三方) 先于页面脚本加载
      },
    },
  },
  {
    // gcj02 参考实现的常量 (PI/EE) 本就超出 double 精度, 逐位照抄别四舍五入
    files: ["app/tesla/static/js/gcj02.js"],
    ...pageScript,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser, module: "readonly" },
    },
    rules: { ...pageScript.rules, "no-loss-of-precision": "off" },
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
