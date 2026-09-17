"""视野内高精度轨迹测试: 步长编译, detail 端点, 预算分摊, 并行
分片合并, gzip, 输入校验。
拆自 test_map.py (结构化重构, 代码逐字节未动)。"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app import database
from app.tesla import repository
from app.tesla.repository import map as map_repository
from tests.seed_factories import seed_drive, seed_positions
from tests.map_seed_helpers import _seed_detail_drive

# ---------------------------------------------------------------- 视野内高精度轨迹
BOX = {"w": 113, "s": 22, "e": 115, "n": 24}


def test_window_keep_compiles_integer_stride_on_postgres():
    """下采样步长必须整除: SA 2.0 的 ``/`` 在 Postgres 方言会 CAST 成 NUMERIC 真除,
    浮点步长让 ``%`` 永远取不到 0 → 轨迹只剩首末 2 点 (真库回归发现)。
    SQLite 方言不做这个转换所以测不出来, 必须用方言编译产物断言。"""
    # 直接构造窗口子查询检查内部表达式 (白盒: 方言差异无公开入口)
    inner = map_repository._position_window().subquery()  # pylint: disable=protected-access
    keep = map_repository._window_keep(inner, 40)         # pylint: disable=protected-access
    sql = str(select(inner.c.rn).where(keep).compile(dialect=postgresql.dialect()))
    assert "AS NUMERIC" not in sql, sql


def test_tracks_detail_endpoint(auth, db):
    _seed_detail_drive(db, 7)
    seed_drive(db, id=8, start_date=datetime(2026, 9, 2, 2, 0),
               end_date=datetime(2026, 9, 2, 3, 0), distance=5.0)
    r = auth.get("/tesla/map/api/tracks/detail",
                 params={"ids": "7,8", "zoom": 13, **BOX})
    assert r.status_code == 200
    assert r.json() == {"count": 1, "tracks": [
        {"id": 7, "pts": [[114.05, 22.55], [114.06, 22.56]]}]}
    # 单点行程 (8) 被丢弃; id 不存在也不报错


def test_tracks_detail_budget_spread(auth, monkeypatch):
    seen = {}

    def fake_parallel(_factory, id_list, per, _bbox):
        seen["ids"], seen["per"] = id_list, per
        return []

    monkeypatch.setattr(repository, "query_detail_parallel", fake_parallel)
    base = "/tesla/map/api/tracks/detail"
    # 轨迹少 (≤50 条) → 全精度, 与缩放级别无关
    for n in (2, 50):
        ids = ",".join(str(i) for i in range(1, n + 1))
        r = auth.get(base, params={"ids": ids, "zoom": 12, **BOX})
        assert r.status_code == 200
        assert seen["per"] == repository.DETAIL_PER_MAX, f"{n} 条时被稀释"
    # 密集 (150 条) → 按总点均摊, 但每条不低于下限 (旧总预算制会稀释到 ~266)
    ids = ",".join(str(i) for i in range(1, 151))
    r = auth.get(base, params={"ids": ids, "zoom": 13, **BOX})
    assert r.status_code == 200
    assert seen["per"] == repository.DETAIL_PER_FLOOR


def test_tracks_detail_caps_ids(auth, monkeypatch):
    """id 上限 150, 多传的截断。"""
    seen = {}

    def fake_parallel(_factory, id_list, _per, _bbox):
        seen["ids"] = list(id_list)
        return []

    monkeypatch.setattr(repository, "query_detail_parallel", fake_parallel)
    ids = ",".join(str(i) for i in range(200))
    r = auth.get("/tesla/map/api/tracks/detail",
                 params={"ids": ids, "zoom": 12, **BOX})
    assert r.status_code == 200
    assert len(seen["ids"]) == repository.DETAIL_MAX_IDS == 150


def test_tracks_detail_downsampling(db):
    """视野内明细按窗口下采样: 首末点必留, 等间隔取点。"""
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=7, start_date=start, end_date=start + timedelta(hours=2),
               distance=20.0, duration_min=120)
    seed_positions(db, 7, [{"date": start + timedelta(seconds=72 * i),
                            "longitude": 114.0 + i * 0.0001, "latitude": 22.5}
                           for i in range(100)])
    d = repository.query_detail(
        db, [7], 20, repository.BBox(113, 22, 115, 24))[0]
    assert len(d.pts) == 21          # stride=5 → i%5 + 首末
    assert d.pts[0][0] == 114.0
    assert d.pts[-1][0] == round(114.0 + 99 * 0.0001, 5)


def test_tracks_detail_gzipped_when_large(auth, db):
    """大响应走 gzip, 手机端省流量 (轨迹点多的接口动辄几 MB)。"""
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=7, start_date=start, end_date=start + timedelta(hours=5),
               distance=30.0, duration_min=300)
    seed_positions(db, 7, [{"date": start + timedelta(seconds=60 * i),
                            "longitude": 114.0 + i * 0.00001, "latitude": 22.5}
                           for i in range(300)])
    r = auth.get("/tesla/map/api/tracks/detail",
                 params={"ids": "7", "zoom": 15, **BOX},
                 headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert r.json()["count"] == 1


def test_tracks_detail_rejects_bad_input(auth, monkeypatch):
    def boom(*_args):
        raise AssertionError("参数非法不应查询数据库")

    monkeypatch.setattr(repository, "query_detail_parallel", boom)
    base = "/tesla/map/api/tracks/detail"
    # ids 非数字 → 400
    assert auth.get(base, params={"ids": "abc", "zoom": 13,
                                  **BOX}).status_code == 400
    # bbox 非法 (w >= e) → 400
    assert auth.get(base, params={"ids": "1", "zoom": 13,
                                  "w": 115, "s": 22, "e": 113, "n": 24}).status_code == 400
    # 空 ids → 200 空结果, 不查库
    r = auth.get(base, params={"ids": "", "zoom": 13, **BOX})
    assert r.status_code == 200 and r.json()["count"] == 0


def test_tracks_detail_parallel_splits_and_merges(db):
    """4 路并行: 结果按 id 升序合并, 乱序传入也照常。"""
    for drive_id in (100, 101, 102, 103, 104, 105):
        _seed_detail_drive(db, drive_id)
    tracks = repository.query_detail_parallel(
        database.session_factory(), [105, 100, 103],
        repository.DETAIL_PER_MAX, repository.BBox(113, 22, 115, 24))
    assert [t.id for t in tracks] == [100, 103, 105]
    assert all(len(t.pts) == 2 for t in tracks)
