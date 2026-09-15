"""My Tesla —— API 路由层 (薄)。

数据源: teslamate_cn (PostgreSQL, TeslaMate 标准表结构), 查询全部在
repository 层 (SQLAlchemy, 方言中立); 测试通过 database.init_engine()
注入 SQLite, 不碰真实库。
时间处理: 库内为 UTC 裸时间戳, 对外输出本地时间 (默认 Asia/Shanghai)。
鉴权: 登录后签发 HMAC 签名的会话 cookie (默认 90 天), 未登录页面跳
应用 scope 内自己的登录页 (/tesla/login), API 回 401。
"""
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Awaitable, Callable
from urllib.parse import quote

from fastapi import (APIRouter, Depends, FastAPI, HTTPException,
                     Request, Response)
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import (account_store, authentication, config, database)
from .tesla.repository import to_local
from .tesla.routers import (charging as charging_routes,
                            changelog as changelog_routes,
                            live as live_routes,
                            map as map_routes, pages,
                            settings as settings_routes,
                            trips as trips_routes)
from .tesla import settings_store, tracks_cache
from .models import User, UsersBase
from .tesla.models import OwnBase
from .schemas import (
    AccountNameUpdate,
    AccountPasswordUpdate,
    InvitationCreated,
    InvitationItem,
    InvitationRequest,
    MeInfo,
    RegisterCredentials,
    UserItem,
    LoginCredentials,
    OkResponse,
)

# 账号管理 API (页面: /accounts, 仅管理员)
accounts = APIRouter(prefix="/accounts/api")


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
    with database.users_session_factory()() as users:
        account_store.ensure_admin(users, config.AUTH_USER, config.AUTH_PASS)
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


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
        _: Request, exc: SQLAlchemyError) -> JSONResponse:
    """数据库异常统一 503 (与旧版 query() 包装行为一致)。"""
    return JSONResponse({"detail": f"数据库查询失败: {exc}"}, status_code=503)


# 无需登录即可访问的路径: 登录/注册页及其接口 (邀请令牌本身就是凭证);
# 登出只清 cookie, 不需要有效会话
_PUBLIC_PATHS = frozenset((
    "/login", "/register",
    # 应用 scope 内的登录页 (scope 收窄, 登录页跟进去, 会话过期 302
    # 不越出 scope, 全屏 App 不弹回 Safari 露地址栏)
    "/tesla/login",
    "/api/login", "/api/logout",
    "/api/register", "/api/invite-status"))
_STATIC_PREFIXES = ("/static/", "/tesla/static/")

# 账号体系从 /tesla 搬到根路径 (账号跟着应用走, 不在业务路由前缀下);
# 旧地址 302/307 兼容 —— 手机上的老书签和已经发出去的邀请链接还能用
_MOVED_PAGES = {
    "/tesla/register": "/register",
    "/tesla/accounts": "/accounts",
}
_MOVED_APIS = {
    "/tesla/api/login": "/api/login",
    "/tesla/api/logout": "/api/logout",
    "/tesla/api/register": "/api/register",
    "/tesla/api/invite-status": "/api/invite-status",
    "/tesla/api/me": "/api/me",
    "/tesla/api/account/name": "/api/account/name",
    "/tesla/api/account/password": "/api/account/password",
}


def _moved_target(path: str) -> str | None:
    """旧地址 → 新地址 (没搬过的返回 None); 查询串由中间件续上。"""
    new = _MOVED_PAGES.get(path) or _MOVED_APIS.get(path)
    if new is None and path.startswith("/tesla/accounts/api/"):
        new = "/accounts/api/" + path[len("/tesla/accounts/api/"):]
    return new


# 应用登录页 → 登录后回哪 (登录页在应用 scope 内, 已登录的访客直接回应用)
_APP_LOGIN_ROOTS = {
    "/tesla/login": "/tesla/charging",
}


