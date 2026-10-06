"""足迹地图视图接线测试: 驾驶员筛选 chip, 一级标题, 「走过的路」同步
(清单对账 + IndexedDB 增量; 加载进度条 2026-09-29 退役 —— 边下边画本就
增量展示)。2026-09-29 起原始轨迹层整链退役
(用户点名「只显示走过的路」), 全精度下载/抽稀细化/轨迹流端点都不再有。
拆自 test_map.py (结构化重构; P7 起按 3.0 单壳改口径)。"""

from tests.tesla_static_files import page_asset_paths, served_page


# ---------------------------------------------------------------- 视图
def _shell(auth):
    """壳 HTML + 引用的样式与脚本全拼起来 (整页断言的口径)。"""
    return served_page(auth, "/tesla")


def test_map_view_skeleton(auth):
    """足迹视图骨架: 摘要两格 (筛选口径, 2026-09-29 用户点名「不需要显示
    行程数量, 就显示里程和时长就行了」—— 原三格太挤, 数字溢出格子)
    + 圆角矩形画布 (fp- 前缀防撞名, 2026-09-27「布局和充电地图一样」);
    时间筛选 3.3.0 下线, 菜单/日历整链退役; 点路不弹详情卡 (同日点名);
    加载进度条同日退役 (与图例重叠, 边下边画本就增量展示)。"""
    html = _shell(auth)
    for frag in ['id="view-map"', 'data-view="map"',
                 'id="fp-map-head"', 'id="fp-stats"', 'id="fp-map"',
                 'id="fp-error"', 'id="fp-retry"',
                 'id="fp-keyhint"',
                 'id="fp-play"', 'id="fp-play-date"',
                 'id="fp-seek"']:
        assert frag in html, f"足迹视图缺少 {frag}"
    # 摘要只剩里程/时长两格: 行程数一格与详情弹层退役净 (点路不弹窗)
    for gone in ('id="st-drives"', 'id="fp-sheet"', 'id="fp-backdrop"'):
        assert gone not in html, f"摘要/弹层残留 {gone}"
    # 关键 id 全页唯一 (孤儿节点会重复 id, JS 绑错元素且不报错)
    for i in ("fp-map", "fp-stats", "fp-error", "fp-play", "fp-play-date",
              "fp-seek", "fp-gutter"):
        assert html.count(f'id="{i}"') == 1, f"壳 {i} 重复"
    # 地图引擎经适配层 (服务商可切, 设置视图定), 幻影黑兜底在适配层;
    # 足迹地图单图钉灰阶底图 (2026-09-30「搞灰」) —— 彩色只留给热力色
    assert 'mapLib.createMap("fp-map"' in html
    assert 'style: "amap://styles/grey"' in html
    # 地图套圆角矩形卡片 (与充电地图同款: 侧距 16px/圆角 16/发丝线/裁圆角)
    assert "#view-map .map-stage {" in html
    for frag in ("border-radius: 16px", "border: 1px solid var(--hairline)",
                 "overflow: hidden"):
        assert frag in html[html.index("#view-map .map-stage {"):
                            html.index("}", html.index("#view-map .map-stage {"))], \
            f"足迹地图圆角卡缺 {frag}"
    # 汇总两数走 summary 端点的筛选口径 (2026-09-29 用户点名「与充电地图
    # 不联动」: 平移缩放数字不动); bbox 仍记 (高倍只画视野内的判定用)
    for frag in ("function renderStats(", "t.gbb", "thinFlat"):
        assert frag in html, f"汇总/bbox 缺 {frag}"
    mv = 'map.on("moveend", () => { trackEvt("moveend"); roadsViewportSync(); });'
    assert mv in html
    # 屏缘缝条 (2026-10-01 用户报「左边缘右划无法呼出菜单」): 卡外 16px 出血
    # 缝里右划谁也接不到, 视图层补一条接力到屏缘。锚就是 #view-map 自己
    # (.view 的 absolute 即定位上下文) —— 反向钉: 不许再立 position:relative
    # (ID 特异度压掉 .view 的 absolute+inset:0, 塌成内容高 → 整页黑屏)
    assert '<div class="drawer-edge" id="fp-gutter"' in html \
           and "#view-map { position: relative; }" not in html
    # 3.0.1 加载条 2026-09-29 整链退役 (用户点名「图例和进度条重叠 —— 去掉
    # 进度条, 异步加载一边展示」: 道路本就流式边下边画): 条/文字/进度格/
    # 两个进度函数全不许回潮 (钉 function 前缀 —— 充地图注释提过旧名, 裸词误伤)
    for gone in ('id="fp-loading"', 'id="fp-prog"', ".fp-load-bar", ".fp-prog",
                 "function showLoading", "function showProgress",
                 "正在下载走过的路", "正在绘制走过的路"):
        assert gone not in html, f"加载进度条残党 {gone}"
    # "©…auto navi" 版权与高德 logo 都按需求去掉 (高德无官方开关, CSS 藏)
    assert ('#map .amap-copyright, #fp-map .amap-copyright,\n'
            '#map .amap-logo, #fp-map .amap-logo { display: none !important; }') in html


