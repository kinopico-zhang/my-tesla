"""注册邀请 (账号库 users.db 的 invitations 表): 管理员签发, 一次一用。"""
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Invitation
from .errors import InvitationError

INVITE_DAYS_CHOICES = (1, 7, 30)   # 邀请有效期档位 (天)


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