def _login_redirect(path: str, query: str) -> str:
    """未登录页面 302 到应用 scope 内的登录页, 带上原地址 (登录完回去)。

    不能全站跳根路径 /login —— 那会越出应用 scope (全屏 App 弹回
    Safari 露地址栏)。账号层页面 (/, /accounts) 没有 scope 问题,
    仍是 /login。"""
    target = "/tesla/login" if (path == "/tesla"
                                or path.startswith("/tesla/")) else "/login"
    if path != target:
        origin = path + (("?" + query) if query else "")
        target += "?next=" + quote(origin, safe="")
    return target


def _is_protected(path: str) -> bool:
    """保护面: 应用 (/tesla) + 账号管理页 (/accounts) + 账号接口 (me / 自助改)。"""
    if path == "/" or path.startswith(("/tesla", "/accounts")):
        return True
    return path == "/api/me" or path.startswith("/api/account/")


@app.middleware("http")
async def auth_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """旧地址搬家重定向; 页面未登录跳登录页, API 未登录 401; 静态放行 + 缓存策略。"""
    path = request.url.path
    moved = _moved_target(path)
    if moved is not None:
        if request.url.query:
            moved += "?" + request.url.query
        # 接口用 307 保住方法与请求体, 页面 302 即可
        api_move = moved.startswith(("/api/", "/accounts/api/"))
        return RedirectResponse(moved, status_code=307 if api_move else 302)
    token_ok = authentication.check_token(request.cookies.get("auth", ""))
    protected = _is_protected(path)
    is_api = protected and "/api/" in path
    resp: Response
    if path == "/login" and token_ok:
        # 已登录的访客不再看表单, 直接进应用
        resp = RedirectResponse("/tesla/charging", status_code=302)
    elif path in _APP_LOGIN_ROOTS and token_ok:
        # 应用自己的登录页: 已登录直接回该应用
        resp = RedirectResponse(_APP_LOGIN_ROOTS[path], status_code=302)
    elif path in _PUBLIC_PATHS or path.startswith(_STATIC_PREFIXES):
        resp = await call_next(request)
    elif is_api and not token_ok:
        resp = JSONResponse({"detail": "未登录"}, status_code=401)
    elif protected and not is_api and not token_ok:
        resp = RedirectResponse(_login_redirect(path, request.url.query),
                                status_code=302)
    else:
        resp = await call_next(request)
    if is_api:
        # API 数据 (如 map config) 禁止缓存, 否则配置更新后浏览器仍用旧响应
        resp.headers["Cache-Control"] = "no-store"
    elif path.startswith(_STATIC_PREFIXES):
        # JS 工具 (trackutil 等) 迭代频繁, 必须重新校验; ETag 命中时 304 很便宜。
        # 只发 Last-Modified 时浏览器走启发式缓存, 会继续用旧 JS (动画因此冻住过)。
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def _page(fname: str) -> FileResponse:
    """账号体系页面 (登录/注册/账号管理): 允许缓存但必须带 ETag 重新校验
    (no-cache), 更新即时生效。应用页面在 tesla 包的 pages 路由。"""
    resp = FileResponse(config.SHARED_STATIC_DIR / fname)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# --------------------------------------------- 根路径 / 登录 / 注册 / 账号管理

