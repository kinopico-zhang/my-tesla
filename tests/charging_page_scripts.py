"""充电页静态资产助手: 页面脚本拼接 + 资产清单。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""


# 充电记录/统计页共用格式化拆去了 format.js: 页面片段断言把先加载的
# format.js 一并拼进来查子串
def _page_scripts(auth, *names):
    return "".join(auth.get(f"/tesla/static/{name}").text for name in names)


# 充电页脚本/样式拆去了 js/ 与 css/ (结构化重构): 整页断言把引用的
# 资产全拼进来查子串
CHARGING_ASSETS = ("css/tesla-charging-page.css", "css/tesla-charging-cards.css",
                   "css/tesla-charging-sheet.css", "js/format.js",
                   "js/charging-page.js", "js/charging-cards.js",
                   "js/charging-filters.js", "js/charging-detail.js",
                   "js/charging-nav.js", "js/charging-cost.js")
