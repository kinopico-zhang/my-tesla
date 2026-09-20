"""多车测试种子助手: 双车场景的快捷播种。
拆自 test_car_filter.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime

from tests.seed_factories import seed_addresses, seed_car, seed_charge, \
    seed_charging, seed_drive, seed_positions


def _seed_two_cars(db) -> None:
    """两台车 + 各自一条充电记录 (定标不同: 车1 = 45/210, 车2 = 60/300)。"""
    seed_car(db)                                   # id=1 臭哈子
    seed_car(db, id=2, name="小黑", model="3",
             trim_badging="P", vin="5YJ3")
    seed_addresses(db)
    # 车 1: 默认种子 (2026-09-07, 快充 90kW 采样, 45 kWh / 210 km)
    seed_charge(db, 1)
    seed_charging(db)
    # 车 2: 2026-09-08, 慢充 11kW, 60 kWh / 300 km, 地址 2 (东莞)
    seed_charging(db, id=2, car_id=2,
                  start_date=datetime(2026, 9, 8, 3, 0),
                  end_date=datetime(2026, 9, 8, 4, 0),
                  address_id=2, start_battery_level=30, end_battery_level=90,
                  charge_energy_added=60.0, charge_energy_used=64.0,
                  duration_min=60, cost=None,
                  start_rated_range_km=100.0, end_rated_range_km=400.0)
    seed_charge(db, 2, date=datetime(2026, 9, 8, 3, 30),
                charger_power=11.0, fast_charger_present=False,
                battery_level=30)


def _seed_two_drives(db) -> None:
    """两台车各一条已结束行程 (额定续航差不同, 验证每车定标 kwh)。"""
    _seed_two_cars(db)
    seed_drive(db, id=1, car_id=1,                 # 车 1: 42.5km, 续航 330→210
               start_rated_range_km=330.0, end_rated_range_km=210.0)
    seed_positions(db, 1, [
        {"date": datetime(2026, 9, 10, 0, 32),
         "longitude": 114.05, "latitude": 22.55},
        {"date": datetime(2026, 9, 10, 1, 44),
         "longitude": 114.06, "latitude": 22.56}])
    seed_drive(db, id=2, car_id=2,                 # 车 2: 100km, 续航 400→300
               start_date=datetime(2026, 9, 11, 5, 0),
               end_date=datetime(2026, 9, 11, 6, 40),
               distance=100.0, duration_min=100,
               start_address_id=2, end_address_id=1,
               start_rated_range_km=400.0, end_rated_range_km=300.0)
    seed_positions(db, 2, [
        {"date": datetime(2026, 9, 11, 5, 0),
         "longitude": 113.75, "latitude": 22.80},
        {"date": datetime(2026, 9, 11, 6, 40),
         "longitude": 113.76, "latitude": 22.81}])
