"""3.3.0 侧滑抽屉菜单测试 (定稿, 用户点名「还是改成侧滑抽屉式的菜单吧,
不要底部常驻了菜单了」): 底部常驻页签 (tab-dock) 整链退役, 左抽屉纯导航
—— 车辆选择 3.3.0 定稿住抽屉顶 (点 pill 全局 setCar), 时间筛选整个下线
(所有视图全时段), 账号卡住设置页; 二级页直挂菜单入口, 二级之间的横滑
切换取消 (sub-pager/sub-tabs 随件退役)。

重点是对账: NAV_GROUPS (tesla-drawer.js) 与 app.html 的视图顺序是两处
手工同步的事实源, 靠肉眼必丢页 —— 对账钉住, 丢页/错序立即红。树状窄版
改款 (窄一点/树状/图标/iOS 风格) 的结构钉住 test_drawer_tree; tab-dock
时代的反向钉 (不许回潮) 住 test_shell_wiring/test_asset_versions。
"""
import re

from tests.tesla_static_files import page_js, served_page

SHELL = "/tesla"
DRAWER_JS = "js/tesla-drawer.js"


def _js(auth, name):
    return auth.get(f"/tesla/static/{name}").text


def _nav_groups(js):
    """NAV_GROUPS 抠成 [组名, [页键]] 列表 (保持声明序)。"""
    i = js.index("const NAV_GROUPS")
    block = js[i:js.index("];", i)]
    return [(m.group(1), re.findall(r'key: "([\w-]+)"', m.group(2)))
            for m in re.finditer(r'lb: "([^"]+)", items: \[([^\]]*)\]', block)]


# ---------------------------------------------------------------- 骨架
def test_drawer_anatomy(auth):
    """左抽屉: 蒙版 + 本体 (内容宽 min(180px, 88vw) —— 两轮收窄, 刚够排
    下最长标签), 纯导航 —— 只有 #drw-nav 一个孩子。菜单圆键 2026-09-27
    退役 (用户点名「设置按钮就不需要了」—— 任意页右划/地图左缘条都能
    呼出抽屉)。刷新按钮不回潮 (每个视图都能下拉刷新, 是冗余入口)。"""
    page = served_page(auth, SHELL)
    for token in ('id="drawer-mask"', '<aside id="drawer"',
                  'class="drw-nav" id="drw-nav"', 'id="bar-row"'):
        assert token in page, f"抽屉骨架缺 {token}"
    assert 'id="menu-key"' not in page and "#menu-key {" not in page   # 圆键退役
    assert page.index('id="fb-pop"') < page.index('id="drawer-mask"')   # 层序
    i = page.index("\n#drawer {")   # 行首锚: 避开 base.css 的 layer-anim 选择器
    block = page[i:page.index("}", i)]
    for frag in ("width: min(180px, 88vw)", "transform: translateX(-100%)",
                 "rgba(22,22,24,.88)", "blur(24px) saturate(180%)",
                 "cubic-bezier(.32,.72,.35,1)"):
        assert frag in block, f"抽屉本体缺 {frag}"
    assert "#drawer.on { transform: translateX(0); }" in page
    assert "#drawer.dragging { transition: none; }" in page   # 拖拽期不过渡
    assert 'id="refresh-btn"' not in page and "refresh-spin" not in page


def test_nav_groups_match_dom(auth):
    """NAV_GROUPS ↔ DOM 对账: 组数/组序/组内页序一一对应 (js 的 items
    vs app.html main 里 section 的先后); 顺序按用户原话 状态/行程/充电/设置。"""
    groups = _nav_groups(_js(auth, DRAWER_JS))
    assert [lb for lb, _ in groups] == ["状态", "行程", "充电", "设置"]
    assert dict(groups) == {
        "状态": ["live"],
        "行程": ["trips", "tripstats", "groups", "map"],   # 行程统计 2026-09-27
        "充电": ["charging", "stats", "battery", "chargemap"],   # 电池健康度 2026-09-27
        "设置": ["settings-account", "settings-db", "settings-map",
                 # 账号 09-27 拆页居首; 常用地点 09-30 (改名管理入口)
                 "settings-drivers", "settings-places", "changelog"]}
    assert sum(len(p) for _, p in groups) == 15          # 15 视图零孤儿
    html = served_page(auth, SHELL)
    keys = [k for _, pages in groups for k in pages]
    pos = [html.index(f'data-view="{k}"') for k in keys]
    assert pos == sorted(pos), "视图顺序与 NAV_GROUPS 不符"
    assert html.count('data-view="') == 15               # 对账没丢页没多页


