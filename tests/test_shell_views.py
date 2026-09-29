"""3.0 单壳视图测试 (P3 立, 随 P4-P6 各视图搬入继续长)。

test_shell_wiring 钉壳本身的骨架约定; 这里放逐视图的生命周期断言
(registerView/首进 boot/手势面) 与跨页资产完整性 —— 引用即存在: 页面里
引用的每个本地资源都真 200, 写错目录的脚本在拼装口径里会静默变空串,
只有逐个打一遍才露馅 (P3 真踩过: 视图脚本落进 js/ 根目录)。
充电视图生命周期 2026-09-26 从 test_shell_wiring 搬来 (那边满 200 行
硬上限)。
"""
from tests.tesla_static_files import (PAGES, page_asset_paths, page_js,
                                      served_page)

SHELL = "/tesla"


def test_all_referenced_assets_exist(auth):
    """引用即存在: 每个页面引用的本地资源都真 200 (写错目录/删文件立红)。"""
    for page in PAGES:
        for ref in page_asset_paths(auth, page):
            r = auth.get(ref)
            assert r.status_code == 200, \
                f"{page} 引用的 {ref} 不存在 ({r.status_code})"

def test_charging_view_lifecycle(auth):
    """充电视图生命周期: registerView 注册, IO 哨兵随 show/hide 建拆,
    首进 boot, 换车/换筛选整页重拉。"""
    js = page_js(auth, SHELL)
    assert 'registerView("charging"' in js
    assert "makePager(" in js
    assert "chgBooted" in js                       # 首次进视图才 boot
    assert "chgPager.start()" in js and "chgPager.stop()" in js
    assert "chgRefetch" in js                      # 详情缓存同页要清


def test_stats_view_lifecycle(auth):
    """统计视图生命周期: 首进视图才注 echarts (hidden 段内 init 是 0×0),
    注入失败亮错误盒等重试 (表格视图 2026-09-27 退役, 不再有落表格兜底),
    回视图补 resize, 四路统计带 car_id。"""
    js = page_js(auth, SHELL)
    assert 'registerView("stats"' in js
    assert "statsBooted" in js                       # 首次进视图才 boot
    assert "await loadEcharts()" in js
    assert "ensureEcharts()" in js                   # 图表库注入 (失败留 loadAll 收尾亮灯)
    assert '"图表库加载失败"' in js                   # 拉不到图表库: 错误盒如实亮灯
    assert "statsResize()" in js                     # 藏起期间变过列数, 回来重排
    assert 'getJSON("/tesla/charging/api/summary?" + statsParams())' in js


def test_groups_and_changelog_lifecycle(auth):
    """分组/日志视图: registerView 注册, 首进才拉数据, 手势面与充电同款;
    分组打开 = 壳级合并弹层直接开 (openMerged 带分组名, 分组页自己当宿主
    —— 2026-09-22 起 sheet 升壳级, 背后停在分组列表不闪行程轨迹)。"""
    js = page_js(auth, SHELL)
    assert 'registerView("groups"' in js
    assert "gpBooted" in js
    assert '"/tesla/trips/api/groups"' in js
    assert 'sheetFrom = "groups";' in js               # 弹层来源: 地址栏镜像 view=groups
    assert "openMerged(item.dataset.ids, null, group)" in js
    # 关弹层停在原列表不刷新 (2026-09-25 用户点名去掉每次关闭转圈重拉):
    # 分组页当宿主后视图没换过, 旧版同键 navigate = refreshCurrent = gpLoad
    close_js = auth.get("/tesla/static/js/view/trips-sheet-close.js").text
    assert "navigate(back)" not in close_js
    assert 'if (key != null) history.replaceState(null, "", "/tesla");' in close_js
    assert 'registerView("changelog"' in js
    assert "clBooted" in js
    assert '"/tesla/changelog/api/entries"' in js
    assert 'bindGestures(gpScroll, { drawer: true, ptr: true, onRefresh: gpLoad })' in js
    assert 'bindGestures(clScroll, { drawer: true, ptr: true, onRefresh: clLoad })' in js
    # 分组页也是弹层宿主: 离开要收干净 (与行程视图 hide 同一套)
    gp_js = auth.get("/tesla/static/js/view/groups-page.js").text
    for frag in ["bumpOpenSeq();", "if (rec) stopRecExport(true);",
                 'if (curKey != null) closeTrip();',
                 'classList.contains("show")) hideSheet();']:
        assert frag in gp_js, f"groups hide 缺 {frag}"


