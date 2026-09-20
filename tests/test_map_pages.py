"""足迹地图视图接线测试: 抽屉时间菜单 (全壳一份), 驾驶员筛选 chip,
全精度流式同步 (清单对账 + IndexedDB 增量 + 进度条 + 本地抽稀细化)。
拆自 test_map.py (结构化重构; P7 起按 3.0 单壳改口径)。"""

from tests.tesla_static_files import page_asset_paths, served_page


# ---------------------------------------------------------------- 视图
def _shell(auth):
    """壳 HTML + 引用的样式与脚本全拼起来 (整页断言的口径)。"""
    return served_page(auth, "/tesla")


def test_map_view_skeleton(auth):
    """足迹视图骨架: 摘要条 + 全出血画布 (fp- 前缀防撞名) + 左缘抽屉条 +
    下载进度条; 时间菜单/日历在抽屉 (全壳一份, 充电视图用例已断言)。"""
    html = _shell(auth)
    for frag in ['id="view-map"', 'data-view="map"',
                 'id="fp-map-head"', 'id="fp-stats"', 'id="fp-map"',
                 'id="fp-loading"', 'id="fp-error"', 'id="fp-retry"',
                 'id="fp-keyhint"', 'id="fp-prog"',
                 'id="fp-zin"', 'id="fp-zout"', 'id="fp-edge"']:
        assert frag in html, f"足迹视图缺少 {frag}"
    # 关键 id 全页唯一 (孤儿节点会重复 id, JS 绑错元素且不报错)
    for i in ("fp-map", "fp-stats", "fp-loading", "fp-error", "fp-prog",
              "fp-zin", "fp-zout"):
        assert html.count(f'id="{i}"') == 1, f"壳 {i} 重复"
    # 地图引擎经适配层 (服务商可切, 设置视图定), 样式兜底幻影黑在适配层
    assert 'mapLib.createMap("fp-map"' in html
    # 3.0.1 加载条改款 (用户点名「进度条放最底下, 不要模糊遮罩, 也不要
    # 转圈」): 不再整屏遮罩蒙地图 —— 地图全程可见; 只在最底下浮一条
    # 文字+进度, 不挡手势; 缩放钮给加载条让位
    assert 'class="fp-load-bar" id="fp-loading" hidden>' in html
    load_block = html[html.index('id="fp-loading"'):html.index('id="fp-error"')]
    assert '<div class="spin"></div>' not in load_block, "加载条不带转圈"
    assert ".fp-load-bar {" in html and "pointer-events: none;" in html
    assert ".fp-load-bar:not([hidden]) ~ .zoom-ctl {" in html
    # "©…auto navi" 版权文字按需求去掉 (高德无官方开关, CSS 藏)
    assert '#map .amap-copyright, #fp-map .amap-copyright { display: none !important; }' in html


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


