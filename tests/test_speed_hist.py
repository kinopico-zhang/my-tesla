"""行车速度直方图测试 (2026-09-27 用户点名「车速分布, 不是最大车速分布」
「纵坐标是 km」): /stats/dimensions 的 by_spd = 各速度段行驶里程 ——
每点采样速度 × 距上一点的间隔 (滞后积分: 每程第一点只起头; 间隔超
60s 的整段丢, 断连缺口不猜; 同秒重复点 0 权重), speed_hist_cache 两级
记账 (内存 + 磁盘 JSONL, 缺哪条补哪条的增量, 不追 id 水位 —— 多车行程
id 交错)。by_spd_kwh = 各速度段行车电量 (2026-09-30 用户点名「电耗分布
横纵坐标不对, 横坐标应该是速度, 纵坐标是平均电耗」: 功率 kW 同口径积分,
负功率 = 动能回收如实负; power 缺采样只积里程), 缓存 v2 起每行 {id, b, w}。

种子数学: 间隔 36s → 每点里程 = 速度 × 36/3600 = 速度 × 0.01 km,
速度取整十让档值落在干净的小数上。"""
import json
from datetime import datetime

from app.tesla import speed_hist_cache
from tests.car_seed_helpers import _seed_two_cars
from tests.seed_factories import seed_drive, seed_positions
from tests.test_trip_stats import _seed_stats

DIM = "/tesla/trips/api/stats/dimensions"


def _seed_pts(db, drive_id, rows):
    """采样点批次: 补经纬度必填默认 (直方图只吃 date/speed, 坐标无关)。"""
    seed_positions(db, drive_id, [
        {"longitude": 114.05, "latitude": 22.55, **r} for r in rows])


def _spd_positions(db):
    """四条行程的采样点 (36s 间隔, 速度 × 0.01 = km, 按滞后积分):
    A: 100 巡航 ×2 → 2.0 km (100-120 档) + 165 ×2 → 3.3 km (≥160 收尾档)
    B: 3600s 缺口整段丢 + 同秒重复点 (0) + 36s 续采 0.9 → 0.9 km (80-100 档)
    C: 15 龟速 ×2 → 0.3 km (<20 档)
    D: 155 ×2 → 3.1 km (140-160 档)"""
    _seed_pts(db, 1, [
        {"date": datetime(2026, 9, 10, 0, 32, 0), "speed": 100.0},
        {"date": datetime(2026, 9, 10, 0, 32, 36), "speed": 100.0},
        {"date": datetime(2026, 9, 10, 0, 33, 12), "speed": 100.0},
        {"date": datetime(2026, 9, 10, 0, 33, 48), "speed": 165.0},
        {"date": datetime(2026, 9, 10, 0, 34, 24), "speed": 165.0},
    ])
    _seed_pts(db, 2, [
        {"date": datetime(2026, 9, 11, 14, 0, 0), "speed": 90.0},
        {"date": datetime(2026, 9, 11, 15, 0, 0), "speed": 90.0},
        {"date": datetime(2026, 9, 11, 15, 0, 0), "speed": 90.0},
        {"date": datetime(2026, 9, 11, 15, 0, 36), "speed": 90.0},
    ])
    _seed_pts(db, 3, [
        {"date": datetime(2026, 9, 12, 3, 30, 0), "speed": 15.0},
        {"date": datetime(2026, 9, 12, 3, 30, 36), "speed": 15.0},
        {"date": datetime(2026, 9, 12, 3, 31, 12), "speed": 15.0},
    ])
    _seed_pts(db, 4, [
        {"date": datetime(2026, 8, 5, 5, 0, 0), "speed": 155.0},
        {"date": datetime(2026, 8, 5, 5, 0, 36), "speed": 155.0},
        {"date": datetime(2026, 8, 5, 5, 1, 12), "speed": 155.0},
    ])


