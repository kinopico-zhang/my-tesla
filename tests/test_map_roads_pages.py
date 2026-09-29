"""走过之路前端接线测试 (3.3.3): 三个新脚本与加载序 / 图例与详情卡骨架 /
栅格四色与本地库 fp_roads 仓 / 道路层同步-渲染各钩子 / 设置页 Web 服务 Key。
新文件的 ?v= 版本钉也在这 (test_asset_versions 200 行不加)。
2026-09-29 原始轨迹层退役后, 渲染只剩道路分支 (只画走过的路); 同日加推断层:
gaps 顶点区间画灰虚线「可能走过」, 不进次数计数 (rowSpans 切已证实段)。"""

from tests.tesla_static_files import page_asset_paths, served_page


def _shell(auth):
    """壳 HTML + 引用的样式与脚本全拼起来 (整页断言的口径)。"""
    return served_page(auth, "/tesla")


# ---------------------------------------------------------------- 脚本与加载序
def test_map_roads_scripts_and_load_order(auth):
    """道路层三脚本: roads-grid (纯逻辑) 在渲染层前, 道路同步在本地库后、
    总同步 (map-boot) 前 —— 同为顶层 const/function, 序即文档。
    细化模块 (map-tracks-refine) 已随原始轨迹层整文件退役。"""
    html = _shell(auth)
    for src in ('js/roads-grid.js?v=3', 'js/view/map-roads-render.js?v=8',
                'js/view/map-roads-boot.js?v=6'):
        assert f'src="/tesla/static/{src}"' in html, f"缺脚本 {src}"
    refs = page_asset_paths(auth, "/tesla")
    assert refs.index("/tesla/static/js/roads-grid.js") \
        < refs.index("/tesla/static/js/view/map-roads-render.js")
    assert refs.index("/tesla/static/js/view/map-local-store.js") \
        < refs.index("/tesla/static/js/view/map-roads-boot.js") \
        < refs.index("/tesla/static/js/view/map-boot.js")
    assert "/tesla/static/js/view/map-tracks-refine.js" not in html, \
        "细化模块应整文件退役 (只画走过的路)"


def test_map_roads_local_store_v3(auth):
    """本地库 v3: 只剩道路仓 fp_roads —— 原始轨迹层退役 (2026-09-29),
    旧库的 fp_tracks 仓升级时删掉释放空间 (全精度点位不再进手机)。"""
    html = _shell(auth)
    for frag in ('const FP_DB = "mytesla", FP_ROADS = "fp_roads";',
                 "indexedDB.open(FP_DB, 3)",
                 'deleteObjectStore("fp_tracks")',
                 "fpRoadAll", "fpRoadPut", "fpRoadDelete", "fpRoadClear"):
        assert frag in html, f"道路仓缺少 {frag}"


def test_map_roads_grid_module(auth):
    """栅格纯逻辑模块: UMD 挂 RoadsGrid, 热力色阶常量 (12 档 × 四锚点),
    格键/切段/插值/打包函数族都在 (c8 单测另测行为, 这里只钉接线)。"""
    html = _shell(auth)
    for frag in ('root.RoadsGrid = factory()', "const STEPS = 12;",
                 '"#3d6fa8", "#21a179", "#d9a521", "#e5484d"',
                 "function cellKey(", "function cellsForFlat(",
                 "function runsByStep(", "function packStat(",
                 "function rowSpans(", "function colorOf(", "function stepOf(",
                 "RoadsGrid.cellCount"):
        assert frag in html, f"栅格模块缺少 {frag}"