@app.get("/")
def root_redirect() -> RedirectResponse:
    """根路径收口到应用默认页 (独立应用, 单一入口)。"""
    return RedirectResponse("/tesla/charging", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page() -> FileResponse:
    """登录页 (My Tesla 的门, 全站唯一)。"""
    return _page("login.html")


@app.get("/tesla/login", response_class=HTMLResponse)
def tesla_login_page() -> FileResponse:
    """Tesla 应用 scope 内的登录页 (同一张): 会话过期 302 过来不越界。"""
    return _page("login.html")


def _set_session_cookie(resp: JSONResponse, user_uuid: str) -> None:
    """会话 cookie 签到 path=/ (账号 + 应用全站通用)。

    单用户时代的旧 cookie path 限定 /tesla, 同名残留会让浏览器在 /tesla
    下优先送旧值 —— 设置新 cookie 前先删掉它。"""
    resp.delete_cookie("auth", path="/tesla")
    resp.set_cookie("auth", authentication.make_token(user_uuid),
                    max_age=config.SESSION_DAYS * 86400, httponly=True,
                    samesite="lax", path="/")


@app.post("/api/login")
def login(creds: LoginCredentials, request: Request,
          users: Session = Depends(database.get_users_db)) -> JSONResponse:
    """校验账密 (账号库, 带单 IP 限速), 签发会话 cookie。"""
    ip = request.client.host if request.client else "?"
    if authentication.ip_locked(ip):
        raise HTTPException(
            429, f"尝试次数过多, 请 {config.LOGIN_LOCK_S} 秒后再试")
    user = account_store.authenticate(users, creds.user, creds.password)
    if user is None:
        authentication.record_fail(ip)
        raise HTTPException(401, "账号或密码错误")
    authentication.clear_fails(ip)
    resp = JSONResponse(OkResponse(ok=True).model_dump())
    _set_session_cookie(resp, user.uuid)
    return resp


@app.post("/api/logout")
def logout() -> JSONResponse:
    """登出 (清本设备的 cookie; 其他设备/其他人不受影响)。"""
    resp = JSONResponse(OkResponse(ok=True).model_dump())
    resp.delete_cookie("auth", path="/tesla")   # 单用户时代的旧 path cookie
    resp.delete_cookie("auth", path="/")
    return resp


def _current_user(request: Request, users: Session) -> User | None:
    """会话 cookie → 账号 (逻辑在账号库)。"""
    return account_store.user_for_cookie(request.cookies.get("auth", ""), users)


def _require_user(request: Request, users: Session) -> User:
    """已登录账号, 否则 401。"""
    user = _current_user(request, users)
    if user is None:
        raise HTTPException(401, "未登录")
    return user


def _require_admin(request: Request, users: Session) -> User:
    """管理员账号, 否则 401/403 (账号管理只有管理员能碰)。"""
    user = _require_user(request, users)
    if not user.is_admin:
        raise HTTPException(403, "仅管理员可管理账号")
    return user


@app.get("/register")
def register_page() -> FileResponse:
    """注册页 (凭邀请令牌进入, 无需登录)。"""
    return _page("register.html")


@app.get("/api/invite-status")
def invite_status(invite: str,
                  users: Session = Depends(database.get_users_db)) -> OkResponse:
    """邀请令牌是否可用 (注册页进页即查, 坏链接直接说原因)。"""
    try:
        account_store.invitation_usable(users, invite)
    except account_store.InvitationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return OkResponse(ok=True)


@app.post("/api/register")
def register(creds: RegisterCredentials, request: Request,
             users: Session = Depends(database.get_users_db)) -> JSONResponse:
    """凭邀请注册账号 (一次一用), 注册即登录。"""
    ip = request.client.host if request.client else "?"
    if authentication.ip_locked(ip):
        raise HTTPException(
            429, f"尝试次数过多, 请 {config.LOGIN_LOCK_S} 秒后再试")
    try:
        account_store.invitation_usable(users, creds.invite)
        user = account_store.create_user(users, creds.name, creds.password)
        account_store.consume_invitation(users, creds.invite)
    except (account_store.InvalidNameError, account_store.PasswordError,
            account_store.InvitationError) as exc:
        raise HTTPException(400, str(exc)) from exc
    authentication.clear_fails(ip)
    resp = JSONResponse(OkResponse(ok=True).model_dump())
    _set_session_cookie(resp, user.uuid)
    return resp


@app.get("/api/me", response_model=MeInfo)
def me(request: Request,
       users: Session = Depends(database.get_users_db)) -> MeInfo:
    """当前会话账号 (名称 + 是否管理员; uuid 不出接口)。"""
    user = _require_user(request, users)
    return MeInfo(name=user.name, is_admin=user.is_admin)


@app.post("/api/account/name", response_model=MeInfo)
def account_change_name(body: AccountNameUpdate, request: Request,
                        users: Session = Depends(database.get_users_db)) -> MeInfo:
    """自助改登录名 (uuid 不变, 会话不掉线)。"""
    user = _require_user(request, users)
    try:
        account_store.rename_user(users, user, body.name)
    except account_store.InvalidNameError as exc:
        raise HTTPException(400, str(exc)) from exc
    return MeInfo(name=user.name, is_admin=user.is_admin)


@app.post("/api/account/password", response_model=OkResponse)
def account_change_password(body: AccountPasswordUpdate, request: Request,
                            users: Session = Depends(database.get_users_db)) -> OkResponse:
    """自助改密码 (先验旧密码; 会话不受影响)。"""
    user = _require_user(request, users)
    try:
        account_store.set_password(users, user,
                                   body.old_password, body.new_password)
    except account_store.PasswordError as exc:
        raise HTTPException(400, str(exc)) from exc
    return OkResponse(ok=True)


# ---------------------------------------------------------------- 账号管理 API

@accounts.get("/users", response_model=list[UserItem])
def accounts_list_users(request: Request,
                        users: Session = Depends(database.get_users_db)) -> list[UserItem]:
    """账号列表 (仅管理员; uuid 不出接口)。"""
    _require_admin(request, users)
    return [UserItem(name=u.name, is_admin=u.is_admin,
                     created_at=to_local(u.created_at))
            for u in account_store.list_users(users)]


@accounts.post("/invitations", response_model=InvitationCreated)
def accounts_create_invitation(body: InvitationRequest, request: Request,
                               users: Session = Depends(database.get_users_db)
                               ) -> InvitationCreated:
    """签发注册邀请 (仅管理员; 前端拼 /register?invite= 链接分享)。"""
    _require_admin(request, users)
    try:
        invitation = account_store.create_invitation(users, body.days)
    except account_store.InvitationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return InvitationCreated(token=invitation.token,
                             expires_at=to_local(invitation.expires_at))


@accounts.get("/invitations", response_model=list[InvitationItem])
def accounts_list_invitations(request: Request,
                              users: Session = Depends(database.get_users_db)
                              ) -> list[InvitationItem]:
    """邀请列表 (仅管理员, 签发时间倒序)。"""
    _require_admin(request, users)
    return [InvitationItem(token=i.token, created_at=to_local(i.created_at),
                           expires_at=to_local(i.expires_at),
                           used_at=to_local(i.used_at) if i.used_at else None,
                           revoked=i.revoked)
            for i in account_store.list_invitations(users)]


@accounts.delete("/invitations/{token}", response_model=OkResponse)
def accounts_revoke_invitation(token: str, request: Request,
                               users: Session = Depends(database.get_users_db)) -> OkResponse:
    """撤销未使用的邀请 (仅管理员)。"""
    _require_admin(request, users)
    if not account_store.revoke_invitation(users, token):
        raise HTTPException(400, "邀请不存在或已被使用")
    return OkResponse(ok=True)


@app.get("/accounts")
def accounts_page() -> FileResponse:
    """账号管理页 (仅管理员; 非管理员进来只见提示)。"""
    return _page("accounts.html")


# My Tesla: 路由全在 tesla 包 (URL 前缀与旧版一致)
app.include_router(pages.router)
app.include_router(charging_routes.charging)
app.include_router(map_routes.mapapi)
app.include_router(trips_routes.trips)
app.include_router(live_routes.live)
app.include_router(settings_routes.settingsapi)
app.include_router(changelog_routes.changelogapi)
# 账号管理
app.include_router(accounts)
app.mount("/static", StaticFiles(directory=config.SHARED_STATIC_DIR), name="shared-static")
app.mount("/tesla/static", StaticFiles(directory=config.STATIC_DIR), name="static")
