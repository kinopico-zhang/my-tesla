"""行程能耗与过路费测试: 充电标定能耗, 过路费存取, 参数校验。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime, timedelta
from app.tesla.models import TripToll
from tests.seed_factories import seed_addresses, seed_charging, seed_drive, seed_position


def test_trip_consumption_from_charge_calibration(auth, db):
    """电耗 = 额定续航差 × 充电换算系数 (桩端口径): 列表/单条/合并三处同源;
    续航回弹夹 0, 里程不足 1km 不算平均。"""
    seed_addresses(db)
    # 充电记录定标: 30 kWh 换 200km 额定续航 → 0.15 kWh/km
    seed_charging(db, id=1, charge_energy_added=30.0,
                  start_rated_range_km=100.0, end_rated_range_km=300.0)
    t = datetime(2026, 9, 10, 0, 32)

    def drive(did, dist, s_rated, e_rated, with_pts=False):
        seed_drive(db, id=did, distance=dist, duration_min=60,
                   start_date=t + timedelta(hours=did),
                   end_date=t + timedelta(hours=did, minutes=60),
                   start_rated_range_km=s_rated, end_rated_range_km=e_rated)
        if with_pts:      # 合并轨迹需要位置点
            for k, lng in enumerate((114.1, 114.2)):
                seed_position(db, did, id=None,
                              date=t + timedelta(hours=did, minutes=10 * k),
                              longitude=lng, latitude=22.5, speed=10.0, power=None)

    drive(11, 80.0, 200.0, 100.0, with_pts=True)   # 15.0 kWh, 187.5 Wh/km
    drive(12, 30.0, 100.0, 80.0, with_pts=True)    # 3.0 kWh, 100 Wh/km
    drive(13, 50.0, 100.0, 110.0)                  # 续航回弹 → 夹 0
    drive(14, 0.4, 200.0, 198.0)                   # 里程 <1km → 平均 None

    by_id = {x["id"]: x
             for x in auth.get("/tesla/trips/api/sessions").json()["items"]}
    assert by_id[11]["kwh"] == 15.0 and by_id[11]["wh_per_km"] == 188.0
    assert by_id[12]["kwh"] == 3.0 and by_id[12]["wh_per_km"] == 100.0
    assert by_id[13]["kwh"] == 0.0 and by_id[13]["wh_per_km"] == 0.0
    assert by_id[14]["kwh"] == 0.3 and by_id[14]["wh_per_km"] is None

    one = auth.get("/tesla/trips/api/sessions/11").json()
    assert one["kwh"] == 15.0 and one["wh_per_km"] == 188.0

    merged = auth.get("/tesla/trips/api/merged?ids=11,12").json()
    assert merged["kwh"] == 18.0                       # 15.0 + 3.0
    assert merged["wh_per_km"] == round(18.0 / 110 * 1000)   # ≈164


def test_trip_toll_store_and_readback(auth, db, owndb):
    """高速费估价回传: 存自有库, 列表/单条回读; 重传覆盖; ¥0 也算有效结果。"""
    seed_addresses(db)
    seed_drive(db, id=1838)
    base = "/tesla/trips/api"

    r = auth.post(f"{base}/1838/toll", json={
        "tolls": 29.0, "toll_km": 40.2, "distance": 77863,
        "roads": [{"road": "G4京港澳高速", "tolls": 14.0},
                  {"road": "S15沈海高速广州支线", "tolls": 7.0}]})
    assert r.status_code == 200 and r.json()["ok"] is True
    it = auth.get(f"{base}/sessions/1838").json()
    assert it["toll"] == 29.0 and it["toll_km"] == 40.2
    lst = auth.get(f"{base}/sessions").json()["items"]
    assert lst[0]["toll"] == 29.0            # 列表同样带估价

    # 跨省长途: 规划里程 178km 也要收 (上限 1000km)
    r = auth.post(f"{base}/1838/toll", json={
        "tolls": 69.0, "toll_km": 114.4, "distance": 178478,
        "roads": [{"road": "G4京港澳高速", "tolls": 69.0}]})
    assert r.status_code == 200

    auth.post(f"{base}/1838/toll", json={
        "tolls": 0, "toll_km": 0, "distance": 12000, "roads": []})   # 重算覆盖
    it = auth.get(f"{base}/sessions/1838").json()
    assert it["toll"] == 0                   # ¥0 = 算过没走收费路, 不是没算

    row = owndb.query(TripToll).filter_by(drive_id=1838).one()   # 只存自有库一行
    assert row.distance == 12000 and "G4" in row.roads or row.roads == "[]"


def test_trip_toll_errors(auth, db):
    """行程不存在 → 404; 负数/越界估价 → 422 (pydantic 校验)。"""
    seed_addresses(db)
    seed_drive(db, id=1838)
    assert auth.post("/tesla/trips/api/9999/toll", json={
        "tolls": 1, "toll_km": 1, "distance": 1, "roads": []}).status_code == 404
    assert auth.post("/tesla/trips/api/1838/toll", json={
        "tolls": -5, "toll_km": 1, "distance": 1, "roads": []}).status_code == 422


def test_trip_driver_mark_errors(auth, db):
    """行程不存在 / 驾驶员不存在 → 404。"""
    assert auth.post("/tesla/trips/api/9999/driver",
                     json={"driver_id": 1}).status_code == 404
    seed_addresses(db)
    seed_drive(db, id=1838)
    r = auth.post("/tesla/trips/api/1838/driver", json={"driver_id": 77})
    assert r.status_code == 404
    assert "驾驶员不存在" in r.json()["detail"]
