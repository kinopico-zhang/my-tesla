"""行程统计视图接口测试 (2026-09-27 新增, 用户点名「加一个行程统计页面,
参考充电统计」): 五路接口 (汇总/按月/常去地点/司机里程/维度聚合) + 车辆
过滤与未定标口径; 壳内视图骨架拆去 test_tripstats_view (司机里程分布
批次把这边顶到 200 行硬上限)。

电耗与行程列表同源: 额定续航差 × 充电定标 (默认种子车 1 = 45 kWh /
210 km 续航差), 没定标的车如实亮 None。落档口径住
repository/trips/trip_stats.py (TRIP_*_EDGES, 与充电统计 _bump 同款);
车速档例外 —— positions 积分的速度段里程, 口径与缓存住
speed_hist_cache.py, 测试拆 test_speed_hist (2026-09-27 真速度分布批次)。
"""
from datetime import datetime

from app.tesla.models import Driver, TripDriver
from tests.car_seed_helpers import _seed_two_drives
from tests.seed_factories import seed_addresses, seed_drive, seed_charging


def _seed_stats(db):
    """四条行程 (车 1, 定标 45/210 → 每 km 额定续航 = 3/14 kWh):
    A 默认种子: 本地 08:32 出发, 42.5km/72分/118km/h, 续航 300→258 → 9.0 kWh
    B 本地 22:00 出发, 150km/120分/135km/h, 续航 260→160 → 21.4 kWh
    C 本地 11:30 出发, 1.5km/8分/15km/h, 无续航数据 (不进电耗, 没地址也照进)
    D 上月 (2026-08) 本地 13:00 出发, 320km/330分/160km/h, 续航 400→50
      → 75.0 kWh; 起点东莞 (长安镇), 终点无地址
    """
    seed_addresses(db)                     # 1=深圳 华为立体车库 2=东莞 长安镇
    seed_charging(db)                      # 车 1 定标 (45 kWh / 210 km)
    seed_drive(db, id=1, start_rated_range_km=300.0, end_rated_range_km=258.0)
    seed_drive(db, id=2, start_date=datetime(2026, 9, 11, 14, 0),
               end_date=datetime(2026, 9, 11, 16, 0),
               distance=150.0, duration_min=120, speed_max=135,
               start_rated_range_km=260.0, end_rated_range_km=160.0)
    seed_drive(db, id=3, start_date=datetime(2026, 9, 12, 3, 30),
               end_date=datetime(2026, 9, 12, 3, 38),
               distance=1.5, duration_min=8, speed_max=15)
    seed_drive(db, id=4, start_date=datetime(2026, 8, 5, 5, 0),
               end_date=datetime(2026, 8, 5, 10, 30),
               distance=320.0, duration_min=330, speed_max=160,
               start_address_id=2, end_address_id=None,
               start_rated_range_km=400.0, end_rated_range_km=50.0)


# ---------------------------------------------------------------- 五路接口
def test_trip_stats_summary(auth, db):
    """汇总: 次数/里程/时长/电耗/平均电耗/最快车速 + 起止日期
    (电耗 = 各行程定标 kwh 之和, 没续航数据的 C 不进)。"""
    _seed_stats(db)
    s = auth.get("/tesla/trips/api/stats/summary").json()
    assert s["trips"] == 4
    assert s["km"] == 514.0                # 42.5 + 150 + 1.5 + 320
    assert s["duration_min"] == 530        # 72 + 120 + 8 + 330
    assert s["kwh"] == 105.4               # 9.0 + 21.4 + 75.0 (C 未定标不计)
    assert s["wh_per_km"] == 205           # 105.4 / 514 km × 1000
    assert s["speed_max"] == 160
    assert s["first_date"] == "2026-08-05" and s["last_date"] == "2026-09-12"


def test_trip_stats_monthly(auth, db):
    """按月分组 (本地月份): 8 月只有 D, 9 月 A/B/C 三条; C 没定标但不影响
    9 月合计 (9.0 + 21.4)。"""
    _seed_stats(db)
    mm = auth.get("/tesla/trips/api/stats/monthly").json()
    assert mm == [
        {"month": "2026-08", "trips": 1, "km": 320.0, "kwh": 75.0},
        {"month": "2026-09", "trips": 3, "km": 194.0, "kwh": 30.4},
    ]


def test_trip_stats_locations(auth, db):
    """常去地点: 起终点地址并计 (地名优先), 次数降序; 终点无地址的 D
    只贡献起点一次。"""
    _seed_stats(db)
    locs = auth.get("/tesla/trips/api/stats/locations").json()
    assert locs == [
        {"name": "长安镇", "trips": 4},        # A/B/C 终点 + D 起点
        {"name": "华为立体车库", "trips": 3},  # A/B/C 起点 (D 终点无地址)
    ]


