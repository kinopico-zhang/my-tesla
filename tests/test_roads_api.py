"""走过之路 API 测试: 清单的 s/rn/m/rv/rd/rt 字段 (含 guess=3) / roads 流
(NDJSON 只回有几何的行, 上限与校验) / tick 踢醒 worker。"""
import json
from datetime import datetime

from fastapi.testclient import TestClient

import app.main as m
from app.tesla.repository.map_roads import road_row, save_road
from app.tesla.roads_fit import ROAD_FIT_V
from tests.map_seed_helpers import _two_point_drive

MANIFEST = "/tesla/map/api/tracks/manifest"
STREAM = "/tesla/map/api/roads/stream"
TICK = "/tesla/map/api/roads/tick"


def _row(owndb, drive_id, status, pts, n, km, err="", v=ROAD_FIT_V,
         gaps=None):
    save_road(owndb, road_row(drive_id, status, v, pts, n, km, err, gaps))


def _seed(db, drive_id, day):
    _two_point_drive(db, drive_id, datetime(2026, 9, day, 2, 0))


# ---------------------------------------------------------------- 清单
def test_manifest_road_fields(auth, db, owndb):
    """s=0 未拟合 / 1 ok / 2 failed|skip / 3 guess (可能走过, rn 照发);
    rd/rt=进度; 旧算法版本 (v 不符) 的行不算数。"""
    _seed(db, 5, 1)   # ok 行
    _row(owndb, 5, "ok", [114.0, 22.5, 114.01, 22.5], 2, 1.2)
    _seed(db, 6, 2)   # 没拟合过
    _seed(db, 7, 3)   # 拟合失败 (占位行, 同 v 不再试)
    _row(owndb, 7, "failed", [], 0, 0.0, "grab_fail")
    _seed(db, 9, 5)   # 可能走过 (对账不过/全批失败, 几何保留)
    _row(owndb, 9, "guess", [114.0, 22.5, 114.01, 22.5], 2, 1.1,
         "km_mismatch", gaps=[[0, 1]])
    _seed(db, 8, 4)   # 旧算法版本的行: 不算数
    _row(owndb, 8, "ok", [114.0, 22.5, 114.01, 22.5], 2, 1.2, v=0)

    man = auth.get(MANIFEST).json()
    rows = {t["id"]: t for t in man["tracks"]}
    assert man["rv"] == ROAD_FIT_V
    assert man["rd"] == 3 and man["rt"] == 5      # ok + failed + guess 算已处理
    assert (rows[5]["s"], rows[5]["rn"], rows[5]["m"]) == (1, 2, 25)
    assert (rows[6]["s"], rows[6]["rn"]) == (0, 0)
    assert (rows[7]["s"], rows[7]["rn"]) == (2, 0)
    assert (rows[9]["s"], rows[9]["rn"]) == (3, 2)   # guess 也有几何可下
    assert (rows[8]["s"], rows[8]["rn"]) == (0, 0)    # 旧 v 不算


# ---------------------------------------------------------------- 流
def test_roads_stream_ok_and_guess_rows(auth, db, owndb):
    """回有几何的行 (ok 证实 + guess 推断, 带 g 区间); failed/skip 没有
    路可画不发; 一行一条 NDJSON。"""
    _seed(db, 5, 1)
    _row(owndb, 5, "ok", [114.0, 22.5, 114.01, 22.5], 2, 1.2)
    _seed(db, 7, 3)
    _row(owndb, 7, "failed", [], 0, 0.0, "grab_fail")
    _seed(db, 9, 5)
    _row(owndb, 9, "guess", [114.0, 22.5, 114.01, 22.5], 2, 1.1,
         "km_mismatch", gaps=[[0, 1]])

    r = auth.get(STREAM, params={"ids": "7,5,9"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert [json.loads(x) for x in r.text.splitlines()] == [
        {"id": 5, "n": 2, "km": 1.2, "pts": [114.0, 22.5, 114.01, 22.5],
         "g": []},
        {"id": 9, "n": 2, "km": 1.1, "pts": [114.0, 22.5, 114.01, 22.5],
         "g": [[0, 1]]}]


def test_roads_stream_missing_id_empty(auth, db):
    """id 不存在 / 空 ids → 200 空流 (客户端没得下时不必报错)。"""
    _seed(db, 5, 1)
    assert auth.get(STREAM, params={"ids": "99"}).text == ""
    r = auth.get(STREAM, params={"ids": ""})
    assert r.status_code == 200 and r.text == ""


def test_roads_stream_validation(auth, db):
    assert auth.get(STREAM, params={"ids": "abc"}).status_code == 400
    assert auth.get(STREAM, params={"ids": "1,x"}).status_code == 400
    assert auth.get(STREAM, params={
        "ids": ",".join(str(i) for i in range(201))}).status_code == 400
    assert auth.get(STREAM, params={
        "ids": ",".join(str(i) for i in range(200))}).status_code == 200


def test_roads_endpoints_require_auth():
    assert TestClient(m.app).get(STREAM, params={"ids": "1"}).status_code == 401
    assert TestClient(m.app).get(MANIFEST).status_code == 401


# ---------------------------------------------------------------- tick
def test_roads_tick_ok(auth):
    """踢 worker: 没起线程也不算错 (nudge 只置事件)。"""
    r = auth.get(TICK)
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_roads_tick_requires_auth():
    assert TestClient(m.app).get(TICK).status_code == 401
