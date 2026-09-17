"""账号层 HTTP 中间件 (独立仓副本): 旧地址搬家重定向 + 登录拦截
(页面 302 / API 401) + 静态放行与缓存策略。挂在主应用上 (app.middleware)。

与 My Home 组合仓的差别只在路径表: 这里只有 Tesla 应用一个 scope, 没有
门厅层。旧地址搬家重定向保留 —— 那是账号体系还在 /tesla 下的历史包袱,
手机上的老书签和已经发出去的邀请链接还能用。
"""
from typing import Awaitable, Callable
from urllib.parse import quote

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from .. import authentication

# 无需登录即可访问的路径: 登录/注册页及其接口 (邀请令牌本身就是凭证);
# 登出只清 cookie, 不需要有效会话 (旧地址 /tesla/api/* 先被搬家重定向
# 到新地址, 再走这里的判断)
_PUBLIC_PATHS = frozenset((
    "/login", "/register",
    # 应用 scope 内的登录页 (会话过期 302 不越出 scope, 全屏 App 不弹回
    # Safari 露地址栏)
    "/tesla/login",
    "/api/login", "/api/logout",
    "/api/register", "/api/invite-status"))
_STATIC_PREFIXES = ("/static/", "/tesla/static/")

# 账号体系从 /tesla 搬到根路径 (账号属于 My Home, 不属于任何一个应用);
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
_APP_LOGIN_ROOTS = {"/tesla/login": "/tesla/charging"}


def _login_redirect(path: str, query: str) -> str:
    """未登录页面 302 到当前 scope 内的登录页, 带上原地址 (登录完回去)。

    应用页 (/tesla…) 跳 /tesla/login (scope 内); 账号管理页 (/accounts)
    没有 scope 问题, 跳根路径 /login。"""
    target = "/tesla/login" if path == "/tesla" or path.startswith("/tesla/") \
        else "/login"
    if path != target:
        origin = path + (("?" + query) if query else "")
        target += "?next=" + quote(origin, safe="")
    return target


def _is_protected(path: str) -> bool:
    """保护面: Tesla 应用 (/tesla) + 账号管理页 + 账号接口 (me / 自助改)。

    根路径 / 不在其中 —— 它是无条件的 302 进 /tesla/charging (见 pages.py)。"""
    if path.startswith("/tesla") or path == "/accounts":
        return True
    return path == "/api/me" or path.startswith("/api/account/")


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
        # 已登录的访客不再看表单, 直接进应用 (独立仓没有门厅)
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
