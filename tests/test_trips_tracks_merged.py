"""多选合并轨迹测试 (连续行程拼一条): pts 按时间串联, ts 是累计行驶秒
(行程间停驶剔除), 段界/段首时刻随载荷下发, 重复 id 去重, 参数校验与
404 口径。2026-09-26 拆自 test_trips_tracks.py (那边满 200 行硬上限;
带洞种子 _seed_track_with_hole 留在那边, 这边借用来种带洞的段)。"""
import json
from datetime import datetime, timedelta

from app.tesla import repository
from app.tesla.models import Address
from tests.seed_factories import (seed_addresses, seed_drive, seed_position,
                                  seed_positions)
from tests.test_trips_tracks import _seed_track_with_hole


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
    assert d["pts"] == [[114.05, 22.55, 30.0, 45000.0, None],
                        [114.06, 22.56, 40.0, None, None],
                        [114.07, 22.57, 50.0, 30000.0, None],
                        [114.08, 22.58, 0, None, None]]
    # 第二段从上一段末尾继续累计: 中间 2h50m 停驶不进 ts
    assert d["ts"] == [0, 600, 600, 1200]
    # 每段起点下标 (前端按段做断档识别, 不混用全局阈值)
    assert d["seg_starts"] == [0, 2]
    # 每段起始时刻 (本地 "YYYY-MM-DD HH:MM"): ts 是累计行驶秒, 客户端推不出
    # 各段墙钟日期 —— 播放中弹层标题随段切换显「第 x 段行程 · 年月日」
    # (2026-09-25 用户点名) 靠它; 流式版每行另带同源的 t0
    assert d["seg_t0s"] == ["2026-09-10 08:32", "2026-09-10 11:32"]
    # 汇总: 首段起 / 末段终, 里程/时长求和, 最高速取 max
    assert d["km"] == 52.54 and d["min"] == 82 and d["speed_max"] == 118
    assert d["date"] == "2026-09-10"
    assert d["start"] == "2026-09-10 08:32" and d["end"] == "2026-09-10 11:42"
    assert d["from"] == "广东省深圳市龙岗区坂田街道"
    assert d["to"] == "广东省东莞市长安镇"


def test_merged_track_gaps_carry_drive_id_and_offset(auth, db):
    """合并流的断档对带所属段 id (前端归档回传到段自己头上 —— 合并的
    it.id 是 "m:..." 字符串, 不带 did 存不进); 下标按已发段累计偏移
    (首段 0 起), 流式每行与整包同口径。"""
    a_raw, b_raw = _seed_track_with_hole(db, drive_id=11)
    # 第二段无洞, 头挨着第一段尾 (~10m): 段间无跳变不产生断档对
    t = datetime(2026, 9, 11, 0, 0)
    seed_drive(db, id=12, start_date=t, end_date=t + timedelta(minutes=5))
    seed_positions(db, 12, [{"date": t + timedelta(seconds=j),
                             "longitude": 114.0129 + j * 1e-4, "latitude": 22.5,
                             "speed": 30.0} for j in range(20)])
    d = auth.get("/tesla/trips/api/merged?ids=11,12").json()
    assert d["gaps"] == [[a_raw, b_raw, 11]]
    # 流式逐行同口径: 首段偏移 0, 第二段无洞
    r = auth.get("/tesla/trips/api/merged_stream?ids=11-12")
    segs = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert segs[1]["gaps"] == [[a_raw, b_raw, 11]]
    assert segs[2]["gaps"] == []


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
    # 任一行程不存在/未完成 → 404
    def raise_not_found(*_args):
        raise repository.NotFound("包含不存在或未完成的行程")

    monkeypatch.setattr(repository, "merged_track", raise_not_found)
    r = auth.get("/tesla/trips/api/merged?ids=1,2")
    assert r.status_code == 404
    assert "不存在或未完成" in r.json()["detail"]
    # 100 段上限已撤 (2026-09-25 用户点名): 101 个 id 照样过参数校验进到
    # 查库 (原先在这里断言 400, 撤上限时漏改)
    r = auth.get("/tesla/trips/api/merged?ids=" +
                 ",".join(str(i) for i in range(101)))
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
