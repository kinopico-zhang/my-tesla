"""驻车常显的实时性: 停车充电的点位 (drive_id 为空) 也要进最后已知量。
2026-09-29 用户实报「状态页面, 驻车的时候没有实时更新, 我都充满电了,
还是显示没电」—— 根因: _last_known 原先内连接 Drive, 充电采样整段被
排除, 电量冻在最后一段行程末值 (修法与口径见 repository/live.py)。"""
from datetime import datetime, timedelta, timezone

from tests.seed_factories import seed_drive, seed_position

_EPOCH = datetime(1970, 1, 1)


def _utcnow() -> datetime:
    """与库内 date 同口径的 UTC 裸时间 (同 test_live_status)。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _epoch(dt: datetime) -> int:
    return int((dt - _EPOCH).total_seconds())


def test_parked_charging_positions_count(auth, db):
    """停车充电: TeslaMate 照写 positions (不带行程), 电量/续航/位置一路
    刷新 —— 最后已知量必须跟到充满, 不许冻在最后一段行程末值 (9%)。"""
    now = _utcnow()
    seed_drive(db, id=1, start_date=now - timedelta(hours=3),
               end_date=now - timedelta(hours=2), distance=5.0)
    # 最后一段行程末点: 低电量 (充电前)
    seed_position(db, drive_id=1, date=now - timedelta(hours=2),
                  longitude=114.0, latitude=22.5, speed=0, odometer=200.0,
                  battery_level=9, rated_battery_range_km=38.0)
    # 充电中的采样点: 不挂行程 (drive_id 空), 电量爬到满
    seed_position(db, drive_id=None, date=now - timedelta(minutes=5),
                  longitude=114.0, latitude=22.5, battery_level=100,
                  rated_battery_range_km=419.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is False and j["drive_id"] is None
    assert j["soc"] == 100 and j["rated_range_km"] == 419.0
    assert j["pos_utc"] == _epoch(now - timedelta(minutes=5))
    # car_id 过滤改走 Position.car_id: 车 2 不看车 1 的充电采样
    j2 = auth.get("/tesla/live/api/status?car_id=2").json()
    assert j2["soc"] is None and j2["rated_range_km"] is None