# ---------------------------------------------------------------- 开合与拖拽
def test_drawer_open_close_wiring(auth):
    """开合两路: 点蒙版收 / Esc 收 (剥层链中环, 关了就
    stopImmediatePropagation 拦住往下传); 开 = 任意页右划 (地图页左缘条,
    菜单圆键 2026-09-27 退役后唯一呼出入口)。开抽屉顺带收筛选弹层。"""
    js = _js(auth, DRAWER_JS)
    for frag in ('$("#drawer-mask").addEventListener("click", closeDrawer)',
                 'if (e.key !== "Escape" || !drawerShown) return;',
                 "e.stopImmediatePropagation();", "closeFbPop();"):
        assert frag in js, f"开合接线缺 {frag}"
    assert '$("#menu-key")' not in js, "菜单圆键接线没拆干净"
    # Esc 链挂载顺序: 详情链 (视图脚本加载期) → 抽屉 → 筛选弹层 —— 一层
    # Esc 只关一层, bootDrawer 必须先于 bindFilterBar 挂
    boot = _js(auth, "js/tesla-app-boot.js")
    assert boot.index("bootDrawer();") < boot.index("bindFilterBar();")
    assert "→ 抽屉 → 筛选弹层" in boot


def test_drawer_drag_wiring(auth):
    """拖拽跟手: 视图右划开 (手势仲裁 drawer 支线转来, 快速右甩 flick 也
    算开); 抽屉身上左划收 (指针捕获, 竖滚放弃, 系统打断弹回开着); 蒙版
    浓度跟手。抽屉也是 fixed + 磨砂 + transform 的层: 7556 第五道保险
    (视口折腾后的微变换收净) 复用 bindSheetSettle。"""
    js = _js(auth, DRAWER_JS)
    ges = _js(auth, "js/tesla-gesture.js")
    for frag in ('mode = "drawer"', "drawerDragMove(dx);", "drawerDragEnd();"):
        assert frag in ges, f"手势仲裁缺 {frag}"
    for frag in ("const flick = dragVx > 0.5;", "d.setPointerCapture(pid);",
                 "if (dx < -w / 3 || (vx < -0.5 && dx < -20)) closeDrawer();",
                 "mask.style.opacity = String(0.5 * (x / w));"):
        assert frag in js, f"抽屉拖拽缺 {frag}"
    assert 'bindSheetSettle($("#drawer"), "on");' in js


def test_gesture_surfaces_and_edges(auth):
    """视图手势面: 各视图滚动器/手势面都接 drawer: true (17 处绑定); 地图
    类画布手势全给引擎 —— 右划开抽屉入口折到画布左缘 40px 窄条 (10-01
    用户报左缘手指常落卡外; #lv-gutter 10-04 / #cm-gutter 10-05 补缝条)。"""
    js = page_js(auth, SHELL)
    assert js.count("{ drawer: true, ptr: true,") == 17
    for edge in ("cm-edge", "cm-gutter", "fp-edge", "fp-gutter", "lv-edge"):
        assert f'bindGestures($("#{edge}"), {{ drawer: true }});' in js, \
            f"{edge} 边条绑定缺"
    page = served_page(auth, SHELL)
    for token in ('class="drawer-edge" id="lv-edge"', 'id="fp-edge"',
                  'id="cm-edge"', 'id="cm-gutter"'):
        assert token in page, f"边条骨架缺 {token}"
    block = page[page.index(".drawer-edge {"):page.index("}", page.index(".drawer-edge {"))]
    for frag in ("position: absolute", "left: 0", "width: 40px", "touch-action: none",
                 "z-index: 40"):
        assert frag in block, f"边条规则缺 {frag}"


