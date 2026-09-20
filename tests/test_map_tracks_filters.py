"""足迹轨迹清单测试: 清单字段 (点数/驾驶员/车/日期), 未完成与单点排除,
汇总日期校验。(v4 起时间/车辆筛选按清单在客户端做, 不再按筛选请求。)"""
from datetime import datetime, timedelta

from app.tesla import tracks_cache
from app.tesla.models import Driver, TripDriver
from tests.seed_factories import (seed_addresses, seed_drive, seed_position)
from tests.map_seed_helpers import _two_point_drive


def test_manifest_carries_driver_car_date_and_count(auth, db, owndb):
    """清单行字段 id/n/d/c/t —— 客户端对账本地库与本地筛选的依据;
    驾驶员标注每次现算 (标/清立即反映), 汇总口径不变。"""
    start = datetime(2026, 9, 1, 2, 0)
    for did in (11, 12, 13):
        seed_drive(db, id=did, start_date=start + timedelta(hours=did),
                   end_date=start + timedelta(hours=did, minutes=10),
                   distance=5.0, duration_min=10)
        seed_position(db, did, id=None, date=start + timedelta(hours=did),
                      longitude=114.0, latitude=22.5)
        seed_position(db, did, id=None,
                      date=start + timedelta(hours=did, minutes=10),
                      longitude=114.01, latitude=22.51)
    owndb.add(Driver(id=1, name="大导子", is_default=True))
    owndb.add(Driver(id=2, name="小导子"))
    owndb.add(TripDriver(drive_id=11, driver_id=2))
    owndb.commit()

    m = auth.get("/tesla/map/api/tracks/manifest").json()
    assert m["v"] == tracks_cache.CACHE_VERSION
    rows = {t["id"]: t for t in m["tracks"]}
    assert len(rows) == 3
    assert rows[11]["d"] == 2                     # 标注小导子
    assert rows[12]["d"] is None                  # 未标注 (默认口径客户端自己兜)
    assert rows[11]["c"] == 1 and rows[11]["t"] == "2026-09-01"
    assert all(t["n"] == 2 for t in rows.values())
    # 汇总仍按驾驶员过滤 (服务端口径与行程页一致)
    s = auth.get("/tesla/map/api/summary", params={"driver_id": 2}).json()
    assert s["drives"] == 1 and s["distance_km"] == 5.0
    s = auth.get("/tesla/map/api/summary", params={"driver_id": 1}).json()
    assert s["drives"] == 2 and s["distance_km"] == 10.0
    s = auth.get("/tesla/map/api/summary", params={"driver_id": 99}).json()
    assert s["drives"] == 0


def test_tracks_excludes_unfinished_and_no_distance(auth, db):
    """distance 为空的行程 (含未关闭) 不进全量轨迹清单。"""
    seed_addresses(db)
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=1, start_date=start, end_date=start + timedelta(hours=1))
    seed_position(db, 1, id=None, date=start, longitude=114.0, latitude=22.5)
    seed_position(db, 1, id=None, date=start + timedelta(minutes=5),
                  longitude=114.1, latitude=22.5)
    seed_drive(db, id=2, start_date=start + timedelta(hours=2),
               end_date=start + timedelta(hours=3), distance=None)
    d = auth.get("/tesla/map/api/tracks/manifest").json()
    assert [t["id"] for t in d["tracks"]] == [1]


def test_tracks_drop_single_point_drives(auth, db):
    """少于 2 个点的行程不成轨迹, 不进清单 (没有可画的线)。"""
    _two_point_drive(db, 5, datetime(2026, 9, 1, 2, 0))
    seed_drive(db, id=6, start_date=datetime(2026, 9, 2, 2, 0),
               end_date=datetime(2026, 9, 2, 3, 0), distance=5.0)
    seed_position(db, 6, id=None, date=datetime(2026, 9, 2, 2, 0),
                  longitude=114.05, latitude=22.55)
    d = auth.get("/tesla/map/api/tracks/manifest").json()
    assert [t["id"] for t in d["tracks"]] == [5]


def test_summary_rejects_bad_date(auth, db):
    """坏日期参数 (如前端 NaN bug 产生的 "NaN-NaN-NaN") 必须 400, 不能
    打穿到数据库 (轨迹筛选已走客户端, 日期参数只剩汇总端点)。"""
    _two_point_drive(db, 1, datetime(2026, 9, 1, 2, 0))
    assert auth.get("/tesla/map/api/summary?from=NaN-NaN-NaN").status_code == 400
    assert auth.get("/tesla/map/api/summary?to=2026-13-99").status_code == 400  # 月日越界
    assert auth.get("/tesla/map/api/summary?from=abc").status_code == 400
