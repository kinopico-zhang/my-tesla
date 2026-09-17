"""行程页细节接线测试: URL 深链 / 瓦片预载 / 样式块守恒 / 多选。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""

from tests.trips_page_assets import TRIPS_ASSETS, _trips_scripts

def test_trips_page_has_url_deeplink(auth):
    """打开行程地址栏变 ?id=X / 合并 ?ids=a,b: pushState/popstate 同步 + 分享直开。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ["urlTripKey", "openByKey", "history.pushState",
                 "addEventListener(\"popstate\"",
                 "/tesla/trips/api/sessions/${",
                 "history.pushState({ k: curKey }, \"\", listURL(curKey))",
                 "history.replaceState(null, \"\", listURL())",
                 '/[-,]/.test(key) ? "ids=" : "id="',
                 # 单条行程头部立即填 (字段随卡片/接口齐), 占位只留给合并流式
                 "if (it.pts || !it.merged) fillSheetHeader(it)",
                 # 坏合并深链: 关弹层 + 抹参回列表 (单条卡片打开的错留在弹层里)
                 "hideSheet(); throw e"]:
        assert frag in html, f"行程页缺少深链片段 {frag}"
    # ids= 逗号经分享渠道常被再编码 (%2C): 深链解析先解码再配, 不许截断
    assert "decodeURIComponent(m[1])" in html


def test_trips_page_preloads_tiles(auth):
    """播放前预载沿途瓦片: 倍率按里程 + DOM 抄模板 + Image() 刷缓存, 失败静默。
    矢量模式没有可抄的瓦片 URL → 扫路预取 (相机沿路线按未来档位扫一遍灌
    TileCache, 收尾补整轨拉远视野); 时长公式抽 animDurMs 与播放同口径。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ["function followZoom(", "async function tileTemplate(", "function tileUrl(",
                 "function preloadTiles(", "正在预载地图", "TrackAnimation.lngLatToTile",
                 "appmaptile", "playTrack(c.pts, c.ts || [], it, zoom)",
                 "setTimeout(resolve, 8000)", "track-animation.js?v=1",
                 # 矢量扫路预取 (隐藏图拉过不认, 只能驱动主图自己扫)
                 "async function preloadVectorTrack(",
                 "const animDurMs = (n, km) =>",
                 "let dur = TripPlayback.animDurMs(N, cum[N - 1]);",
                 "dur = TripPlayback.animDurMs(N, cum[N - 1]);",
                 "tripMap.setZoomAndCenter(z, p, true)",
                 # 环形前瞻: 容器四周扩出 (wrap 裁掉可视区不变), 播放中四周
                 # 瓦片提前 4~13s 进缓存 = 真正的边播边下; logo 推回可视区
                 "width: calc(100% + 320px); height: calc(100% + 640px);",
                 "left: -160px; top: -320px;",
                 "#trip-map .amap-logo {",
                 "#trip-map .amap-copyright { display: none !important; }",
                 "transform: translate(160px, -320px);",
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
    html = auth.get("/tesla/trips").text
    assert "<style>" not in html, "样式应全在 css/ 文件里"
    for name in TRIPS_ASSETS:
        if not name.startswith("css/"):
            continue
        css = auth.get(f"/tesla/static/{name}").text
        assert css.count("{") == css.count("}"), f"{name} 花括号不配平, 后半规则全被吞"


def test_trips_page_has_multiselect(auth):
    """多选连续行程: 长按卡片进选择模式 + 底栏 (全选/上限提示) + 合并接口直开。"""
    html = auth.get("/tesla/trips").text
    html += _trips_scripts(auth)
    for frag in ['id="selbar"', 'id="sel-go"', 'id="sel-cancel"',
                 'id="sel-count"', 'id="sel-all"', 'id="sel-cap"', "MERGE_MAX = 100",
                 "body.selecting", "pickCard", "enterSelect", "exitSelect",
                 "openMerged", "/tesla/trips/api/merged_stream?ids=",
                 "mergedCache", "loadMergedStream(", "sess.append(d.pts, d.ts)",
                 "setupLongPress", "HOLD_MS = 480",
                 'addEventListener("contextmenu"']:
        assert frag in html, f"行程页缺少多选片段 {frag}"
    # 多选按钮已撤: 长按卡片是唯一入口 (触屏长按/桌面按住)
    assert 'id="merge-btn"' not in html
    # 合并弹层复用播放: pts 随 it 一起传入 (不走单条轨迹接口)
    assert "it.pts ? it : trackCache.get(it.id)" in html
    # 合并轨迹按段做断档识别 (各段采样密度不同), 单段照旧全局一套
    assert "function splitSegments(" in html
    assert "splitSegments(pts, it.seg_starts)" in html
    assert "TrackUtil.splitGaps(pts)" in html
