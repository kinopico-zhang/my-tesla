"""充电记录转换语义测试 (repository 层): 字段/价格口径, 地点优先级,
缺费用, 日期区间边界。
拆自 test_charging.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime

from app.tesla import repository
from app.tesla.models import Geofence
from tests.seed_factories import seed_addresses, seed_charge, seed_charging

# ---------------------------------------------------------------- 转换语义 (repository)
def test_session_fields_and_price(db):
    seed_addresses(db)
    seed_charge(db, 1)
    seed_charging(db)          # 默认: 45/48kWh, 25.5 元, 无 geofence
    row = repository.list_charging_sessions(db, repository.SessionFilter(
        None, "all", None, "date_desc", 0, 50))[1][0]
    assert row.id == 1
    assert row.start == "2026-09-07 23:50"      # UTC 15:50 → 北京时间
    assert row.date == "2026-09-07"
    assert row.location == "华为立体车库"         # 无 geofence 时退回 address
    assert row.price_per_kwh == round(25.5 / 48.0, 3)
    assert row.is_fast is True                   # charges 有 90kW 采样
    assert row.outside_temp == 28.5
    assert row.city == "深圳市"


def test_session_geofence_preferred(db):
    db.add(Geofence(id=7, name="公司"))
    db.commit()
    seed_addresses(db)
    seed_charging(db, geofence_id=7)
    seed_charge(db, 1)
    item = repository.list_charging_sessions(db, repository.SessionFilter(
        None, "all", None, "date_desc", 0, 50))[1][0]
    assert item.location == "公司"


def test_session_without_cost(db):
    seed_addresses(db)
    seed_charging(db, cost=None)
    item = repository.list_charging_sessions(db, repository.SessionFilter(
        None, "all", None, "date_desc", 0, 50))[1][0]
    assert item.cost is None
    assert item.price_per_kwh is None


def test_parse_date_range_boundaries():
    rng = repository.parse_date_range("2026-01-01", "2026-01-31")
    assert rng is not None
    # 北京时间 1/1 00:00 = UTC 前一天 16:00; to 的边界是次日零点 (左闭右开)
    assert rng.start == datetime(2025, 12, 31, 16, 0)
    assert rng.end == datetime(2026, 1, 31, 16, 0)
    assert repository.parse_date_range(None, None) is None
    try:
        repository.parse_date_range("2026-13-99", None)
        raise AssertionError("非法日期应抛 ValueError")
    except ValueError as exc:
        assert "日期格式错误" in str(exc)