def test_trips_view_lifecycle(auth):
    """行程视图 (生命周期最重): 首进才拉列表/起终点树/预载高德; 离开视图
    收干净 —— bump openSeq 掐在途打开与流式下载, 停录制, 关弹层, 退多选;
    自己的 loadMore (不走 makePager); 深链 ?id=/?ids= 冷启消费直开。"""
    js = page_js(auth, SHELL)
    assert 'registerView("trips"' in js
    assert "trBooted" in js                            # 首次进视图才 boot
    assert "trFetchRegions()" in js                    # 起终点树随首进拉
    assert "async function loadMore()" in js           # 自持 loadMore (不走 makePager)
    assert "openSeq++" in js                           # 离开视图: 掐在途会话
    assert "stopRecExport(true)" in js                 # 导出录制取消
    assert "exitSelect()" in js                        # 退多选态
    assert "closeTrip()" in js and "hideSheet()" in js
    # 深链: 冷启抠出再洗参, 导航完直开 (2.0 分享链接不丢)
    assert 'bootQs.get("id") || bootQs.get("ids")' in js
    assert "openByKey(tripKey)" in js
    # 零历史条目: 打开的行程 replaceState 镜像 (可分享), 不 pushState
    # (3.0 起镜像是壳地址; 分组页打开的合并镜像 view=groups —— 宿主就是
    # 分组页, 刷新落在分组背后)
    assert 'const v = it.merged && sheetFrom === "groups" ? "groups" : "trips";' in js
    assert "`/tesla?view=${v}&` + (/[-,]/.test(curKey) ? \"ids=\" : \"id=\") + curKey" in js


def test_trips_request_wiring(auth):
    """行程列表请求: car_id 穿参 + 里程档换算 km_min/km_max (时间筛选 3.3.0
    下线, 全时段不带时间参数); 弹层镜像地址可裸开 (urlTripKey/listURL 一族
    已删, 无残留引用)。"""
    js = page_js(auth, SHELL)
    assert '"car_id", String(shellState.carId)' in js  # 多车
    assert 'p.set("km_min", kb.min)' in js
    assert 'p.set("km_max", kb.max)' in js
    for gone in ("function urlTripKey", "function listURL", "function syncURL",
                 "function filterQS", "const cameFromGroups",
                 "addEventListener(\"popstate\""):
        assert gone not in js, f"旧地址栏机制残留: {gone}"


def test_selecting_bottom_slot(auth):
    """行程多选态: selbar 占屏底槽, 底栈筛选条 (#bar-row; 菜单圆键
    2026-09-27 退役后只剩它) 整个藏起让位 (floor 收口)。"""
    page = served_page(auth, SHELL)
    assert "body.selecting #bar-row { display: none; }" in page