def test_speed_bins_endpoint(auth, db):
    """端点口径: by_spd = 各速度段行驶里程 (不是每程最高车速的任何口径);
    每程第一点只起头不积分, 没采样点的行程如实 0。"""
    _seed_stats(db)
    _spd_positions(db)
    d = auth.get(DIM).json()
    assert d["by_spd"] == [0.3, 0, 0, 0, 0.9, 2.0, 0, 3.1, 3.3]
    assert d["by_spd_kwh"] == [0.0] * 9    # 没播功率: 电量如实 0 (里程照积)


def test_speed_bins_car_filter(auth, db):
    """多车: 采样按行程归属各车, ?car_id=N 只积分那台。"""
    _seed_two_cars(db)
    seed_drive(db, id=1, car_id=1)
    _seed_pts(db, 1, [
        {"date": datetime(2026, 9, 10, 0, 32, 0), "speed": 110.0},
        {"date": datetime(2026, 9, 10, 0, 32, 36), "speed": 110.0},
    ])
    seed_drive(db, id=2, car_id=2, start_date=datetime(2026, 9, 11, 5, 0),
               end_date=datetime(2026, 9, 11, 6, 40), distance=100.0,
               duration_min=100)
    _seed_pts(db, 2, [
        {"car_id": 2, "date": datetime(2026, 9, 11, 5, 0, 0), "speed": 90.0},
        {"car_id": 2, "date": datetime(2026, 9, 11, 5, 0, 36), "speed": 90.0},
    ])
    assert auth.get(DIM).json()["by_spd"] == [0, 0, 0, 0, 0.9, 1.1, 0, 0, 0]
    assert auth.get(DIM + "?car_id=1").json()["by_spd"][5] == 1.1
    assert auth.get(DIM + "?car_id=2").json()["by_spd"][4] == 0.9


def test_speed_hist_cold_scan_writes_disk(auth, db, tmp_path):
    """冷启: 现场积分 + 落盘 (JSONL: 首行头 {v}, 之后一行一条 {id, b, w})。"""
    _seed_stats(db)
    _spd_positions(db)
    assert len(auth.get(DIM).json()["by_spd"]) == 9
    lines = (tmp_path / "speed_hist_cache.json").read_text(
        encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"v": speed_hist_cache.CACHE_VERSION}
    assert len(lines) == 5                    # 头行 + 四条行程
    rec = {json.loads(x)["id"]: json.loads(x) for x in lines[1:]}
    assert rec[1]["b"] == [0, 0, 0, 0, 0, 2.0, 0, 0, 3.3]
    assert rec[2]["b"] == [0, 0, 0, 0, 0.9, 0, 0, 0, 0]
    assert rec[1]["w"] == [0, 0, 0, 0, 0, 0, 0, 0, 0]   # 没播功率: 电量 0


def test_speed_hist_warm_memory_skips_scan(auth, db, monkeypatch):
    _seed_stats(db)
    _spd_positions(db)
    assert auth.get(DIM).status_code == 200   # 预热内存缓存

    def boom(*_args):
        raise AssertionError("缓存已最新, 不应现场积分")

    monkeypatch.setattr(speed_hist_cache, "_scan", boom)
    assert auth.get(DIM).json()["by_spd"] == [0.3, 0, 0, 0, 0.9, 2.0, 0, 3.1, 3.3]


def test_speed_hist_disk_cache_without_scan(auth, db, tmp_path, monkeypatch):
    """磁盘缓存直接复用 (不做现场积分); 行程没采样点 → 缺哪条补哪条,
    这里盘上已覆盖全部行程。"""
    (tmp_path / "speed_hist_cache.json").write_text(json.dumps(
        {"v": speed_hist_cache.CACHE_VERSION}) + "\n"
        + json.dumps({"id": 1, "b": [0, 0, 0, 0, 0, 7.7, 0, 0, 0],
                      "w": [0, 0, 0, 0, 0, 1.5, 0, 0, 0]}) + "\n")
    seed_drive(db, id=1)

    def boom(*_args):
        raise AssertionError("磁盘缓存已最新, 不应现场积分")

    monkeypatch.setattr(speed_hist_cache, "_scan", boom)
    assert auth.get(DIM).json()["by_spd"] == [0, 0, 0, 0, 0, 7.7, 0, 0, 0]
    assert auth.get(DIM).json()["by_spd_kwh"] == [0, 0, 0, 0, 0, 1.5, 0, 0, 0]


