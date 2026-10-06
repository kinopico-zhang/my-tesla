"""手势仲裁自愈 + 左缘右划取证钉 (2026-10-04 用户报「右划返回失效」)。

jsdom 复现实锤的哑火路: 一次触摸的 end/cancel 被系统吞掉 (边缘手势抢
走/打断), tesla-gesture 的 tid 永占 → 该元素的手势哑火到整页重载。
v7 自愈 = 新触摸起手时对账 e.touches, 被跟的那根已不在 (手指早离屏)
就清场认新触摸 (半开的抽屉/下拉先收拾干净); 真多指照旧只认第一根。
取证补盲: 缝条 (0-40px) 盖在边条 (卡内 16-56px) 头上, 左缘起手全落
缝条 —— 10-01 的边条/画布两路探针因此从没响过 (证据真空)。v16 补缝
条起手/收手/被抢三探针 + 地图首启版本信标 + 抽屉开张信标, 下次复现
翻服务日志就能定罪到具体一环。住新文件: test_drawer / test_map_pages
/ test_map_roads_pages 三处候选都顶满 200 行硬上限。"""
from tests.tesla_static_files import served_page

SHELL = "/tesla"


def _js(auth, name):
    return auth.get(f"/tesla/static/{name}").text


def test_gesture_swallowed_end_selfheal(auth):
    """v7 自愈: 占着 tid 的那根已不在 e.touches (end 被吞, 手指早离屏)
    就清场认新触摸; drawer/ptr 半程先各自收尾。"""
    js = _js(auth, "js/tesla-gesture.js")
    for frag in ("gone = true",
                 "e.touches.item(i).identifier === tid",
                 'if (mode === "drawer") drawerDragEnd();',
                 "ptrRelease(el, true);",
                 'tid = -1; mode = "";'):
        assert frag in js, f"手势自愈缺 {frag}"
    # 只认第一根的规矩不回潮: 真多指 (旧指还在 e.touches 里) 照旧让位
    assert "if (!gone) return;" in js


def test_map_gutter_forensics_wiring(auth):
    """左缘取证补盲 (2026-10-04): 缝条三探针 (起手/收手/被抢 cancel ——
    抢走的触摸没有 end, 正是自愈要医的病) + 地图首启版本信标 (确认手机
    真跑上 v16, 排除旧缓存混跑) + 抽屉开张信标 (手势链最后一环)。"""
    mf = _js(auth, "js/view/map-filters.js")
    for frag in ('diag("fp_gutter_touch"', 'diag("fp_gutter_end"',
                 'diag("fp_gutter_cancel"', 'diag("fp_boot"',
                 'diag("fp_drawer_open"', "const fpOrigOpenDrawer = openDrawer;"):
        assert frag in mf, f"缝条取证缺 {frag}"
    page = served_page(auth, SHELL)
    assert "tesla-gesture.js?v=9" in page, "手势仲裁没升 v9"
    assert "map-filters.js?v=17" in page, "map-filters 没升 v17"
