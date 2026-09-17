"""账号存取门面 (账号库 users.db): 用户 (scrypt 密码) + 注册邀请。

旧 account_store.py (217 行) 按域拆成包: errors / passwords / users /
invitations; 调用方一律 `from app import account_store` 后按属性取用,
拆分后不变 (结构化重构)。"""
from .errors import InvalidNameError, InvitationError, PasswordError
from .invitations import (
    INVITE_DAYS_CHOICES,
    consume_invitation,
    create_invitation,
    invitation_usable,
    list_invitations,
    revoke_invitation,
)
from .passwords import hash_password, verify_password
from .users import (
    admin_user,
    authenticate,
    create_user,
    ensure_admin,
    find_by_name,
    get_user,
    list_users,
    rename_user,
    set_password,
    user_count,
    user_for_cookie,
)

__all__ = [
    "INVITE_DAYS_CHOICES",
    "InvalidNameError",
    "InvitationError",
    "PasswordError",
    "admin_user",
    "authenticate",
    "consume_invitation",
    "create_invitation",
    "create_user",
    "ensure_admin",
    "find_by_name",
    "get_user",
    "hash_password",
    "invitation_usable",
    "list_invitations",
    "list_users",
    "rename_user",
    "revoke_invitation",
    "set_password",
    "user_count",
    "user_for_cookie",
    "verify_password",
]
