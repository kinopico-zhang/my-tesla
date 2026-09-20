"""多车 car_id 穿参测试 (行程/足迹地图/当前驾驶): 双车种子下缺省 =
全部, ?car_id=N = 子集; kwh 换算按各自车的充电定标。充电域见
test_car_filter.py。
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.tesla import repository
from tests.car_seed_helpers import _seed_two_cars, _seed_two_drives
from tests.seed_factories import seed_drive, seed_positions


def _utcnow() -> datetime:
    """与库内 date 同口径的 UTC 裸时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- 行程域

def test_trips_sessions_filter_by_car_and_per_car_kwh(auth, db):
    _seed_two_drives(db)
    d = auth.get("/tesla/trips/api/sessions").json()
    assert d["total"] == 2
    assert {i["id"] for i in d["items"]} == {1, 2}
    d1 = auth.get("/tesla/trips/api/sessions?car_id=1").json()
    assert d1["total"] == 1 and [i["id"] for i in d1["items"]] == [1]
    d2 = auth.get("/tesla/trips/api/sessions?car_id=2").json()
    assert d2["total"] == 1 and [i["id"] for i in d2["items"]] == [2]
    # kwh 按各自车的定标算: 车1 = 120km × 45/210 = 25.7,
    # 车2 = 100km × 60/300 = 20.0 (合算口径会得 24.7 / 20.6, 能区分)
    assert d1["items"][0]["kwh"] == pytest.approx(25.7)
    assert d2["items"][0]["kwh"] == pytest.approx(20.0)
    # 单条行程也用自己的车 (不随查询参数)
    one = auth.get("/tesla/trips/api/sessions/2").json()
    assert one["kwh"] == pytest.approx(20.0)


def test_trips_regions_filter_by_car(auth, db):
    _seed_two_drives(db)
    tree = auth.get("/tesla/trips/api/regions").json()
    assert tree["start"][0]["name"] == "广东省" and tree["start"][0]["count"] == 2
    tree1 = auth.get("/tesla/trips/api/regions?car_id=1").json()
    # 车 1 只从深圳出发: 省计数 1, 市级只剩深圳市
    assert tree1["start"][0]["count"] == 1
    assert [c["name"] for c in tree1["start"][0]["children"]] == ["深圳市"]


# ---------------------------------------------------------------- 足迹地图域

def test_map_summary_and_manifest_filter_by_car(auth, db):
    _seed_two_drives(db)
    s = auth.get("/tesla/map/api/summary").json()
    assert s["drives"] == 2 and s["distance_km"] == 142.5
    s1 = auth.get("/tesla/map/api/summary?car_id=1").json()
    assert s1["drives"] == 1 and s1["distance_km"] == 42.5
    s2 = auth.get("/tesla/map/api/summary?car_id=2").json()
    assert s2["drives"] == 1 and s2["distance_km"] == 100.0

    # 清单带 c/t 字段, 车辆/时间筛选在客户端按清单本地做
    m = auth.get("/tesla/map/api/tracks/manifest").json()
    assert [(t["id"], t["c"], t["t"]) for t in m["tracks"]] == [
        (1, 1, "2026-09-10"), (2, 2, "2026-09-11")]
    # 轨迹本体按 id 流式下发, 带自己的 car_id
    r = auth.get("/tesla/map/api/tracks/stream", params={"ids": "2"})
    lines = [json.loads(x) for x in r.text.splitlines()]
    assert [t["id"] for t in lines] == [2]
    assert lines[0]["car_id"] == 2
    assert lines[0]["pts"] == [113.75, 22.8, 113.76, 22.81]


# ---------------------------------------------------------------- 当前驾驶域

def test_live_status_filter_by_car_and_per_car_kwh(auth, db):
    _seed_two_cars(db)
    now = _utcnow()
    seed_drive(db, id=501, car_id=1,
               start_date=now - timedelta(minutes=30), end_date=None,
               distance=None, duration_min=None)
    seed_positions(db, 501, [
        {"date": now - timedelta(minutes=30), "speed": 20, "odometer": 100.0,
         "longitude": 114.05, "latitude": 22.55,
         "battery_level": 90, "rated_battery_range_km": 400.0},
        {"date": now - timedelta(seconds=30), "speed": 55, "odometer": 112.0,
         "longitude": 114.10, "latitude": 22.57,
         "battery_level": 85, "rated_battery_range_km": 380.0}])
    seed_drive(db, id=502, car_id=2,
               start_date=now - timedelta(minutes=20), end_date=None,
               distance=None, duration_min=None)
    seed_positions(db, 502, [
        {"date": now - timedelta(minutes=20), "speed": 30, "odometer": 200.0,
         "longitude": 113.75, "latitude": 22.80,
         "battery_level": 80, "rated_battery_range_km": 400.0},
        {"date": now - timedelta(seconds=10), "speed": 62, "odometer": 212.0,
         "longitude": 113.80, "latitude": 22.82,
         "battery_level": 76, "rated_battery_range_km": 380.0}])

    # 缺省 = 全库最新 → 车 2 的行程
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is True and j["drive_id"] == 502
    # 车 1: 定标 45/210 → 20km 续航差 × 3/14 = 4.3
    j1 = auth.get("/tesla/live/api/status?car_id=1").json()
    assert j1["driving"] is True and j1["drive_id"] == 501
    assert j1["kwh"] == pytest.approx(4.3)
    # 车 2: 定标 60/300 = 0.2 → 20 × 0.2 = 4.0
    j2 = auth.get("/tesla/live/api/status?car_id=2").json()
    assert j2["drive_id"] == 502 and j2["kwh"] == pytest.approx(4.0)
    # 未知车辆 → 不在开
    j9 = auth.get("/tesla/live/api/status?car_id=99").json()
    assert j9["driving"] is False and j9["drive_id"] is None


# ---------------------------------------------------------------- 换算系数本身

def test_charge_efficiency_per_car(db):
    _seed_two_cars(db)
    assert repository.charge_efficiency(db) == pytest.approx(105.0 / 510.0)
    assert repository.charge_efficiency(db, 1) == pytest.approx(45.0 / 210.0)
    assert repository.charge_efficiency(db, 2) == pytest.approx(60.0 / 300.0)
    assert repository.charge_efficiency(db, 99) is None
