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
    # Tenant scope comes from the JWT only. Client org headers are ignored so a
    # stolen/minted access token cannot be pointed at another org via X-Voxbulk-Org-Id.
    org_id = payload.get("org_id")

    if not user_id or not org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

    user = db.execute(select(User).where(User.id == str(user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    token_tv = int(payload.get("tv") or 0)
    user_tv = int(getattr(user, "token_version", 0) or 0)
    if token_tv != user_tv:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please sign in again",
        )

    stmt = select(OrganisationMembership.id).where(
        OrganisationMembership.user_id == str(user_id),
        OrganisationMembership.org_id == str(org_id),
    )
    membership_id = db.execute(stmt).scalar_one_or_none()
    if membership_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    # AI Demo handoff tokens are bound to a live DemoSession — reject after the call ends.
    demo_session_id = str(payload.get("demo_session_id") or "").strip()
    if demo_session_id:
        from app.models.demo_session import DemoSession

        demo = db.get(DemoSession, demo_session_id)
        status_val = str(getattr(demo, "status", "") or "").strip().lower() if demo is not None else ""
        if demo is None or status_val not in {"active"}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Demo session ended — please request a new demo",
            )

    return CurrentPrincipal(user_id=str(user_id), org_id=str(org_id), token_payload=payload)


_DEMO_WRITE_ALLOW_PREFIXES = (
    "/ai-demo/",
    "/api/ai-demo/",
    "/auth/logout",
    "/api/auth/logout",
    "/health",
    "/api/health",
)

_DEMO_WRITE_ALLOW_EXACT = {
    "/customer-feedback/locations",
    "/api/customer-feedback/locations",
    "/customer-feedback/locations/preview",
    "/api/customer-feedback/locations/preview",
}


def _assert_demo_writes_blocked(request: Request, principal: CurrentPrincipal) -> None:
    """Demo handoff JWTs are view-only — block mutating dashboard APIs."""
    payload = principal.token_payload or {}
    if not (payload.get("demo_access") or payload.get("demo_session_id")):
        return
    method = str(request.method or "GET").upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return
    path = str(request.url.path or "")
    for prefix in _DEMO_WRITE_ALLOW_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return
    if method == "POST" and path.rstrip("/") in {p.rstrip("/") for p in _DEMO_WRITE_ALLOW_EXACT}:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Demo sessions are view-only — saving or changing account data is blocked",
    )


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
    _assert_demo_writes_blocked(request, principal)
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
    _assert_demo_writes_blocked(request, principal)
    return principal


def get_tenant_org_id(principal: CurrentPrincipal = Depends(get_current_principal)) -> str:
    return principal.org_id


def require_billing_access(
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> CurrentPrincipal:
    from app.services.org_rbac import OrgRbacService

    try:
        OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return principal


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
