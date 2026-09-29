"""实时驾驶状态测试: 字段口径, 在开判据, 电耗标定边界, 驻车带的最后行程。
拆自 test_live.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime, timedelta, timezone

from tests.seed_factories import seed_charging, seed_drive, seed_position

_EPOCH = datetime(1970, 1, 1)

def _utcnow() -> datetime:
    """与库内 date 同口径的 UTC 裸时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _epoch(dt: datetime) -> int:
    """UTC 裸时间 → epoch 秒 (与 repository._utc_seconds 同算法)。"""
    return int((dt - _EPOCH).total_seconds())


# ---------------------------------------------------------------- 在开: 字段口径

def test_live_status_fields(auth, db):
    """开着的行程: 速度/SOC/位置取最新采样点, 里程 = odometer 差,
    电耗 = 续航差 (首个/最新非空轮询值) × 充电定标 (与行程页同口径)。"""
    now = _utcnow()
    seed_charging(db)   # 默认种子: 45 kWh / 210 km 续航增量 → 定标 3/14
    seed_drive(db, id=500, start_date=now - timedelta(minutes=40),
               end_date=None, distance=None, duration_min=None)
    seed_position(db, drive_id=500, date=now - timedelta(minutes=40),
                  longitude=114.05, latitude=22.55, speed=12,
                  odometer=100.0, battery_level=97, rated_battery_range_km=402.0)
    seed_position(db, drive_id=500, date=now - timedelta(minutes=20),
                  longitude=114.10, latitude=22.57, speed=40,
                  odometer=112.4, battery_level=93, rated_battery_range_km=None)
    seed_position(db, drive_id=500, date=now - timedelta(seconds=70),
                  longitude=114.20, latitude=22.59, speed=55,
                  odometer=120.0, battery_level=91, rated_battery_range_km=377.2)
    seed_position(db, drive_id=500, date=now - timedelta(seconds=30),
                  longitude=114.26, latitude=22.61, speed=62,
                  odometer=124.8, battery_level=90, rated_battery_range_km=None)

    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is True
    assert j["drive_id"] == 500
    assert j["speed"] == 62                                 # 最新点车速
    assert j["soc"] == 90
    assert j["rated_range_km"] == 377.2                # 最新非空轮询值
    assert j["km"] == 24.8                             # odometer 差
    assert j["kwh"] == 5.3                             # (402-377.2) × 3/14
    assert j["lng"] == 114.26 and j["lat"] == 22.61
    assert j["pos_utc"] == _epoch(now - timedelta(seconds=30))
    assert j["started_utc"] == _epoch(now - timedelta(minutes=40))
    # 服务器时钟锚: 手机时钟不准时前端靠它校偏差, 否则已行驶被钳成 0:00
    assert abs(j["now_utc"] - _epoch(now)) < 5
    assert isinstance(j["start"], str) and j["start"]


# ---------------------------------------------------------------- 在开判据

