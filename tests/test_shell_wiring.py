"""3.0 单壳 (/tesla) 布线棘轮 (P2 立, P7 切换后壳是唯一页面)。

壳的骨架约定用字符串断言钉住: 三层结构 (视图列表 → 悬浮筛选条 → 弹层)、
右划抽屉 + 下拉刷新手势面、touch-action 禁缩放、--top-clear 顶带留白、
零历史条目 (无 pushState)、echarts 按需注入、充电视图 registerView
生命周期、car_id 多车穿参。P3-P6 每搬入一个视图这里相应放宽 (如
data-view 计数), 但已立下的约定只许收紧不许回潮。
"""
from tests.tesla_static_files import (page_asset_paths, page_js,
                                      served_page)

SHELL = "/tesla"


def test_unauth_redirected_to_login(client):
    """未登录进壳: 302 到应用 scope 内的登录页, 带原地址回跳。"""
    r = client.get(SHELL, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/tesla/login?next=%2Ftesla"


def test_shell_skeleton(auth):
    """壳骨架: 三层结构 + 顶带留白 + 各固定层的标记都在。"""
    html = auth.get(SHELL).text
    for token in ('id="top-blur"', 'id="view-charging"',
                  'data-view="charging"', 'id="ptr"', 'id="bar-row"',
                  'id="menu-key"', 'id="filter-bar"', 'id="fb-pop"',
                  'id="drawer-mask"', '<aside id="drawer"', 'id="toast"'):
        assert token in html, f"壳缺骨架标记 {token}"
    # P2 充电 1 个 → P3 +统计/分组/日志 = 4 个 → P4 +行程 = 5 个 →
    # P5 +充电地图/足迹/驾驶 = 8 个 → P6 +设置三视图 (数据来源/地图设置/
    # 驾驶员; 日志 P3 已在设置组) = 11 个到齐
    assert html.count('data-view="') == 11


def test_drawer_anatomy(auth):
    """抽屉: 分组导航全量 (用户原话的四组), 顶=时间/车辆, 底=账号/登出。
    刷新按钮已撤 (用户点名): 每个视图都能下拉刷新, 按钮是冗余入口。"""
    js = page_js(auth, SHELL)
    page = served_page(auth, SHELL)
    for token in ('"充电记录"', '"充电统计"', '"充电地图"',
                  '"行程列表"', '"行程分组"', '"足迹地图"', '"驾驶"',
                  '"数据来源"', '"地图设置"', '"驾驶员"', '"更新日志"',
                  'bootDrawer', "car-pills",
                  '$("#acct-row")', "logout", "drwIcon"):
        assert token in js, f"抽屉缺 {token}"
    assert "NAV_GROUPS" in js          # 分组显示 (不是平铺列表)
    # 刷新按钮不许回来 (下拉刷新 + 换车/换时间档整页重拉已覆盖)
    assert 'id="refresh-btn"' not in page
    assert "refresh-spin" not in page
    # 导航 = 图标瓦片网格 (用户点名: 抽屉加宽, 子项每行 4 个压纵向空间)
    assert ".drw-grid" in page and "repeat(4, 1fr)" in page
    assert "width: min(400px, 92vw)" in page
    # 顶部一排: 车辆在前, 时间范围在后 (用户点名); 时间菜单要写明是时间范围
    assert page.index('id="drw-cars"') < page.index('id="time-menu"')
    assert '<span class="drw-lb">时间范围</span>' in page
    # 首行控件不进顶部模糊带 (用户点名, 与视图内容同一条全局上边界)
    assert "padding: calc(var(--top-clear) + 14px) 14px 10px;" in page
    # 时间菜单展开时整块占满一行 (日历 7×34px 在半宽里放不下)
    assert ".drw-menu[open] { flex-basis: 100%; }" in page


def test_zero_history_entries(auth):
    """零历史条目路由 (禁 iOS 边缘后退的前提): 永不 pushState,
    浏览器滚动恢复关掉, 带参旧链接进来只在加载期消费后 replaceState 洗掉。"""
    js = page_js(auth, SHELL)
    assert "pushState(" not in js
    assert 'history.scrollRestoration = "manual"' in js
    assert 'history.replaceState(null, "", "/tesla")' in js


def test_zoom_and_gesture_surfaces(auth):
    """禁双指缩放 (body 收口 pan-y) + 手势面接线: 列表滚动器右开抽屉/
    在顶下拉刷新, 筛选条横滑区手势仲裁不掺和。"""
    page = served_page(auth, SHELL)
    assert "touch-action: pan-y" in page          # 禁缩放的主闸
    assert "touch-action: pan-x" in page          # 筛选条原生横滑
    js = page_js(auth, SHELL)
    assert "bindGestures(chgScroll, { drawer: true, ptr: true, onRefresh: chgRefetch })" in js
    assert "GESTURE_SLOP" in js                   # 8px 轴仲裁


def test_top_clear_band(auth):
    """顶部模糊带不放固定控件: 列表初始态停在 --top-clear 界下,
    顶带本体只是视觉层。"""
    page = served_page(auth, SHELL)
    assert "--top-clear" in page
    assert "calc(var(--top-clear) + 6px) 0 var(--bar-clear)" in page  # 滚动器让位


def test_z_ladder(auth):
    """z 阶梯 (自定义属性): 内容 < 筛选条 < 抽屉 < 充电弹层 < alert < toast。"""
    page = served_page(auth, SHELL)
    for token in ("--z-bar: 50", "--z-drawer: 96", "--z-chg-sheet: 100",
                  "--z-alert: 120", "--z-toast: 130"):
        assert token in page, f"z 阶梯缺 {token}"


def test_pull_refresh_wiring(auth):
    """每页下拉刷新: 指示器文案三态, 松手才真正拉数据, 取消 (touchcancel)
    弹回不刷新。"""
    page = served_page(auth, SHELL)
    for token in ("下拉刷新", "松手刷新", "正在刷新"):
        assert token in page, f"下拉刷新缺文案 {token}"
    js = page_js(auth, SHELL)
    assert "ptrRelease" in js
    assert 'e.type === "touchcancel"' in js       # 系统打断只弹回不刷
    # 回调登记收进 bindGestures (cfg.onRefresh): 视图漏给 bindPTR 传回调
    # 的话指示器会空转不拉数 (P5 前踩过, 四个视图一起中招)
    assert "if (cfg.ptr) bindPTR(el, cfg.onRefresh)" in js


def test_charging_view_lifecycle(auth):
    """充电视图生命周期: registerView 注册, IO 哨兵随 show/hide 建拆,
    首进 boot, 换车/换筛选整页重拉。"""
    js = page_js(auth, SHELL)
    assert 'registerView("charging"' in js
    assert "makePager(" in js
    assert "chgBooted" in js                       # 首次进视图才 boot
    assert "chgPager.start()" in js and "chgPager.stop()" in js
    assert "chgRefetch" in js                      # 详情缓存同页要清


def test_echarts_lazy_loaded(auth):
    """echarts 1MB 不再随页拖: 壳不引 echarts.min.js, 详情打开才按需注入。"""
    assert not any("echarts.min.js" in p for p in page_asset_paths(auth, SHELL))
    js = page_js(auth, SHELL)
    assert "loadEcharts" in js
    assert "await loadEcharts()" in js             # 用到才等注入


def test_car_id_wiring(auth):
    """多车穿参: 车辆行拉 /tesla/charging/api/car, 全部 pill 缺省,
    sessionParams 带 car_id, 选择持久化 tesla.shell。"""
    js = page_js(auth, SHELL)
    assert '"/tesla/charging/api/car"' in js
    assert 'data-car=""' in js                     # "全部" pill (缺省)
    assert "shellState.carId != null" in js        # 全部 = 不带 car_id
    assert '"car_id", String(shellState.carId)' in js
    assert '"tesla.shell"' in js                   # localStorage 持久化


def test_url_consumed_at_load(auth):
    """旧链接 (?type=/?region=/?cost=/?range=/?from=&to=) 加载期消费进
    壳状态, 随后洗掉 —— 分享链接进壳不丢筛选。"""
    js = page_js(auth, SHELL)
    assert 'qs.get("type")' in js
    assert 'qs.get("cost")' in js
    assert 'qs.get("region")' in js
    assert 'trQs.get("range")' in js or 'qs.get("range")' in js
    assert "脏参数丢弃" in js                      # 越界参数静默丢弃, 不 500


def test_time_range_shared(auth):
    """时间筛选五份合一份: 档位/日历在 tesla-time-range, 抽屉里改档
    当前视图整体重拉。"""
    js = page_js(auth, SHELL)
    assert "const TIME_RANGES" in js
    for v in ('"24h"', '"7d"', '"30d"', '"180d"', '"1y"', '"all"'):
        assert f"v: {v}," in js, f"时间档缺 {v}"
    assert "onTimeChange" in js and "setTimeRange" in js


def test_filter_bar_chips(auth):
    """悬浮筛选条: 有筛选的视图全部走 chips (充电三枚 / 行程 / 足迹 / 充电
    地图的度量), 弹层 #fb-pop 锚在 chip 上方, 没注册 chips 的视图整条收起。
    用户点名两条硬规矩: 筛选只在屏底固定位置 (顶部不许再有筛选控件),
    chip 是裸文字不框椭圆 (选中靠底色, 不靠边框)。"""
    js = page_js(auth, SHELL)
    for v in ("charging", "trips", "map", "chargemap"):
        assert f'registerChips("{v}"' in js
    assert '"no-chips"' in js
    assert "anchorPop" in js
    assert "closeFbPop" in js
    page = served_page(auth, SHELL)
    assert 'id="view-seg"' not in page       # 顶部不留筛选控件
    i = page.index(".fchip {")               # chip 不框椭圆: 无边框无圆标
    block = page[i:page.index("}", i)]
    assert "border" not in block