# ---------------------------------------------------------------- 同步与格合并
def test_map_roads_sync_flow(auth):
    """道路层同步: 清单对账 (rv 算法版 / rn 点数 / 拟合态 s —— worker 把
    guess 重拟合成 ok 时点数不变, 不盯 s 手机就一直画旧虚线), 流式下载边下
    边画, 格
    合并 roadRebuild 换筛选只重算不请求, 色阶上限 roadMax 随合并维护
    (下载抬了上限收尾重铺一遍色)。ok/guess 两态都算有几何 (推断层一起下),
    次数计数只从已证实段来 (roadCellsOf 剔推断层)。两条 iOS 冻结线
    (25 行 / 200 程) 钉住不回潮。"""
    html = _shell(auth)
    for frag in ("const ROAD_FMT_V = 3;", "man.rv !== ROAD_FMT_V",
                 "(r.s === 1 || r.s === 3)", "s.pts.length === r.rn * 2",
                 "s.s === r.s",
                 '"/tesla/map/api/roads/stream?ids="',
                 "fpRoadsSync", "roadDownload", "roadRebuild",
                 "mergeCells", "roadAsTrack", "roadCellsById.set",
                 "RoadsGrid.rowSpans(pts, row.g || [])",
                 "roadsById.set", "if (nc > roadMax) roadMax = nc;", "roadMax = 0;",
                 "roadMax !== max0"):
        assert frag in html, f"道路同步缺少 {frag}"
    # 冻结线: 下载 25 行让一帧, 合并 200 程让一帧
    assert "sinceYield >= 25" in html
    assert "++n % 200 === 0" in html


def test_map_roads_render_wiring(auth):
    """道路渲染 (渲染层唯一分支): 连续热力色阶切段折线 / 低倍主档单线降级
    + 跨 15 级换画 (缩放收尾防抖 scheduleRoadZoom, 细化循环退役后由它接管) /
    ≥15 级只画视野内 (2026-09-29 手机端放到最大整页崩: 全量分段折线几万条
    iOS 内存爆 —— roadsInView 取视野集, 平移/缩放收尾 roadsViewportSync 防抖
    增删, _dropOut 摘视野外的线)。档位一律看实时缩放 (roadBand 变量等换画
    防抖才追上, 跨档缩小的当口还停在高档 —— 大视野按高档口径一口气补出
    全城分段线, 同日「放大再缩小页面卡死」即此; 且分档线 13→15: 13 级一屏
    还是一个都会区的程数, 视野裁剪救不了)。点路不弹详情卡 (同日用户点名
    「点击路不要弹窗」: selectRoad/选中高亮/底部详情卡整链退役)。推断层
    (gaps 区间) 画灰虚线 GUESS_OPT「可能走过」—— 与证实段共享端点不断线,
    不进次数计数。图例多—少渐变条。"""
    html = _shell(auth)
    for frag in ("makeRoadLines", "roadLegend",
                 "roadZoomCrossed", "scheduleRoadZoom", "redrawRoads",
                 "dominantStep", "linesById.set",
                 "RoadsGrid.rowSpans(pts, g)", "RoadsGrid.runsByStep",
                 "RoadsGrid.stepColor(r.b)", "RoadsGrid.stepOf(",
                 "map.getZoom() < ROAD_ZOOM",
                 "const GUESS_OPT", 'strokeStyle: "dashed"',
                 "roadsInView", "roadInViewNow", "roadsViewportSync",
                 "_dropOut", "lines._band = band",
                 "走过的路"):
        assert frag in html, f"道路渲染缺少 {frag}"
    # 点路不弹窗 (2026-09-29 用户点名): 详情卡/选中态整链退役净
    for gone in ("selectRoad", "fp-sheet", "fp-backdrop", "fp-sh-",
                 "line._rest", "可能走过的路 (推断)"):
        assert gone not in html, f"详情卡残党 {gone}"
    # 档位实时口径: 低倍降级判定/视野闸/换画跳过/折线记账全看 getZoom()
    # (吃滞后变量的旧路不许回潮); 视野补线分帧 (跨回低倍/换画接管即作废)
    for frag in ("band = map && map.getZoom() >= ROAD_ZOOM ? 1 : 0",
                 "map.getZoom() < ROAD_ZOOM) ? list : list.filter(roadInView)",
                 "map.getZoom() < ROAD_ZOOM) return;",
                 "const rb = map.getZoom() >= ROAD_ZOOM ? 1 : 0",
                 "map.add(lines);\n        linesById.set(add[i].id, lines);"):
        assert frag in html, f"档位实时口径缺少 {frag}"
    # 缩放收尾接防抖换画 + 视野增删; 平移收尾视野增删 (汇总三数不跟视野走,
    # 2026-09-29 用户点名与充电地图不联动 —— summary 筛选口径就是终态)
    assert "scheduleRoadZoom(); roadsViewportSync();" in html
    assert 'trackEvt("moveend"); roadsViewportSync(); });' in html


