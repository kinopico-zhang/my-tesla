"""3.0 单壳视图测试 (P3 立, 随 P4-P6 各视图搬入继续长)。

test_shell_wiring 钉壳本身的骨架约定; 这里放逐视图的生命周期断言
(registerView/首进 boot/手势面) 与跨页资产完整性 —— 引用即存在: 页面里
引用的每个本地资源都真 200, 写错目录的脚本在拼装口径里会静默变空串,
只有逐个打一遍才露馅 (P3 真踩过: 视图脚本落进 js/ 根目录)。
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


def test_stats_view_lifecycle(auth):
    """统计视图生命周期: 首进视图才注 echarts (hidden 段内 init 是 0×0),
    注入失败整页落表格 (forceTableMode), 回视图补 resize, 四路统计带
    car_id。"""
    js = page_js(auth, SHELL)
    assert 'registerView("stats"' in js
    assert "statsBooted" in js                       # 首次进视图才 boot
    assert "await loadEcharts()" in js
    assert "forceTableMode()" in js                  # 图表库拉不到的兜底
    assert "statsResize()" in js                     # 藏起期间变过列数, 回来重排
    assert 'getJSON("/tesla/charging/api/summary?" + statsParams())' in js


def test_groups_and_changelog_lifecycle(auth):
    """分组/日志视图: registerView 注册, 首进才拉数据, 手势面与充电同款;
    分组打开走内存跳转 (navigate + openMerged, 不再整页深链)。"""
    js = page_js(auth, SHELL)
    assert 'registerView("groups"' in js
    assert "gpBooted" in js
    assert '"/tesla/trips/api/groups"' in js
    assert 'navigate("trips")' in js                   # 内存跳转 (零历史条目)
    assert "openMerged(item.dataset.ids)" in js
    assert 'registerView("changelog"' in js
    assert "clBooted" in js
    assert '"/tesla/changelog/api/entries"' in js
    assert 'bindGestures(gpScroll, { drawer: true, ptr: true, onRefresh: gpLoad })' in js
    assert 'bindGestures(clScroll, { drawer: true, ptr: true, onRefresh: clLoad })' in js


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
    # (3.0 起镜像是壳地址, ?view= 让刷新直落行程视图)
    assert '"/tesla?view=trips&" + (/[-,]/.test(curKey) ? "ids=" : "id=")' in js


def test_trips_request_wiring(auth):
    """行程列表请求: 时间档全局摊平 + car_id 穿参 + 里程档换算 km_min/km_max;
    弹层镜像地址可裸开 (urlTripKey/listURL 一族已删, 无残留引用)。"""
    js = page_js(auth, SHELL)
    assert "...timeRangeParams()" in js                # 时间档抽屉全局摊进请求
    assert '"car_id", String(shellState.carId)' in js  # 多车
    assert 'p.set("km_min", kb.min)' in js
    assert 'p.set("km_max", kb.max)' in js
    for gone in ("function urlTripKey", "function listURL", "function syncURL",
                 "function filterQS", "const cameFromGroups",
                 "addEventListener(\"popstate\""):
        assert gone not in js, f"旧地址栏机制残留: {gone}"


def test_selecting_bottom_slot(auth):
    """行程多选态: selbar 占屏底槽, 筛条整行藏起 (floor 收口)。"""
    page = served_page(auth, SHELL)
    assert "body.selecting #bar-row { display: none; }" in page


def test_map_views_lifecycle(auth):
    """地图三视图 (P5): 首进才起地图 (boot 进 show); 足迹/充电地图保留
    AMap 实例秒开, 离开只收弹层/掐细化防抖; live 离开清轮询走秒定时器 +
    销毁地图, lvGen 代次作废在途响应; 画布 touch-action:none 全给高德,
    手势走摘要条/面板区 (PTR+右划) 与左缘 24px 抽屉条; 结束态链接内存跳转;
    三视图请求都带 car_id。"""
    js = page_js(auth, SHELL)
    assert 'registerView("chargemap"' in js
    assert 'registerView("map"' in js
    assert 'registerView("live"' in js
    assert "cmBoot()" in js and "fpBoot()" in js        # 首进才起地图
    assert "clearTimeout(refineTimer)" in js            # 离开掐细化防抖
    assert "lvMap.destroy()" in js                      # live 离开销毁地图
    assert "clearInterval(lvPollTimer)" in js and "clearInterval(lvTicker)" in js
    assert "if (gen !== lvGen) return;" in js           # 迟到响应作废
    assert "openByKey(lvEndedKey)" in js                # 结束态内存跳转 (零历史条目)
    assert js.count('"car_id", String(shellState.carId)') >= 3   # 三视图多车穿参
    assert ('bindGestures(fpHead, { drawer: true, ptr: true, '
            'onRefresh: () => fpSync() })') in js
    assert 'bindGestures($("#lv-panels"), { drawer: true, ptr: true, onRefresh: poll })' in js
    assert 'bindGestures($("#fp-edge"), { drawer: true })' in js
    # 深链偏好: ?driver_id= (足迹) / ?metric= (充电地图, 旧页叫 ?view=,
    # 302 时换名) 加载期抠出, 洗参前
    assert 'fpQs0.get("driver_id")' in js
    assert 'cmQs0.get("metric")' in js
    page = served_page(auth, SHELL)
    assert "width: 24px" in page                # 左缘抽屉条 (floor)
    assert 'id="fp-map"' in page and 'id="cm-map"' in page and 'id="lv-map"' in page


def test_settings_views_lifecycle(auth):
    """设置三视图+账号弹层 (P6): 旧设置页一页拆三 (数据来源/地图设置/驾驶员),
    每次进视图都拉现值 (设置对象两视图共用, 不读到旧值); 删除二次确认替
    native confirm; 账号卡进抽屉账号行的底部弹层 —— 关层让路键盘
    (ViewportDoctor.settled 没回满不拆层, 固定壳收键黑带的防治)。"""
    js = page_js(auth, SHELL)
    assert 'registerView("settings-db"' in js
    assert 'registerView("settings-map"' in js
    assert 'registerView("settings-drivers"' in js
    assert "dbLoad" in js and "mapSetLoad" in js and "loadDrivers" in js
    assert 'sendJSON("/tesla/api/settings"' in js           # 保存走带方法请求
    assert 'await getJSON("/tesla/trips/api/regions")' in js  # 保存并实测
    assert '"确认删除"' in js                                 # 删除二次确认 (3s 窗)
    assert "confirm(" not in js                               # 不用 native confirm
    # 账号弹层: 抽屉账号行点开 (先收抽屉), settled() 没回满不拆层
    assert '$("#acct-row").addEventListener("click", openAcct)' in js
    assert "ViewportDoctor.settled()" in js
    assert "closeDrawer()" in js
    page = served_page(auth, SHELL)
    for token in ('id="acct-sheet"', 'id="acct-backdrop"', 'id="me-pass-save"',
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
    assert "#view-stats > .view-scroll { max-width: 920px; }" in page
    assert "#view-changelog > .view-scroll" in page
