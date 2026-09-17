"""行程轨迹测试: 单条全精度与降采样, 多选合并 (拼接/去重/校验)。
拆自 test_trips.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime, timedelta
from app.tesla import repository
from app.tesla.models import Address
from tests.seed_factories import seed_addresses, seed_drive, seed_position, seed_positions


# ---------------------------------------------------------------- 轨迹
def test_trip_track_full_resolution_with_speed(auth, db):
    seed_addresses(db)
    seed_drive(db, id=7)
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_position(db, 7, id=None, date=t0, longitude=114.05, latitude=22.55,
                  speed=30.0, power=45000.0)
    seed_position(db, 7, id=None,
                  date=t0 + timedelta(minutes=72, seconds=1),
                  longitude=114.06, latitude=22.56, speed=None, power=None)
    r = auth.get("/tesla/trips/api/7/track")
    assert r.status_code == 200
    # 每点 [lng, lat, speed, power_W]; 速度缺失按 0 (停车), power 可为 null;
    # ts 是相对起点的秒偏移 (播放动画里算"已行驶时长"和平均功耗)
    assert r.json() == {"id": 7,
                        "pts": [[114.05, 22.55, 30.0, 45000.0],
                                [114.06, 22.56, 0, None]],
                        "ts": [0, 4321]}


def test_trip_track_downsamples_beyond_5000(auth, db):
    """5000 点上限: 超长轨迹等间隔抽取 (首末点必留)。"""
    seed_addresses(db)
    seed_drive(db, id=7, start_date=datetime(2026, 9, 10, 0, 32),
               end_date=datetime(2026, 9, 10, 3, 0))
    t0 = datetime(2026, 9, 10, 0, 32)
    seed_positions(db, 7, [{"date": t0 + timedelta(seconds=i),
                            "longitude": 114.0 + i * 1e-5, "latitude": 22.5}
                           for i in range(10001)])
    d = auth.get("/tesla/trips/api/7/track").json()
    assert 5000 <= len(d["pts"]) <= 5002     # stride=2 → ~5001 点
    assert d["pts"][0][0] == 114.0
    assert d["pts"][-1][0] == round(114.0 + 10000 * 1e-5, 5)
    assert d["ts"][0] == 0 and d["ts"][-1] == 10000


def test_trip_track_404_when_no_points(auth, db):
    seed_addresses(db)
    seed_drive(db, id=999)                       # 0 点
    r = auth.get("/tesla/trips/api/999/track")
    assert r.status_code == 404
    seed_position(db, 999, id=None)              # 只剩 1 个点画不了线, 也算没有
    r = auth.get("/tesla/trips/api/999/track")
    assert r.status_code == 404
    assert "没有轨迹数据" in r.json()["detail"]


# ---------------------------------------------------------------- 合并轨迹 (多选连续行程)
def test_merged_track_stitches_and_skips_parking(auth, db):
    """多段行程拼一条轨迹: pts 按时间串联, ts 是"累计行驶秒" (行程间停驶剔除),
    汇总 = 首段起/末段终 + 各项求和 (前端弹层播放/统计照常)。"""
    db.add(Address(id=3, name="m", city="c", display_name="中途点"))
    db.commit()
    seed_addresses(db)
    t = datetime(2026, 9, 10, 0, 32)             # 北京时间 08:32
    seed_drive(db, id=11, distance=42.5, duration_min=72, speed_max=118,
               start_address_id=1, end_address_id=3, start_date=t,
               end_date=t + timedelta(minutes=72))
    seed_position(db, 11, id=None, date=t, longitude=114.05, latitude=22.55,
                  speed=30.0, power=45000.0)
    seed_position(db, 11, id=None, date=t + timedelta(minutes=10),
                  longitude=114.06, latitude=22.56, speed=40.0, power=None)
    # 停驶 2h50m 后的第二段 (这段间隔不应计入 ts)
    seed_drive(db, id=12, distance=10.04, duration_min=10, speed_max=96,
               start_address_id=3, end_address_id=2,
               start_date=t + timedelta(hours=3),
               end_date=t + timedelta(hours=3, minutes=10))
    seed_position(db, 12, id=None, date=t + timedelta(hours=3),
                  longitude=114.07, latitude=22.57, speed=50.0, power=30000.0)
    seed_position(db, 12, id=None, date=t + timedelta(hours=3, minutes=10),
                  longitude=114.08, latitude=22.58, speed=None, power=None)
    r = auth.get("/tesla/trips/api/merged?ids=12,11")   # 乱序传入
    assert r.status_code == 200
    d = r.json()
    assert d["ids"] == [11, 12] and d["n"] == 2
    assert d["pts"] == [[114.05, 22.55, 30.0, 45000.0],
                        [114.06, 22.56, 40.0, None],
                        [114.07, 22.57, 50.0, 30000.0],
                        [114.08, 22.58, 0, None]]
    # 第二段从上一段末尾继续累计: 中间 2h50m 停驶不进 ts
    assert d["ts"] == [0, 600, 600, 1200]
    # 每段起点下标 (前端按段做断档识别, 不混用全局阈值)
    assert d["seg_starts"] == [0, 2]
    # 汇总: 首段起 / 末段终, 里程/时长求和, 最高速取 max
    assert d["km"] == 52.54 and d["min"] == 82 and d["speed_max"] == 118
    assert d["date"] == "2026-09-10"
    assert d["start"] == "2026-09-10 08:32" and d["end"] == "2026-09-10 11:42"
    assert d["from"] == "广东省深圳市龙岗区坂田街道"
    assert d["to"] == "广东省东莞市长安镇"


def test_merged_track_downsamples_each_segment(auth, db):
    """每段预算按原始点数占比分配 (总预算 12000), 短段仍有 200 保底。"""
    seed_addresses(db)
    t = datetime(2026, 9, 10, 0, 32)
    for drive_id in (11, 12):
        seed_drive(db, id=drive_id, distance=5.0, duration_min=5, speed_max=50,
                   start_date=t + timedelta(hours=drive_id * 3),
                   end_date=t + timedelta(hours=drive_id * 3, minutes=10))
        seed_positions(db, drive_id,
                       [{"date": t + timedelta(hours=drive_id * 3, seconds=i),
                         "longitude": 114.0 + i * 1e-5, "latitude": 22.5}
                        for i in range(400)])
    d = auth.get("/tesla/trips/api/merged?ids=11,12").json()
    # 4000/2 = 2000/段 → stride=1 → 全保留
    assert len(d["pts"]) == 800


def test_merged_track_dedupes_ids(auth, db):
    """重复 id 去重, 仍然只算一段。"""
    seed_addresses(db)
    t = datetime(2026, 9, 10, 0, 32)
    for drive_id in (11, 12):
        seed_drive(db, id=drive_id, start_date=t + timedelta(hours=drive_id),
                   end_date=t + timedelta(hours=drive_id, minutes=10))
        seed_position(db, drive_id, id=None,
                      date=t + timedelta(hours=drive_id), longitude=114.0,
                      latitude=22.5, speed=10.0, power=None)
        seed_position(db, drive_id, id=None,
                      date=t + timedelta(hours=drive_id, minutes=10),
                      longitude=114.1, latitude=22.5, speed=10.0, power=None)
    r = auth.get("/tesla/trips/api/merged?ids=11,12,11,12")
    assert r.status_code == 200
    assert r.json()["ids"] == [11, 12]        # 去重后 2 个
    assert r.json()["n"] == 2


def test_merged_track_validation_and_404(auth, monkeypatch):
    def never(*_args):
        raise AssertionError("参数非法不应查库")

    monkeypatch.setattr(repository, "merged_track", never)
    assert auth.get("/tesla/trips/api/merged?ids=abc").status_code == 400
    assert auth.get("/tesla/trips/api/merged?ids=1").status_code == 400
    assert auth.get("/tesla/trips/api/merged?ids=" +
                    ",".join(str(i) for i in range(101))).status_code == 400
    # 任一行程不存在/未完成 → 404
    def raise_not_found(*_args):
        raise repository.NotFound("包含不存在或未完成的行程")

    monkeypatch.setattr(repository, "merged_track", raise_not_found)
    r = auth.get("/tesla/trips/api/merged?ids=1,2")
    assert r.status_code == 404
    assert "不存在或未完成" in r.json()["detail"]


def test_merged_track_404_when_no_points(auth, db):
    """行程都在但没有轨迹点 → 404, 前端抹掉地址栏参数。"""
    seed_addresses(db)
    t = datetime(2026, 9, 10, 0, 32)
    seed_drive(db, id=1, start_date=t, end_date=t + timedelta(minutes=10))
    seed_drive(db, id=2, start_date=t + timedelta(hours=1),
               end_date=t + timedelta(hours=1, minutes=10))
    r = auth.get("/tesla/trips/api/merged?ids=1,2")
    assert r.status_code == 404
    assert "没有轨迹数据" in r.json()["detail"]
