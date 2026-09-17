"""账号的增查改 (账号库 users.db 的 users 表)。

uuid 由后端生成, 全程不出接口 (用户列表 / me 都不带); 名称是唯一登录名,
本人可改; 管理员 (is_admin) 才有账号管理权限, 业务功能所有账号都有。"""
import uuid as uuid_module
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import authentication
from ..models import User
from .errors import InvalidNameError, PasswordError
from .passwords import _check_name, _check_password, hash_password, verify_password


def user_count(session: Session) -> int:
    """账号总数 (启动时判断要不要种管理员)。"""
    return len(session.execute(select(User.uuid)).all())


def create_user(session: Session, name: str, password: str, *,
                is_admin: bool = False) -> User:
    """建账号 (名称唯一; uuid 后端生成)。"""
    name = _check_name(name)
    _check_password(password)
    if find_by_name(session, name) is not None:
        raise InvalidNameError("这个名称已被占用")
    user = User(uuid=uuid_module.uuid4().hex, name=name,
                password_hash=hash_password(password),
                is_admin=is_admin, created_at=datetime.utcnow())
    session.add(user)
    session.commit()
    return user


def ensure_admin(session: Session, name: str, password: str) -> None:
    """账号库为空时种入管理员 (env 账密; 只种一次, 之后走界面改)。"""
    if user_count(session) == 0:
        create_user(session, name, password, is_admin=True)


def find_by_name(session: Session, name: str) -> User | None:
    """按登录名精确找。"""
    return session.execute(
        select(User).where(User.name == name)).scalar_one_or_none()


def get_user(session: Session, user_uuid: str) -> User | None:
    """按 uuid 找 (会话解析用)。"""
    return session.get(User, user_uuid)


def admin_user(session: Session) -> User | None:
    """管理员账号 (旧版 cookie 的虚拟身份落到它)。"""
    return session.execute(
        select(User).where(User.is_admin)).scalar_one_or_none()


def user_for_cookie(cookie: str, users: Session) -> User | None:
    """会话 cookie → 账号 (My Tesla 与家庭记账两个应用共用的入口;
    旧版两段 cookie 按管理员会话处理)。"""
    user_uuid = authentication.check_token(cookie)
    if user_uuid is None:
        return None
    if user_uuid == authentication.LEGACY_ADMIN:
        return admin_user(users)
    return get_user(users, user_uuid)


def authenticate(session: Session, name: str, password: str) -> User | None:
    """登录校验: 名称存在 + 密码匹配。"""
    user = find_by_name(session, name)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def rename_user(session: Session, user: User, new_name: str) -> User:
    """改登录名 (唯一性校验; uuid 不动 → 会话不掉线)。"""
    new_name = _check_name(new_name)
    other = find_by_name(session, new_name)
    if other is not None and other.uuid != user.uuid:
        raise InvalidNameError("这个名称已被占用")
    user.name = new_name
    session.commit()
    return user


def set_password(session: Session, user: User,
                 old_password: str, new_password: str) -> None:
    """自助改密码 (先验旧密码)。"""
    if not verify_password(old_password, user.password_hash):
        raise PasswordError("旧密码不正确")
    _check_password(new_password)
    user.password_hash = hash_password(new_password)
    session.commit()


def list_users(session: Session) -> list[User]:
    """全部账号 (管理员在前, 其余按创建先后)。"""
    users = session.execute(select(User)).scalars().all()
    return sorted(users, key=lambda u: (not u.is_admin, u.created_at))
