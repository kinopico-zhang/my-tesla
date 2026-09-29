"""充电详情测试 (API 口径): 单条详情, 站点坐标, 国标标签撤除, 月度统计,
地点聚合。页面接线断言在 test_charging_detail_page.py (2026-09-21 超
200 行硬上限拆出)。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime

from app.tesla.models import Address
from tests.seed_factories import seed_addresses, seed_charge, seed_charging

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
    assert d["curve"]["tabs"] == ["kw", "voltage", "current"]   # 真值齐全
    assert d["cable"] == "CCS"
    assert d["charger_brand"] is None               # <invalid> 已过滤
    assert d["charger_type"] == "Tesla"
    assert d["tesla_supercharger"] is False         # 第三方桩: brand 不是 Tesla
    assert d["start_rated_range"] == 120.0
    assert d["end_rated_range"] == 330.0


def test_session_detail_nav_coords(auth, db):
    """详情带充电站坐标 (WGS-84); 没坐标的地址给 None (地理编码成功与否
    照实反映, 前端导航按钮已撤, 字段留给往后再用)。"""
    db.add(Address(id=1, name="华为立体车库", city="深圳市",
                   display_name="深圳市华为立体车库",
                   latitude=22.55, longitude=114.05))
    db.commit()
    seed_charging(db)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["lat"] == 22.55 and d["lng"] == 114.05


def test_session_detail_no_coords(auth, db):
    """没反向地理编码过的地址: 坐标字段是 None。"""
    seed_addresses(db)                     # 默认地址没有坐标
    seed_charging(db)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["lat"] is None and d["lng"] is None


def test_session_detail_pw_tabs(auth, db):
    """曲线档位 (tabs) 只发有真数据的 —— 2026-09-21 查真库定位 "充电曲线
    为啥一直是0": 车辆直流快充不回报电压/电流, TeslaMate 原样落库成恒 2V /
    0A 的死字段 (家充 AC 的 400V / 220A 是真的)。死档不下发, 前端不画 0 平线。"""
    seed_addresses(db)
    seed_charging(db)                      # 快充: 电压电流死字段
    seed_charge(db, 1, charger_voltage=2.0, charger_actual_current=0.0)
    seed_charge(db, 1, id=None, date=datetime(2026, 9, 7, 16, 10),
                battery_level=30, charger_power=93.0,
                charger_voltage=2.0, charger_actual_current=0.0)
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["curve"]["tabs"] == ["kw"]            # 只剩功率

    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 15, 50),
                  end_date=datetime(2026, 9, 8, 23, 2))
    seed_charge(db, 2, date=datetime(2026, 9, 8, 16, 0),
                charger_power=7.0, charger_voltage=220.0,
                charger_actual_current=0.0)        # 电压真, 电流死
    d = auth.get("/tesla/charging/api/sessions/2").json()
    assert d["curve"]["tabs"] == ["kw", "voltage"]


def test_session_region_field(auth, db):
    """省市区链 (大→小, " · " 连) 列表与详情同一口径 (用户点名信息量
    对齐 + 从大到小排): 连写与 OSM 链都剥得出; 解析不出省 = None,
    前端退化到市级字段。"""
    seed_addresses(db)                       # 1=广东省深圳市龙岗区坂田街道
    db.add(Address(id=3, name="翠湖边", city="昆明市",
                   display_name="翠湖西路, 华山街道, 五华区, 昆明市, 云南省, 650031, 中国"))
    db.add(Address(id=4, name="无名地", city=None, display_name="某处"))
    db.commit()
    seed_charging(db, id=1, address_id=1)
    seed_charging(db, id=2, address_id=3)
    seed_charging(db, id=3, address_id=4)
    items = {i["id"]: i for i in auth.get(
        "/tesla/charging/api/sessions").json()["items"]}
    assert items[1]["region"] == "广东省 · 深圳市 · 龙岗区"   # 旧版连写
    assert items[2]["region"] == "云南省 · 昆明市 · 五华区"   # OSM 逗号链
    assert items[3]["region"] is None                        # 解析不出省
    d = auth.get("/tesla/charging/api/sessions/1").json()
    assert d["region"] == "广东省 · 深圳市 · 龙岗区"          # 详情同口径


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
    assert d["tesla_supercharger"] is True     # Tesla+Gb 采样 = 特斯拉超充


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
