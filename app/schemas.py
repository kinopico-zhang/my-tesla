"""账号与更新日志的接口模型。

应用业务模型在 app/tesla/schemas.py; `from` 是 Python 关键字,
字段名用 from_ + alias="from"。
"""
from datetime import datetime

from pydantic import BaseModel


class ChangelogItem(BaseModel):
    """更新日志的一条改动 (用户视角的一句话)。"""
    kind: str                  # 新增 | 改进 | 修复
    text: str

class ChangelogVersion(BaseModel):
    """更新日志的一个版本: 一批改动的合并。"""
    version: str               # x.y.z: x 大改版, y 新功能, z 问题修复
    date: str                  # 批次日期 YYYY-MM-DD
    items: list[ChangelogItem]

class OkResponse(BaseModel):
    """通用 ok 应答 (登录/登出/诊断)。"""

    ok: bool

class LoginCredentials(BaseModel):
    """登录请求体。"""

    user: str
    password: str

# ---------------------------------------------------------------- 账号
class RegisterCredentials(BaseModel):
    """注册请求体: 凭邀请令牌创建账号。"""

    invite: str
    name: str
    password: str

class MeInfo(BaseModel):
    """当前会话的账号 (uuid 是内部标识, 不出接口)。"""

    name: str
    is_admin: bool

class AccountNameUpdate(BaseModel):
    """自助改登录名。"""

    name: str

class AccountPasswordUpdate(BaseModel):
    """自助改密码 (先验旧密码)。"""

    old_password: str
    new_password: str

class UserItem(BaseModel):
    """账号列表项 (管理员看; 不含 uuid —— 对用户不可见)。"""

    name: str
    is_admin: bool
    created_at: datetime    # 本地时间 (直接展示)

class InvitationRequest(BaseModel):
    """签发邀请: 有效期天数 (1 / 7 / 30)。"""

    days: int

class InvitationCreated(BaseModel):
    """刚签发的邀请 (前端拼注册链接给管理员复制/分享)。"""

    token: str
    expires_at: datetime    # 本地时间 (直接展示)

class InvitationItem(BaseModel):
    """邀请列表项 (状态由前端按 used/revoked/时间现算)。"""

    token: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    revoked: bool
