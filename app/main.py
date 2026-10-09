"""My Tesla 独立部署的装配: 内嵌账号体系 (app/home) + TeslaMate 展示应用 (/tesla/*)。

独立仓 = 从 My Home 组合仓拆出来的自足部署: clone 下来建 .venv,
python -m app 即起 (部署配置全走命令行参数, --help 看全量;
首启无管理员时浏览器打开 /setup 引导注册)。账号归启动方: 经 My Home
组合仓启动时本模块不参与 —— 外层加载 app/tesla 子包挂业务路由, 账号
用组合仓自己的门厅层 (同一枚会话 cookie); 本模块只在独立启动时生效,
自带账号层全量挂上。

数据源: teslamate_cn (PostgreSQL, TeslaMate 标准表结构), 查询全部在
repository 层 (SQLAlchemy, 方言中立); 测试通过 database.init_engine()
注入 SQLite, 不碰真实库。时间处理: 库内为 UTC 裸时间戳, 对外输出本地
时间。鉴权: 登录后签 HMAC 签名的会话 cookie (默认 90 天), 未登录页面跳
/tesla/login (scope 内, 全屏 App 不弹回浏览器露地址栏), API 回 401;
中间件在 app/home/middleware。
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from . import config, database
from .home import STATIC_DIR as HOME_STATIC_DIR
from .home import accounts_api, middleware as home_middleware
from .home import pages as home_pages, session_api
from .models import UsersBase
from .tesla import background, settings_store
from .tesla.models import OwnBase
from .tesla.routers import (charging as charging_routes,
                            changelog as changelog_routes,
                            live as live_routes,
                            map as map_routes, pages,
                            settings as settings_routes,
                            trips as trips_routes)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """启动时建引擎 + 后台预热缓存, 关闭时释放连接池。

    自有库 (SQLite) 的表由应用自己建 (create_all), 与 TeslaMate
    原库 (迁移建的表, 只读) 完全隔离。"""
    # 先建自有库再读设置: TeslaMate 连接可被设置页覆盖 (未设回落 env 定位)
    database.init_own_engine()
    OwnBase.metadata.create_all(database.own_engine())
    database.migrate_own_db()   # create_all 只建新表, 老库补列的配方在 database 包
    # 账号库 (独立文件): 建表即可 —— 空库首启由登录页自动引去 /setup
    # 引导注册管理员 (启动器与 env 都不再种账号)
    database.init_users_engine()
    UsersBase.metadata.create_all(database.users_engine())
    with database.own_session_factory()() as own:   # pylint: disable=not-callable
        url = settings_store.engine_url(own)
    database.init_engine(url)
    # TeslaMate 后台预热/worker (共享配方): 数据源可用即起, 真首启未配则
    # 等向导第二步存好真地址再开 (tesla/background.py)
    background.launch_when_configured()
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
