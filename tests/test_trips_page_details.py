"""行程细节接线测试: 深链镜像 / 瓦片预载 / 样式块守恒 / 多选。
拆自 test_trips.py (结构化重构; P7 起按 3.0 单壳改口径 —— 深链是
replaceState 镜像 ?view=trips&id=X, 旧页地址 302 进壳由 boot 消费)。"""

from tests.tesla_static_files import page_asset_paths, served_page

def test_trips_page_has_url_deeplink(auth):
    """2.0 的分享链接照用: 旧地址 302 成 /tesla?view=trips&id=X (pages.py),
    boot 冷启抠参 → openByKey 直开弹层; 打开的行程用 replaceState 把地址栏
    镜像成 /tesla?view=trips&id=X / 合并 ?ids=a,b (零历史条目, 返回不留栈)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        # 冷启消费: 洗参前抠出 id/ids (URLSearchParams 自动解码, 分享渠道
        # 再编码的 %2C 也不用手工 decode 了), 抠到就直接开行程视图
        'bootQs.get("id") || bootQs.get("ids")',
        "if (tripKey) openByKey(tripKey)",
        # 打开弹层: 地址栏镜像 (单条 id= / 合并 ids=), 不留历史; 分组页
        # 打开的合并镜像 view=groups (宿主是分组页, 刷新落在分组背后)
        'const v = it.merged && sheetFrom === "groups" ? "groups" : "trips";',
        "`/tesla?view=${v}&` + (/[-,]/.test(curKey) ? \"ids=\" : \"id=\") + curKey",
        "openByKey",
        "/tesla/trips/api/sessions/${",
        # 单条行程头部立即填 (字段随卡片/接口齐); 合并带着汇总 (分组页条目/
        # 多选聚合, 2026-09-23 用户点名不等地图) 也先填 —— 占位只留给取不到
        # 汇总的深链
        "if (it.pts || !it.merged || it.km != null) fillSheetHeader(it)",
        # 合并深链先取轻量汇总再开弹层 (2026-09-24 用户再报「加载地图时平
        # 均电耗空着, 过一会儿才出来」: 2026-09-23 的 info 直填盖住了分组/
        # 多选, 深链重开还在全程占位 —— 流式汇总头要等地图引擎装载后才随
        # 流发出): 服务端只查 drives 不碰轨迹点; 取不到照旧无 info 占位,
        # 错误收场交给后面的流式
        "try { info = await getJSON(`/tesla/trips/api/merged_summary?ids=${key}`); }",
        "catch { info = null; }",
        "await openMerged(key, true, info);",
        # 坏合并深链: 关弹层 + 洗掉行程参数回列表 (单条卡片打开的错留在弹层里)
        "hideSheet(); throw e",
        "history.replaceState(null, \"\", \"/tesla\");"]:
        assert frag in html, f"行程页缺少深链片段 {frag}"
    # 历史栈操作已清偿 (零历史条目): 镜像只 wash 地址栏 (test_shell_wiring 钉)

def test_trips_page_preloads_tiles(auth):
    """播放前预载沿途瓦片: 倍率按里程 + DOM 抄模板 + Image() 刷缓存, 失败静默。
    矢量模式没有可抄的瓦片 URL → 扫路预取 (相机沿路线按未来档位扫一遍灌
    TileCache, 收尾补整轨拉远视野); 时长公式抽 animDurMs 与播放同口径。"""
    html = served_page(auth, "/tesla")
    for frag in ["function followZoom(", "async function tileTemplate(",
                 # 模板返回造 URL 的函数 (从高德地图 DOM 抄一张真实瓦片
                 # URL 当模板, lang/style/scale 跟实际渲染走)
                 "return tileTplCache = (x, y, z) => tpl",
                 "function preloadTiles(", "正在预载地图", "TrackAnimation.lngLatToTile",
                 "appmaptile", "playTrack(c.pts, c.ts || [], it, zoom, false, true)",
                 "setTimeout(resolve, 8000)", "track-animation.js?v=3",
                 # 矢量扫路预取 (隐藏图拉过不认, 只能驱动主图自己扫)
                 "async function preloadVectorTrack(",
                 "const animDurMs = (n, km) =>",
                 "let dur = TripPlayback.animDurMs(N, cum[N - 1]);",
                 # 流式开播把 dur 换成全程里程档 (节拍开播定死, append 不再重算)
                 "dur = TripPlayback.animDurMs(N, kmFull);",
                 "tripMap.setZoomAndCenter(z, p, true)",
                 # 环形前瞻: 容器四周扩出 (wrap 裁掉可视区不变), 播放中四周
                 # 瓦片提前 4~13s 进缓存 = 真正的边播边下; logo 也按需求去掉
                 "width: calc(100% + 320px); height: calc(100% + 640px);",
                 "left: -160px; top: -320px;",
                 "#trip-map .amap-logo { display: none !important; }",
                 "#trip-map .amap-copyright { display: none !important; }",
                 "const MAP_RING_X = 160, MAP_RING_Y = 320;",
                 "const FIT_AVOID = [46 + MAP_RING_Y, 46 + MAP_RING_Y,"
                 " 46 + MAP_RING_X, 46 + MAP_RING_X];",
                 "tripMap.setFitView(allLines, false, FIT_AVOID);",
                 "tripMap.setFitView([whole], true, FIT_AVOID);",
                 "VECTOR_PRELOAD_STEP_MS = 400, VECTOR_PRELOAD_CAP_MS = 4000,",
                 "VECTOR_PRELOAD_STEP_FRAC = 0.85, VECTOR_PRELOAD_BRACKET_MS = 150;",
                 "return speedZoom(TripPlayback.windowMeanSpeed("
                 "vt, pts, dur * vt[i] / vtTotal, dur));",
                 "hystZoom = TripPlayback.hysteresisZoom(curveZoomAt(i), hystZoom);",
                 # 跨界预取: 档位边界过渡步把曲线档也扫一眼 (变焦跨档那刻
                 # 新档瓦片已在手, 地名不再等取数)
                 "const zTarget = Math.round(curveZoomAt(idx));",
                 "if (zTarget !== hystZoom) await visitBracket(zTarget, toGcj(pts[idx]));",
                 "if (zoomUserLock) return Math.round(zoomUserZoom || tripMap.getZoom());",
                 "else await preloadVectorTrack(c.pts, c.ts || [], zoom,"]:
        assert frag in html, f"行程页缺少瓦片预载片段 {frag}"


def test_trips_page_style_block_balanced(auth):
    """样式拆去了 css/ 四件套 (页面不再有 <style>): 每件花括号必须配平 ——
    少一个 } 会让 CSS 错误恢复把其后全部规则吞进未闭合的规则
    (ct-drv 接缝曾丢 }, 弹层/底栏/选中态全体裸奔, 且控制台无任何报错,
    只有页面悄悄变丑)。"""
    html = auth.get("/tesla").text
    assert "<style>" not in html, "样式应全在 css/ 文件里"
    for ref in page_asset_paths(auth, "/tesla"):
        if not ref.endswith(".css"):
            continue
        css = auth.get(ref).text
        assert css.count("{") == css.count("}"), \
            f"{ref} 花括号不配平, 后半规则全被吞"


def test_trips_page_has_multiselect(auth):
    """多选连续行程: 长按卡片进选择模式 + 底栏 (全选/合并) + 合并接口直开。
    100 段上限 2026-09-25 撤掉: sel-cap 提示与 MERGE_MAX 不应再出现。"""
    html = served_page(auth, "/tesla")
    for frag in ['id="selbar"', 'id="sel-go"', 'id="sel-cancel"',
                 'id="sel-count"', 'id="sel-all"',
                 "body.selecting", "pickCard", "enterSelect", "exitSelect",
                 "openMerged", "/tesla/trips/api/merged_stream?ids=",
                 "mergedCache", "loadMergedStream(",
                 "sess.append(d.pts, d.ts, d.gaps, d.t0)",   # 第 4 参段首时刻 (标题随段切换)
                 "setupLongPress", "HOLD_MS = 480",
                 'addEventListener("contextmenu"']:
        assert frag in html, f"行程页缺少多选片段 {frag}"
    # 上限退役: 提示元素/封顶常量不再接线 (撤元素防孤儿引用)
    assert 'id="sel-cap"' not in html
    assert "MERGE_MAX" not in html
    # 多选按钮已撤: 长按卡片是唯一入口 (触屏长按/桌面按住)
    assert 'id="merge-btn"' not in html
    # 合并弹层复用播放: pts 随 it 一起传入 (不走单条轨迹接口)
    assert "it.pts ? it : trackCache.get(it.id)" in html
    # 多选聚合 (2026-09-23 用户点名弹层一开就显数, 不等地图): 列表新→旧,
    # 时间上首段在末尾; ΣkWh÷Σkm 与合并汇总头同口径, 没电耗的段不计入
    assert "const kws = picked.map(it => it.kwh).filter(v => v != null);" in html
    assert "start: picked[picked.length - 1].start, end: picked[0].end," in html
    # 合并轨迹按段做断档识别 (各段采样密度不同), 单段照旧全局一套
    assert "function splitSegments(" in html
    assert "splitSegments(pts, it.seg_starts)" in html
    assert "TrackUtil.splitGaps(pts)" in html
