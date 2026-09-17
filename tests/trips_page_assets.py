"""行程页静态资产清单: CSS 四件套 + 拆分后的全部 JS 模块拼接。
行程页样式拆去了 css/ 四件套, 脚本按域拆成了 19 个模块 (结构化重构):
页面片段断言可能落在其中任何一个, 全部拼起来查子串 (含 "not in" 守卫,
残留在哪个文件都算回潮)。拆自 test_trips.py (代码逐字节未动)。"""


# 行程页样式拆去了 css/ 四件套, 脚本按域拆成了 19 个模块 (结构化重构):
# 页面片段断言可能落在其中任何一个, 全部拼起来查子串 (含 "not in" 守卫,
# 残留在哪个文件都算回潮)
TRIPS_ASSETS = ("css/tesla-trips-page.css", "css/tesla-trips-cards.css",
                "css/tesla-trips-sheet.css", "css/tesla-trips-playback.css",
                "js/format.js", "js/track-animation.js", "js/trip-playback.js",
                "js/trips-list-page.js", "js/trips-list-url.js",
                "js/trips-list-time-filters.js", "js/trips-list-region-filters.js",
                "js/trips-list-select.js", "js/trips-list-groups.js",
                "js/trips-sheet-page.js", "js/trips-playback-bar.js",
                "js/trips-gap-routing.js", "js/trips-playback-zoom.js",
                "js/trips-playback-overlays.js", "js/trips-playback-loop.js",
                "js/trips-playback-session.js", "js/trips-preload-tiles.js",
                "js/trips-preload-vector.js", "js/trips-sheet-driver.js",
                "js/trips-sheet-open.js", "js/trips-export-video.js",
                "js/trips-sheet-close.js")


def _trips_scripts(auth):
    return "".join(auth.get(f"/tesla/static/{name}").text for name in TRIPS_ASSETS)
