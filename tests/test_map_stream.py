"""全精度轨迹流测试: NDJSON 一行一条, 按 ids 取, 全精度无抽稀,
上限, gzip, 输入校验。(v4 起取代旧 /tracks/detail 视野内明细接口。)"""
import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import app.main as m
from tests.seed_factories import seed_drive, seed_position, seed_positions
from tests.map_seed_helpers import _two_point_drive

BASE = "/tesla/map/api/tracks/stream"


def _lines(r):
    return [json.loads(x) for x in r.text.splitlines()]


def test_stream_returns_ndjson_one_track_per_line(auth, db):
    _two_point_drive(db, 5, datetime(2026, 9, 1, 2, 0))
    _two_point_drive(db, 6, datetime(2026, 9, 2, 2, 0))
    r = auth.get(BASE, params={"ids": "6,5"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    # 一行一条, pts 扁平 [lng, lat, ...]; 缓存序 (日期升序) 与请求序无关
    assert _lines(r) == [
        {"id": 5, "car_id": 1, "date": "2026-09-01", "km": 12.3, "min": 25,
         "pts": [114.05, 22.55, 114.06, 22.56]},
        {"id": 6, "car_id": 1, "date": "2026-09-02", "km": 12.3, "min": 25,
         "pts": [114.05, 22.55, 114.06, 22.56]}]


def test_stream_full_precision_no_downsampling(auth, db):
    """全精度: 400 点一个不少 (旧粗轨迹接口每条抽到 ~40 点)。"""
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=7, start_date=start, end_date=start + timedelta(hours=2),
               distance=50.0, duration_min=120)
    seed_positions(db, 7, [{"date": start + timedelta(seconds=18 * i),
                            "longitude": 114.0 + i * 0.0001, "latitude": 22.5}
                           for i in range(400)])
    track = _lines(auth.get(BASE, params={"ids": "7"}))[0]
    assert len(track["pts"]) == 800                  # 扁平: 400 点 × 2
    assert track["pts"][0] == 114.0 and track["pts"][1] == 22.5
    assert track["pts"][-2] == round(114.0 + 399 * 0.0001, 5)
    assert track["pts"][-1] == 22.5


def test_stream_skips_missing_and_single_point(auth, db):
    """id 不存在不报错; 单点行程不成轨迹 (清单里也不会有它)。"""
    _two_point_drive(db, 5, datetime(2026, 9, 1, 2, 0))
    seed_drive(db, id=8, start_date=datetime(2026, 9, 2, 2, 0),
               end_date=datetime(2026, 9, 2, 3, 0), distance=5.0)
    seed_position(db, 8, id=None, date=datetime(2026, 9, 2, 2, 0),
                  longitude=114.05, latitude=22.55)
    assert [t["id"] for t in _lines(
        auth.get(BASE, params={"ids": "5,8,99"}))] == [5]


def test_stream_gzipped_when_large(auth, db):
    """大响应走 gzip, 手机端省流量 (全精度轨迹动辄几 MB)。"""
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=7, start_date=start, end_date=start + timedelta(hours=5),
               distance=30.0, duration_min=300)
    seed_positions(db, 7, [{"date": start + timedelta(seconds=60 * i),
                            "longitude": 114.0 + i * 0.00001, "latitude": 22.5}
                           for i in range(300)])
    r = auth.get(BASE, params={"ids": "7"},
                 headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert len(_lines(r)) == 1


def test_stream_rejects_bad_input(auth, db):
    # ids 非数字 → 400
    assert auth.get(BASE, params={"ids": "abc"}).status_code == 400
    assert auth.get(BASE, params={"ids": "1,x"}).status_code == 400
    # 超 200 条 → 400 (防误把全量塞进一个请求); 恰好 200 条 → 放行
    assert auth.get(BASE, params={
        "ids": ",".join(str(i) for i in range(201))}).status_code == 400
    assert auth.get(BASE, params={
        "ids": ",".join(str(i) for i in range(200))}).status_code == 200
    # 空 ids → 200 空流 (客户端没得下时不必报错)
    r = auth.get(BASE, params={"ids": ""})
    assert r.status_code == 200 and r.text == ""


def test_stream_requires_auth():
    assert TestClient(m.app).get(
        BASE, params={"ids": "1"}).status_code == 401
