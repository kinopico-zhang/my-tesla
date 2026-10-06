"""3.0 单壳 (/tesla) 布线棘轮 (P2 立, P7 切换后壳是唯一页面)。

壳的骨架约定用字符串断言钉住: 视图直挂 main → 悬浮筛选条/菜单键 → 抽屉 →
弹层、下拉刷新手势面、touch-action 禁缩放、--top-clear 顶带留白、零历史
条目 (无 pushState)、echarts 按需注入、car_id 多车穿参。
P3-P6 每搬入一个视图这里相应放宽 (如 data-view 计数), 但已立下的约定只许
收紧不许回潮。3.3.0 抽屉的分组/拖拽/边条结构住 test_drawer。
充电视图生命周期 2026-09-26 搬去 test_shell_views (逐视图生命周
期本就住那边), 页面标题锁步拆去 test_asset_versions —— 这边满 200 行
硬上限。
"""
import re

from tests.tesla_static_files import (page_asset_paths, page_js,
                                      served_page)

SHELL = "/tesla"


def test_unauth_redirected_to_login(client):
    """未登录进壳: 302 到应用 scope 内的登录页, 带原地址回跳。"""
    r = client.get(SHELL, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/tesla/login?next=%2Ftesla"


def test_shell_skeleton(auth):
    """壳骨架: 12 视图直挂 main + 顶带留白 + 各固定层的标记都在
    (3.3.0 定稿: 筛选条 + 左抽屉; tab-dock 整编退役; 菜单圆键 2026-09-27
    退役 —— 边缘右划呼出抽屉全覆盖, 用户点名撤)。"""
    html = auth.get(SHELL).text
    for token in ('id="top-clear-probe"', 'id="view-charging"',
                  'data-view="charging"', 'id="filter-bar"',
                  'id="fb-pop"',
                  'id="drawer-mask"', '<aside id="drawer"', 'id="toast"'):
        assert token in html, f"壳缺骨架标记 {token}"
    assert 'id="menu-key"' not in html, "菜单圆键回潮了 (边缘右划已全覆盖)"
    # tab-dock 时代的标记不许回潮 (底部常驻页签/组包裹/二级横滑)
    for gone in ('id="tab-dock"', 'class="tab-group"', 'class="sub-pager"',
                 'class="sub-tabs"', "tesla-tab-dock", "syncTabDock"):
        assert gone not in html, f"tab-dock 残留 {gone}"
    # 下拉刷新改橡皮筋 + 文字提示 (用户点名): 药丸指示器浮层不许回潮,
    # 提示与手势钉在 test_pull_refresh_wiring
    assert 'id="ptr"' not in html and "ptr-lb" not in html
    # P2 充电 1 个 → P3 +统计/分组/日志 = 4 个 → P4 +行程 = 5 个 →
    # P5 +充电地图/足迹/驾驶 = 8 个 → P6 +设置三视图 (数据来源/地图设置/
    # 驾驶员; 日志 P3 已在设置组) = 11 个到齐; 3.3.0 定稿回 11 视图直挂;
    # 2026-09-27 账号设置拆独立页 → 12 个, 同日行程统计入行程组 → 13 个,
    # 同日电池健康度入充电组 → 14 个; 2026-09-30 常用地点入设置组 → 15 个
    assert html.count('data-view="') == 15


def test_zero_history_entries(auth):
    """零历史条目路由 (禁 iOS 边缘后退的前提): 永不 pushState,
    浏览器滚动恢复关掉, 带参旧链接进来只在加载期消费后 replaceState 洗掉。"""
    js = page_js(auth, SHELL)
    assert "pushState(" not in js
    assert 'history.scrollRestoration = "manual"' in js
    assert 'history.replaceState(null, "", "/tesla")' in js


def test_zoom_and_gesture_surfaces(auth):
    """禁双指缩放 (body 收口 pan-y) + 手势面接线: 列表滚动器右划开抽屉/
    在顶下拉刷新, 筛选条横滑区手势仲裁不掺和。"""
    page = served_page(auth, SHELL)
    assert "touch-action: pan-y" in page          # 禁缩放的主闸
    assert "touch-action: pan-x" in page          # 筛选条原生横滑
    js = page_js(auth, SHELL)
    assert "bindGestures(chgScroll, { drawer: true, ptr: true, onRefresh: chgRefetch })" in js
    assert "GESTURE_SLOP" in js                   # 8px 轴仲裁
    # 抽屉支线 (3.3.0 定稿回归): 仲裁只认右划 (dx > 0), 左划交还系统
    assert 'mode = "drawer"' in js and "drawerDragMove(dx)" in js
    # ptr 判定收紧 (2026-09-27 用户点名「左右滑会被判定下滑」): 明确向下
    # (dy > 2|dx|) 且在顶才算下拉刷新, 45° 斜角一律交还系统
    assert "dy > Math.abs(dx) * 2 && el.scrollTop <= 0" in js


def test_top_clear_band(auth):
    """顶部几何 (3.3.0 两级口径; 2026-09-27 用户报「状态页面最上面进入到了
    模糊地带」→ 全 app 统一): --content-top 直接落全局上边界 --top-clear
    (安全区+36px 起, 独立模式的系统磨砂带 ~96px 不再压内容, music 同款),
    各页 sec-head 的 20px 顶距随之退役 —— 全 app 标题同一水平线;
    --top-clear 只管钉顶的固定控件 (下拉刷新提示/抽屉躲系统磨砂带),
    量尺探针还在。"""
    page = served_page(auth, SHELL)
    assert "--top-clear" in page
    assert "--content-top: var(--top-clear)" in page
    assert "padding: var(--content-top) 0 var(--bar-clear)" in page  # 滚动器起点
    assert "calc(var(--top-clear) + 6px)" not in page   # 旧内容起点退役
    assert "calc(env(safe-area-inset-top, 0px) + 14px)" not in page   # 旧 14px 起点退役
    # sec-head 20px 顶距不许回潮 (标题统一落 --content-top 一条线)
    assert "padding: 20px 16px 4px" not in page
    assert "padding: 20px 0 4px" not in page


def test_z_ladder(auth):
    """z 阶梯 (自定义属性): 内容 < 筛选条/菜单键 < 筛选弹层 < 抽屉 < 充电
    弹层 < alert < toast。"""
    page = served_page(auth, SHELL)
    for token in ("--z-bar: 50", "--z-fb-pop: 85", "--z-drawer-mask: 95",
                  "--z-drawer: 96", "--z-chg-sheet: 100",
                  "--z-alert: 120", "--z-toast: 130"):
        assert token in page, f"z 阶梯缺 {token}"


def test_pull_refresh_wiring(auth):
    """每页下拉刷新 (橡皮筋款, 用户点名): 绑定面跟手阻尼下移, 过阈值
    (~70px 阻尼后) 浮出「松开刷新」裸文字提示; 松手 armed 才真正拉数,
    取消 (touchcancel) 只弹回不刷新。药丸气泡不许回潮。"""
    page = served_page(auth, SHELL)
    # 橡皮筋与提示: 弹回过渡 + 拉动跟手 + 过阈值浮出的裸文字
    for token in ('id="ptr-hint"', "松开刷新", ".ptr-elastic", ".ptr-pulling"):
        assert token in page, f"下拉刷新橡皮筋缺 {token}"
    # 药丸气泡不许回潮: 无 spinner/箭头骨架, 无第三态文案
    for token in ("正在刷新", 'id="ptr"', 'class="ptr-'):
        assert token not in page, f"下拉刷新气泡回潮 {token}"
    js = page_js(auth, SHELL)
    assert "ptrRelease" in js
    assert 'e.type === "touchcancel"' in js       # 系统打断只弹回不刷
    # 回调登记收进 bindGestures (cfg.onRefresh): 视图漏给 bindPTR 传回调
    # 的话手势会空转不拉数 (P5 前踩过); ptrMove = 下拉位移挂载 (舞台图传整舞台)
    assert "if (cfg.ptr) bindPTR(el, cfg.onRefresh, cfg.ptrMove)" in js


def test_boot_first_navigate_hides_default_view(auth):
    """冷启首跳把默认亮着的状态页藏净 (P2 叠影教训): HTML 里默认亮着
    view-live (其余 13 页 hidden), navigate 第一次跳转时还没有「上一视图」
    可藏 —— 恢复上次视图直跳行程页时状态页留在原地就是两页叠影。首跳
    (无上一视图) 必须把其余视图全藏掉。"""
    js = page_js(auth, SHELL)
    assert "querySelectorAll" in js
    assert "冷启首跳" in js
    html = served_page(auth, SHELL)
    assert 'class="view" id="view-live" data-view="live">' in html   # 唯一亮着
    assert len(re.findall(r'<section class="view"[^>]* hidden>', html)) == 14


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
    """旧充电链接 (?type=/?region=/?cost=) 加载期消费进壳状态, 随后洗掉
    —— 分享链接进壳不丢筛选; 时间参数 (?range=/?from=&to=) 3.3.0 随时间
    筛选下线, 进来直接被洗掉。"""
    js = page_js(auth, SHELL)
    assert 'qs.get("type")' in js
    assert 'qs.get("cost")' in js
    assert 'qs.get("region")' in js
    assert "脏参数丢弃" in js                      # 越界参数静默丢弃, 不 500


def test_time_filter_retired(auth):
    """时间筛选 3.3.0 整链下线 (用户令「时间筛选去掉, 所有的视图都是所有
    时间」): 档位/日历/时间 chip/参数拼装全拆, 各视图拉数不带 from/to
    (全时段); 模块文件本身也退役 (404)。"""
    page = served_page(auth, SHELL)
    for gone in ('id="time-menu"', "timeRangeParams", "timeLabel",
                 "onTimeChange", 'qs.get("range")'):
        assert gone not in page, f"时间筛选残留 {gone}"
    assert auth.get("/tesla/static/js/tesla-time-range.js").status_code == 404


def test_filter_bar_chips(auth):
    """悬浮筛选条: 有筛选的视图走 chips (充电三枚 / 行程), 弹层 #fb-pop
    锚在 chip 上方, 没注册 chips 的视图整条收起 (充电地图的度量
    2026-09-27 搬进页内 pills; 足迹 2026-10-02 驾驶员筛选并进播放条行尾
    #fp-drv, 也退役)。用户点名两条硬规矩: 筛选只在屏底固定位置
    (顶部不许再有筛选控件), chip 是裸文字不框椭圆 (选中靠底色, 不靠边框)。"""
    js = page_js(auth, SHELL)
    for v in ("charging", "trips"):
        assert f'registerChips("{v}"' in js
    assert 'registerChips("map"' not in js    # 足迹 chips 退役 (并播放条行)
    assert '"no-chips"' in js
    assert "anchorPop" in js
    assert "closeFbPop" in js
    # 点外收走 pointerdown (2026-10-02 全弹窗「从哪来回哪去」: 地图画布
    # preventDefault 后不合成 click, 靠 click 点地图收不起); Esc 一层一关
    assert 'document.addEventListener("pointerdown"' in js
    assert "e.stopImmediatePropagation();" in js
    page = served_page(auth, SHELL)
    assert 'id="view-seg"' not in page       # 顶部不留筛选控件
    i = page.index(".fchip {")               # chip 不框椭圆: 无边框无圆标
    block = page[i:page.index("}", i)]
    assert "border" not in block
