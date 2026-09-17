// stylelint 配置: 覆盖四个应用的全部 CSS (见 run_tests.sh 调用)。
// 基于 stylelint-config-standard, 按手写紧凑样式表的实情收窄:
// 保留抓真错的规则 (解析错误/未知属性/非法取值/重复声明), 关掉纯排版意见
// (紧凑单行/空行节奏/颜色老写法) —— 存量代码不重排, 新代码同风格。
const config = {
  extends: ["stylelint-config-standard"],
  rules: {
    // Safari/WebKit 兼容前缀是手写故意保留的 (backdrop-filter/
    // -webkit-tap-highlight-color 等), 不当冗余报错
    "property-no-vendor-prefix": null,
    "value-no-vendor-prefix": null,
    "media-feature-name-no-vendor-prefix": null,
    "at-rule-no-vendor-prefix": null,
    // 紧凑单行规则 + 不强制空行是全仓库既有风格
    "declaration-block-single-line-max-declarations": null,
    "rule-empty-line-before": null,
    "comment-empty-line-before": null,
    "at-rule-empty-line-before": null,
    "declaration-empty-line-before": null,
    "custom-property-empty-line-before": null,
    // rgba(…,.5) 老写法与 min-/max- 媒体查询照旧 (行为等价, 不为改写而改写)
    "color-function-notation": null,
    "color-function-alias-notation": null,
    "alpha-value-notation": null,
    "media-feature-range-notation": null,
    // 特异度顺序/重复选择器/长属性合并/弃用关键字 (word-break: break-word
    // 全浏览器实支持) 属代码风格权衡, 手写样式里合法且常见
    "no-descending-specificity": null,
    "no-duplicate-selectors": null,
    "declaration-block-no-redundant-longhand-properties": null,
    "declaration-property-value-keyword-no-deprecated": null,
  },
};

export default config;