# ---------------------------------------------------------------- 骨架与样式
def test_map_roads_skeleton(auth):
    """图例默认藏 (无道路层不露), 只剩「少—多」热力渐变条 (2026-09-29 用户
    点名「去掉虚线, 去掉数字, 只保留多和少」—— 虚线样例/次数帽/拟合进度行
    整排退役); 点路不弹详情卡 (同日点名「点击路不要弹窗」, 详情弹层整块
    拆净)。"""
    html = _shell(auth)
    assert 'class="legend" id="fp-legend" hidden>' in html
    for frag in ('class="lg-grad"', '<span class="lg-cap">少</span>',
                 '<span class="lg-cap">多</span>'):
        assert frag in html, f"骨架缺少 {frag}"
    # 图例退役净: 虚线样例/两行进度/次数帽不许回潮
    for gone in ('class="lg-guess"', "<span>可能走过 (推断)</span>",
                 'id="fp-lg-max"', 'id="fp-lg-prog"', "<span>走过次数</span>"):
        assert gone not in html, f"图例残留 {gone}"
    # 详情弹层退役净: 弹窗本体/次数两格不许回潮 (点路不弹窗)
    for gone in ('id="fp-sheet"', 'id="fp-backdrop"', 'id="fp-sh-cnt"',
                 'id="fp-sh-sub"', 'id="fp-sh-km"'):
        assert gone not in html, f"详情弹层残留 {gone}"
    assert html.count('id="fp-legend"') == 1, "壳 fp-legend 重复"


def test_map_roads_colors_and_grid_css(auth):
    """四锚点只进色阶常量与图例渐变条 (CSS 摆渡同口径): 渐变条与折线的
    colorOf 同为锚点逐通道线性插值 (两端 0%/100%, 中间恰在 1/3、2/3)。"""
    html = _shell(auth)
    for hexc in ("#3d6fa8", "#21a179", "#d9a521", "#e5484d"):
        assert html.count(hexc) >= 2, f"{hexc} 应同时出现在 JS 锚点与 CSS 渐变"
    assert html.count("#8e99ab") == 1, "推断虚线灰应只在 GUESS_OPT (图例样例已退役)"
    assert "#view-map .lg-grad {" in html
    assert "linear-gradient(to right, #3d6fa8, #21a179 33.33%," in html
    assert ".lg-sw" not in html, "四色点图例应随热力渐变条退役"


# ---------------------------------------------------------------- 设置页
def test_settings_amap_web_key_field(auth):
    """设置页 Web 服务 Key (轨迹拟合) 独立成卡 (2026-09-29 用户点名「要配置
    两个 key」: 两类型易拿混分卡配置): 密码框留空保持现值, 当前状态行, 写明
    与地图 Key 是两种类型不能混用, 独立保存钮存后踢 worker (/roads/tick)。"""
    html = _shell(auth)
    for frag in ('<h2>足迹道路拟合</h2>', 'id="amap-web-key"', 'id="amap-web-now"',
                 'type="password" id="amap-web-key"', 'id="amap-web-save"',
                 "两种类型, 不能混用", '"/tesla/map/api/roads/tick"'):
        assert frag in html, f"Web 服务 Key 设置缺少 {frag}"
    # 地图显示卡还在 (JS Key + 安全码 + 样式), 保存钮互不越界
    assert '<h2>地图显示</h2>' in html and 'id="amap-save"' in html