def test_map_views_lifecycle(auth):
    """地图三视图 (P5): 首进才起地图 (boot 进 show); 足迹/充电地图保留
    AMap 实例秒开, 离开只收弹层; live 离开清轮询走秒定时器 +
    销毁地图, lvGen 代次作废在途响应; 画布 touch-action:none 全给高德,
    手势走摘要条 (PTR), 右划开抽屉的入口折到画布左缘 24px 窄条 (3.3.0
    定稿回归); 三视图请求都带 car_id;
    状态页常显化: 空态/结束态占位屏退役, 任何车辆态 #live 都吃满 stage
    (2026-09-26 用户点名「不管车辆什么状态都显示实时数据和地图位置」)。"""
    js = page_js(auth, SHELL)
    assert 'registerView("chargemap"' in js
    assert 'registerView("map"' in js
    assert 'registerView("live"' in js
    assert "cmBoot()" in js and "fpBoot()" in js        # 首进才起地图
    # 足迹视图详情弹层已退役 (2026-09-29「点路不弹窗」), 离开无层可收
    assert "lvMap.destroy()" in js                      # live 离开销毁地图
    assert "clearInterval(lvPollTimer)" in js and "clearInterval(lvTicker)" in js
    assert "if (gen !== lvGen) return;" in js           # 迟到响应作废
    assert js.count('"car_id", String(shellState.carId)') >= 3   # 三视图多车穿参
    assert ('bindGestures(fpHead, { drawer: true, ptr: true, '
            'onRefresh: () => fpSync() })') in js
    assert 'bindGestures($("#lv-panels"), { drawer: true, ptr: true, onRefresh: poll })' in js
    for edge in ("cm-edge", "fp-edge", "lv-edge"):      # 左缘窄条供右划开抽屉
        assert f'$("#{edge}"), {{ drawer: true }}' in js
    # 深链偏好: ?driver_id= (足迹) / ?metric= (充电地图, 旧页叫 ?view=,
    # 302 时换名) 加载期抠出, 洗参前
    assert 'fpQs0.get("driver_id")' in js
    assert 'cmQs0.get("metric")' in js
    page = served_page(auth, SHELL)
    assert 'id="fp-map"' in page and 'id="cm-map"' in page and 'id="lv-map"' in page
    # 状态页常显化 (2026-09-26 用户点名「不管车辆什么状态都显示实时数据和
    # 地图位置」): 空态/结束态占位屏整节退役 —— #live 常驻吃满 stage, 手势
    # 面就是面板+地图本来的绑法, 右划/下拉覆盖整页
    assert 'id="idle"' not in page and 'id="ended"' not in page
    assert "state-view" not in page and "ended-link" not in page
    # 地图顶中的最后一段行程直达钮 (2026-09-27 两上两撤) 整链退役
    assert "ended-pill" not in page and "lvRenderParked" in page


def test_settings_views_lifecycle(auth):
    """设置四视图+账号 (P6): 旧设置页一页拆三 (数据来源/地图设置/驾驶员),
    每次进视图都拉现值 (设置对象两视图共用, 不读到旧值); 删除二次确认替
    native confirm; 账号 2026-09-27 拆成独立页 (设置组首位) —— 改名称/改
    密码开底部弹层, 关层让路键盘 (ViewportDoctor.settled 没回满不拆层,
    固定壳收键黑带的防治), 进视图/下拉刷新重拉当前登录。"""
    js = page_js(auth, SHELL)
    assert 'registerView("settings-account"' in js
    assert 'registerView("settings-db"' in js
    assert 'registerView("settings-map"' in js
    assert 'registerView("settings-drivers"' in js
    assert "dbLoad" in js and "mapSetLoad" in js and "loadDrivers" in js
    assert 'sendJSON("/tesla/api/settings"' in js           # 保存走带方法请求
    assert 'await getJSON("/tesla/trips/api/regions")' in js  # 保存并实测
    assert '"确认删除"' in js                                 # 删除二次确认 (3s 窗)
    assert "confirm(" not in js                               # 不用 native confirm
    # 账号页: 当前登录 acctCardLoad (/api/me), 登出走 /api/logout; 改名存住后卡上同步
    assert "acctCardLoad" in js
    assert 'await getJSON("/api/me")' in js
    assert 'fetch("/api/logout", { method: "POST" })' in js
    assert '$("#acct-row").addEventListener("click", openAcct)' in js
    assert ('bindGestures($("#acct-scroll"), '
            '{ drawer: true, ptr: true, onRefresh: acctCardLoad })') in js
    assert "ViewportDoctor.settled()" in js
    page = served_page(auth, SHELL)
    for token in ('id="acct-card"', 'id="acct-sheet"', 'id="acct-backdrop"',
                  'id="me-pass-save"', 'id="logout"',
                  'data-view="settings-account"', 'id="acct-scroll"',
                  'data-view="settings-db"', 'data-view="settings-map"',
                  'data-view="settings-drivers"', "tesla-settings.css"):
        assert token in page, f"设置组缺标记 {token}"


def test_floor_css_loads_last(auth):
    """收口层: 各视图 CSS 带旧页 main 宽度/顶置 toast 整份入壳, floor 必须
    最后加载压回壳样式 (main 满宽 + toast 屏底)。"""
    paths = [p for p in page_asset_paths(auth, SHELL) if p.endswith(".css")]
    assert paths[-1].endswith("tesla-shell-floor.css")
    page = served_page(auth, SHELL)
    assert "max-width: 760px" in page                # 充电默认宽 (view-scroll)
    assert page.count(".view-scroll { max-width: 920px; }") == 2   # 两张统计页
    assert "#view-changelog > .view-scroll" in page
