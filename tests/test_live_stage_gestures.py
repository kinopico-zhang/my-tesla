"""状态页左缘缝条 + 三舞台图下拉一体 (2026-10-04 用户报两处)。#175「在
状态页面, 我划了好多次才打开设置菜单」—— 舞台两侧 14px 出血缝里的触摸
谁也接不到 (卡内左缘条 #lv-edge 从 14px 才起), 屏缘 0-14px 是死缝;
#176「下拉的时候, 图标和数字会陷到地图后面」—— 下拉位移原来只挂触摸
宿主 (静态定位), 会被后画的 position:relative 画布盖过, 头部沉进地图。

#175 修法: #lv-gutter 视图层缝条 (0-40px 直挂 #view-live, 不进
.live-stage —— 舞台一被 transform 就成绝对定位后代的包含块), 左缘右划
从物理屏缘处处能呼出; 缝条自带 ptr (盖着卡内 14-40px 的原下拉面不丢) +
起手/收手/被抢三探针 + lv_boot 首启信标 —— 下次复现翻服务日志就能定罪
到具体一环, 10-01 的取证真空不重演。#176 修法: bindPTR 加 ptrMove 挂载
(宿主 → 位移元素的 WeakMap), 三舞台图 (live/.live-stage、足迹/#view-map、
充电地图/#view-chargemap) 下拉时整舞台一体跟手; 滚动视图不带 ptrMove,
行为分毫不动。住新文件: test_drawer / test_shell_wiring / test_shell_views
三处候选都顶满 200 行硬上限。"""
from tests.tesla_static_files import served_page

SHELL = "/tesla"


def _js(auth, name):
    return auth.get(f"/tesla/static/{name}").text


def test_lv_gutter_covers_screen_edge(auth):
    """#175: #lv-gutter 直挂 #view-live 段内 (live 视图区), .drawer-edge
    40px 全套规则吃现成; 缝条带 ptr+drawer —— 盖住卡内条 14-40px 的原
    下拉面, 不丢下拉。"""
    page = served_page(auth, SHELL)
    assert 'class="drawer-edge" id="lv-gutter"' in page, "状态页缝条骨架缺"
    assert page.index('id="view-live"') < page.index('id="lv-gutter"') < \
        page.index('data-view="trips"'), "缝条不在状态视图段内"
    js = _js(auth, "js/view/live-driving.js")
    assert 'const lvStage = $(".live-stage");' in js
    for frag in ('bindGestures($("#lv-panels"), { drawer: true, ptr: true, '
                 'onRefresh: poll, ptrMove: lvStage });',
                 'bindGestures($("#lv-gutter"), { drawer: true, ptr: true, '
                 'onRefresh: poll, ptrMove: lvStage });'):
        assert frag in js, f"状态页手势面缺 {frag}"


def test_lv_gutter_forensics_wiring(auth):
    """#175 取证: 缝条三探针 (起手/收手/被抢 cancel —— 被抢走的触摸没有
    end, 正是手势哑火要医的病) + lv_boot 首启信标 (确认手机真跑上 v13,
    排除旧缓存混跑)。"""
    js = _js(auth, "js/view/live-driving.js")
    for frag in ('diag("lv_gutter_touch"', 'diag("lv_gutter_end"',
                 'diag("lv_gutter_cancel"', 'diag("lv_boot"',
                 "if (!lvBootedDiag) { lvBootedDiag = true;"):
        assert frag in js, f"缝条取证缺 {frag}"


def test_ptr_move_indirection(auth):
    """#176: bindPTR 第三参 ptrMove 落 WeakMap (默认自身 = 旧行为分毫
    不动); ptrPull/ptrRelease 位移写挂载元素而不是触摸宿主 —— 宿主是
    静态定位会被后画的画布盖过, 头部才沉进地图。"""
    js = _js(auth, "js/tesla-pull-refresh.js")
    for frag in ("const PTR_MOVE = new WeakMap();",
                 "if (moveEl) PTR_MOVE.set(el, moveEl);",
                 "const m = PTR_MOVE.get(el) || el;",
                 "m.classList.add(\"ptr-pulling\");",
                 "m.style.transform = `translateY(${off}px)`;"):
        assert frag in js, f"位移挂载缺 {frag}"
    ges = _js(auth, "js/tesla-gesture.js")
    assert "if (cfg.ptr) bindPTR(el, cfg.onRefresh, cfg.ptrMove);" in ges, \
        "手势仲裁没把 ptrMove 透传给 bindPTR"


def test_three_stage_views_move_whole(auth):
    """#176 三舞台图: 状态页挂 .live-stage, 足迹挂 #view-map, 充电地图挂
    #view-chargemap —— 下拉时头部+画布一体跟手 (用户点名「不要陷到地图
    后面」); 滚动视图不带 ptrMove 的照旧只动自己。"""
    assert 'ptrMove: $("#view-map") });' in _js(auth, "js/view/map-filters.js")
    assert 'ptrMove: $("#view-chargemap") });' in \
        _js(auth, "js/view/chargemap-time-filters.js")
    page = served_page(auth, SHELL)
    assert "tesla-pull-refresh.js?v=3" in page, "下拉件没升 v3 (位移挂载)"
