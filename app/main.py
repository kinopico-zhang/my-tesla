"""My Tesla 独立部署的装配: 内嵌账号体系 (app/home) + TeslaMate 展示应用 (/tesla/*)。

独立仓 = 从 My Home 组合仓拆出来的自足部署: clone 下来建 .venv 与
.env (至少 AUTH_PASS, 见 .env.example), ./run.sh 即起。My Home 组合
部署时本模块不参与 —— 外层加载 app/tesla 子包挂自己的路由, 账号体系
用组合仓自己的门厅层 (同一枚会话 cookie)。

数据源: teslamate_cn (PostgreSQL, TeslaMate 标准表结构), 查询全部在
repository 层 (SQLAlchemy, 方言中立); 测试通过 database.init_engine()
注入 SQLite, 不碰真实库。时间处理: 库内为 UTC 裸时间戳, 对外输出本地
时间。鉴权: 登录后签 HMAC 签名的会话 cookie (默认 90 天), 未登录页面跳
/tesla/login (scope 内, 全屏 App 不弹回浏览器露地址栏), API 回 401;
中间件在 app/home/middleware。
"""
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from . import account_store, config, database
from .home import STATIC_DIR as HOME_STATIC_DIR
from .home import accounts_api, middleware as home_middleware
from .home import pages as home_pages, session_api
from .models import UsersBase
from .tesla import settings_store, tracks_cache
from .tesla.models import OwnBase
from .tesla.routers import (charging as charging_routes,
                            changelog as changelog_routes,
                            live as live_routes,
                            map as map_routes, pages,
                            settings as settings_routes,
                            trips as trips_routes)


def _migrate_own_db() -> None:
    """create_all 只建新表不改旧表: 已有生产库要补的列写在这里 (幂等)。"""
    with database.own_engine().begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(app_settings)")}
        if "amap_style" not in cols:   # v: 高德地图样式 (设置页可换, 三页地图共用)
            conn.exec_driver_sql(
                "ALTER TABLE app_settings ADD COLUMN amap_style TEXT NOT NULL DEFAULT ''")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """启动时建引擎 + 后台预热缓存, 关闭时释放连接池。

    自有库 (SQLite) 的表由应用自己建 (create_all), 与 TeslaMate
    原库 (迁移建的表, 只读) 完全隔离。"""
    # 先建自有库再读设置: TeslaMate 连接可被设置页覆盖 (未设回落 env 定位)
    database.init_own_engine()
    OwnBase.metadata.create_all(database.own_engine())
    _migrate_own_db()
    # 账号库 (独立文件): 首启种管理员 (env 账密, 之后走界面改)
    database.init_users_engine()
    UsersBase.metadata.create_all(database.users_engine())
    if config.AUTH_PASS:
        with database.users_session_factory()() as users:  # pylint: disable=not-callable
            account_store.ensure_admin(users, config.AUTH_USER, config.AUTH_PASS)
    else:
        print("AUTH_PASS 未设置: 首启不种管理员 —— 在 .env 里设 AUTH_PASS 后重启",
              file=sys.stderr)
    with database.own_session_factory()() as own:   # pylint: disable=not-callable
        url = settings_store.engine_url(own)
    database.init_engine(url)
    # 后台预热轨迹缓存 (全量下采样 ~15s, 不阻塞启动)
    threading.Thread(target=tracks_cache.warm,
                     args=(database.session_factory(),), daemon=True).start()
    yield
    database.dispose_engine()
    database.dispose_own_engine()
    database.dispose_users_engine()


app = FastAPI(title="My Tesla", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2048)   # 轨迹 JSON 压缩 ~5x
app.middleware("http")(home_middleware.auth_middleware)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
        _: Request, exc: SQLAlchemyError) -> JSONResponse:
    """数据库异常统一 503 (与旧版 query() 包装行为一致)。"""
    return JSONResponse({"detail": f"数据库查询失败: {exc}"}, status_code=503)


# 账号体系 (门厅共享层的独立仓副本): 登录/注册页面 + 会话接口 + 账号管理
app.include_router(home_pages.router)
app.include_router(session_api.api)
app.include_router(accounts_api.accounts)
# Tesla 应用: 路由全在 tesla 包 (URL 前缀与组合部署一致)
app.include_router(pages.router)
app.include_router(charging_routes.charging)
app.include_router(map_routes.mapapi)
app.include_router(trips_routes.trips)
app.include_router(live_routes.live)
app.include_router(settings_routes.settingsapi)
app.include_router(changelog_routes.changelogapi)
app.mount("/static", StaticFiles(directory=HOME_STATIC_DIR), name="home-static")
app.mount("/tesla/static", StaticFiles(directory=config.STATIC_DIR), name="static")
