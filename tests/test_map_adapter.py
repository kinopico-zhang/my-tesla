"""地图引擎适配层 (tesla-map-adapter.js) 的结构棘轮: 高德单服务商
(2026-09-25 用户点名「地图只保留高德」, 可切换的 OSM 官方源/dhuar 镜像
整链退役)。四张地图 (足迹/充电地图/实时/轨迹弹层) 只许经 mapLib 建图
建层 —— 高德对象 (new AMap.Map 等) 只准出现在适配层本体里, 视图再直连
就是改版漏收编; 退役的 Leaflet 垫片路不许回潮。"""

from pathlib import Path

from tests.tesla_static_files import page_asset_paths, served_page

ADAPTER = Path("app/tesla/static/js/tesla-map-adapter.js")


def _shell(auth):
    return served_page(auth, "/tesla")


def test_adapter_loaded_before_view_scripts(auth):
    """适配层脚本在引用序上先于一切视图脚本: WebGL 缓冲补丁在适配层
    顶层 (脚本一执行就装), 引用序错乱会留下黑帧隐患。"""
    paths = page_asset_paths(auth, "/tesla")
    ai = paths.index("/tesla/static/js/tesla-map-adapter.js")
    first_view = next(i for i, p in enumerate(paths) if "/js/view/" in p)
    assert ai < first_view


def test_adapter_dialect_surface():
    """适配层方言面: 高德单服务商 (引擎按需注入 + 缺 Key 自报) + 坐标口径
    (高德要 GCJ-02, 视图统一喂 WGS-84) + 规划降级 (不可用/失败 → null)。"""
    src = ADAPTER.read_text(encoding="utf-8")
    for frag in [
        "webapi.amap.com/maps?v=2.0",                # 高德引擎按需注入
        'e.noKey = true',                            # 高德缺 Key: 视图各自引导
        "GCJ02.wgs84ToGcj02",                        # 坐标口径: 高德要 GCJ-02
        "drivingSearch",                             # 规划原语 (断档补路 + 高速费)
        "new AMap.Map(",                             # 工厂面: 建图
        "new AMap.Polyline(",                        # 工厂面: 线
        "new AMap.CircleMarker(",                    # 工厂面: 圆点
        "new AMap.Marker(",                          # 工厂面: 标注
        "new AMap.Pixel(",                           # 工厂面: 像素偏移
        "new AMap.HeatMap(",                         # 工厂面: 热力 (充电地图)
    ]:
        assert frag in src, f"适配层缺少 {frag}"
    # 退役的 Leaflet/OSM 家族不许回潮 (垫片已删, vendor/ 不再有 leaflet.*)
    for dead in ["leaflet", "Leaflet", "openstreetmap", "dhuar", "tileUrl",
                 "L.map(", "L.heatLayer"]:
        assert dead not in src, f"退役路回潮: {dead}"


def test_osm_family_stays_retired():
    """OSM 家族退役棘轮 (2026-09-25 只留高德): 瓦片压暗滤镜 (官方源/国内
    镜像只有亮色标准图, CSS 反色滤镜变夜景)、Leaflet 容器/版权角标规则、
    导出视频的 Leaflet <img> 瓦片合成路, 全部拆净; 深底色留着 (高德暗色
    样式的瓦片空窗也统一深色, 录制底色同款)。"""
    css = Path("app/tesla/static/css/tesla-map-canvas.css").read_text(encoding="utf-8")
    assert ".leaflet-tile" not in css
    assert ".leaflet-container" not in css
    assert ".leaflet-control-attribution" not in css
    assert "#fp-map, #cm-map, #lv-map, #trip-map { background: #0b0d10; }" in css
    exp = (Path("app/tesla/static/js/view/trips-export-video.js")
           .read_text(encoding="utf-8"))
    assert "tileFilter" not in exp
    assert "getComputedStyle(tile)" not in exp
    sheet_css = (Path("app/tesla/static/css/tesla-trips-sheet.css")
                 .read_text(encoding="utf-8"))
    assert "leaflet" not in sheet_css
    for gone in Path("app/tesla/static/vendor").glob("leaflet*"):
        assert False, f"Leaflet 垫片没删净: {gone}"


def test_views_never_touch_amap_directly(auth):
    """视图脚本不许直连高德对象: 全部经 mapLib 工厂 (单服务商收口的根基)。
    charging-nav.js 例外 —— 它做的是外部 App 深链, 与渲染引擎无关。"""
    adapter = ADAPTER.read_text(encoding="utf-8")
    for token in ["new AMap.Map(", "AMap.plugin(", "AMap.HeatMap"]:
        assert token in adapter, f"适配层缺少 {token}"
    for p in page_asset_paths(auth, "/tesla"):
        if not p.endswith(".js") or "tesla-map-adapter" in p:
            continue
        src = auth.get(p).text
        if p.endswith("charging-nav.js"):
            continue   # 外部 App 深链 (高德/百度 App 的 GCJ-02 口径), 不归引擎管
        for token in ["AMap.", "GCJ02.wgs84ToGcj02"]:
            assert token not in src, f"{p} 直连了 {token} (应走 mapLib)"


def test_settings_map_change_resets_adapter(auth):
    """设置页改地图配置 (样式/Key): reset 作废缓存配置 + 预热新引擎,
    maplib:swap 事件让三张常驻地图 (足迹/充电/轨迹弹层) 自毁, 下次进视图
    自动重建 —— 免整页刷新 (换高德 Key 除外, Key 绑在引擎脚本上); 高德
    引擎装过就不重装 (换样式/安全码免刷新的前提)。服务商下拉已随
    「只留高德」整组退役, 不许回潮。"""
    html = _shell(auth)
    assert 'id="map-provider"' not in html
    assert 'id="amap-rows"' not in html
    assert "map_provider" not in html
    assert "mapLib.reset();" in html
    assert 'dispatchEvent(new CustomEvent("maplib:swap"))' in html
    assert "已切换地图样式" in html
    assert "if (window.AMap) return;" in ADAPTER.read_text(encoding="utf-8")
    # 三张常驻地图都挂了 swap 自毁 (实时页本来就每次进视图重建, 不用挂)
    listeners = sorted(
        p for p in page_asset_paths(auth, "/tesla")
        if p.endswith(".js") and 'addEventListener("maplib:swap"' in auth.get(p).text)
    assert listeners == [
        "/tesla/static/js/view/chargemap-time-filters.js",
        "/tesla/static/js/view/map-filters.js",
        "/tesla/static/js/view/trips-sheet-page.js",
    ]
