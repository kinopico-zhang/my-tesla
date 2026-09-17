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
        url, connect_args={"check_same_thread": False})   # 请求线程池会换线程复用连接
    _OwnEngineState.factory = sessionmaker(_OwnEngineState.engine,
                                           expire_on_commit=False)


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
