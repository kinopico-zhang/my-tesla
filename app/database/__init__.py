"""数据库引擎门面: 三套引擎 (TeslaMate 生产库 / 自有库 / 账号库)。

旧 database.py (231 行) 按库拆成包: teslamate_engine / own_engine /
users_engine; 调用方一律 `from app import database` 后按属性取用,
拆分后不变 (结构化重构)。"""
from .own_engine import (
    dispose_own_engine,
    get_own_db,
    init_own_engine,
    own_engine,
    own_session_factory,
    _OwnEngineState,
)
from .teslamate_engine import (
    DB_CONTAINER,
    DOCKER_BIN_CANDIDATES,
    build_db_url,
    dispose_engine,
    engine,
    get_db,
    init_engine,
    rebuild_engine,
    resolve_db_host,
    session_factory,
    _EngineState,
)
from .users_engine import (
    dispose_users_engine,
    get_users_db,
    init_users_engine,
    users_engine,
    users_session_factory,
)

__all__ = [
    "DB_CONTAINER",
    "DOCKER_BIN_CANDIDATES",
    # 私有持有者类也走门面 (测试隔离直接拨它的属性; 名单见 tests/test_defensive_paths.py)
    "_EngineState",
    "_OwnEngineState",
    "build_db_url",
    "dispose_engine",
    "dispose_own_engine",
    "dispose_users_engine",
    "engine",
    "get_db",
    "get_own_db",
    "get_users_db",
    "init_engine",
    "init_own_engine",
    "init_users_engine",
    "own_engine",
    "own_session_factory",
    "rebuild_engine",
    "resolve_db_host",
    "session_factory",
    "users_engine",
    "users_session_factory",
]
