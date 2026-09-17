"""足迹轨迹查询测试: 降采样, 司机过滤, 未完成排除, 日期区间。
拆自 test_map.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime, timedelta


from app.tesla.models import Driver, TripDriver
from tests.seed_factories import (seed_addresses, seed_drive, seed_position,
                            seed_positions)
from tests.map_seed_helpers import _two_point_drive

def test_tracks_downsamples_to_40_per_drive(auth, db):
    """全量轨迹每条 ~40 点: 窗口下采样首末点必留。"""
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=9, start_date=start, end_date=start + timedelta(hours=2),
               distance=50.0, duration_min=120)
    seed_positions(db, 9, [{"date": start + timedelta(seconds=18 * i),
                            "longitude": 114.0 + i * 0.0001, "latitude": 22.5}
                           for i in range(400)])
    d = auth.get("/tesla/map/api/tracks").json()
    assert d["count"] == 1
    assert len(d["tracks"][0]["pts"]) == 41       # 400/40=10 → i%10 + 首末
    assert d["tracks"][0]["pts"][0][0] == 114.0
    assert d["tracks"][0]["pts"][-1][0] == round(114.0 + 399 * 0.0001, 5)


def test_tracks_filter_by_driver(auth, db, owndb):
    """轨迹/汇总按驾驶员筛选, 口径与行程页一致: 显式标注的 + 默认驾驶员时
    未标注的; 驾驶员不存在 → 空。"""
    start = datetime(2026, 9, 1, 2, 0)
    for did in (11, 12, 13):
        seed_drive(db, id=did, start_date=start + timedelta(hours=did),
                   end_date=start + timedelta(hours=did, minutes=10),
                   distance=5.0, duration_min=10)
        seed_positions(db, did, [
            {"date": start + timedelta(hours=did),
             "longitude": 114.0, "latitude": 22.5},
            {"date": start + timedelta(hours=did, minutes=10),
             "longitude": 114.01, "latitude": 22.51}])
    owndb.add(Driver(id=1, name="大导子", is_default=True))
    owndb.add(Driver(id=2, name="小导子"))
    owndb.add(TripDriver(drive_id=11, driver_id=2))
    owndb.commit()

    assert auth.get("/tesla/map/api/tracks").json()["count"] == 3      # 全部
    t = auth.get("/tesla/map/api/tracks",
                 params={"driver_id": 2}).json()                        # 标注小导子
    assert [x["id"] for x in t["tracks"]] == [11]
    t = auth.get("/tesla/map/api/tracks",
                 params={"driver_id": 1}).json()                        # 默认 → 含未标注
    assert sorted(x["id"] for x in t["tracks"]) == [12, 13]
    assert auth.get("/tesla/map/api/tracks",
                    params={"driver_id": 99}).json()["count"] == 0      # 不存在 → 空
    s = auth.get("/tesla/map/api/summary", params={"driver_id": 2}).json()
    assert s["drives"] == 1 and s["distance_km"] == 5.0
    s = auth.get("/tesla/map/api/summary", params={"driver_id": 1}).json()
    assert s["drives"] == 2 and s["distance_km"] == 10.0


def test_tracks_excludes_unfinished_and_no_distance(auth, db):
    """distance 为空的行程 (含未关闭) 不进全量轨迹, 与旧 TRACKS_SQL 口径一致。"""
    seed_addresses(db)
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=1, start_date=start, end_date=start + timedelta(hours=1))
    seed_position(db, 1, id=None, date=start, longitude=114.0, latitude=22.5)
    seed_position(db, 1, id=None, date=start + timedelta(minutes=5),
                  longitude=114.1, latitude=22.5)
    seed_drive(db, id=2, start_date=start + timedelta(hours=2),
               end_date=start + timedelta(hours=3), distance=None)
    d = auth.get("/tesla/map/api/tracks").json()
    assert [t["id"] for t in d["tracks"]] == [1]


def test_tracks_date_filtering(auth, db):
    for i, start in enumerate((datetime(2026, 1, 15, 2, 0),
                               datetime(2026, 8, 1, 2, 0),
                               datetime(2026, 9, 1, 2, 0))):
        _two_point_drive(db, i + 1, start)
    base = "/tesla/map/api/tracks"
    assert [t["id"] for t in auth.get(base).json()["tracks"]] == [1, 2, 3]

    def ids(qs):
        return [t["id"] for t in auth.get(base + qs).json()["tracks"]]

    assert ids("?from=2026-07-01") == [2, 3]
    assert ids("?to=2026-08-31") == [1, 2]
    assert ids("?from=2026-07-01&to=2026-08-31") == [2]


def test_tracks_rejects_bad_date(auth, db):
    """坏日期参数 (如前端 NaN bug 产生的 "NaN-NaN-NaN") 必须 400, 不能打穿到数据库。"""
    _two_point_drive(db, 1, datetime(2026, 9, 1, 2, 0))
    assert auth.get("/tesla/map/api/tracks?from=NaN-NaN-NaN").status_code == 400
    assert auth.get("/tesla/map/api/tracks?to=2026-13-99").status_code == 400  # 月日越界
    assert auth.get("/tesla/map/api/tracks?from=abc").status_code == 400


def test_disk_cache_corrupt_file_is_ignored(auth, db, tmp_path):
    """磁盘缓存损坏 (非法 JSON) 当作没有, 全量重建不报错。"""
    (tmp_path / "tracks_cache.json").write_text("not-json{{{")
    _two_point_drive(db, 4, datetime(2026, 9, 1, 2, 0))
    d = auth.get("/tesla/map/api/tracks").json()
    assert d["count"] == 1
