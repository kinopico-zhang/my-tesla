"""自有库 (SQLite, data/mytesla.db) 的引擎: app 自产数据 (断档补路 / 行程
分组 / 驾驶员标注 / 设置等), 与 TeslaMate 生产库完全隔离的第二套引擎。"""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.exc import OperationalError
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


def _add_col(conn: Connection, table: str, col: str, ddl: str,
             cols: set[str] | None = None) -> None:
    """幂等加列 (老库补列): cols 可传预读的列名单 (省一次 PRAGMA)。
    检查与 ALTER 之间列被并启的另一进程先加 → sqlite 报 duplicate
    column, 当已迁移吞掉 (2026-10-14 8500/8501 双 uvicorn 同启实锤
    掐死过 8501)。"""
    if cols is None:
        cols = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
    if col in cols:
        return
    try:
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    except OperationalError as exc:
        if "duplicate column name" not in str(exc):
            raise


def migrate_own_db() -> None:
    """create_all 只建新表不改旧表: 已有生产库要补的列写在这里 (幂等,
    双进程同启竞态安全 —— _add_col 吞并启 duplicate)。

    配方单一来源 —— My Home 组合仓的 lifespan 起同一份自有库时调的也是
    它 (组合部署 / 单仓部署共用同一个 data/mytesla.db, 补列只记一处)。"""
    with own_engine().begin() as conn:
        # v: 高德地图样式 (设置页可换, 三页地图共用)
        _add_col(conn, "app_settings", "amap_style", "TEXT NOT NULL DEFAULT ''")
        # v: 地图服务商 (2026-09-25 起只留高德, 列不再读写; 老库列留着)
        _add_col(conn, "app_settings", "map_provider", "TEXT NOT NULL DEFAULT ''")
        # v: 高德 Web 服务 key (足迹道路拟合 / 地名 worker)
        _add_col(conn, "app_settings", "amap_web_key", "TEXT NOT NULL DEFAULT ''")
        # v: 历史道路首轮回填完成旗 (蒙版掀盖判据)
        _add_col(conn, "app_settings", "roads_initial_done",
                 "BOOLEAN NOT NULL DEFAULT 0")
        # v: 推断层顶点区间 (可能走过, 虚线渲染)
        _add_col(conn, "drive_roads", "gaps", "VARCHAR NOT NULL DEFAULT '[]'")
        # v: 高德区划三列 (2026-10-14 地名高德化 v2) —— v1 老行补列默认空,
        # 读侧该址回退 TeslaMate 解析, worker 重查 (v bump) 后补齐
        for col in ("province", "city", "district"):
            _add_col(conn, "place_names", col, "TEXT NOT NULL DEFAULT ''")
        # v3 完整结构化 (2026-10-17 设置页「地点显示」模板): 镇/门牌街/门牌
        # 号/最近道路/最近 POI/区划码/推荐串/应答原文随行落库 —— v2 老行
        # 补列默认空, worker 重查 (v bump) 后补齐
        for col in ("township", "street", "number", "road", "poi", "adcode",
                    "rec", "raw"):
            _add_col(conn, "place_names", col, "TEXT NOT NULL DEFAULT ''")
        # v: 地点显示模板三界面 (2026-10-17): 空串 = 默认口径 (不套模板)
        for col in ("place_tpl_trips", "place_tpl_charging", "place_tpl_places"):
            _add_col(conn, "app_settings", col, "TEXT NOT NULL DEFAULT ''")


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