# ---------------------------------------------------------------- 全精度同步
def test_map_footprint_sync_flow(auth):
    """v4 全精度流式同步: 清单驱动对账浏览器本地库 (IndexedDB), 缺的
    分批流式下载 (边下边画 + 进度条 + 视野跟随扩大), 细化纯本地抽稀
    不再发请求; 所有刷新入口收口 fpSync (互斥, 进行中再触发排一轮)。"""
    html = _shell(auth)
    # 本地库 (IndexedDB): 打不开退化内存模式, 绝不挡渲染
    for frag in ["fpLocalOpen", "fpLocalAll", "fpLocalPut",
                 "fpLocalDelete", "fpLocalClear",
                 'indexedDB.open(FP_DB, 1)',
                 'createObjectStore(FP_STORE, { keyPath: "id" })',
                 'const FP_DB = "mytesla", FP_STORE = "fp_tracks";']:
        assert frag in html, f"本地库缺少 {frag}"
    # 清单对账: 格式版本不符清库, 点数不符重下, 清单没有的删掉
    for frag in ['const FP_FMT_V = 5;',               # = 服务端 CACHE_VERSION
                 '"/tesla/map/api/tracks/manifest?_="',
                 "man.v !== FP_FMT_V",
                 "s.pts.length === r.n * 2",
                 "fpLocalDelete(localDb, drop)",
                 "fpLocalClear(localDb)"]:
        assert frag in html, f"清单对账缺少 {frag}"
    # 流式下载: 一批 50 条, NDJSON 逐行解析, 下载一条画一条
    for frag in ['"/tesla/map/api/tracks/stream?ids="',
                 "const CHUNK = 50;",
                 "resp.body.getReader()", "new TextDecoder()",
                 "appendIfVisible(t)", "fpLocalPut(localDb, t)",
                 "showProgress(done, total)", "正在下载轨迹 ",
                 "map.setFitView(overlays, true, [40, 40, 40, 40])"]:
        assert frag in html, f"流式下载缺少 {frag}"
    # fpSync 互斥: 同步中再触发 (换筛选/下拉刷新) 排一轮, 不并发
    for frag in ["fpSyncing", "fpAgain"]:
        assert frag in html, f"同步互斥缺少 {frag}"
    # 细化本地化 (3.0.1 用户口径「先把所有坐标缓存到手机本地, 放大到足够
    # 大的时候精细化渲染所有的点」): 概览 ~40 点/条 + 档位抽稀 (13→2000 /
    # 14→6000 / 15 全精度, 预算调大: 放大后拐角不再被抽掉)。坐标本来就
    # 整库全精度存本地库 (v4 全精度下载), 细化纯本地换线不发请求; 所有
    # 轨迹都细化到当前档 —— 15 级全库全精度 (视野内的先换, 其余分轮补
    # 齐), 13/14 级全库到档, 平移不闪粗线; 换档逐条增量升/降 (detailTier
    # 记档), 不再整版退回概览; 分轮限量, 没细化完自动续轮 (原先只最新
    # 150 条有细线); 选中过的永不降级
    for frag in ["const COARSE_PER = 40;", "TrackUtil.decimateFlat",
                 "TrackUtil.splitGapsFlat",
                 "const BAND_PER = { 13: 2000, 14: 6000, 15: 0 };",
                 "const REFINE_BATCH = 80;", "const REFINE_POINTS = 200000;",
                 "function targetPer(t, band) {",
                 "if (fullIds.has(t.id)) return 0;",
                 "return BAND_PER[band];",
                 "detailTier.set(t.id, per);",
                 "detailTier.get(t.id) === want",
                 "refineTimer = setTimeout(refineVisible, 80);",
                 "fullIds.add(t.id)", "refineSelected"]:
        assert frag in html, f"本地细化缺少 {frag}"
    assert "scanned < 150" not in html, "150 条扫描上限已退役 (老轨迹细化不到)"
    assert "BAND_PER[Math.min(band, 14)]" not in html, \
        "15 级视野外压 14 级底档已退役 (用户点名: 放大后全精度渲染所有点)"
    assert "detailTier.clear();" in html, "换渲染集/回概览要连档位记录一起清"
    assert "tracks/detail" not in html, "旧明细端点客户端必须删干净"
    assert 'id="fp-refine-tip"' not in html, "细化提示浮层已被本地细化取代"
    assert ".refine-tip" not in html, "细化提示样式必须删干净"
    # 筛选全本地: 清单行 t/c/d × 时间/车/驾驶员, 汇总仍走服务端
    for frag in ["fpRowVisible(row)", "fpVisibleTracks()",
                 "row.d === drvId || (fpDefaultDrv && row.d == null)",
                 '"/tesla/map/api/summary" + trackParams()']:
        assert frag in html, f"本地筛选缺少 {frag}"


def test_map_local_store_loads_before_boot(auth):
    """本地库模块在同步模块 (map-boot) 之前加载 (fpSync 直接调 fpLocal*)。"""
    refs = page_asset_paths(auth, "/tesla")
    i_store = refs.index("/tesla/static/js/view/map-local-store.js")
    i_boot = refs.index("/tesla/static/js/view/map-boot.js")
    assert i_store < i_boot, "map-local-store.js 必须先于 map-boot.js 加载"
