"""自有库 (SQLite, data/mytesla.db) 的引擎: app 自产数据 (断档补路 / 行程
分组 / 驾驶员标注 / 设置等), 与 TeslaMate 生产库完全隔离的第二套引擎。"""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .. import config


class _OwnEngineState:
    """自有库引擎持有者 (SQLite, 与 TeslaMate 引擎分开)。"""

    engine: Engine | None = None
    factory: sessionmaker[Session] | None = None


def init_own_engine(url: str | None = None) -> None:
    """创建自有库引擎 (缺省 data/mytesla.db, 测试可注入别的 SQLite)。"""
    if url is None:
        url = config.OWN_DB_URL
    if url.startswith("sqlite:///"):
        parent = Path(url.removeprefix("sqlite:///")).parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)
    _OwnEngineState.engine = create_engine(
        url, connect_args={"check_same_thread": False,   # 请求线程池会换线程复用连接
                           "timeout": 30})   # 足迹道路 worker 写库 vs API 读并发, busy 等待加长
    _OwnEngineState.factory = sessionmaker(_OwnEngineState.engine,
                                           expire_on_commit=False)


def migrate_own_db() -> None:
    """create_all 只建新表不改旧表: 已有生产库要补的列写在这里 (幂等)。

    配方单一来源 —— My Home 组合仓的 lifespan 起同一份自有库时调的也是
    它 (组合部署 / 单仓部署共用同一个 data/mytesla.db, 补列只记一处)。"""
    with own_engine().begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(app_settings)")}
        if "amap_style" not in cols:   # v: 高德地图样式 (设置页可换, 三页地图共用)
            conn.exec_driver_sql(
                "ALTER TABLE app_settings ADD COLUMN amap_style TEXT NOT NULL DEFAULT ''")
        if "map_provider" not in cols:  # v: 地图服务商 (2026-09-25 起只留高德,
            # 列不再读写; 已装库的列留着, 迁移测试仍盖着加列路径)
            conn.exec_driver_sql(
                "ALTER TABLE app_settings ADD COLUMN map_provider TEXT NOT NULL DEFAULT ''")
        if "amap_web_key" not in cols:  # v: 高德 Web 服务 key (足迹道路拟合)
            conn.exec_driver_sql(
                "ALTER TABLE app_settings ADD COLUMN amap_web_key TEXT NOT NULL DEFAULT ''")
        rcols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(drive_roads)")}
        if "gaps" not in rcols:  # v: 推断层顶点区间 (可能走过, 虚线渲染)
            conn.exec_driver_sql(
                "ALTER TABLE drive_roads ADD COLUMN gaps VARCHAR NOT NULL DEFAULT '[]'")


def dispose_own_engine() -> None:
    """释放自有库连接池 (测试隔离也用它)。"""
    if _OwnEngineState.engine is not None:
        _OwnEngineState.engine.dispose()
    _OwnEngineState.engine = None
    _OwnEngineState.factory = None


def own_engine() -> Engine:
    """自有库引擎 (启动时建表用)。"""
    if _OwnEngineState.engine is None:
        raise RuntimeError("自有库引擎未初始化 (init_own_engine 未调用)")
    return _OwnEngineState.engine


def own_session_factory() -> sessionmaker[Session]:
    """自有库会话工厂。"""
    if _OwnEngineState.factory is None:
        raise RuntimeError("自有库引擎未初始化 (init_own_engine 未调用)")
    return _OwnEngineState.factory


def get_own_db() -> Iterator[Session]:
    """FastAPI 依赖: 每请求一个自有库会话, 请求结束自动关闭。"""
    factory = own_session_factory()
    with factory() as session:  # pylint: disable=not-callable
        yield session
