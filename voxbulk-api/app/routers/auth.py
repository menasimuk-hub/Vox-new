from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
import httpx
import secrets
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db, get_engine, get_sessionmaker
from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.core.security import create_access_token, hash_password, verify_password
from app.models.membership import OrganisationMembership
from app.models.onboarding_request import OnboardingRequest
from app.models.organisation import Organisation
from app.models.organisation_invite import OrganisationInvite
from app.models.user import User
from app.schemas.auth import ForgotPasswordIn, RegisterIn, ResetPasswordIn
from app.services.password_reset_service import PasswordResetService
from app.services.product_email_triggers import ProductEmailTriggers
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_voice_service import TelnyxCallerIdService
from app.services.social_oauth import SocialOAuthService, oauth_http_error, OAuthFlowError, OAuthCallbackResult
from app.services.gocardless_service import BillingService
from app.services.org_invite_service import (
    attach_pending_invites,
    consume_invite_for_user,
    organisations_for_user,
    pending_invite_payloads,
    setup_new_invited_user,
)
from app.services.org_rbac import OrgRbacService, effective_role
from app.core.admin_rbac import can_manage_admin_users, get_active_admin_user, resolve_admin_role
from datetime import timedelta
from jose import JWTError, jwt

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_RESET_MSG = "If this email matches an account, we've sent instructions to reset your password."


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    PasswordResetService.request_reset(db, email=str(payload.email))
    return {"ok": True, "message": _GENERIC_RESET_MSG}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    ok, msg = PasswordResetService.consume_reset(db, raw_token=payload.token, new_password=payload.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"ok": True, "message": msg}


def _organisation_or_403_if_suspended(db: Session, org_id: str) -> Organisation:
    org_ent = db.execute(select(Organisation).where(Organisation.id == str(org_id))).scalar_one_or_none()
    if org_ent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    if bool(org_ent.is_suspended):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organisation suspended")
    return org_ent


