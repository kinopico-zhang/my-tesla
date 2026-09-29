"""足迹地图视图接线测试: 驾驶员筛选 chip, 一级标题, 「走过的路」同步
(清单对账 + IndexedDB 增量 + 进度条)。2026-09-29 起原始轨迹层整链退役
(用户点名「只显示走过的路」), 全精度下载/抽稀细化/轨迹流端点都不再有。
拆自 test_map.py (结构化重构; P7 起按 3.0 单壳改口径)。"""

from tests.tesla_static_files import page_asset_paths, served_page


# ---------------------------------------------------------------- 视图
def _shell(auth):
    """壳 HTML + 引用的样式与脚本全拼起来 (整页断言的口径)。"""
    return served_page(auth, "/tesla")


def test_map_view_skeleton(auth):
    """足迹视图骨架: 摘要两格 (筛选口径, 2026-09-29 用户点名「不需要显示
    行程数量, 就显示里程和时长就行了」—— 原三格并排太挤, 数字溢出格子)
    + 圆角矩形画布 (fp- 前缀防撞名, 2026-09-27 用户点名「足迹地图的页面
    布局和充电地图一样」) + 下载进度条; 时间筛选 3.3.0 下线 (全时段),
    时间菜单/日历已整链退役; 点路不弹详情卡 (同日点名, 弹层整块拆净)。"""
    html = _shell(auth)
    for frag in ['id="view-map"', 'data-view="map"',
                 'id="fp-map-head"', 'id="fp-stats"', 'id="fp-map"',
                 'id="fp-loading"', 'id="fp-error"', 'id="fp-retry"',
                 'id="fp-keyhint"', 'id="fp-prog"',
                 'id="fp-zin"', 'id="fp-zout"']:
        assert frag in html, f"足迹视图缺少 {frag}"
    # 摘要只剩里程/时长两格: 行程数一格与详情弹层退役净 (点路不弹窗)
    for gone in ('id="st-drives"', 'id="fp-sheet"', 'id="fp-backdrop"'):
        assert gone not in html, f"摘要/弹层残留 {gone}"
    # 关键 id 全页唯一 (孤儿节点会重复 id, JS 绑错元素且不报错)
    for i in ("fp-map", "fp-stats", "fp-loading", "fp-error", "fp-prog",
              "fp-zin", "fp-zout"):
        assert html.count(f'id="{i}"') == 1, f"壳 {i} 重复"
    # 地图引擎经适配层 (服务商可切, 设置视图定), 样式兜底幻影黑在适配层
    assert 'mapLib.createMap("fp-map"' in html
    # 地图套圆角矩形卡片 (与充电地图同款: 侧距 16px/圆角 16/发丝线/裁圆角)
    assert "#view-map .map-stage {" in html
    for frag in ("border-radius: 16px", "border: 1px solid var(--hairline)",
                 "overflow: hidden"):
        assert frag in html[html.index("#view-map .map-stage {"):
                            html.index("}", html.index("#view-map .map-stage {"))], \
            f"足迹地图圆角卡缺 {frag}"
    # 汇总两数走 summary 端点的筛选口径 (2026-09-29 用户点名「足迹地图和
    # 充电地图的逻辑是不一样的, 不用联动」: 此前照充电地图抄了视野内口径,
    # 平移缩放数字跟着跳; 同批撤行程数一格 —— 三格太挤数字溢出);
    # bbox 仍记 (高倍只画视野内的判定用)
    for frag in ("function renderStats(", "t.gbb"):
        assert frag in html, f"汇总/bbox 缺 {frag}"
    mv = 'map.on("moveend", () => { trackEvt("moveend"); roadsViewportSync(); });'
    assert mv in html
    # 缩放钮收口到本页 (与充电地图的互盖拆除): 卡内 bottom 14px
    assert "#view-map .zoom-ctl {" in html
    # 3.0.1 加载条改款 (用户点名「进度条放最底下, 不要模糊遮罩, 也不要
    # 转圈」): 不再整屏遮罩蒙地图 —— 地图全程可见; 只在最底下浮一条
    # 文字+进度, 不挡手势; 缩放钮给加载条让位
    assert 'class="fp-load-bar" id="fp-loading" hidden>' in html
    load_block = html[html.index('id="fp-loading"'):html.index('id="fp-error"')]
    assert '<div class="spin"></div>' not in load_block, "加载条不带转圈"
    assert ".fp-load-bar {" in html and "pointer-events: none;" in html
    assert "#view-map .fp-load-bar:not([hidden]) ~ .zoom-ctl {" in html
    # "©…auto navi" 版权与高德 logo 都按需求去掉 (高德无官方开关, CSS 藏)
    assert ('#map .amap-copyright, #fp-map .amap-copyright,\n'
            '#map .amap-logo, #fp-map .amap-logo { display: none !important; }') in html


