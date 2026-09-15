"""账号存取 (账号库 users.db): 用户 (scrypt 密码) + 注册邀请。

uuid 由后端生成, 全程不出接口 (用户列表 / me 都不带); 名称是唯一登录名,
本人可改; 管理员 (is_admin) 才有账号管理权限, 业务功能所有账号都有。
"""
import hashlib
import hmac
import re
import secrets
import uuid as uuid_module
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import authentication
from .models import Invitation, User

# scrypt 参数: n=2^14 / r=8 / p=1 一次哈希 ~16MB 内存 + 几十毫秒,
# NAS 上可承受, 也足够拖慢离线爆破
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2 ** 14, 8, 1, 32

# 名称: 2~20 个字符, 不含空白/控制符 (可中文/字母/数字/常用符号)
_NAME_RE = re.compile(r"^\S(.*\S)?$", re.S)

INVITE_DAYS_CHOICES = (1, 7, 30)   # 邀请有效期档位 (天)


class InvalidNameError(ValueError):
    """名称不合法 / 已被占用 (路由转 400)。"""


class PasswordError(ValueError):
    """密码不合法 / 旧密码不对 (路由转 400/403)。"""


class InvitationError(ValueError):
    """邀请不可用: 不存在 / 已用 / 过期 / 已撤销 (路由转 400)。"""


def hash_password(password: str) -> str:
    """明文 → "scrypt$<salt>$<hash>"。"""
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(),
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                            dklen=_DKLEN).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """验密码 (常数时间比对; 坏格式一律 False)。"""
    try:
        algo, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        expect = hashlib.scrypt(password.encode(), salt=salt.encode(),
                                n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                                dklen=_DKLEN).hex()
        return hmac.compare_digest(expect, digest)
    except (ValueError, AttributeError):
        return False


def _check_name(name: str) -> str:
    """名称规范: 去空白后 2~20 字符且不含内部空白。"""
    name = (name or "").strip()
    if not 2 <= len(name) <= 20 or not _NAME_RE.match(name) or any(c.isspace() for c in name):
        raise InvalidNameError("名称需 2~20 个字符, 且不含空格")
    return name


def _check_password(password: str) -> str:
    if not 6 <= len(password or "") <= 64:
        raise PasswordError("密码需 6~64 个字符")
    return password


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


# ---------------------------------------------------------------- 注册邀请

def create_invitation(session: Session, days: int) -> Invitation:
    """签发邀请 (一次一用; days 限 INVITE_DAYS_CHOICES 档位)。"""
    if days not in INVITE_DAYS_CHOICES:
        raise InvitationError("有效期只支持 1 / 7 / 30 天")
    now = datetime.utcnow()
    invitation = Invitation(
        token=secrets.token_urlsafe(24), created_at=now,
        expires_at=now + timedelta(days=days))
    session.add(invitation)
    session.commit()
    return invitation


def invitation_usable(session: Session, token: str) -> Invitation:
    """取邀请并校验可用性 (不存在/已用/过期/撤销都抛 InvitationError)。"""
    invitation = session.get(Invitation, token or "")
    if invitation is None:
        raise InvitationError("邀请链接无效")
    if invitation.revoked:
        raise InvitationError("邀请链接已被撤销")
    if invitation.used_at is not None:
        raise InvitationError("邀请链接已被使用")
    if invitation.expires_at <= datetime.utcnow():
        raise InvitationError("邀请链接已过期")
    return invitation


def consume_invitation(session: Session, token: str) -> Invitation:
    """取可用邀请并标记已用 (注册成功时调用)。"""
    invitation = invitation_usable(session, token)
    invitation.used_at = datetime.utcnow()
    session.commit()
    return invitation


def revoke_invitation(session: Session, token: str) -> bool:
    """撤销未使用的邀请 (已用/不存在的返回 False, 撤销成功 True)。"""
    invitation = session.get(Invitation, token or "")
    if invitation is None or invitation.used_at is not None or invitation.revoked:
        return False
    invitation.revoked = True
    session.commit()
    return True


def list_invitations(session: Session) -> list[Invitation]:
    """全部邀请 (签发时间倒序)。"""
    invitations = session.execute(select(Invitation)).scalars().all()
    return sorted(invitations, key=lambda i: i.created_at, reverse=True)
