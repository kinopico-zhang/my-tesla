"""足迹轨迹缓存测试: 冷/暖/盘缓存, 旧版本重建, 增量追加, 坏文件
忽略, MapTrack 模型往返, diag 端点。
拆自 test_map.py (结构化重构, 代码逐字节未动)。"""
import json
from datetime import datetime

from fastapi.testclient import TestClient

import app.main as m
from app.tesla import repository, tracks_cache
from app.tesla.schemas import MapTrack
from tests.seed_factories import seed_drive
from tests.map_seed_helpers import _two_point_drive

def test_tracks_cold_cache_queries_everything(auth, db, tmp_path, monkeypatch):
    _two_point_drive(db, 5, datetime(2026, 9, 1, 2, 0))
    real_query = repository.query_tracks
    seen = {}

    def spy(session, after):
        seen["after"] = after
        return real_query(session, after)

    monkeypatch.setattr(repository, "query_tracks", spy)
    r = auth.get("/tesla/map/api/tracks")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 1
    assert d["tracks"][0]["id"] == 5
    assert d["tracks"][0]["km"] == 12.3          # round(12.34, 1)
    assert d["tracks"][0]["pts"] == [[114.05, 22.55], [114.06, 22.56]]
    assert seen["after"] == -1                    # 无缓存 → 全量
    # 结果落盘 (带算法版本号)
    cache = json.loads((tmp_path / "tracks_cache.json").read_text(encoding="utf-8"))
    assert cache["max_id"] == 5
    assert cache["v"] == tracks_cache.CACHE_VERSION
    assert cache["tracks"][0]["id"] == 5


def test_tracks_warm_memory_cache_skips_query(auth, db, monkeypatch):
    _two_point_drive(db, 10, datetime(2026, 9, 1, 2, 0))
    assert auth.get("/tesla/map/api/tracks").json()["count"] == 1   # 预热内存缓存

    def boom(*_args):
        raise AssertionError("缓存已最新, 不应查询数据库")

    monkeypatch.setattr(repository, "query_tracks", boom)
    assert auth.get("/tesla/map/api/tracks").json()["count"] == 1


def test_tracks_disk_cache_used_without_query(auth, db, tmp_path, monkeypatch):
    track = {"id": 3, "date": "2026-07-01", "km": 1.0, "min": 5,
             "pts": [[114.0, 22.5], [114.1, 22.6]]}
    (tmp_path / "tracks_cache.json").write_text(json.dumps(
        {"v": tracks_cache.CACHE_VERSION, "max_id": 3, "tracks": [track]}))
    seed_drive(db, id=3, distance=1.0)       # max_id 与磁盘一致 → 无新行程

    def boom(*_args):
        raise AssertionError("磁盘缓存已最新, 不应查询数据库")

    monkeypatch.setattr(repository, "query_tracks", boom)
    d = auth.get("/tesla/map/api/tracks").json()
    assert d["count"] == 1
    assert d["tracks"][0]["id"] == 3


def test_tracks_old_cache_version_triggers_full_rebuild(
        auth, db, tmp_path, monkeypatch):
    """旧版本缓存 (无 v 字段) 必须作废全量重建, 不能直接复用旧采样。"""
    track = {"id": 1, "date": "2026-01-01", "km": 5.0, "min": 10,
             "pts": [[114.0, 22.5], [114.1, 22.6]]}
    (tmp_path / "tracks_cache.json").write_text(
        json.dumps({"max_id": 3, "tracks": [track]}))    # 无 v → 版本不符
    _two_point_drive(db, 1, datetime(2026, 9, 1, 2, 0))
    real_query = repository.query_tracks
    seen = {}

    def spy(session, after):
        seen["after"] = after
        return real_query(session, after)

    monkeypatch.setattr(repository, "query_tracks", spy)
    assert auth.get("/tesla/map/api/tracks").json()["count"] == 1
    assert seen["after"] == -1                    # 无视磁盘 max_id, 全量重建
    cache = json.loads((tmp_path / "tracks_cache.json").read_text(encoding="utf-8"))
    assert cache["v"] == tracks_cache.CACHE_VERSION   # 重建后写入新版本号


def test_tracks_incremental_append(auth, db, tmp_path, monkeypatch):
    _two_point_drive(db, 5, datetime(2026, 8, 1, 2, 0))
    assert auth.get("/tesla/map/api/tracks").json()["count"] == 1   # max_id=5
    _two_point_drive(db, 8, datetime(2026, 9, 1, 2, 0))             # 新行程
    real_query = repository.query_tracks
    seen = {}

    def spy(session, after):
        seen["after"] = after
        return real_query(session, after)

    monkeypatch.setattr(repository, "query_tracks", spy)
    d = auth.get("/tesla/map/api/tracks").json()
    assert seen["after"] == 5                    # 只查 id > 5 的新行程
    assert [t["id"] for t in d["tracks"]] == [5, 8]   # 按日期排序
    cache = json.loads((tmp_path / "tracks_cache.json").read_text(encoding="utf-8"))
    assert cache["max_id"] == 8
    assert len(cache["tracks"]) == 2


def test_maptrack_model_roundtrip_from_old_disk_format():
    """旧版磁盘缓存里的 dict 能原样反序列化 (格式兼容, 不必重扫全库)。"""
    legacy = {"id": 9, "date": "2026-09-01", "km": 12.3, "min": 25,
              "pts": [[114.05, 22.55], [114.06, 22.56]]}
    track = MapTrack.model_validate(legacy)
    assert track.model_dump() == legacy


def test_diag_endpoint_logs_and_requires_auth(auth, capsys):
    r = auth.post("/tesla/map/api/diag", json={"stage": "map_complete", "ua": "test"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert "MAPDIAG" in capsys.readouterr().out
    # 未登录 401
    assert TestClient(m.app).post(
        "/tesla/map/api/diag", json={"stage": "x"}).status_code == 401
