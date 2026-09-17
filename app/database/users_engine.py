"""账号库 (SQLite, data/users.db) 的引擎: 独立文件, 与业务库分开。

持有者做成小类 (_SqliteState) 是为了错误信息里带上库名; 记账库
(app/bookkeeping/store) 与曲库 (app/music) 各自有同构的一套。"""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .. import config


class _SqliteState:
    """独立 SQLite 库的引擎持有者 (与自有库同构; 记账库在 app/bookkeeping/store)。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.engine: Engine | None = None
        self.factory: sessionmaker[Session] | None = None

    def init(self, url: str | None, default_url: str) -> None:
        """创建引擎 (缺省走 config 里的默认文件, 测试可注入别的 SQLite)。"""
        if url is None:
            url = default_url
        if url.startswith("sqlite:///"):
            parent = Path(url.removeprefix("sqlite:///")).parent
            if str(parent):
                parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url, connect_args={"check_same_thread": False})
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    def dispose(self) -> None:
        """释放连接池 (测试隔离也用它)。"""
        if self.engine is not None:
            self.engine.dispose()
        self.engine = None
        self.factory = None

    def engine_or_fail(self) -> Engine:
        """引擎 (未初始化是装配错误, 直接炸)。"""
        if self.engine is None:
            raise RuntimeError(f"{self.name}库引擎未初始化 (init 未调用)")
        return self.engine

    def session_factory_or_fail(self) -> sessionmaker[Session]:
        """会话工厂 (未初始化是装配错误, 直接炸)。"""
        if self.factory is None:
            raise RuntimeError(f"{self.name}库引擎未初始化 (init 未调用)")
        return self.factory


_users_state = _SqliteState("账号")


def init_users_engine(url: str | None = None) -> None:
    """创建账号库引擎 (缺省 data/users.db)。"""
    _users_state.init(url, config.USERS_DB_URL)


def dispose_users_engine() -> None:
    """释放账号库连接池。"""
    _users_state.dispose()


def users_engine() -> Engine:
    """账号库引擎 (启动时建表用)。"""
    return _users_state.engine_or_fail()


def users_session_factory() -> sessionmaker[Session]:
    """账号库会话工厂。"""
    return _users_state.session_factory_or_fail()


def get_users_db() -> Iterator[Session]:
    """FastAPI 依赖: 每请求一个账号库会话。"""
    with users_session_factory()() as session:  # pylint: disable=not-callable
        yield session
