from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token
from app.models.membership import OrganisationMembership
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


@dataclass(frozen=True)
class CurrentPrincipal:
    user_id: str
    org_id: str
    token_payload: dict


def _principal_from_token(request: Request, db: Session, token: str) -> CurrentPrincipal:
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

    user_id = payload.get("sub")
    org_id = payload.get("org_id") or request.headers.get("X-Voxbulk-Org-Id") or request.headers.get("X-Retover-Org-Id")

    if not user_id or not org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

    stmt = select(OrganisationMembership.id).where(
        OrganisationMembership.user_id == str(user_id),
        OrganisationMembership.org_id == str(org_id),
    )
    membership_id = db.execute(stmt).scalar_one_or_none()
    if membership_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    return CurrentPrincipal(user_id=str(user_id), org_id=str(org_id), token_payload=payload)


def _assert_user_access(user: User | None, *, allow_pending: bool = False) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    status_val = str(getattr(user, "deletion_status", "active") or "active")
    if status_val == "archived":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deleted")
    if status_val == "pending" and not allow_pending:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deletion is pending — access is restricted until processed or cancelled",
        )
    if not user.is_active and not (allow_pending and status_val == "pending"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> CurrentPrincipal:
    principal = _principal_from_token(request, db, token)
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    _assert_user_access(user, allow_pending=False)
    return principal


def get_current_principal_allow_pending(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> CurrentPrincipal:
    """For deletion-status and cancel-delete routes while request is pending."""
    principal = _principal_from_token(request, db, token)
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    _assert_user_access(user, allow_pending=True)
    return principal


def get_tenant_org_id(principal: CurrentPrincipal = Depends(get_current_principal)) -> str:
    return principal.org_id


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def get_current_user(
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> User:
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    return _assert_user_access(user, allow_pending=False)


def require_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user
