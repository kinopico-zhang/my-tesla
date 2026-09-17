"""账号会话接口 (/api/*): 登录/登出 + 凭邀请注册 + 当前账号 (me) 与自助改。

会话是 HMAC 签名的 cookie (默认 90 天), 门厅与三个应用全站通用;
登录/注册接口带单 IP 限速 (authentication)。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import account_store, authentication, config, database
from ..models import User
from ..schemas import (
    AccountNameUpdate,
    AccountPasswordUpdate,
    LoginCredentials,
    MeInfo,
    OkResponse,
    RegisterCredentials,
)

api = APIRouter(prefix="/api")


def _set_session_cookie(resp: JSONResponse, user_uuid: str) -> None:
    """会话 cookie 签到 path=/ (门厅 + 三个应用全站通用)。

    单用户时代的旧 cookie path 限定 /tesla, 同名残留会让浏览器在 /tesla
    下优先送旧值 —— 设置新 cookie 前先删掉它。"""
    resp.delete_cookie("auth", path="/tesla")
    resp.set_cookie("auth", authentication.make_token(user_uuid),
                    max_age=config.SESSION_DAYS * 86400, httponly=True,
                    samesite="lax", path="/")


def _current_user(request: Request, users: Session) -> User | None:
    """会话 cookie → 账号 (逻辑在账号库, 各应用共用)。"""
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


@api.post("/login")
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


@api.post("/logout")
def logout() -> JSONResponse:
    """登出 (清本设备的 cookie; 其他设备/其他人不受影响)。"""
    resp = JSONResponse(OkResponse(ok=True).model_dump())
    resp.delete_cookie("auth", path="/tesla")   # 单用户时代的旧 path cookie
    resp.delete_cookie("auth", path="/")
    return resp


@api.get("/invite-status")
def invite_status(invite: str,
                  users: Session = Depends(database.get_users_db)) -> OkResponse:
    """邀请令牌是否可用 (注册页进页即查, 坏链接直接说原因)。"""
    try:
        account_store.invitation_usable(users, invite)
    except account_store.InvitationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return OkResponse(ok=True)


@api.post("/register")
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


@api.get("/me", response_model=MeInfo)
def me(request: Request,
       users: Session = Depends(database.get_users_db)) -> MeInfo:
    """当前会话账号 (名称 + 是否管理员; uuid 不出接口)。"""
    user = _require_user(request, users)
    return MeInfo(name=user.name, is_admin=user.is_admin)


@api.post("/account/name", response_model=MeInfo)
def account_change_name(body: AccountNameUpdate, request: Request,
                        users: Session = Depends(database.get_users_db)) -> MeInfo:
    """自助改登录名 (uuid 不变, 会话不掉线)。"""
    user = _require_user(request, users)
    try:
        account_store.rename_user(users, user, body.name)
    except account_store.InvalidNameError as exc:
        raise HTTPException(400, str(exc)) from exc
    return MeInfo(name=user.name, is_admin=user.is_admin)


@api.post("/account/password", response_model=OkResponse)
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
