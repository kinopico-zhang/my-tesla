"""足迹地图 API 测试 (下采样 / 缓存 / 增量逻辑, SQLite 种子跑真实 SQL)。"""
import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

import app.main as m
from app import database
from app.tesla import repository, tracks_cache
from app.tesla.repository import map as map_repository
from app.tesla.models import Driver, TripDriver
from app.tesla.schemas import MapTrack
from tests.conftest import (seed_addresses, seed_drive, seed_position,
                            seed_positions)


# ---------------------------------------------------------------- config
def test_config_empty_without_env(auth, monkeypatch):
    monkeypatch.delenv("AMAP_KEY", raising=False)
    monkeypatch.delenv("AMAP_SECURITY_CODE", raising=False)
    monkeypatch.delenv("AMAP_STYLE", raising=False)
    # 样式默认幻影黑: 底色纯黑配深色 App (用户明确要的观感); 官方深色样式
    # 按设计不带地名, 要地名走设置页 (极夜蓝或自建样式 ID)
    assert auth.get("/tesla/map/api/config").json() == \
        {"amap_key": None, "security_code": None,
         "style": "amap://styles/dark"}


def test_config_returns_env_values(auth, monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "abc123")
    monkeypatch.setenv("AMAP_SECURITY_CODE", "sec456")
    monkeypatch.setenv("AMAP_STYLE", "amap://styles/light")
    assert auth.get("/tesla/map/api/config").json() == \
        {"amap_key": "abc123", "security_code": "sec456",
         "style": "amap://styles/light"}


# ---------------------------------------------------------------- summary
def test_map_summary(auth, db):
    seed_addresses(db)
    seed_drive(db, id=1, distance=52525.4, duration_min=66000,
               start_date=datetime(2025, 3, 24, 4, 0),
               end_date=datetime(2025, 3, 24, 5, 0))
    d = auth.get("/tesla/map/api/summary").json()
    assert d == {"drives": 1, "distance_km": 52525.4, "duration_min": 66000,
                 "first_date": "2025-03-24", "last_date": "2025-03-24"}
    # 日期过滤 (本地日期)
    d2 = auth.get("/tesla/map/api/summary",
                  params={"from": "2026-01-01"}).json()
    assert d2 == {"drives": 0, "distance_km": 0.0, "duration_min": 0,
                  "first_date": None, "last_date": None}


# ---------------------------------------------------------------- tracks + 缓存
def _two_point_drive(db, drive_id, start):
    seed_drive(db, id=drive_id, start_date=start,
               end_date=start + timedelta(hours=1),
               distance=12.34, duration_min=25)
    seed_position(db, drive_id, id=None, date=start,
                  longitude=114.05, latitude=22.55)
    seed_position(db, drive_id, id=None, date=start + timedelta(minutes=10),
                  longitude=114.06, latitude=22.56)


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


def test_map_page_time_menu_in_nav_row(auth):
    """时间下拉 (含自定义日历) 在顶栏 nav-row (与全站一致); 筛选行只剩驾驶员。"""
    html = auth.get("/tesla/map").text
    html += auth.get("/tesla/static/map.js?v=1").text
    for frag in ['id="time-menu"', 'data-v="24h"', 'data-v="7d"', 'data-v="30d"',
                 'data-v="180d"', 'data-v="1y"', 'data-v="all"',
                 'data-v="custom"', 'id="tm-cal"', 'id="tm-prev"', 'id="tm-next"',
                 'id="tm-ym"', 'id="tm-sel"', 'id="tm-apply"', 'function calRender()',
                 '再点结束日期', 'class="filters"',
                 # 手机: 下拉面板锚全宽 header (本页 header 不滚动无定位, 要补 relative)
                 '@media (max-width: 479px)', 'header { position: relative; }',
                 '.nav-menu { position: static; }']:
        assert frag in html, f"足迹页缺少 {frag}"
    # 时间菜单紧跟品牌下拉在顶栏; 筛选行只剩驾驶员, 没配驾驶员整行藏掉不占位
    assert '</details>\n    <details class="nav-menu time-menu" id="time-menu">' in html
    assert '<div class="filters" id="filters" hidden>' in html
    assert '"#filters").hidden = false' in html   # 有驾驶员才亮
    assert "chips-range" not in html and ".chip {" not in html
    assert 'id="tm-from"' not in html
    # 关键 id 全页唯一 (孤儿节点会重复 id, JS 绑错元素且不报错)
    for i in ("time-menu", "time-lb", "time-opts", "tm-dates", "tm-cal", "tm-prev",
              "tm-next", "tm-ym", "tm-sel", "brand-menu", "logout"):
        assert html.count(f'id="{i}"') == 1, f"足迹页 {i} 重复"
    # 筛选行太宽时手机端自己横滑, 不把整个页面带着滑 (下拉锚在 header 不受裁)
    assert ".filters { overflow-x: auto; scrollbar-width: none; }" in html
    assert ".filters::-webkit-scrollbar { display: none; }" in html
    # 地图样式走 config (设置页可换), 不再写死幻影黑
    assert 'mapStyle: cfg.style || "amap://styles/dark"' in html
    # "©…auto navi" 版权文字按需求去掉 (高德无官方开关, CSS 藏)
    assert '#map .amap-copyright { display: none !important; }' in html


def test_map_page_driver_filter(auth):
    """驾驶员筛选下拉: 选项来自设置页驾驶员表 (没配驾驶员整颗藏掉),
    口径与行程页一致 (默认驾驶员含未标注); 写进 URL 可分享。"""
    html = auth.get("/tesla/map").text
    html += auth.get("/tesla/static/map.js?v=1").text
    for frag in ['id="drv-menu"', 'id="drv-opts"', 'id="drv-lb"', "驾驶员: 全部",
                 '"/tesla/api/drivers"', "$(\"#drv-menu\").hidden = false",
                 'u.searchParams.set("driver_id", drvId)',
                 'u.searchParams.delete("driver_id")',
                 "trackParams()", "driver_id=" + '" + drvId']:
        assert frag in html, f"足迹页缺少 {frag}"
    # 筛选藏到拉到驾驶员选项才出现; 深链带入的驾驶员不存在要回落"全部"
    assert '<details class="nav-menu" id="drv-menu" hidden>' in html
    assert "drivers.find(d => d.id === drvId)" in html
    # 地名首帧竞态: 矢量样式数据异步加载, 首帧不画地名; complete 后延时补
    # 重渲染 (setFeatures 同值重设只触发重绘), 否则地名要等下次交互才出现
    assert 'map.setFeatures(map.getFeatures())' in html
    assert 'setTimeout(nudge, 1500); setTimeout(nudge, 5000); setTimeout(nudge, 12000);' in html


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


def _seed_detail_drive(db, drive_id):
    start = datetime(2026, 9, 1, 2, 0)
    seed_drive(db, id=drive_id, start_date=start,
               end_date=start + timedelta(hours=1),
               distance=10.0, duration_min=60)
    seed_position(db, drive_id, id=None, date=start,
                  longitude=114.05, latitude=22.55)
    seed_position(db, drive_id, id=None, date=start + timedelta(minutes=10),
                  longitude=114.06, latitude=22.56)


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
