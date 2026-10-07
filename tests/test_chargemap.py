"""充电地图视图测试: /map-locations 充电点聚合接口 + 壳内视图骨架。

聚合口径: 按地址聚合 (次数降序), 无坐标的地址不上图; 展示名与列表
口径一致 (geofence 名优先, 同地址多次充电取最近一次的名字)。
"""
from datetime import datetime

from app.tesla.models import Address, Geofence
from tests.seed_factories import seed_charge, seed_charging
from tests.tesla_static_files import served_page


def _seed_points(db):
    """三个地址: 深圳有坐标 (两笔充电, 其中新的一笔挂 geofence), 东莞有坐标
    (一笔快充), 第三个没有反向地理编码坐标 (一笔充电, 不上图)。"""
    db.add(Address(id=1, name="华为立体车库", city="深圳市",
                   display_name="深圳市华为立体车库", latitude=22.55, longitude=114.05))
    db.add(Address(id=2, name="虎门充电站", city="东莞市",
                   display_name="东莞市虎门充电站", latitude=22.81, longitude=113.67))
    db.add(Address(id=3, name="没坐标的地方", city="某市", display_name="某地"))
    db.add(Geofence(id=8, name="家"))
    db.commit()
    seed_charging(db, geofence_id=None)             # 09-07 深圳, 无 geofence
    seed_charge(db, 1)
    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 10, 0),
                  end_date=datetime(2026, 9, 8, 12, 0), geofence_id=8,
                  charge_energy_added=10.0, charge_energy_used=11.0,
                  duration_min=120, cost=None, start_battery_level=50,
                  end_battery_level=70)             # 09-08 深圳, 最新一笔挂 geofence "家"
    seed_charging(db, id=3, start_date=datetime(2026, 9, 9, 2, 0),
                  end_date=datetime(2026, 9, 9, 2, 40), address_id=2,
                  charge_energy_added=30.0, charge_energy_used=30.0,
                  duration_min=40, cost=10.0, start_battery_level=85,
                  end_battery_level=95)             # 09-09 东莞
    seed_charge(db, 3, charger_power=250.0)
    seed_charging(db, id=4, start_date=datetime(2026, 9, 10, 1, 0),
                  end_date=datetime(2026, 9, 10, 2, 0), address_id=3,
                  charge_energy_used=5.0, duration_min=60, cost=2.0)


# ---------------------------------------------------------------- 聚合接口
def test_map_locations_endpoint(auth, db):
    """按地址聚合充电点: 次数降序, 无坐标地址不上图, geofence 名 (最新一笔) 优先。"""
    _seed_points(db)
    d = auth.get("/tesla/charging/api/map-locations").json()
    assert len(d) == 2                             # 没坐标的地址 3 不上图
    a1, a2 = d
    assert (a1["id"], a1["name"]) == (1, "家")      # 最新一笔挂 geofence → 展示名
    assert a1["city"] == "深圳市"
    assert (a1["lat"], a1["lng"]) == (22.55, 114.05)
    assert (a1["sessions"], a1["fast_sessions"]) == (2, 1)
    assert (a1["energy"], a1["cost"]) == (59.0, 25.5)   # 48+11 kWh, 25.5 元
    assert (a2["id"], a2["name"], a2["sessions"]) == (2, "虎门充电站", 1)
    assert (a2["fast_sessions"], a2["energy"], a2["cost"]) == (1, 30.0, 10.0)


def test_map_locations_geofence_only_on_older_session(auth, db):
    """同地址较新一笔没挂 geofence: 展示名回落地址名 (取最近一次充电的名字)。"""
    db.add(Address(id=1, name="华为立体车库", city="深圳市",
                   display_name="深圳市华为立体车库", latitude=22.55, longitude=114.05))
    db.add(Geofence(id=7, name="公司"))
    db.commit()
    seed_charging(db, geofence_id=7)               # 09-07 挂 "公司"
    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 10, 0),
                  end_date=datetime(2026, 9, 8, 12, 0), geofence_id=None,
                  duration_min=120)                # 09-08 没挂 → 用地址名
    d = auth.get("/tesla/charging/api/map-locations").json()
    assert d[0]["name"] == "华为立体车库"


def test_map_locations_respects_date_range(auth, db):
    """from=09-09 只剩东莞那笔 (与列表同日期口径)。"""
    _seed_points(db)
    d = auth.get("/tesla/charging/api/map-locations",
                 params={"from": "2026-09-09"}).json()
    assert len(d) == 1 and d[0]["id"] == 2


def test_map_locations_rejects_bad_date(auth, db):
    r = auth.get("/tesla/charging/api/map-locations", params={"from": "2026-13-99"})
    assert r.status_code == 400
    assert "日期格式错误" in r.json()["detail"]


def test_map_locations_empty(auth, db):
    assert auth.get("/tesla/charging/api/map-locations").json() == []


