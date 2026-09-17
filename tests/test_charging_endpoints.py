"""充电接口测试: 车辆/汇总/会话列表 (排序/过滤/搜索/分页)。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime

from tests.seed_factories import (seed_addresses, seed_car, seed_charge,
                            seed_charging)

# ---------------------------------------------------------------- 接口
def test_car_endpoint(auth, db):
    seed_car(db)
    r = auth.get("/tesla/charging/api/car")
    assert r.status_code == 200
    assert r.json() == [{"id": 1, "name": "臭哈子", "model": "Y",
                         "trim_badging": "50", "vin": "LRW1"}]


def test_summary_endpoint(auth, db):
    seed_addresses(db)
    # 快充 45/48kWh 25.5 元 + 慢充 (无 charges 采样, is_fast=False)
    seed_charging(db)
    seed_charge(db, 1)
    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 10, 0),
                  end_date=datetime(2026, 9, 8, 12, 0),
                  charge_energy_added=10.0, charge_energy_used=11.0,
                  duration_min=120, cost=None, start_battery_level=50,
                  end_battery_level=70, start_rated_range_km=200.0,
                  end_rated_range_km=280.0)
    d = auth.get("/tesla/charging/api/summary").json()
    assert d["sessions"] == 2
    assert d["fast_sessions"] == 1
    assert d["energy_added"] == 55.0
    assert d["energy_used"] == 59.0
    assert d["cost"] == 25.5
    assert d["price_per_kwh"] == round(25.5 / 59.0, 3)
    assert d["duration_min"] == 552
    assert d["soc_gain"] == 80
    assert d["range_gain"] == round((330 - 120) + (280 - 200), 1)
    assert d["first_date"] == "2026-09-07"
    assert d["last_date"] == "2026-09-08"


def test_summary_respects_date_range(auth, db):
    seed_addresses(db)
    seed_charging(db)          # 09-07
    seed_charging(db, id=2, start_date=datetime(2026, 8, 1, 1, 0),
                  end_date=datetime(2026, 8, 1, 3, 0))
    d = auth.get("/tesla/charging/api/summary",
                 params={"from": "2026-09-01"}).json()
    assert d["sessions"] == 1
    assert d["first_date"] == "2026-09-07"


def test_sessions_list(auth, db):
    seed_addresses(db)
    seed_charging(db, id=332)
    d = auth.get("/tesla/charging/api/sessions?limit=1").json()
    assert d["total"] == 1
    assert len(d["items"]) == 1
    assert d["items"][0]["id"] == 332


def test_sessions_rejects_unknown_sort(auth):
    r = auth.get("/tesla/charging/api/sessions?sort=hack")
    assert r.status_code == 400
    assert "不支持的排序" in r.json()["detail"]


def test_sessions_sort_orders_with_nulls_last(auth, db):
    """排序键齐全 + None 值排最后 (等价 Postgres NULLS LAST)。"""
    seed_addresses(db)
    # 1: 09-08 (最新) 30 元 55kWh 120 分; 2: 09-07 10 元 28kWh 150 分;
    # 3: 09-06 各字段全空
    seed_charging(db, id=1, cost=30.0, charge_energy_used=55.0,
                  duration_min=120, start_date=datetime(2026, 9, 8, 15, 50),
                  end_date=datetime(2026, 9, 8, 20, 0))
    seed_charging(db, id=2, cost=10.0, charge_energy_used=28.0, duration_min=150)
    seed_charging(db, id=3, cost=None, charge_energy_used=None,
                  duration_min=None, start_date=datetime(2026, 9, 6, 15, 50))
    base = "/tesla/charging/api/sessions?limit=50"

    def ids(qs):
        return [i["id"] for i in auth.get(f"{base}{qs}").json()["items"]]

    assert ids("&sort=date_desc") == [1, 2, 3]
    assert ids("&sort=date_asc") == [3, 2, 1]
    assert ids("&sort=cost_desc") == [1, 2, 3]     # None 排最后
    assert ids("&sort=cost_asc") == [2, 1, 3]
    assert ids("&sort=energy_desc") == [1, 2, 3]
    assert ids("&sort=energy_asc") == [2, 1, 3]
    assert ids("&sort=duration_desc") == [2, 1, 3]


def test_sessions_type_filter(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1)                      # 快充 (90kW 采样)
    seed_charge(db, 1, charger_power=90.0, fast_charger_present=True)
    seed_charging(db, id=2, start_date=datetime(2026, 9, 8, 10, 0))
    seed_charge(db, 2, charger_power=8.0, fast_charger_present=False,
                date=datetime(2026, 9, 8, 10, 5))
    assert auth.get("/tesla/charging/api/sessions?type=fast"
                    ).json()["total"] == 1
    assert auth.get("/tesla/charging/api/sessions?type=slow"
                    ).json()["total"] == 1
    assert auth.get("/tesla/charging/api/sessions"
                    ).json()["total"] == 2


def test_sessions_cost_filter(auth, db):
    """费用筛选: 已记录 / 未记录 (费用记 0 也算已记录); 非法值 400。"""
    seed_addresses(db)
    seed_charging(db, id=1, cost=25.5)                       # 记了费用
    seed_charging(db, id=2, cost=0.0,                        # 记了 0 元也算已记录
                  start_date=datetime(2026, 9, 8, 10, 0))
    seed_charging(db, id=3, cost=None,                       # 没记
                  start_date=datetime(2026, 9, 9, 10, 0))
    base = "/tesla/charging/api/sessions"
    assert auth.get(base, params={"cost": "recorded"}).json()["total"] == 2
    assert auth.get(base, params={"cost": "missing"}).json()["total"] == 1
    assert auth.get(base).json()["total"] == 3               # 不带 = 全部
    # 前端默认就发 cost=all (首屏), 必须当"全部"收下 —— 曾因不认 all 首屏 400
    assert auth.get(base, params={"cost": "all"}).json()["total"] == 3
    r = auth.get(base, params={"cost": "hack"})
    assert r.status_code == 400 and r.json()["detail"] == "不支持的费用筛选"


def test_sessions_search_by_address(auth, db):
    seed_addresses(db)
    seed_charging(db, id=1)
    seed_charging(db, id=2, address_id=2,            # 东莞
                  start_date=datetime(2026, 9, 8, 10, 0))
    base = "/tesla/charging/api/sessions"
    assert auth.get(base, params={"q": "龙岗"}).json()["total"] == 1
    assert auth.get(base, params={"q": "东莞"}).json()["total"] == 1
    assert auth.get(base, params={"q": "不存在的地方"}).json()["total"] == 0


def test_sessions_pagination(auth, db):
    seed_addresses(db)
    for i in range(5):
        seed_charging(db, id=i + 1,
                      start_date=datetime(2026, 9, 7 + i, 15, 50))
    base = "/tesla/charging/api/sessions?sort=date_asc"
    d1 = auth.get(f"{base}&offset=0&limit=2").json()
    assert d1["total"] == 5 and [i["id"] for i in d1["items"]] == [1, 2]
    d2 = auth.get(f"{base}&offset=2&limit=2").json()
    assert [i["id"] for i in d2["items"]] == [3, 4]
    assert auth.get(f"{base}&offset=4&limit=2").json()["items"][0]["id"] == 5
    assert auth.get(f"{base}&offset=99&limit=2").json()["items"] == []
