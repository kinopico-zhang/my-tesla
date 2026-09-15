"""账号库表 (data/users.db): 账号 + 注册邀请。

业务表 (TeslaMate 映射 + My Tesla 自有表) 在 app/tesla/models.py。
"""

from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UsersBase(DeclarativeBase):
    """账号库基类 (data/users.db, 与业务库分开的独立文件)。"""


class User(UsersBase):
    """账号: uuid 由后端生成 (对用户不可见, 改名不变, 会话都认它)。

    名称/密码本人可自助改; is_admin = 账号管理权限 (邀请注册/用户列表),
    业务功能所有账号都有。"""

    __tablename__ = "users"

    uuid: Mapped[str] = mapped_column(primary_key=True)   # uuid4().hex
    name: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]          # scrypt$<salt>$<hash>
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Invitation(UsersBase):
    """注册邀请: 管理员签发, 一次一用, 带有效期; revoked = 手动撤销。"""

    __tablename__ = "invitations"

    token: Mapped[str] = mapped_column(primary_key=True)  # token_urlsafe
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked: Mapped[bool] = mapped_column(default=False)
