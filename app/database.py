"""数据库引擎: 定位 teslamate_cn 的 Postgres 容器并建立 SQLAlchemy 引擎。

生产库是 TeslaMate 迁移建的表 (只读 + 费用回写一处), 引擎在 lifespan
里初始化; 测试通过 init_engine() 注入 SQLite, 不碰真实数据库。

自有库 (SQLite, 断档补路等 app 自产数据) 走第二套引擎 init_own_engine(),
与 TeslaMate 库完全隔离。
"""
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config

DB_CONTAINER = os.environ.get("TMDB_CONTAINER", "teslamate_cn_database_1")

# QNAP Container Station 的 docker 不在 PATH 里, 按顺序尝试
DOCKER_BIN_CANDIDATES = [
    os.environ.get("DOCKER_BIN", ""),
    "/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker",
    shutil.which("docker") or "",
]


class _EngineState:
    """进程级引擎持有者 (避免 global 语句)。"""

    engine: Engine | None = None
    factory: sessionmaker[Session] | None = None


def resolve_db_host() -> str:
    """解析数据库容器 IP: 环境变量 > docker inspect。"""
    host = os.environ.get("TMDB_HOST")
    if host:
        return host
    for bin_path in filter(None, DOCKER_BIN_CANDIDATES):
        try:
            out = subprocess.check_output(
                [bin_path, "inspect", DB_CONTAINER, "--format",
                 "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
                text=True, timeout=10, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if out:
            return out
    raise RuntimeError(
        f"无法定位数据库容器 {DB_CONTAINER}，请设置 TMDB_HOST 环境变量指向 PostgreSQL 地址")


def build_db_url(overrides: dict[str, str] | None = None) -> str:
    """拼接 SQLAlchemy 连接串: 设置页字段 > env > docker 容器定位。"""
    ov = {k: v for k, v in (overrides or {}).items() if v}   # 空串 = 未设, 走下层
    user = ov.get("user") or os.environ.get("TMDB_USER", "teslamate")
    password = ov.get("password") or os.environ.get("TMDB_PASS", "123456")
    host = ov.get("host") or os.environ.get("TMDB_HOST") or resolve_db_host()
    port = ov.get("port") or os.environ.get("TMDB_PORT", "5432")
    name = ov.get("name") or os.environ.get("TMDB_NAME", "teslamate")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def init_engine(url: str | None = None) -> None:
    """创建引擎与会话工厂 (url 缺省走 TeslaMate Postgres 定位逻辑)。"""
    if url is None:
        url = build_db_url()
    connect_args = ({"connect_timeout": 10} if url.startswith("postgresql")
                    else {})  # SQLite (测试) 不认 postgres 专属参数
    _EngineState.engine = create_engine(
        url, pool_size=4, max_overflow=2, pool_pre_ping=True,
        connect_args=connect_args)
    _EngineState.factory = sessionmaker(_EngineState.engine, expire_on_commit=False)


def rebuild_engine(url: str) -> None:
    """换库重连 (设置页保存 TeslaMate 连接后调用): 旧池释放, 新引擎顶上。

    进行中的请求还攥着旧会话, dispose 只关空闲连接, 不打断它们。"""
    dispose_engine()
    init_engine(url)


def dispose_engine() -> None:
    """释放连接池并清空持有者 (测试隔离也用它)。"""
    if _EngineState.engine is not None:
        _EngineState.engine.dispose()
    _EngineState.engine = None
    _EngineState.factory = None


def engine() -> Engine:
    """当前引擎 (建表等底层操作用)。"""
    if _EngineState.engine is None:
        raise RuntimeError("数据库引擎未初始化 (init_engine 未调用)")
    return _EngineState.engine


def session_factory() -> sessionmaker[Session]:
    """会话工厂 (后台线程等非请求场景用; 路由内请用 get_db 依赖)。"""
    if _EngineState.factory is None:
        raise RuntimeError("数据库引擎未初始化 (init_engine 未调用)")
    return _EngineState.factory


def get_db() -> Iterator[Session]:
    """FastAPI 依赖: 每请求一个会话, 请求结束自动关闭。"""
    factory = session_factory()
    with factory() as session:  # pylint: disable=not-callable
        yield session


# ---------------------------------------------------------------- 自有库

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


# ------------------------------------------------- 账号库 (独立文件)

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