def test_footprint_map_gate(auth):
    """足迹地图闸 (2026-10-06 用户点名「足迹道路拟合的 key 没填, 那么足迹
    地图将不可用, 菜单灰色」): 没配 Web 服务 Key 就没有道路拟合数据, 整页
    没意义 —— 菜单叶行灰掉不可点 (pointer-events 掐掉), navigate 拦旁路
    (上次停留视图恢复), 地图设置存上 Key 即时开闸 (mapSetLoad 同步现值,
    不用刷新); 默认放行, 设置拉取失败不误锁。"""
    js = _js(auth, DRAWER_JS)
    for frag in ("function setMapGate(", "function mapGateOpen()",
                 "async function initMapGate()", 'drw-leaf[data-nav="map"]',
                 'classList.toggle("off"', "web_key_masked", "initMapGate();"):
        assert frag in js, f"足迹地图闸缺 {frag}"
    nav = _js(auth, "js/tesla-navigation.js")
    assert 'if (key === "map" && !mapGateOpen()) return;' in nav, \
        "navigate 没拦足迹地图旁路"
    css = _js(auth, "css/tesla-drawer.css")
    assert ".drw-leaf.off { opacity: .4; pointer-events: none; }" in css, \
        "闸灰行样式缺"


def test_drawer_edge_unified(auth):
    """左缘右划统一呼出 (2026-10-07 用户点名「所有页面都要有统一的呼出设
    置菜单的逻辑: 左边缘任意位置右划」): 壳级 bindDrawerEdge 在 document
    捕获段挂一遍 —— 任何视图的任何表面 (页头/筛选条/没绑手势的角落) 起手
    ≤40px 右拖 → 抽屉, 不再靠每个视图自己记得绑。三处让位: .drawer-edge
    (地图页边条/缝条自己的 bindGestures 认, 双喂会掐死甩动测速) / 弹层
    (.sheet/#placed-sheet 有自己的层级) / 抽屉已开。手势仲裁同步让出
    左缘带: 滚动器 drawer 支线只认起手 >40px 的。"""
    js = _js(auth, DRAWER_JS)
    for frag in ("const DRAWER_EDGE = 40;", "function bindDrawerEdge()",
                 "t.clientX > DRAWER_EDGE",       # 只管左缘带
                 'input[type="range"], .drawer-edge, ',   # 滑块/边条/弹层让位
                 '"#drawer, #drawer-mask, .sheet, #placed-sheet"',
                 "e.preventDefault();",            # 认下后掐原生滚动
                 "drawerDragMove(dx);", "{ capture: true, passive: false }",
                 "bindDrawerEdge();"):             # bootDrawer 挂上
        assert frag in js, f"左缘统一呼出缺 {frag}"
    ges = _js(auth, "js/tesla-gesture.js")
    # 滚动器 drawer 支线让出左缘带; .drawer-edge 例外 (边条/缝条自己认)
    assert '(sx > DRAWER_EDGE || el.classList.contains("drawer-edge"))' in ges, \
        "手势仲裁没让出左缘带"
    assert "DRAWER_EDGE" in ges.split("/* global")[1].split("*/")[0], \
        "DRAWER_EDGE 没进手势仲裁的全局声明"


# ---------------------------------------------------------------- 导航通路
def test_navigation_plain_hidden(auth):
    """navigate 唯一通路: 页面各自 hidden 切换 (3.3.0 草稿的 tab-group 组
    路由已撤); 冷启首跳把默认亮着的状态页藏净 (P2 叠影教训)。"""
    nav = _js(auth, "js/tesla-navigation.js")
    for frag in ("prev.el.hidden = true;", "next.el.hidden = false;",
                 'document.querySelectorAll("main > .view").forEach(v => { v.hidden = true; });',
                 "冷启首跳", "syncDrawerNav(key);"):
        assert frag in nav, f"navigation 缺 {frag}"
    for gone in ("TABS", "hideGroup", "showGroup", "pagerEl", ".scrollTo("):
        assert gone not in nav, f"组路由残留: {gone}"
    html = served_page(auth, SHELL)
    assert html.count('<section class="view"') == 15
    assert 'class="view" id="view-live" data-view="live">' in html   # 唯一亮着
    assert len(re.findall(r'<section class="view"[^>]* hidden>', html)) == 14