def test_map_view_driver_chip(auth):
    """驾驶员筛选 (2026-10-02 并进播放条行尾 #fp-drv, 屏底条这页退役):
    选项来自设置视图驾驶员表 (没配驾驶员整颗藏掉), 口径与行程视图一致
    (默认驾驶员含未标注); 深链 ?driver_id= 抠出, 表里已删回落"全部"。"""
    html = _shell(auth)
    for frag in ['id="fp-drv"', "fpDrvLabel", "buildFpDrvPop",
                 '"驾驶员: 全部"', '"/tesla/api/drivers"', "fpFetchDrivers",
                 "fpSaveFilters", "fpDrvChipSync", '$("#fp-drv").addEventListener',
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
    分批流式下载 (边下边画 + 视野跟随扩大, 无进度条); 所有刷新入口收口
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


# ---------------------------------------------------------------- 时间回放
def test_map_playback_wiring(auth):
    """播放条 (2026-10-01 用户点名重做「去掉放大缩小按钮, 地图下方改成播放
    按钮加进度条, 可播放暂停/调进度, 视角实时变化框住所有路径): [▶/‖][进度条]
    一条在地图卡外下方 (✕ 钮退役); 10-02 修三处: 回放色按累计升温 (报「一开始
    的路径不是黄的」—— live 读 playStat); 回放只在人看着时活着 (报「打开就自动
    播放」—— 切视图/切后台整场收播, 大帧间隔停原地); 正常层藏而不拆; 两格联动;
    出口钩变否决; 打开即开播 (不等铺层); 10-04 收场兜底重画改暗铺一帧换装。"""
    html = _shell(auth)
    for frag in ('<div class="playbar" id="fp-bar">', 'id="fp-play" class="pb-btn"',
                 'aria-label="按时间顺序回放走过的路"', 'id="fp-seek" class="pb-seek"',
                 "#fp-bar { margin: 10px 16px var(--bar-clear); }",
                 "var(--pb, 0%)", "#fp-legend { width: max-content; bottom: 14px; }",
                 "#fp-legend .lg-cap { white-space: nowrap; }"):
        assert frag in html, f"播放条缺少 {frag}"
    # 缩放钮/旧控制排退役净 (foot-gap 占位随 .map-foot 整排拆)
    for gone in ('id="fp-zin"', 'id="fp-zout"', '<div class="map-foot"',
                 'id="fp-stop"', "foot-gap", "#view-map .zoom-ctl", "play-row"):
        assert gone not in html, f"缩放钮/旧控制排残留 {gone}"
    js = auth.get("/tesla/static/js/view/map-roads-playback.js").text
    for frag in ("fpPlayEnter", "fpPlayResume", "fpPlayPause", "fpPlaySeek",
                 "fpPlayExit", "fpPlayFit", "setBounds", "mapLib.bounds",
                 "PLAY_SEEK_CHUNK", 'addEventListener("maplib:swap"',
                 '$("#fp-play").addEventListener', '$("#fp-seek").addEventListener',
                 "playLayerOk = !tracksRendering && overlays",
                 "writeStats", "fpRestoreStats", "o.show()", "FP_ICON_PAUSE", "--pb",
                 'addEventListener("visibilitychange"', "mapLib.bounds(playCam), true)",
                 "roadPlayMerge", "roadPlayBump", "makeRoadLines(t, true)", "PLAY_UI_MS",
                 "renderTracks(fpVisibleTracks(), true)", "gen === renderGen"):
        assert frag in js, f"回放模块缺少 {frag}"
    # 让路闸/出口钩/藏层: 正常层回放期只藏不拆 (收场 show 亮回); renderTracks
    # 入口反调 fpPlayExit(false) —— 换筛选/同步任何重渲染都是对回放态的否决
    for ref, frag in (("map-tracks-render.js", "if (fpPlaying) fpPlayExit(false);"),
                      ("map-tracks-render.js", "if (fpPlaying) for (const l of lines) l.hide();"),
                      ("map-roads-render.js", "if (fpPlaying) return;"),
                      ("map-roads-render.js", "if (fpPlaying || !map || !mapReady"),
                      ("map-roads-boot.js", "overlays.length && !fpPlaying"),
                      ("map-boot.js", "if (roadsById.size && !autoOn) await renderTracks"),
                      ("map-tracks-render.js", "roadBand === 0 && !fpPlaying && !hidden"),
                      ("map-tracks-render.js", "let tracksRendering = false;")):
        assert frag in auth.get(f"/tesla/static/js/view/{ref}").text, \
            f"{ref} 让路闸/旗缺少 {frag}"


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