def test_live_status_stale_open_drive_is_not_driving(auth, db):
    """未关闭但位置点在几个月前 (TeslaMate 中断残留) → 不算在开;
    仍报最后已知电量/续航/位置 (状态页不开车常显, 2026-09-26 用户点名)。"""
    old = datetime(2026, 8, 21, 9, 8)
    seed_drive(db, id=1838, start_date=old, end_date=None, distance=None)
    seed_position(db, drive_id=1838, date=old, longitude=114.0, latitude=22.5,
                  speed=20, odometer=100.0, battery_level=90,
                  rated_battery_range_km=300.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is False and j["drive_id"] is None
    assert j["soc"] == 90 and j["rated_range_km"] == 300.0
    assert j["lng"] == 114.0 and j["lat"] == 22.5
    assert j["pos_utc"] == _epoch(old)


def test_live_status_picks_freshest_open_drive(auth, db):
    """多条未关闭行程里取位置点最新的那条 (与出发时间无关)。"""
    old = datetime(2026, 8, 21, 9, 8)
    now = _utcnow()
    seed_drive(db, id=1838, start_date=old, end_date=None, distance=None)
    seed_position(db, drive_id=1838, date=old, longitude=114.0, latitude=22.5,
                  speed=20)
    seed_drive(db, id=2208, start_date=now - timedelta(minutes=5),
               end_date=None, distance=None)
    seed_position(db, drive_id=2208, date=now - timedelta(seconds=10),
                  longitude=114.1, latitude=22.6, speed=33,
                  odometer=10.0, battery_level=80)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is True and j["drive_id"] == 2208 and j["speed"] == 33


def test_live_status_ignores_just_closed_drive(auth, db):
    """位置点再新, 行程已闭合 (end_date 非空) 就不是当前驾驶
    (但最后已知位置照报, 状态页常显)。"""
    now = _utcnow()
    seed_drive(db, id=1, start_date=now - timedelta(minutes=10),
               end_date=now - timedelta(seconds=60), distance=5.0)
    seed_position(db, drive_id=1, date=now - timedelta(seconds=61),
                  longitude=114.0, latitude=22.5, speed=10, odometer=100.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is False and j["drive_id"] is None
    assert j["lng"] == 114.0 and j["lat"] == 22.5
    assert j["pos_utc"] == _epoch(now - timedelta(seconds=61))


def test_live_status_parked_returns_last_known(auth, db):
    """常态停车: 最后已知电量/续航/位置照报 (状态页常显, 全库最新位置点,
    行程开没开完不管); 电量/续航取最新非空值 (流式点位大多缺席);
    car_id 选定只看那台车。"""
    now = _utcnow()
    seed_drive(db, id=1, start_date=now - timedelta(hours=2),
               end_date=now - timedelta(hours=1), distance=5.0)
    # 行程末点: 有位置无电量无续航 (流式点常态)
    seed_position(db, drive_id=1, date=now - timedelta(hours=1),
                  longitude=114.30, latitude=22.70, speed=0, odometer=200.0)
    # 行程早段: 电量/续航都在 (取这俩的最新非空值)
    seed_position(db, drive_id=1, date=now - timedelta(hours=2),
                  longitude=114.0, latitude=22.5, speed=30, odometer=190.0,
                  battery_level=78, rated_battery_range_km=310.0)
    # 另一台车位置更新: 缺省 (全库) 看它, car_id=1 不串台
    seed_drive(db, id=2, car_id=2, start_date=now - timedelta(minutes=30),
               end_date=now - timedelta(minutes=10))
    seed_position(db, drive_id=2, car_id=2, date=now - timedelta(minutes=10),
                  longitude=113.0, latitude=23.5, battery_level=55)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is False and j["drive_id"] is None
    assert j["lng"] == 113.0 and j["lat"] == 23.5    # 全库最新位置 = 车 2 (更新)
    assert j["soc"] == 55                            # 电量同口径: 最新非空 (车 2)
    assert j["rated_range_km"] == 310.0              # 全库最新非空续航只有车 1 有
    j1 = auth.get("/tesla/live/api/status?car_id=1").json()
    assert j1["lng"] == 114.3 and j1["lat"] == 22.7  # 车 1: 行程末点 (无电量常态)
    assert j1["soc"] == 78 and j1["rated_range_km"] == 310.0
    j2 = auth.get("/tesla/live/api/status?car_id=2").json()
    assert j2["lng"] == 113.0 and j2["soc"] == 55
    assert j2["rated_range_km"] is None              # 车 2 从没有过非空续航


def test_live_status_parked_last_drive(auth, db):
    """驻车带最后一段已结束行程 (2026-09-27 用户点名「驻车的时候, 显示
    最后一段行程」): 条目走行程列表同一条目组装 (_trip_item), car_id
    选定只看那台车。"""
    now = _utcnow()
    seed_drive(db, id=1, start_date=now - timedelta(hours=2),
               end_date=now - timedelta(hours=1), distance=5.0, duration_min=30)
    seed_position(db, drive_id=1, date=now - timedelta(hours=1),
                  longitude=114.0, latitude=22.5, odometer=100.0)
    d = auth.get("/tesla/live/api/status").json()["last_drive"]
    assert d["id"] == 1 and d["km"] == 5.0 and d["min"] == 30
    assert d["date"] and d["start"] and d["end"]   # 副行「最后行程 日期 起–止」
    assert auth.get("/tesla/live/api/status?car_id=2").json()["last_drive"] is None


def test_live_status_parked_empty_db(auth, db):
    """空库: 不开车也没任何已知量 —— 全部 None (前端各格显 –)。"""
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is False
    for k in ("soc", "rated_range_km", "lng", "lat", "pos_utc", "drive_id",
              "last_drive"):
        assert j[k] is None, k


# ---------------------------------------------------------------- 电耗口径边界

def test_live_status_without_calibration_hides_kwh(auth, db):
    """没有充电定标 (无可用充电记录) 时电耗格显示占位, 其余照常。"""
    now = _utcnow()
    seed_drive(db, id=9, start_date=now - timedelta(minutes=3),
               end_date=None, distance=None)
    seed_position(db, drive_id=9, date=now - timedelta(minutes=3),
                  longitude=114.0, latitude=22.5, speed=5,
                  odometer=100.0, battery_level=90, rated_battery_range_km=400.0)
    seed_position(db, drive_id=9, date=now - timedelta(seconds=20),
                  longitude=114.01, latitude=22.51, speed=30,
                  odometer=101.5, battery_level=89, rated_battery_range_km=398.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["driving"] is True
    assert j["km"] == 1.5
    assert j["kwh"] is None


def test_live_status_short_drive_and_regen_clamp(auth, db):
    """续航回弹 (校准/回收) 夹到 0。(原先还带里程 <1km 平均电耗 → None 的
    边界断言, 该字段随平均电耗格 2026-09-29 用户点名删除一并退役。)"""
    now = _utcnow()
    seed_charging(db)
    seed_drive(db, id=7, start_date=now - timedelta(minutes=1),
               end_date=None, distance=None)
    seed_position(db, drive_id=7, date=now - timedelta(minutes=1),
                  longitude=114.0, latitude=22.5, speed=3,
                  odometer=100.0, battery_level=90, rated_battery_range_km=400.0)
    seed_position(db, drive_id=7, date=now - timedelta(seconds=10),
                  longitude=114.001, latitude=22.501, speed=8,
                  odometer=100.4, battery_level=90, rated_battery_range_km=402.0)
    j = auth.get("/tesla/live/api/status").json()
    assert j["km"] == 0.4
    assert j["kwh"] == 0.0
