"""充电地图页测试: /map-locations 充电点聚合接口 + 页面骨架 + 导航入口。

聚合口径: 按地址聚合 (次数降序), 无坐标的地址不上图; 展示名与列表
口径一致 (geofence 名优先, 同地址多次充电取最近一次的名字)。
"""
from datetime import datetime

from app.tesla.models import Address, Geofence
from tests.conftest import seed_charge, seed_charging

PAGES = ["/tesla/charging", "/tesla/stats", "/tesla/chargemap", "/tesla/map",
         "/tesla/trips", "/tesla/groups", "/tesla/live", "/tesla/settings"]


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


# ---------------------------------------------------------------- 页面
def test_chargemap_page_skeleton(auth):
    """充电地图页: 全屏热力图 + 三视图切换 + 颜色梯度图例 + 点击就近取点弹详情。"""
    html = auth.get("/tesla/chargemap").text
    html += auth.get("/tesla/static/chargemap.js?v=1").text
    for frag in [
        "<title>充电地图 · My Tesla</title>",
        '<a class="on" href="/tesla/chargemap">充电地图</a>',
        'id="map"',
        'id="view-seg"',
        '<button data-v="energy" class="on">充电电量</button>',
        '<button data-v="sessions">充电次数</button>',
        '<button data-v="cost">充电费用</button>',
        'id="st-places"', 'id="st-sessions"', 'id="st-energy"',   # 汇总行
        'id="legend"', 'id="lg-mode"', 'id="lg-ramp"', 'id="lg-row"',   # 热力图例
        'id="sh-name"', 'id="sh-sessions"', 'id="sh-fast"',
        'id="sh-energy"', 'id="sh-cost"',                          # 详情弹层
        'id="keyhint"', 'id="zin"', 'id="zout"',                   # Key 引导 + 缩放钮
        '"/tesla/charging/api/map-locations"',                     # 数据源
        "plugin=AMap.HeatMap",                                     # 热力插件随主脚本加载
        "new AMap.HeatMap(", "setDataSet",                         # 热力层
        "const GRADIENT = {",                                      # 蓝→红梯度 (图例同色)
        "PICK_PX", "pickNearest",                                  # 点击就近取点弹详情
        'GCJ02.wgs84ToGcj02',                                      # WGS-84 → GCJ-02
        '"/tesla/map/api/config?_="',                              # 高德配置 (Key/样式)
        "const VIEWS = {",
        "renderLegend", "setFitView", "gradientCss",
        "gesturestart",                                            # iOS 双指缩放防劫持
        "syncURL",
    ]:
        assert frag in html, f"充电地图页缺少 {frag}"
    # 时间菜单在顶栏 nav-row (与全站一致); 筛选行只剩三视图切换
    assert '</details>\n    <details class="nav-menu time-menu" id="time-menu">' in html
    assert '<div class="filters">\n    <div class="seg" id="view-seg">' in html


def test_chargemap_link_in_all_nav_menus(auth):
    """每个业务页的页签菜单都有充电地图入口; 上次停留页/登录回跳白名单收录。"""
    for path in PAGES:
        html = auth.get(path).text
        assert 'href="/tesla/chargemap">充电地图</a>' in html, path   # 含 on 态
    lastpage = auth.get("/tesla/static/lastpage.js?v=1").text
    assert '"/tesla/chargemap", "/tesla/map"' in lastpage
    login_js = auth.get("/static/login.js?v=1").text
    assert "stats|chargemap|map" in login_js