def test_map_view_driver_chip(auth):
    """驾驶员筛选 chip: 选项来自设置视图驾驶员表 (没配驾驶员整颗藏掉),
    口径与行程视图一致 (默认驾驶员含未标注); 深链 ?driver_id= 加载期抠出,
    表里已删的回落"全部"。"""
    html = _shell(auth)
    for frag in ['registerChips("map"', "fpDrvLabel", "buildFpDrvPop",
                 '"驾驶员: 全部"', '"/tesla/api/drivers"', "fpFetchDrivers",
                 "fpSaveFilters", "refreshBarChips",
                 'fpQs0.get("driver_id")',              # 深链加载期抠出 (洗参前)
                 "drivers.some(d => d.id === drvId)",   # 已删驾驶员回落全部
                 "if (!drivers.length) return;"]:       # 没配驾驶员 chip 不出现
        assert frag in html, f"足迹视图缺少 {frag}"
    # 地名首帧竞态: 矢量样式数据异步加载, 首帧不画地名; complete 后延时补
    # 重渲染 (setFeatures 同值重设只触发重绘), 否则地名要等下次交互才出现
    assert 'map.setFeatures(map.getFeatures())' in html
    assert 'setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);' in html


# ---------------------------------------------------------------- 道路层同步
def test_map_footprint_sync_flow(auth):
    """同步只走「走过的路」(2026-09-29 用户点名「只显示走过的路就行了,
    不需要显示每一条轨迹」): 清单驱动对账道路本地库 (IndexedDB), 缺的
    分批流式下载 (边下边画 + 进度条 + 视野跟随扩大); 所有刷新入口收口
    fpSync (互斥, 进行中再触发排一轮)。"""
    html = _shell(auth)
    # 本地库 (IndexedDB): 只剩道路仓, v3 升级顺手删旧轨迹仓释放空间
    for frag in ["fpLocalOpen", "fpRoadAll", "fpRoadPut",
                 "fpRoadDelete", "fpRoadClear",
                 'indexedDB.open(FP_DB, 3)',
                 'createObjectStore(FP_ROADS, { keyPath: "id" })',
                 'deleteObjectStore("fp_tracks")',
                 'const FP_DB = "mytesla", FP_ROADS = "fp_roads";']:
        assert frag in html, f"本地库缺少 {frag}"
    # 清单驱动 + 道路流式下载: 一批 50 条, NDJSON 逐行解析, 下一题画一道
    for frag in ['"/tesla/map/api/tracks/manifest?_="',
                 '"/tesla/map/api/roads/stream?ids="',
                 "const CHUNK = 50;",
                 "resp.body.getReader()", "new TextDecoder()",
                 "appendIfVisible(row)", "fpRoadPut(localDb, row)",
                 "showProgress(done, total)", "正在下载走过的路 ",
                 "map.setFitView(overlays, true, [40, 40, 40, 40])"]:
        assert frag in html, f"道路同步缺少 {frag}"
    # fpSync 互斥: 同步中再触发 (换筛选/下拉刷新) 排一轮, 不并发
    for frag in ["fpSyncing", "fpAgain"]:
        assert frag in html, f"同步互斥缺少 {frag}"
    # 原始轨迹层拆净: 三个曾用文件里不得再有轨迹流/轨迹仓/抽稀细化
    for ref in ("js/view/map-boot.js", "js/view/map-tracks-render.js",
                "js/view/map-roads-boot.js"):
        js = auth.get(f"/tesla/static/{ref}").text
        for gone in ("tracks/stream", "fpLocalPut", "fpLocalAll",
                     "decimateFlat", "BAND_PER", "makeTrackLines"):
            assert gone not in js, f"{ref} 残留 {gone}"
    assert "map-tracks-refine.js" not in html, "细化模块应整文件退役"
    assert "refineVisible" not in html and "selectTrack" not in html, \
        "原始轨迹细化/选中残党"
    assert "/tesla/map/api/tracks/stream" not in html, "轨迹流端点客户端引用拆净"
    assert "tracks/detail" not in html, "旧明细端点客户端必须删干净"
    assert 'id="fp-refine-tip"' not in html, "细化提示浮层已被本地细化取代"
    assert ".refine-tip" not in html, "细化提示样式必须删干净"
    # 筛选全本地: 清单行 c/d × 车/驾驶员 (时间筛选已下线), 汇总仍走服务端
    for frag in ["fpRowVisible(row)", "fpVisibleTracks()",
                 "row.d === drvId || (fpDefaultDrv && row.d == null)",
                 '"/tesla/map/api/summary" + trackParams()']:
        assert frag in html, f"本地筛选缺少 {frag}"


def test_map_page_titles(auth):
    """一级标题 (3.3.0 用户令「充电地图和足迹地图, 也要跟其他页面一样, 最
    上面也有一级标题」): 两张地图页补 sec-head h2, 与充电/分组/行程同款
    26px (五份副本锁步钉在 test_asset_versions); 头部侧距 16px 对齐其他
    页标题的进屏距离。"""
    html = _shell(auth)
    for h2 in ("<h2>足迹地图</h2>", "<h2>充电地图</h2>"):
        assert html.count(h2) == 1, f"{h2} 应恰好一份"
    assert html.index("<h2>足迹地图</h2>") > html.index('id="fp-map-head"')
    assert html.index("<h2>充电地图</h2>") > html.index('id="cm-map-head"')
    assert "map-head .sec-head" in html
    assert "padding: var(--content-top) 16px 0;" in html


def test_map_local_store_loads_before_boot(auth):
    """本地库模块在同步模块 (map-boot) 之前加载 (fpSync 直接调 fpLocal*)。"""
    refs = page_asset_paths(auth, "/tesla")
    i_store = refs.index("/tesla/static/js/view/map-local-store.js")
    i_boot = refs.index("/tesla/static/js/view/map-boot.js")
    assert i_store < i_boot, "map-local-store.js 必须先于 map-boot.js 加载"
