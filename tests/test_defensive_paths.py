"""防御路径测试: 密钥生成 / 登录限速自愈 / 容器定位回退 / 引擎守卫 /
自有库迁移 / 统一错误契约 (503 / 400) / 轨迹缓存降级 / 地区解析兜底。

这些是列表/播放主流程之外的分支, 平时不出场, 出场就是生产事故面。"""
import json
import subprocess as subprocess_module

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import (authentication, config, database)  # pylint: disable=wrong-import-position
from app.tesla import repository, settings_store, tracks_cache  # pylint: disable=wrong-import-position
import app.main as main_module  # pylint: disable=wrong-import-position
from app.tesla.models import Driver  # pylint: disable=wrong-import-position
from tests.conftest import seed_drive  # pylint: disable=wrong-import-position


# ---------------------------------------------------------------- 密钥与限速
def test_secret_file_regenerates_when_missing_or_short(tmp_path, monkeypatch):
    """密钥文件缺失/过短都要重生成 (>=32 字节), 合格则原样复用。"""
    secret_file = tmp_path / "secret"
    monkeypatch.setattr(config, "SECRET_FILE", secret_file)
    first = authentication._load_secret()  # pylint: disable=protected-access
    assert len(first) >= 32 and secret_file.read_bytes() == first
    assert authentication._load_secret() == first  # pylint: disable=protected-access
    secret_file.write_bytes(b"short")
    second = authentication._load_secret()  # pylint: disable=protected-access
    assert len(second) >= 32 and second != first


def test_record_fail_clears_scanner_bloated_table(monkeypatch):
    """失败表被扫描器撑爆 (>10000 条) 时整体清空重来, 防内存失控。"""
    fails = {f"10.{i // 65536}.{i // 256 % 256}.{i % 256}": (1, 0)
             for i in range(10001)}
    monkeypatch.setattr(authentication, "_login_fails", fails)
    authentication.record_fail("192.0.2.9")
    assert len(fails) == 1 and "192.0.2.9" in fails


# ---------------------------------------------------------------- 容器定位 / 引擎守卫
def test_resolve_db_host_env_inspect_and_failure(monkeypatch):
    """定位链: 环境变量直通 > docker inspect > RuntimeError。"""
    monkeypatch.setenv("TMDB_HOST", "db.lan")
    assert database.resolve_db_host() == "db.lan"
    monkeypatch.delenv("TMDB_HOST")
    monkeypatch.setattr(subprocess_module, "check_output",
                        lambda *_a, **_k: "172.17.0.2\n")
    assert database.resolve_db_host() == "172.17.0.2"
    monkeypatch.setattr(subprocess_module, "check_output", lambda *_a, **_k: "")
    monkeypatch.setattr(database, "DOCKER_BIN_CANDIDATES", ["/bin/false"])
    with pytest.raises(RuntimeError, match="TMDB_HOST"):
        database.resolve_db_host()


def test_init_engine_defaults_to_env_url(monkeypatch):
    """init_engine() 不带参: 走 env 拼出的 Postgres URL (create 不连接)。"""
    monkeypatch.setenv("TMDB_HOST", "db.lan")
    database.init_engine()
    assert database.engine().url.host == "db.lan"


def test_engine_guards_raise_when_uninitialized(monkeypatch):
    for state in (database._EngineState, database._OwnEngineState):  # pylint: disable=protected-access
        monkeypatch.setattr(state, "engine", None)
        monkeypatch.setattr(state, "factory", None)
    with pytest.raises(RuntimeError, match="init_engine"):
        database.engine()
    with pytest.raises(RuntimeError, match="init_engine"):
        database.session_factory()
    with pytest.raises(RuntimeError, match="init_own_engine"):
        database.own_engine()
    with pytest.raises(RuntimeError, match="init_own_engine"):
        database.own_session_factory()