def test_trip_stats_dimensions(auth, db):
    """维度聚合: 出发时段每 2 小时一组 (本地时区), 距离/时长/电耗落档计数
    (没值的不进档 —— C 没续航不进电耗档)。车速档不在此验 —— 真速度分布
    (positions 积分里程) 拆去 test_speed_hist。"""
    _seed_stats(db)
    d = auth.get("/tesla/trips/api/stats/dimensions").json()
    # 出发时段: A 08:32→4 组, C 11:30→5 组, D 13:00→6 组, B 22:00→11 组
    assert d["by_hour"] == [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1]
    # 距离: C 1.5→<2, A 42.5→20-50, B 150→150-200, D 320→≥300
    assert d["by_dist"] == [1, 0, 0, 0, 1, 0, 0, 1, 0, 1]
    # 时长: C 8分→<10分, A 72分→1-1.5时, B 120分→2-3时, D 330分→≥5时
    assert d["by_dur"] == [1, 0, 0, 0, 0, 1, 0, 1, 0, 1]
    # 电耗: A 212→200-220, B 143→140-160, D 234→220-240; C 未定标不计
    assert d["by_wh"] == [0, 0, 0, 1, 0, 0, 1, 1, 0, 0]


def test_trip_stats_drivers(auth, db, owndb):
    """司机里程分布 (2026-09-27 用户点名「行驶统计加一个司机里程分布」):
    归集口径与行程卡片同款 —— 显式标注 > 默认驾驶员兜底; 没驾驶员配置时
    整体归「未标注」; 按里程降序。D (320km) 标给小导子, 其余三条未标注
    落默认大导子 (42.5 + 150 + 1.5 = 194)。"""
    _seed_stats(db)
    owndb.add(Driver(id=1, name="大导子", is_default=True))
    owndb.add(Driver(id=2, name="小导子"))
    owndb.add(TripDriver(drive_id=4, driver_id=2))
    owndb.commit()
    assert auth.get("/tesla/trips/api/stats/drivers").json() == [
        {"name": "小导子", "km": 320.0, "trips": 1},
        {"name": "大导子", "km": 194.0, "trips": 3},
    ]
    assert auth.get("/tesla/trips/api/stats/drivers?car_id=99").json() == []
    # 没配任何驾驶员: 不硬造默认名, 如实归「未标注」
    for row in owndb.query(Driver).all():
        owndb.delete(row)
    owndb.commit()
    assert auth.get("/tesla/trips/api/stats/drivers").json() == [
        {"name": "未标注", "km": 514.0, "trips": 4},
    ]


def test_trip_stats_uncalibrated_car(auth, db):
    """没有充电记录 (未定标) 的车: 电耗两路如实 None / 全 0, 次数照常。"""
    seed_addresses(db)
    seed_drive(db, id=1)
    s = auth.get("/tesla/trips/api/stats/summary").json()
    assert s["trips"] == 1 and s["km"] == 42.5
    assert s["kwh"] is None and s["wh_per_km"] is None
    mm = auth.get("/tesla/trips/api/stats/monthly").json()
    assert mm == [{"month": "2026-09", "trips": 1, "km": 42.5, "kwh": None}]
    d = auth.get("/tesla/trips/api/stats/dimensions").json()
    assert d["by_wh"] == [0] * 10 and sum(d["by_dist"]) == 1
    assert d["by_spd"] == [0.0] * 9    # 没播采样点: 速度档全 0 (直方图如实)


def test_trip_stats_filter_by_car(auth, db):
    """多车: 缺省并集, ?car_id=N 只数那台 (电耗各按自己车的定标)。"""
    _seed_two_drives(db)                    # 车1 42.5km/25.7kWh, 车2 100km/20.0kWh
    s = auth.get("/tesla/trips/api/stats/summary").json()
    assert s["trips"] == 2 and s["km"] == 142.5
    s1 = auth.get("/tesla/trips/api/stats/summary?car_id=1").json()
    assert s1["trips"] == 1 and s1["km"] == 42.5 and s1["kwh"] == 25.7
    s2 = auth.get("/tesla/trips/api/stats/summary?car_id=2").json()
    assert s2["trips"] == 1 and s2["km"] == 100.0 and s2["kwh"] == 20.0
    # 未知车辆 → 空结果 (宽容口径, 不 4xx)
    assert auth.get("/tesla/trips/api/stats/summary?car_id=99").json()[
        "trips"] == 0


def test_trip_stats_empty_db(auth, db):
    """空库: 各档全 0 / 空列表 / 汇总 None, 页面图表落"暂无数据"。"""
    assert auth.get("/tesla/trips/api/stats/summary").json() == {
        "trips": 0, "km": 0.0, "duration_min": 0, "kwh": None,
        "wh_per_km": None, "speed_max": None,
        "first_date": None, "last_date": None}
    assert auth.get("/tesla/trips/api/stats/monthly").json() == []
    assert auth.get("/tesla/trips/api/stats/locations").json() == []
    assert auth.get("/tesla/trips/api/stats/drivers").json() == []
    d = auth.get("/tesla/trips/api/stats/dimensions").json()
    assert d["by_hour"] == [0] * 12
    assert d["by_dist"] == [0] * 10 and d["by_dur"] == [0] * 10
    assert d["by_spd"] == [0.0] * 9 and d["by_wh"] == [0] * 10