def test_boot_default_live(auth):
    """冷启缺省落「状态」页 (3.3.0 前是充电记录); tab-dock 接线不留残影。"""
    js = _js(auth, "js/tesla-app-boot.js")
    assert ': (VIEWS[lastView] ? lastView : "live")' in js
    assert "bootDrawer();" in js
    assert "bindTabDock" not in page_js(auth, SHELL)


def test_selecting_hides_bottom_stack(auth):
    """多选态藏屏底悬浮条 (#bar-row, 圆键退役后只剩筛选条) —— selbar 占
    屏底槽; 磨砂幽灵对策 (layer-anim) 两选择器 (筛选条/抽屉)。"""
    page = served_page(auth, SHELL)
    assert "body.selecting #bar-row { display: none; }" in page
    for sel in ("#filter-bar,", "#drawer {"):
        assert f"body.layer-anim {sel}" in page


# ---------------------------------------------------------------- 全局 chips
def test_global_chips_retired(auth):
    """全局 chips 双双退役: 车辆选择定稿住抽屉顶 (点 pill 全局 setCar, 车辆
    卡钉在 test_drawer_tree), 时间筛选整个下线 (用户令「时间筛选去掉, 所有
    的视图都是所有时间」) —— #shell-stash/时间菜单/日历/参数拼装整链拆掉,
    筛选条只剩各视图自己的 chips; 菜单圆键 2026-09-27 退役后, 没注册
    chips 的视图整条 #bar-row 收起, 底部让位 --bar-clear 跟着收
    (body.no-bar, 几何在 tesla-base)。"""
    page = served_page(auth, SHELL)
    js = page_js(auth, SHELL)
    for gone in ('id="shell-stash"', 'id="time-menu"', "GLOBAL_CHIP_VIEWS",
                 "timeLabel", "timeRangeParams", "onTimeChange",
                 'id: "car"', "currentCarLabel", "function stashBack()"):
        assert gone not in page, f"全局 chips 残留 {gone}"
    assert auth.get("/tesla/static/js/tesla-time-range.js").status_code == 404
    assert '$("#bar-row").classList.toggle("no-chips", noChips);' in js
    assert "#bar-row.no-chips { display: none; }" in page
    assert 'document.body.classList.toggle("no-bar", noChips);' in js
    assert "body.no-bar { --bar-clear: calc(env(safe-area-inset-bottom) + 10px); }" in page
    assert 'setCar(b.dataset.car === "" ? null : +b.dataset.car);' in js


# ---------------------------------------------------------------- 账号卡
def test_account_card(auth):
    """账号三卡 (3.3.0 从抽屉底部搬来, 2026-09-27 拆成账号设置独立页 —— 设置组
    首位, 数据来源第二), id 沿用抽屉时代命名; 2026-10-05 二改 (用户点名): 账号
    名行内编辑 + 修改密码 + 登出分三张卡, 说明行退役; 抽屉本体纯导航 —— 账号
    不在抽屉里 (车辆选择定稿住抽屉顶, 时间筛选已下线)。"""
    page = served_page(auth, SHELL)
    for token in ('id="acct-card"', 'id="acct-name"', 'id="acct-badge"',
                  'id="me-name-input"', 'id="me-name-cancel"',
                  'id="pass-card"', 'id="me-pass-save"', 'id="logout"',
                  "acct-out", '<h2>账号设置</h2>', 'id="acct-scroll"'):
        assert token in page, f"账号卡缺 {token}"
    acct = page.index('data-view="settings-account"')
    db = page.index('data-view="settings-db"')
    assert acct < page.index('id="acct-card"') < db   # 三卡住自己的独立页 (设置组首位)
    assert 'id="acct-card"' not in page[db:page.index('id="view-settings-map"')]   # 数据来源页不再有
    drw = page[page.index('<aside id="drawer"'):page.index("</aside>")]
    for gone in ("acct", "time-menu", "logout"):
        assert gone not in drw, f"抽屉里混进了 {gone}"