# ---------------------------------------------------------------- 视图
def test_chargemap_view_skeleton(auth):
    """充电地图视图: 圆角矩形地图 + 三视角度量 pills + 颜色梯度图例 + 点击就近
    取点弹详情 (壳内撞名 id 加 cm- 前缀, 裸 #map/#legend/#keyhint 归别的
    视图; 生命周期/手势断言在 test_shell_views)。2026-09-27 用户点名两轮:
    先「地图要放在一个圆角矩形里 / 视图切换和图例放到一个水平线上」,
    再「图例放在地图内部左下角, 视图切换按钮居中放在地图外部下方」+
    「缩放的时候, 最大值最小值要动态的变化, 根据视野内的数字计算。
    最大值的颜色一直是红色的, 最小值是蓝色」「上面的三个数字也要跟着变,
    显示视野内的数据」: 图例回画布内左下角浮卡, 极值/汇总三数/热力归一
    全按视野内地点算 (平移/缩放收尾 updateViewport 重算)。"""
    html = served_page(auth, "/tesla")
    for frag in [
        'id="view-chargemap"', 'data-view="chargemap"',
        'id="cm-map"',
        'class="mini-seg cm-views" id="cm-views"',            # 度量 pills (地图外脚下, 居中)
        'data-v="energy">充电电量', 'data-v="sessions">充电次数',
        'data-v="cost">充电费用',
        'function cmSyncViews()',                              # 换档亮灯 + 重画热力
        'id="st-places"', 'id="st-sessions"', 'id="st-energy"',   # 汇总行 (视野内口径)
        'id="cm-legend"', 'id="lg-ramp"', 'id="lg-row"',       # 热力图例 (画布内左下角)
        'id="sh-name"', 'id="sh-sessions"', 'id="sh-fast"',
        'id="sh-energy"', 'id="sh-cost"',                          # 详情弹层
        'id="cm-keyhint"', 'id="cm-zin"', 'id="cm-zout"',          # Key 引导 + 缩放钮
        '"/tesla/charging/api/map-locations?"',                 # 数据源
        "plugin=AMap.HeatMap",                                     # 热力插件随主脚本加载
        "new AMap.HeatMap(", "setDataSet",                         # 热力层
        "const GRADIENT = {",                                      # 蓝→红梯度 (图例同色)
        "PICK_PX", "pickNearest",                                  # 点击就近取点弹详情
        'GCJ02.wgs84ToGcj02',                                      # WGS-84 → GCJ-02
        '"/tesla/map/api/config?_="',                              # 高德配置 (Key/样式)
        "const cmViews = {",                                       # 三视图 (壳内防撞名前缀)
        "renderLegend", "setFitView", "gradientCss",
        "visibleLocations", "updateViewport",                      # 视野内极值/汇总
        'for (const ev of ["moveend", "zoomend"]) cmMap.on(ev, updateViewport)',
        "hmNormMax",                                               # 热力归一跟视野最大走 (红端)
        "gesturestart",                                            # iOS 双指缩放防劫持
        "cmSaveFilters",                                           # 度量偏好持久化 (替代旧 syncURL)
    ]:
        assert frag in html, f"充电地图视图缺少 {frag}"
    # 地图套圆角矩形卡片 (侧距 16px 对齐 .map-head, 与状态页地图卡同款)
    assert "#view-chargemap .map-stage {" in html
    for frag in ("margin: 10px 16px 0", "border-radius: 16px",
                 "border: 1px solid var(--hairline)", "overflow: hidden"):
        assert frag in html[html.index("#view-chargemap .map-stage {"):
                            html.index("}", html.index("#view-chargemap .map-stage {"))], \
            f"地图圆角矩形缺 {frag}"
    # 脚下只剩度量 pills 一件, 整行居中 (底距吃 --bar-clear)
    assert ".cm-foot {" in html and ".cm-views { flex: none; }" in html
    assert "justify-content: center" in html[html.index(".cm-foot {"):
                                       html.index("}", html.index(".cm-foot {"))]
    assert '<div class="legend" id="cm-legend" hidden>' in html
    # 图例浮在画布内左下角 (磨砂浮卡), 与缩放钮 (右下角) 分居两侧
    lg = html[html.index(".legend {"):html.index("}", html.index(".legend {"))]
    for frag in ("position: absolute", "left: 14px", "bottom: 14px"):
        assert frag in lg, f"图例画布内左下角缺 {frag}"
    # 度量切换退役的两件不许回潮: 屏底筛选条 chip 与图例档名行
    assert 'registerChips("chargemap"' not in html
    assert '"视角: " + cmViews[cmMode].lb' not in html
    assert 'id="lg-mode"' not in html
    assert 'id="view-seg"' not in html


def test_chargemap_gutter_covers_screen_edge(auth):
    """#189 (2026-10-05 用户报「充电地图地图位置不能够滑动屏幕边缘返回呼
    出菜单」): 地图卡两侧 16px 出血缝是死区 —— 卡内 #cm-edge 从卡缘 16px
    才起, iPhone 边缘右划的手指天然落 0-16px 次次落空。#cm-gutter 视图层
    缝条直挂 #view-chargemap (足迹 #fp-gutter / 状态页 #lv-gutter 同款接力
    到物理屏缘); 定位上下文就是 .view 的 absolute —— 另立 position:relative
    会把整页塌成内容高 (足迹页黑屏事故), 反向钉死; 三探针再犯翻日志定罪。"""
    page = served_page(auth, "/tesla")
    assert 'class="drawer-edge" id="cm-gutter"' in page, "充电地图缝条骨架缺"
    assert page.index('id="view-chargemap"') < page.index('id="cm-gutter"') < \
        page.index('id="cm-backdrop"'), "缝条不在充电地图视图段内"
    assert "#view-chargemap { position: relative; }" not in page, \
        "缝条定位靠 .view 的 absolute, 别另立 relative (整页塌高事故)"
    js = auth.get("/tesla/static/js/view/chargemap-time-filters.js").text
    assert 'bindGestures($("#cm-gutter"), { drawer: true });' in js
    for frag in ('diag("cm_gutter_touch"', 'diag("cm_gutter_end"',
                 'diag("cm_gutter_cancel"'):
        assert frag in js, f"缝条取证缺 {frag}"


def test_chargemap_link_in_login_whitelist(auth):
    """登录回跳白名单仍收旧充电地图路径: 2.x 存的上次停留值跳旧路径, 302
    落回壳充电地图视图, 不丢。"""
    login_js = auth.get("/static/login.js?v=3").text
    assert "stats|chargemap|map" in login_js