@router.get("/invite-preview")
def invite_preview(token: str, db: Session = Depends(get_db)):
    if not token or not str(token).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token required")
    tok = str(token).strip()
    inv = db.execute(select(OrganisationInvite).where(OrganisationInvite.token == tok)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if inv.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already used")
    if inv.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite expired")
    org = db.execute(select(Organisation).where(Organisation.id == inv.org_id)).scalar_one_or_none()
    return {
        "email": inv.email,
        "org_id": inv.org_id,
        "organisation_name": org.name if org else None,
        "role": inv.role,
    }


@router.post("/accept-invite")
def accept_invite(payload: dict, db: Session = Depends(get_db)):
    tok = str(payload.get("token") or "").strip()
    password = payload.get("password")
    pwd = str(password) if password is not None else ""
    if not tok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token required")
    if len(pwd) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password minimum 6 characters")

    inv = db.execute(select(OrganisationInvite).where(OrganisationInvite.token == tok)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if inv.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already used")
    if inv.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite expired")

    _organisation_or_403_if_suspended(db, inv.org_id)

    email_norm = inv.email.strip().lower()
    user = db.execute(select(User).where(User.email == email_norm)).scalar_one_or_none()
    is_new_user = user is None

    if user is None:
        user = User(
            email=email_norm,
            password_hash=hash_password(pwd),
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        setup_new_invited_user(db, user=user, email=email_norm, inv=inv)
    else:
        if not user.password_hash or not verify_password(pwd, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password for this email")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
        consume_invite_for_user(db, inv=inv, user=user)

    db.commit()
    db.refresh(user)

    if is_new_user:
        with get_sessionmaker()() as s2:
            org = s2.get(Organisation, inv.org_id)
            ProductEmailTriggers.send_new_user_welcome_safe(
                s2,
                to_email=str(user.email),
                organisation_name=(org.name if org else "") or "",
            )

    token = create_access_token(subject=user.id, org_id=inv.org_id)
    return {"access_token": token, "token_type": "bearer", "org_id": inv.org_id, "user_id": user.id}


@router.get("/pending-invites")
def pending_invites(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return {"invites": pending_invite_payloads(db, email=str(user.email or ""))}


@router.post("/accept-invite-session")
def accept_invite_session(
    payload: dict,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    """Accept a team invite while already signed in (no password required)."""
    tok = str(payload.get("token") or "").strip()
    if not tok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token required")

    inv = db.execute(select(OrganisationInvite).where(OrganisationInvite.token == tok)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if inv.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already used")
    if inv.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite expired")

    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    if str(user.email or "").strip().lower() != inv.email.strip().lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invite email does not match your account")

    _organisation_or_403_if_suspended(db, inv.org_id)
    consume_invite_for_user(db, inv=inv, user=user)
    db.commit()

    token = create_access_token(subject=user.id, org_id=inv.org_id)
    return {"access_token": token, "token_type": "bearer", "org_id": inv.org_id, "user_id": user.id}


def _oauth_org_selection_token(*, user_id: str, organisations: list[dict[str, object]]) -> str:
    settings = get_settings()
    now = datetime.utcnow()
    payload = {
        "typ": "oauth_org_select",
        "user_id": user_id,
        "organisations": organisations,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_oauth_org_selection_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired org selection") from exc
    if payload.get("typ") != "oauth_org_select":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org selection token")
    return payload


@router.get("/oauth/org-selection")
def oauth_org_selection_preview(token: str, db: Session = Depends(get_db)):
    payload = _decode_oauth_org_selection_token(str(token or "").strip())
    user_id = str(payload.get("user_id") or "")
    user = db.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    orgs = payload.get("organisations")
    if not isinstance(orgs, list) or not orgs:
        orgs = organisations_for_user(db, user_id=user_id)
    return {"organisations": orgs}


@router.post("/oauth/complete-org-selection")
def oauth_complete_org_selection(payload: dict, db: Session = Depends(get_db)):
    sel_tok = str(payload.get("selection_token") or "").strip()
    org_id = str(payload.get("org_id") or "").strip()
    if not sel_tok or not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selection_token and org_id required")
    decoded = _decode_oauth_org_selection_token(sel_tok)
    user_id = str(decoded.get("user_id") or "")
    user = db.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    mem = db.execute(
        select(OrganisationMembership.id).where(
            OrganisationMembership.user_id == user.id,
            OrganisationMembership.org_id == org_id,
        )
    ).scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    if not user.is_superuser:
        org_ent = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
        if org_ent is not None and bool(org_ent.is_suspended):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organisation suspended")
    token = create_access_token(subject=user.id, org_id=org_id)
    return {"access_token": token, "token_type": "bearer", "org_id": org_id, "user_id": user.id}


@router.get("/my-organisations")
def my_organisations(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is not None:
        attach_pending_invites(db, user=user)
        db.commit()
    rows = OrgRbacService.list_organisations_for_user(db, user_id=principal.user_id)
    return {"organisations": rows, "active_org_id": principal.org_id}


@router.post("/switch-organisation")
def switch_organisation(
    payload: dict,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    org_id = str(payload.get("org_id") or "").strip()
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="org_id required")
    mem = OrgRbacService.membership_for(db, org_id=org_id, user_id=principal.user_id)
    if mem is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    if not db.execute(select(User).where(User.id == principal.user_id, User.is_active.is_(True))).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    _organisation_or_403_if_suspended(db, org_id)
    token = create_access_token(subject=principal.user_id, org_id=org_id)
    return {"access_token": token, "token_type": "bearer", "org_id": org_id, "user_id": principal.user_id}


def _ensure_onboarding_requests_table_for_local_dev() -> None:
    settings = get_settings()
    if str(settings.env).lower() in {"dev", "development", "local"}:
        OnboardingRequest.__table__.create(bind=get_engine(), checkfirst=True)

@router.post("/me/role")
def set_my_role(payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    role = payload.get("role")
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role required")
    role_str = str(role).strip()
    if not role_str:
        role_str = ""

    mem = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == principal.user_id,
            OrganisationMembership.org_id == principal.org_id,
        )
    ).scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    mem.role = role_str or None
    db.add(mem)
    db.commit()
    return {"ok": True, "role": mem.role}

@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """
    Minimal self-serve registration for end-to-end integration.

    Creates:
    - Organisation
    - User
    - Membership

    Returns an access token for the newly created org.
    """
    existing = db.execute(select(User.id).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    raw_org_id = payload.org_id
    if isinstance(raw_org_id, str):
        raw_org_id = raw_org_id.strip() or None

    org: Organisation | None = None
    if raw_org_id:
        org = db.execute(select(Organisation).where(Organisation.id == str(raw_org_id))).scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    else:
        org = Organisation(name=payload.organisation_name)
        db.add(org)
        db.flush()

    user = User(email=str(payload.email), password_hash=hash_password(payload.password), is_active=True, is_superuser=False)
    db.add(user)
    db.flush()

    mem_role = "member" if raw_org_id else "owner"
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role=mem_role))
    promo_code = str(payload.promo_code or "").strip().upper() or None
    if promo_code:
        try:
            from app.services.promo_offer_service import PromoOfferError, PromoOfferService

            PromoOfferService.redeem_for_org(db, org_id=org.id, user_id=user.id, promo_code=promo_code)
        except PromoOfferError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    elif not raw_org_id:
        BillingService.assign_plan_cash(db, org_id=org.id, plan_code="starter")
    db.commit()

    with get_sessionmaker()() as s2:
        ProductEmailTriggers.send_new_user_welcome_safe(
            s2,
            to_email=str(user.email),
            organisation_name=org.name or "",
        )

    token = create_access_token(subject=user.id, org_id=org.id)
    return {"access_token": token, "token_type": "bearer", "org_id": org.id, "user_id": user.id}


@router.post("/self-serve")
def self_serve(payload: dict, db: Session = Depends(get_db)):
    """
    Legacy self-serve signup — creates an active account immediately (no admin approval).
    Prefer POST /auth/register for new integrations.
    """
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    organisation_name = str(payload.get("organisation_name") or "").strip()
    promo_code = str(payload.get("promo_code") or "").strip().upper() or None

    if not email or not password or not organisation_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email, password, organisation_name required")

    reg = RegisterIn(
        email=email,
        password=password,
        organisation_name=organisation_name,
        promo_code=promo_code,
    )
    return register(reg, db)


@router.post("/token")
async def issue_token(request: Request, db: Session = Depends(get_db)):
    """
    Token issuance (Phase 2 minimal).

    Expects form fields:
    - username (email)
    - password
    - org_id (optional if user has exactly one membership)
    """
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    org_id = form.get("org_id")

    if not username or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="username and password required")

    email_norm = str(username).strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email_norm)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    del_status = str(getattr(user, "deletion_status", "active") or "active")
    if del_status in ("pending", "archived"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not available for sign-in")

    # Guard against legacy/partial users created without password_hash.
    if not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(str(password), user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    attach_pending_invites(db, user=user)
    db.commit()

    resolved_org_id: str | None = str(org_id) if org_id else None
    if resolved_org_id:
        membership = db.execute(
            select(OrganisationMembership.id).where(
                OrganisationMembership.user_id == user.id,
                OrganisationMembership.org_id == resolved_org_id,
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    else:
        org_ids = list(
            db.execute(
                select(OrganisationMembership.org_id).where(OrganisationMembership.user_id == user.id)
            ).scalars()
        )
        if len(org_ids) == 0:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organisation membership")
        if len(org_ids) != 1:
            return {
                "org_selection_required": True,
                "organisations": OrgRbacService.list_organisations_for_user(db, user_id=user.id),
            }
        resolved_org_id = str(org_ids[0])

    if not user.is_superuser:
        org_ent = db.execute(select(Organisation).where(Organisation.id == str(resolved_org_id))).scalar_one_or_none()
        if org_ent is not None and bool(org_ent.is_suspended):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organisation suspended")

    token = create_access_token(subject=user.id, org_id=resolved_org_id)
    return {"access_token": token, "token_type": "bearer", "org_id": resolved_org_id, "user_id": user.id}


@router.get("/me")
def me(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    """Protected endpoint proving auth + tenant dependency works."""
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    membership = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == principal.user_id,
            OrganisationMembership.org_id == principal.org_id,
        )
    ).scalar_one_or_none()
    org_ent = db.execute(select(Organisation).where(Organisation.id == principal.org_id)).scalar_one_or_none()
    raw_role = membership.role if membership else None
    clinic_role = effective_role(raw_role)
    org_onboarding_state = getattr(org_ent, "onboarding_state", None) or "account_created"
    dashboard_setup_complete = bool(org_onboarding_state == "onboarding_completed" or (membership and membership.dashboard_setup_completed_at is not None))
    admin_access = bool(user.is_superuser or get_active_admin_user(db, user) is not None)
    admin_role = resolve_admin_role(db, user) if admin_access else None
    from app.services.account_deletion_service import AccountDeletionService

    deletion = AccountDeletionService.get_status(db, user=user, org_id=principal.org_id)

    return {
        "user_id": principal.user_id,
        "org_id": principal.org_id,
        "email": user.email,
        "deletion_status": deletion.get("deletion_status"),
        "deletion_label": deletion.get("deletion_label"),
        "deletion_requested_at": deletion.get("deletion_requested_at"),
        "role": clinic_role,
        "is_superuser": bool(user.is_superuser),
        "admin_access": admin_access,
        "admin_role": admin_role if admin_role != "none" else None,
        "can_manage_admin_users": can_manage_admin_users(db, user) if admin_access else False,
        "tenant_role": clinic_role,
        "dashboard_setup_complete": dashboard_setup_complete,
        "onboarding_state": org_onboarding_state,
        "onboarding_complete": org_onboarding_state == "onboarding_completed",
        "booking_software_slug": getattr(org_ent, "booking_software_slug", None),
        "category_id": getattr(org_ent, "category_id", None),
        "phone": TelnyxCallerIdService.phone_status(user),
    }


@router.post("/me/dashboard-setup")
def save_dashboard_setup(
    payload: dict,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    """Persist clinic dashboard wizard completion (survives logout). Optional profile JSON for UX continuity."""
    membership = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == principal.user_id,
            OrganisationMembership.org_id == principal.org_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

    profile = payload.get("profile")
    if profile is not None:
        try:
            membership.dashboard_setup_profile_json = json.dumps(profile)
        except (TypeError, ValueError):
            membership.dashboard_setup_profile_json = None

    membership.dashboard_setup_completed_at = datetime.utcnow()
    db.add(membership)
    db.commit()
    return {"ok": True, "dashboard_setup_complete": True}


@router.get("/me/phone")
def my_phone_status(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return TelnyxCallerIdService.phone_status(user)


@router.put("/me/phone")
def save_my_phone(payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    try:
        user = TelnyxCallerIdService.save_phone(db, user=user, phone_number=str(payload.get("phone_number") or ""))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TelnyxCallerIdService.phone_status(user)


@router.post("/me/phone/verify")
def start_my_phone_verification(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    try:
        res = TelnyxCallerIdService.start_verification(db, user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {**TelnyxCallerIdService.phone_status(user), **res}


@router.post("/me/phone/refresh")
def refresh_my_phone_verification(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    try:
        user = TelnyxCallerIdService.refresh_verification(db, user=user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TelnyxCallerIdService.phone_status(user)


@router.get("/social-login/providers")
def public_social_login_providers(db: Session = Depends(get_db)):
    """
    Public endpoint for the sign-in page to discover which social providers are enabled/configured.

    The actual OAuth redirect flow is handled by /auth/oauth/{provider}/start and /callback.
    """
    return ProviderSettingsService.social_login_public_availability(db)


def _oauth_landing_path(settings, *, return_to: str | None) -> str:
    if str(return_to or "").strip().lower() == "dashboard":
        return f"{settings.dashboard_app_origin.rstrip('/')}/login"
    return f"{settings.public_app_origin.rstrip('/')}/signin"


def _resolve_oauth_return_to(request: Request, state: str | None) -> str | None:
    return_to = None
    if state:
        try:
            from app.services.social_oauth import _decode_state

            return_to = _decode_state(state).get("return_to")
        except Exception:
            return_to = None
    if not return_to:
        try:
            return_to = request.cookies.get("voxbulk_oauth_return_to")
        except Exception:
            return_to = None
    clean = str(return_to or "").strip().lower()
    return clean or None


def _clear_oauth_cookies(res: RedirectResponse) -> None:
    res.delete_cookie("voxbulk_oauth_nonce", path="/auth/oauth")
    res.delete_cookie("voxbulk_oauth_provider", path="/auth/oauth")
    res.delete_cookie("voxbulk_oauth_return_to", path="/auth/oauth")
    res.delete_cookie("retover_oauth_nonce", path="/auth/oauth")
    res.delete_cookie("retover_oauth_provider", path="/auth/oauth")


@router.get("/oauth/{provider}/start")
def oauth_start(
    provider: str,
    request: Request,
    invite_token: str | None = None,
    org_id: str | None = None,
    return_to: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Start OAuth flow for a provider.

    - invite_token/org_id are optional context hints to preserve invite/tenant flows.
    - return_to=dashboard sends the user back to the dashboard login page after OAuth.
    """
    try:
        # Bind state to this browser using a nonce cookie (prevents login CSRF/replay).
        nonce = secrets.token_urlsafe(20)
        url = SocialOAuthService.build_authorize_url(
            db,
            provider=provider,
            nonce=nonce,
            invite_token=invite_token,
            org_id=org_id,
            return_to=return_to,
        )
        res = RedirectResponse(url=url, status_code=302)
        secure = False
        try:
            secure = request.url.scheme == "https" if request else False
        except Exception:
            secure = False
        return_to_clean = str(return_to or "").strip().lower()
        if return_to_clean:
            res.set_cookie(
                key="voxbulk_oauth_return_to",
                value=return_to_clean,
                httponly=True,
                secure=secure,
                samesite="lax",
                max_age=10 * 60,
                path="/auth/oauth",
            )
        res.set_cookie(
            key="voxbulk_oauth_nonce",
            value=nonce,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=10 * 60,
            path="/auth/oauth",
        )
        res.set_cookie(
            key="voxbulk_oauth_provider",
            value=str(provider).lower(),
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=10 * 60,
            path="/auth/oauth",
        )
        return res
    except OAuthFlowError as e:
        raise oauth_http_error(e)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    """
    OAuth callback endpoint.

    Redirects back to the sign-in page with the normal FastAPI bearer token handed off in the URL hash.
    """
    settings = get_settings()
    landing = _oauth_landing_path(settings, return_to=_resolve_oauth_return_to(request, state))

    if error:
        msg = error_description or error
        q = httpx.QueryParams({"oauth_error": msg, "provider": provider})
        res = RedirectResponse(url=f"{landing}?{q}", status_code=302)
        _clear_oauth_cookies(res)
        return res

    if not code or not state:
        q = httpx.QueryParams({"oauth_error": "Missing code/state", "provider": provider})
        res = RedirectResponse(url=f"{landing}?{q}", status_code=302)
        _clear_oauth_cookies(res)
        return res

    try:
        # Validate nonce cookie matches state nonce (prevents login CSRF).
        nonce_cookie = None
        provider_cookie = None
        try:
            nonce_cookie = request.cookies.get("voxbulk_oauth_nonce") if request else None
            provider_cookie = request.cookies.get("voxbulk_oauth_provider") if request else None
            if not nonce_cookie:
                nonce_cookie = request.cookies.get("retover_oauth_nonce") if request else None
            if not provider_cookie:
                provider_cookie = request.cookies.get("retover_oauth_provider") if request else None
        except Exception:
            nonce_cookie = None
            provider_cookie = None

        if not nonce_cookie or not provider_cookie:
            raise OAuthFlowError("Missing OAuth session cookie")
        if str(provider_cookie).lower().strip() != str(provider).lower().strip():
            raise OAuthFlowError("Provider mismatch")

        # Decode state once here to verify nonce/provider before exchanging code.
        from app.services.social_oauth import _decode_state  # local import

        st = _decode_state(state)
        if st.get("provider") != str(provider).lower().strip():
            raise OAuthFlowError("State/provider mismatch")
        if st.get("nonce") != nonce_cookie:
            raise OAuthFlowError("Invalid OAuth session")

        landing = _oauth_landing_path(settings, return_to=st.get("return_to"))

        outcome = await SocialOAuthService.handle_callback(db, provider=provider, code=code, state=state)

        if outcome.org_selection_token:
            frag = httpx.QueryParams({"oauth_org_select": outcome.org_selection_token, "oauth": "1"})
            res = RedirectResponse(url=f"{landing}#{frag}", status_code=302)
            _clear_oauth_cookies(res)
            return res

        token = str(outcome.access_token or "")
        org_id = str(outcome.org_id or "")
        user_id = str(outcome.user_id or "")
        is_new = bool(outcome.is_new)

        if is_new and user_id and org_id:
            with get_sessionmaker()() as s2:
                wel_email = s2.execute(select(User.email).where(User.id == user_id)).scalar_one_or_none()
                org_name = s2.execute(select(Organisation.name).where(Organisation.id == org_id)).scalar_one_or_none()
                if wel_email:
                    ProductEmailTriggers.send_new_user_welcome_safe(
                        s2,
                        to_email=str(wel_email),
                        organisation_name=str(org_name or ""),
                    )
    except Exception as e:
        q = httpx.QueryParams({"oauth_error": str(e) or "OAuth failed", "provider": provider})
        res = RedirectResponse(url=f"{landing}?{q}", status_code=302)
        _clear_oauth_cookies(res)
        return res

    # Handoff via fragment so it is not sent to the server.
    frag = httpx.QueryParams(
        {
            "access_token": token,
            "org_id": org_id,
            "user_id": user_id,
            "oauth": "1",
            "new_user": "1" if is_new else "0",
        }
    )
    res = RedirectResponse(url=f"{landing}#{frag}", status_code=302)
    _clear_oauth_cookies(res)
    return res


