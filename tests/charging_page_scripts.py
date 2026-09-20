"""充电视图静态资产助手: 页面脚本拼接 + 资产清单。
拆自 test_charging.py (结构化重构; P7 起指向壳内 js/view/ 版本)。"""


# 充电记录/统计视图共用格式化拆去了 format.js: 片段断言把先加载的
# format.js 一并拼进来查子串
def _page_scripts(auth, *names):
    return "".join(auth.get(f"/tesla/static/{name}").text for name in names)


# 充电视图脚本/样式拆去了 js/view/ 与 css/ (3.0 单壳): 整页断言把引用的
# 资产全拼进来查子串
CHARGING_ASSETS = ("css/tesla-charging-page.css", "css/tesla-charging-cards.css",
                   "css/tesla-charging-sheet.css", "js/format.js",
                   "js/view/charging-page.js", "js/view/charging-cards.js",
                   "js/view/charging-filters.js", "js/view/charging-detail.js",
                   "js/view/charging-nav.js", "js/view/charging-cost.js")