def test_speed_hist_old_version_rebuilds(auth, db, tmp_path, monkeypatch):
    """旧版本盘缓存整册作废全量重建, 不能复用。"""
    (tmp_path / "speed_hist_cache.json").write_text(json.dumps(
        {"v": 0, "1": [9.9] * 9}))            # 版本不符
    _seed_stats(db)
    real_scan = speed_hist_cache._scan
    seen = {}

    def spy(session, ids):
        seen["ids"] = ids
        return real_scan(session, ids)

    monkeypatch.setattr(speed_hist_cache, "_scan", spy)
    assert auth.get(DIM).json()["by_spd"] == [0.0] * 9   # 无采样点
    assert sorted(seen["ids"]) == [1, 2, 3, 4]           # 无视盘缓存, 全量重建


def test_speed_hist_incremental_missing_only(auth, db, monkeypatch):
    """增量 = 缺哪条补哪条: 已记账的四条不重扫, 新行程只扫它自己。"""
    _seed_stats(db)
    _spd_positions(db)
    assert auth.get(DIM).status_code == 200
    seed_drive(db, id=5, start_date=datetime(2026, 9, 13, 1, 0),
               end_date=datetime(2026, 9, 13, 1, 30), distance=30.0,
               duration_min=30)
    _seed_pts(db, 5, [
        {"date": datetime(2026, 9, 13, 1, 0, 0), "speed": 130.0},
        {"date": datetime(2026, 9, 13, 1, 0, 36), "speed": 130.0},
    ])
    real_scan = speed_hist_cache._scan
    seen = {}

    def spy(session, ids):
        seen["ids"] = ids
        return real_scan(session, ids)

    monkeypatch.setattr(speed_hist_cache, "_scan", spy)
    assert auth.get(DIM).json()["by_spd"] == [0.3, 0, 0, 0, 0.9, 2.0, 1.3, 3.1, 3.3]
    assert seen["ids"] == [5]


def test_speed_bins_kwh_power_integration(auth, db):
    """各速度段电量 (by_spd_kwh): 功率 kW × 间隔积分, 与里程同速度档同
    滞后口径 —— 间隔归属后点, 首点是锚不积 (里程侧同款); 含动能回收
    (负功率如实负, 平均电耗才会出现负段); power 缺采样的点只积里程不积
    电量。36s 间隔 → 每点电量 = 功率 × 0.01 kWh: 100 km/h 三点中首点
    是锚, 20 kW 只在第 2 点积一段 → 0.2 kWh, 第 3 点功率缺采样只积
    里程; 40 km/h (40-60 档) -10 kW ×2 → -0.2 kWh (下坡回收多于耗电)。"""
    _seed_stats(db)
    _seed_pts(db, 1, [
        {"date": datetime(2026, 9, 10, 0, 32, 0), "speed": 100.0, "power": 20.0},
        {"date": datetime(2026, 9, 10, 0, 32, 36), "speed": 100.0, "power": 20.0},
        {"date": datetime(2026, 9, 10, 0, 33, 12), "speed": 100.0},   # 功率缺采样
        {"date": datetime(2026, 9, 10, 0, 33, 48), "speed": 40.0, "power": -10.0},
        {"date": datetime(2026, 9, 10, 0, 34, 24), "speed": 40.0, "power": -10.0},
    ])
    d = auth.get(DIM).json()
    assert d["by_spd"] == [0, 0, 0.8, 0, 0, 2.0, 0, 0, 0]
    assert d["by_spd_kwh"] == [0, 0, -0.2, 0, 0, 0.2, 0, 0, 0]


def test_speed_hist_corrupt_file_ignored(auth, db, tmp_path):
    """磁盘缓存损坏当作没有, 全量重建不报错。"""
    (tmp_path / "speed_hist_cache.json").write_text("not-json{{{")
    seed_drive(db, id=1)
    assert auth.get(DIM).json()["by_spd"] == [0.0] * 9
