"""TeslaMate 生产库 (PostgreSQL) 的引擎: 容器定位 + 连接串 + 会话。

生产库是 TeslaMate 迁移建的表 (只读 + 费用回写一处), 引擎在 lifespan
里初始化; 测试通过 init_engine() 注入 SQLite, 不碰真实数据库。"""
import os
import shutil
import subprocess
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

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
