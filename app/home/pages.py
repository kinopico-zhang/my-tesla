"""账号层的 HTML 页面 (独立仓副本): 登录 + 注册 + 账号管理 + 平台域名
验证文件 (静态文件在 app/home/static)。

独立仓没有门厅页 —— 根路径 / 无条件 302 进 Tesla 应用 (未登录会在
/tesla/charging 被 middleware 再跳一次登录页)。
"""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from . import STATIC_DIR

router = APIRouter()

# 平台域名验证文件 (微信等): 名字带 hash 的 TXT 丢进 verify/ 目录,
# 根路径原样吐回。验证方不带 cookie 来抓, 中间件对非保护路径本来就放行
# (未登录不 302); 文件名只认字母数字连字符, 顺带堵目录穿越。
_VERIFY_DIR = Path(__file__).resolve().parent / "verify"
_VERIFY_NAME = re.compile(r"[0-9A-Za-z-]{1,64}")


def _page(fname: str) -> FileResponse:
    """HTML 页面: 允许缓存但必须带 ETag 重新校验 (no-cache), 更新即时生效。"""
    resp = FileResponse(STATIC_DIR / fname)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@router.get("/", response_class=HTMLResponse)
def root_page() -> RedirectResponse:
    """根路径直接进 Tesla 应用 (独立仓没有门厅)。"""
    return RedirectResponse("/tesla/charging", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page() -> FileResponse:
    """登录页 (与应用 scope 内的 /tesla/login 同一张)。"""
    return _page("login.html")


@router.get("/tesla/login", response_class=HTMLResponse)
def tesla_login_page() -> FileResponse:
    """Tesla 应用 scope 内的登录页: 会话过期 302 过来不越界。"""
    return _page("login.html")


@router.get("/register", response_class=HTMLResponse)
def register_page() -> FileResponse:
    """注册页 (凭邀请令牌进入, 无需登录)。"""
    return _page("register.html")


@router.get("/accounts")
def accounts_page() -> FileResponse:
    """账号管理页 (账号层共享, 仅管理员; 非管理员进来只见提示)。"""
    return _page("accounts.html")


@router.api_route("/{name}.txt", methods=["GET", "HEAD"])
def platform_verify_file(name: str) -> FileResponse:
    """根路径的平台验证 TXT (微信域名验证等): 文件在 verify/ 目录里才吐,
    没有 (或名字不合规) 404 —— 按需部署, 与其余路由一样。"""
    path = _VERIFY_DIR / f"{name}.txt"
    if not _VERIFY_NAME.fullmatch(name) or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)
