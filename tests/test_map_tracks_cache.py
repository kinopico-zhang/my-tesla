"""足迹轨迹缓存测试: 冷/暖/盘缓存, 旧版本重建, 增量追加, 坏文件
忽略, MapTrack 模型往返, diag 端点 (缓存由清单端点驱动加载)。
拆自 test_map.py (结构化重构; v4 起清单端点取代旧 /tracks)。"""
import json
from datetime import datetime

from fastapi.testclient import TestClient

import app.main as m
from app.tesla import repository, tracks_cache
from app.tesla.schemas import MapTrack
from tests.seed_factories import seed_drive
from tests.map_seed_helpers import _two_point_drive

MANIFEST = "/tesla/map/api/tracks/manifest"


def _rows(r):
    return r.json()["tracks"]


def test_tracks_cold_cache_queries_everything(auth, db, tmp_path, monkeypatch):
    _two_point_drive(db, 5, datetime(2026, 9, 1, 2, 0))
    real_query = repository.query_tracks
    seen = {}

    def spy(session, after):
        seen["after"] = after
        return real_query(session, after)

    monkeypatch.setattr(repository, "query_tracks", spy)
    r = auth.get(MANIFEST)
    assert r.status_code == 200
    assert r.json()["v"] == tracks_cache.CACHE_VERSION
    assert _rows(r) == [{"id": 5, "n": 2, "d": None, "c": 1, "t": "2026-09-01"}]
    assert seen["after"] == -1                    # 无缓存 → 全量
    # 结果落盘 (JSONL: 首行头 {v, max_id}, 之后一行一条轨迹, pts 扁平)
    lines = (tmp_path / "tracks_cache.json").read_text(
        encoding="utf-8").splitlines()
    head, track_line = json.loads(lines[0]), json.loads(lines[1])
    assert head == {"v": tracks_cache.CACHE_VERSION, "max_id": 5}
    assert track_line["pts"] == [114.05, 22.55, 114.06, 22.56]


def test_tracks_warm_memory_cache_skips_query(auth, db, monkeypatch):
    _two_point_drive(db, 10, datetime(2026, 9, 1, 2, 0))
    assert len(_rows(auth.get(MANIFEST))) == 1    # 预热内存缓存

    def boom(*_args):
        raise AssertionError("缓存已最新, 不应查询数据库")

    monkeypatch.setattr(repository, "query_tracks", boom)
    assert len(_rows(auth.get(MANIFEST))) == 1


def test_tracks_disk_cache_used_without_query(auth, db, tmp_path, monkeypatch):
    track = {"id": 3, "car_id": 1, "date": "2026-07-01", "km": 1.0, "min": 5,
             "pts": [114.0, 22.5, 114.1, 22.6]}
    (tmp_path / "tracks_cache.json").write_text(json.dumps(
        {"v": tracks_cache.CACHE_VERSION, "max_id": 3}) + "\n"
        + json.dumps(track) + "\n")   # JSONL: 头行 + 轨迹行
    seed_drive(db, id=3, distance=1.0)       # max_id 与磁盘一致 → 无新行程

    def boom(*_args):
        raise AssertionError("磁盘缓存已最新, 不应查询数据库")

    monkeypatch.setattr(repository, "query_tracks", boom)
    assert _rows(auth.get(MANIFEST)) == [
        {"id": 3, "n": 2, "d": None, "c": 1, "t": "2026-07-01"}]


def test_tracks_old_cache_version_triggers_full_rebuild(
        auth, db, tmp_path, monkeypatch):
    """旧版本缓存 (无 v 字段的旧单册 JSON) 必须作废全量重建, 不能复用。"""
    track = {"id": 1, "date": "2026-01-01", "km": 5.0, "min": 10,
             "pts": [114.0, 22.5, 114.1, 22.6]}
    (tmp_path / "tracks_cache.json").write_text(
        json.dumps({"max_id": 3, "tracks": [track]}))    # 无 v → 版本不符
    _two_point_drive(db, 1, datetime(2026, 9, 1, 2, 0))
    real_query = repository.query_tracks
    seen = {}

    def spy(session, after):
        seen["after"] = after
        return real_query(session, after)

    monkeypatch.setattr(repository, "query_tracks", spy)
    assert len(_rows(auth.get(MANIFEST))) == 1
    assert seen["after"] == -1                    # 无视磁盘 max_id, 全量重建
    head = json.loads((tmp_path / "tracks_cache.json").read_text(
        encoding="utf-8").splitlines()[0])
    assert head["v"] == tracks_cache.CACHE_VERSION   # 重建后写入新版本号


def test_tracks_incremental_append(auth, db, tmp_path, monkeypatch):
    _two_point_drive(db, 5, datetime(2026, 8, 1, 2, 0))
    auth.get(MANIFEST)                                   # max_id=5
    _two_point_drive(db, 8, datetime(2026, 9, 1, 2, 0))  # 新行程
    real_query = repository.query_tracks
    seen = {}

    def spy(session, after):
        seen["after"] = after
        return real_query(session, after)

    monkeypatch.setattr(repository, "query_tracks", spy)
    rows = _rows(auth.get(MANIFEST))
    assert seen["after"] == 5                    # 只查 id > 5 的新行程
    assert [t["id"] for t in rows] == [5, 8]     # 按日期排序
    lines = (tmp_path / "tracks_cache.json").read_text(
        encoding="utf-8").splitlines()
    assert json.loads(lines[0])["max_id"] == 8
    assert len(lines) == 3                       # 头行 + 2 条轨迹


def test_disk_cache_corrupt_file_is_ignored(auth, db, tmp_path):
    """磁盘缓存损坏 (非法 JSON) 当作没有, 全量重建不报错。"""
    (tmp_path / "tracks_cache.json").write_text("not-json{{{")
    _two_point_drive(db, 4, datetime(2026, 9, 1, 2, 0))
    assert len(_rows(auth.get(MANIFEST))) == 1


def test_maptrack_model_roundtrip_from_disk_format():
    """磁盘缓存里的 dict 能原样反序列化 (v4 起 pts 扁平 [lng, lat, ...];
    旧版点对嵌套, 但版本号不符在 _read_disk_cache 就整体作废了)。"""
    data = {"id": 9, "car_id": 2, "date": "2026-09-01", "km": 12.3, "min": 25,
            "pts": [114.05, 22.55, 114.06, 22.56]}
    track = MapTrack.model_validate(data)
    assert track.model_dump() == data


def test_diag_endpoint_logs_and_requires_auth(auth, capsys):
    r = auth.post("/tesla/map/api/diag", json={"stage": "map_complete", "ua": "test"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert "MAPDIAG" in capsys.readouterr().out
    # 未登录 401
    assert TestClient(m.app).post(
        "/tesla/map/api/diag", json={"stage": "x"}).status_code == 401
