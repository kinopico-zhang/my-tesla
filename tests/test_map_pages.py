"""足迹地图页接线测试: 顶栏时间菜单, 司机筛选。
拆自 test_map.py (结构化重构, 代码逐字节未动)。"""



# ---------------------------------------------------------------- 页面
def _map_page(auth):
    """页面 HTML + 拆出的样式与脚本全拼起来 (结构化重构后整页断言的口径)。"""
    html = auth.get("/tesla/map").text
    for name in ("css/tesla-map-page.css", "css/tesla-map-canvas.css",
                 "js/map-page.js", "js/map-tracks-render.js",
                 "js/map-tracks-refine.js", "js/map-boot.js",
                 "js/map-filters.js"):
        html += auth.get(f"/tesla/static/{name}").text
    return html


def test_map_page_time_menu_in_nav_row(auth):
    """时间下拉 (含自定义日历) 在顶栏 nav-row (与全站一致); 筛选行只剩驾驶员。"""
    html = _map_page(auth)
    for frag in ['id="time-menu"', 'data-v="24h"', 'data-v="7d"', 'data-v="30d"',
                 'data-v="180d"', 'data-v="1y"', 'data-v="all"',
                 'data-v="custom"', 'id="tm-cal"', 'id="tm-prev"', 'id="tm-next"',
                 'id="tm-ym"', 'id="tm-sel"', 'id="tm-apply"', 'function calRender()',
                 '再点结束日期', 'class="filters"',
                 # 手机: 下拉面板锚全宽 header (本页 header 不滚动无定位, 要补 relative)
                 '@media (max-width: 479px)', 'header { position: relative; }',
                 '.nav-menu { position: static; }']:
        assert frag in html, f"足迹页缺少 {frag}"
    # 时间菜单紧跟品牌下拉在顶栏; 筛选行只剩驾驶员, 没配驾驶员整行藏掉不占位
    assert '</details>\n    <details class="nav-menu time-menu" id="time-menu">' in html
    assert '<div class="filters" id="filters" hidden>' in html
    assert '"#filters").hidden = false' in html   # 有驾驶员才亮
    assert "chips-range" not in html and ".chip {" not in html
    assert 'id="tm-from"' not in html
    # 关键 id 全页唯一 (孤儿节点会重复 id, JS 绑错元素且不报错)
    for i in ("time-menu", "time-lb", "time-opts", "tm-dates", "tm-cal", "tm-prev",
              "tm-next", "tm-ym", "tm-sel", "brand-menu", "logout"):
        assert html.count(f'id="{i}"') == 1, f"足迹页 {i} 重复"
    # 筛选行太宽时手机端自己横滑, 不把整个页面带着滑 (下拉锚在 header 不受裁)
    assert ".filters { overflow-x: auto; scrollbar-width: none; }" in html
    assert ".filters::-webkit-scrollbar { display: none; }" in html
    # 地图样式走 config (设置页可换), 不再写死幻影黑
    assert 'mapStyle: cfg.style || "amap://styles/dark"' in html
    # "©…auto navi" 版权文字按需求去掉 (高德无官方开关, CSS 藏)
    assert '#map .amap-copyright { display: none !important; }' in html


def test_map_page_driver_filter(auth):
    """驾驶员筛选下拉: 选项来自设置页驾驶员表 (没配驾驶员整颗藏掉),
    口径与行程页一致 (默认驾驶员含未标注); 写进 URL 可分享。"""
    html = _map_page(auth)
    for frag in ['id="drv-menu"', 'id="drv-opts"', 'id="drv-lb"', "驾驶员: 全部",
                 '"/tesla/api/drivers"', "$(\"#drv-menu\").hidden = false",
                 'u.searchParams.set("driver_id", drvId)',
                 'u.searchParams.delete("driver_id")',
                 "trackParams()", "driver_id=" + '" + drvId']:
        assert frag in html, f"足迹页缺少 {frag}"
    # 筛选藏到拉到驾驶员选项才出现; 深链带入的驾驶员不存在要回落"全部"
    assert '<details class="nav-menu" id="drv-menu" hidden>' in html
    assert "drivers.find(d => d.id === drvId)" in html
    # 地名首帧竞态: 矢量样式数据异步加载, 首帧不画地名; complete 后延时补
    # 重渲染 (setFeatures 同值重设只触发重绘), 否则地名要等下次交互才出现
    assert 'map.setFeatures(map.getFeatures())' in html
    assert 'setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);' in html
