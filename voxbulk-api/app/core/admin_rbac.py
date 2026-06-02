"""Coarse admin-console RBAC (superadmin / admin / accountant / technical/support / marketing)."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.admin_user import AdminUser
from app.models.user import User

CAP_INTEGRATION = "integration"  # webhooks, provider secrets, social login, integration reads
CAP_BILLING = "billing"  # billing overview, plans, synthetic payment/invoice posts
CAP_ORG_OPS = "org_ops"  # organisations, categories, onboarding approvals, operations overview, org users
CAP_EMAIL = "email"  # SMTP + templates under /admin/email
CAP_AI_TEAM = "ai_team"  # AI Team outbound sales agent
CAP_SUPPORT = "support"  # support tickets

_ROLE_CAPS: dict[str, frozenset[str]] = {
    "accountant": frozenset({CAP_BILLING, CAP_ORG_OPS}),
    "technical": frozenset({CAP_SUPPORT}),
    "support": frozenset({CAP_SUPPORT}),
    "marketing": frozenset({CAP_EMAIL, CAP_AI_TEAM}),
}


def get_active_admin_user(db: Session, user: User) -> AdminUser | None:
    au = db.execute(select(AdminUser).where(AdminUser.id == user.id)).scalar_one_or_none()
    if au is None and user.email:
        au = db.execute(select(AdminUser).where(AdminUser.email == user.email.strip().lower())).scalar_one_or_none()
    if au is None or not au.is_active:
        return None
    return au


def resolve_admin_role(db: Session, user: User) -> str:
    """
    Returns superadmin | admin | accountant | technical | support | marketing | none
    """
    au = get_active_admin_user(db, user)
    if au is not None:
        if au.is_superuser:
            return "superadmin"
        raw = (au.role or "").strip().lower()
        if raw in {"admin"}:
            return "superadmin"
        if raw in {"superadmin", "accountant", "marketing", "technical", "support"}:
            return raw
        return "marketing"
    if user.is_superuser:
        return "superadmin"
    return "none"


def role_has_cap(role: str, cap: str) -> bool:
    if role == "superadmin":
        return True
    return cap in _ROLE_CAPS.get(role, frozenset())


def can_manage_admin_users(db: Session, user: User) -> bool:
    """Creates/deletes platform admin rows (AdminUser CRUD)."""
    email_norm = (user.email or "").strip().lower()
    if not email_norm:
        return False
    au = db.execute(select(AdminUser).where(AdminUser.email == email_norm)).scalar_one_or_none()
    if au is None:
        return bool(user.is_superuser)
    return bool(au.is_superuser)


def require_platform_admin(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """
    Active legacy superuser OR active AdminUser row may use the admin console JWT.
    """
    if user.is_superuser:
        return user
    au = db.execute(select(AdminUser).where(AdminUser.id == user.id)).scalar_one_or_none()
    if au is None and user.email:
        au = db.execute(select(AdminUser).where(AdminUser.email == user.email.strip().lower())).scalar_one_or_none()
    if au is not None and au.is_active:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin access required")


def require_cap(cap: str) -> Callable[..., User]:
    def dependency(user: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> User:
        role = resolve_admin_role(db, user)
        if role == "superadmin":
            return user
        if role_has_cap(role, cap):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires permission: {cap}",
        )

    return dependency