# ---------------------------------------------------------------- 自有库迁移
def test_migrate_own_db_adds_amap_style_column():
    """旧版自有库 (无 amap_style 列) 启动时自动补列, 且幂等。"""
    with database.own_engine().begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS app_settings")
        conn.exec_driver_sql(
            "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tmdb_host TEXT,"
            " tmdb_port TEXT, tmdb_user TEXT, tmdb_password TEXT, tmdb_name TEXT,"
            " amap_key TEXT, amap_security_code TEXT, updated_at DATETIME)")
    main_module._migrate_own_db()  # pylint: disable=protected-access
    with database.own_engine().connect() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(app_settings)")}
    assert "amap_style" in cols
    main_module._migrate_own_db()  # pylint: disable=protected-access  # 再跑不炸


# ---------------------------------------------------------------- 统一错误契约
def test_sqlalchemy_error_maps_to_503(auth, monkeypatch):
    """路由里的 SQLAlchemyError 统一兜成 503, 不把异常细节裸奔给前端。"""

    def boom(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repository, "list_trips", boom)
    r = auth.get("/tesla/trips/api/sessions")
    assert r.status_code == 503
    assert "数据库查询失败" in r.json()["detail"]


def test_charging_rejects_unknown_sort_and_bad_pagination(auth):
    assert auth.get("/tesla/charging/api/sessions?sort=bogus").status_code == 400
    assert auth.get("/tesla/charging/api/sessions?offset=-1").status_code == 400


def test_mapdiag_tolerates_malformed_json(auth):
    """诊断上报收到坏 JSON 不炸 (只写日志, 永远 ok)。"""
    r = auth.post("/tesla/map/api/diag", content=b"not-json{",
                  headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_merged_stream_rejects_ids_out_of_range(auth, db):
    seed_drive(db, id=1)
    assert auth.get("/tesla/trips/api/merged_stream?ids=1").status_code == 400


def test_rename_group_rejects_blank_name(auth):
    r = auth.patch("/tesla/trips/api/groups/7", json={"name": "   "})
    assert r.status_code == 400


def test_change_driver_rejects_blank_name(auth):
    r = auth.patch("/tesla/api/drivers/7", json={"name": "   "})
    assert r.status_code == 400


# ---------------------------------------------------------------- 设置与驾驶员
def test_tmdb_host_falls_back_empty_when_docker_lookup_fails(owndb, monkeypatch):
    """docker 定位失败: GET 设置页不炸 (host 留空), 拼连接串时才报错。"""
    monkeypatch.delenv("TMDB_HOST", raising=False)

    def boom():
        raise RuntimeError("找不到容器")

    monkeypatch.setattr(database, "resolve_db_host", boom)
    assert settings_store.effective_tmdb(owndb)["host"] == ""
    monkeypatch.setenv("TMDB_HOST", "db.lan")
    assert "db.lan" in settings_store.engine_url(owndb)


def test_update_driver_can_unset_default(auth, owndb):
    owndb.add(Driver(id=1, name="大导子", is_default=True))
    owndb.commit()
    r = auth.patch("/tesla/api/drivers/1", json={"is_default": False})
    assert r.status_code == 200 and r.json()["is_default"] is False


# ---------------------------------------------------------------- 轨迹缓存降级
def test_tracks_cache_warm_swallows_backend_failure(monkeypatch):
    """启动预热失败要静默 (首次访问会重试), 不能把启动线程炸了。"""

    def boom(_factory):
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(tracks_cache, "load_tracks", boom)
    tracks_cache.warm(database.session_factory())  # 不抛即通过 (工厂不会被真正使用)


def test_disk_cache_with_wrong_version_is_ignored():
    """磁盘缓存版本不符 = 当没有 (全量重建), 不读旧结构。"""
    with open(tracks_cache.cache_file(), "w", encoding="utf-8") as handle:
        json.dump({"v": 999, "max_id": 5, "tracks": []}, handle)
    assert tracks_cache._read_disk_cache() == (-1, [])  # pylint: disable=protected-access


# ---------------------------------------------------------------- 地区解析兜底
def test_parse_region_rejects_province_less_chain(db):
    """全是国家名/邮编的地址链解析不出省 → 无地区; 空路径地区过滤 → 空。"""
    assert repository.parse_region("中国,518000") == (None, None, None)
    assert not repository.region_address_ids(db, " / ")
