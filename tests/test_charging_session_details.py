"""充电详情测试: 单条详情, 导航坐标, 国标标签撤除, 月度统计,
地点聚合。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime

from app.tesla.models import Address
from tests.seed_factories import seed_addresses, seed_charge, seed_charging
from tests.charging_page_scripts import CHARGING_ASSETS, _page_scripts

def test_session_detail(auth, db):
    seed_addresses(db)
    seed_charging(db)
    seed_charge(db, 1, date=datetime(2026, 9, 7, 16, 0),
                fast_charger_brand="<invalid>", fast_charger_type="Tesla")
    seed_charge(db, 1, id=None, date=datetime(2026, 9, 7, 16, 10),
                battery_level=30, charger_power=80.0,
                charger_actual_current=200.0, charge_energy_added=10.0,
                conn_charge_cable=None, fast_charger_brand=None,
                fast_charger_type=None)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["curve"]["minutes"] == [10.0, 20.0]    # 距 start (15:50) 的分钟数
    assert d["curve"]["soc"] == [20, 30]
    assert d["curve"]["kw"] == [90.0, 80.0]
    assert d["cable"] == "CCS"
    assert d["charger_brand"] is None               # <invalid> 已过滤
    assert d["charger_type"] == "Tesla"
    assert d["start_rated_range"] == 120.0
    assert d["end_rated_range"] == 330.0


def test_session_detail_nav_coords(auth, db):
    """详情带充电站坐标 (WGS-84) —— 前端导航换算的原料; 没坐标的地址给 None。"""
    db.add(Address(id=1, name="华为立体车库", city="深圳市",
                   display_name="深圳市华为立体车库",
                   latitude=22.55, longitude=114.05))
    db.commit()
    seed_charging(db)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["lat"] == 22.55 and d["lng"] == 114.05


def test_session_detail_no_coords(auth, db):
    """没反向地理编码过的地址: 坐标字段是 None (前端不渲染导航按钮)。"""
    seed_addresses(db)                     # 默认地址没有坐标
    seed_charging(db)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["lat"] is None and d["lng"] is None


def test_charging_detail_nav_button(auth):
    """详情「导航到充电站」: 先弹选单让用户挑地图 App, 点一个只拉一个。"""
    html = auth.get("/tesla/charging").text
    html += _page_scripts(auth, *CHARGING_ASSETS)
    for frag in [
        'id="nav-go"', "🧭 导航到充电站",
        'id="nav-bd"', 'id="nav-apps"', 'id="nav-cancel"',     # 选单
        'data-app="amap"', 'data-app="baidu"',
        'data-app="tencent"', 'data-app="apple"',
        "openNavChooser",                     # 点按钮先弹选单
        # 没装的地图长按隐藏 (localStorage 记住), ＋ 胶囊恢复 —— 网页枚举不了装了哪些 App
        "navHiddenApps", "function renderNavApps()", "data-restore",
        "长按可隐藏没装的地图", "长按隐藏后的 click 吞掉",
        "function navAppUrl(",                # 一个 App 一个 URL
        "GCJ02.wgs84ToGcj02",                 # WGS-84 → GCJ-02, 不转偏几百米
        "iosamap://navi", "androidamap://navi",    # 高德 (iOS / 安卓 scheme)
        "baidumap", "://map/direction", "coord_type=gcj02",   # 百度 (iOS/安卓 scheme 前缀不同)
        "qqmap://map/routeplan", "fromcoord=CurrentLocation",   # 腾讯
        "maps.apple.com/?daddr",                   # 苹果地图
    ]:
        assert frag in html, f"充电详情导航缺少 {frag}"
    # 不自动探测连环拉起: iOS 拉 scheme 前先弹「在 xx 中打开」确认框,
    # 确认前页面不切后台, 探测窗口一过就把装了的 App 连环拉起 (用户实测)
    js = _page_scripts(auth, *CHARGING_ASSETS)
    for gone in ["NAV_PROBE_MS", "visibilitychange", "uri.amap.com/navigation"]:
        assert gone not in js, f"自动探测链残留: {gone}"
    # 坐标换算库要先于页面脚本加载
    page = auth.get("/tesla/charging").text
    assert page.index("gcj02.js") < page.index("charging-page.js")


def test_session_detail_hides_national_standard_tags(auth, db):
    """国标取值 (线缆 GB_DC / 类型 Gb, 国内满屏都是) 不进详情 —— 用户点名撤掉。

    品牌 Tesla 不受影响; 非国标取值 (CCS / v3) 照常展示。
    """
    seed_addresses(db)
    seed_charging(db)
    seed_charge(db, 1, conn_charge_cable="GB_DC",
                fast_charger_brand="Tesla", fast_charger_type="Gb")
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["cable"] is None and d["charger_type"] is None
    assert d["charger_brand"] == "Tesla"       # 国标过滤不殃及品牌


def test_session_detail_404(auth):
    assert auth.get("/tesla/charging/api/sessions/99999").status_code == 404


def test_monthly_endpoint(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1, cost=150.0, charge_energy_used=300.0,
                  duration_min=60)
    seed_charging(db, id=2, start_date=datetime(2026, 8, 1, 2, 0),
                  end_date=datetime(2026, 8, 1, 4, 0), cost=None,
                  charge_energy_used=None)
    d = auth.get("/tesla/charging/api/monthly").json()
    assert d == [
        {"month": "2026-08", "sessions": 1, "energy_used": None,
         "cost": None, "fast_sessions": 0},
        {"month": "2026-09", "sessions": 1, "energy_used": 300.0,
         "cost": 150.0, "fast_sessions": 0},
    ]


def test_locations_endpoint(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1, address_id=2)          # 东莞 1 次
    seed_charging(db, id=2, address_id=1,          # 深圳 2 次
                  start_date=datetime(2026, 9, 8, 10, 0))
    seed_charging(db, id=3, address_id=1,
                  start_date=datetime(2026, 9, 9, 10, 0))
    d = auth.get("/tesla/charging/api/locations").json()
    assert d[0]["location"] == "华为立体车库"        # 次数多的排前面
    assert d[0]["sessions"] == 2
    assert d[0]["city"] == "深圳市"
    assert d[1]["location"] == "长安镇"
    assert d[1]["city"] == "东莞市"
