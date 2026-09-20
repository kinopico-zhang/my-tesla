"""地图引擎适配层 (tesla-map-adapter.js) 的结构棘轮: 服务商可切换
(高德/OpenStreetMap, 设置页定)。四张地图 (足迹/充电地图/实时/轨迹弹层)
只许经 mapLib 建图建层 —— 高德对象 (new AMap.Map 等) 只准出现在适配层
本体里, 视图再直连就是改版漏收编。"""

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
    """适配层方言面: 双服务商路由 (amap 直通 / osm 垫片) + 坐标口径
    (高德 GCJ-02, OSM 原始 WGS-84) + 规划降级 (OSM 无免费驾车规划)。"""
    src = ADAPTER.read_text(encoding="utf-8")
    for frag in [
        'provider === "osm" ? "osm" : "amap"',      # config 下发的服务商归一
        "webapi.amap.com/maps?v=2.0",                # 高德引擎按需注入
        "/tesla/static/vendor/leaflet.js",           # OSM 引擎本地自带 (不走 CDN)
        'e.noKey = true',                            # 高德缺 Key: 视图各自引导
        "GCJ02.wgs84ToGcj02",                        # 坐标口径: 高德要 GCJ-02
        "p[0], p[1]",                                # OSM 用原始 WGS-84 (原样透传)
        "drivingSearch",                             # 规划原语 (断档补路 + 高速费)
        "L.heatLayer",                               # 热力垫片 (充电地图)
        "preferCanvas: true",                        # 矢量进画布 (导出视频不污染)
        "crossOrigin: true",                         # 瓦片带跨域头 (导出可合成)
        "zoomSnap: 0",                               # 播放要分数档变焦
    ]:
        assert frag in src, f"适配层缺少 {frag}"


def test_views_never_touch_amap_directly(auth):
    """视图脚本不许直连高德对象: 全部经 mapLib 工厂 (服务商切换的根基)。
    charging-nav.js 例外 —— 它做的是外部 App 深链, 与渲染引擎无关。"""
    adapter = (Path("app/tesla/static/js/tesla-map-adapter.js")
               .read_text(encoding="utf-8"))
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


def test_settings_provider_switch_resets_adapter(auth):
    """设置页换服务商: 适配层缓存的配置作废 (reset), 已起的地图实例
    由整页刷新换干净 —— toast 里说清楚。"""
    html = _shell(auth)
    assert 'id="map-provider"' in html
    assert '<option value="osm">OpenStreetMap (无需 Key)</option>' in html
    assert "mapLib.reset();" in html
    assert "已切换地图服务商" in html
