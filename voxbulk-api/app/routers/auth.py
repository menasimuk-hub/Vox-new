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
from app.services.social_oauth import SocialOAuthService, oauth_http_error, OAuthFlowError
from app.services.gocardless_service import BillingService
from app.core.admin_rbac import can_manage_admin_users, get_active_admin_user, resolve_admin_role

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
        db.add(OrganisationMembership(org_id=inv.org_id, user_id=user.id, role=inv.role))
    else:
        if not user.password_hash or not verify_password(pwd, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password for this email")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
        mem = db.execute(
            select(OrganisationMembership.id).where(
                OrganisationMembership.user_id == user.id,
                OrganisationMembership.org_id == inv.org_id,
            )
        ).scalar_one_or_none()
        if mem is None:
            db.add(OrganisationMembership(org_id=inv.org_id, user_id=user.id, role=inv.role))
        elif inv.role:
            mobj = db.execute(
                select(OrganisationMembership).where(
                    OrganisationMembership.user_id == user.id,
                    OrganisationMembership.org_id == inv.org_id,
                )
            ).scalar_one_or_none()
            if mobj is not None and mobj.role is None:
                mobj.role = inv.role
                db.add(mobj)

    inv.consumed_at = datetime.utcnow()
    db.add(inv)
    db.commit()
    db.refresh(user)

    if is_new_user:
        try:
            with get_sessionmaker()() as s2:
                org = s2.get(Organisation, inv.org_id)
                ProductEmailTriggers.send_new_user_welcome(
                    s2,
                    to_email=str(user.email),
                    extra_variables={
                        "organisation_name": (org.name if org else "") or "",
                        "user_name": str(user.email).split("@")[0],
                        "first_name": str(user.email).split("@")[0],
                    },
                )
        except Exception:
            pass

    token = create_access_token(subject=user.id, org_id=inv.org_id)
    return {"access_token": token, "token_type": "bearer", "org_id": inv.org_id, "user_id": user.id}


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

    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
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

    try:
        with get_sessionmaker()() as s2:
            ProductEmailTriggers.send_new_user_welcome(
                s2,
                to_email=str(user.email),
                extra_variables={
                    "organisation_name": org.name or "",
                    "user_name": str(user.email).split("@")[0],
                    "first_name": str(user.email).split("@")[0],
                },
            )
    except Exception:
        pass

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

    # Guard against legacy/partial users created without password_hash.
    if not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(str(password), user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

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
        if len(org_ids) != 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="org_id required")
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
    clinic_role = membership.role if membership else None
    org_onboarding_state = getattr(org_ent, "onboarding_state", None) or "account_created"
    dashboard_setup_complete = bool(org_onboarding_state == "onboarding_completed" or (membership and membership.dashboard_setup_completed_at is not None))
    admin_access = bool(user.is_superuser or get_active_admin_user(db, user) is not None)
    admin_role = resolve_admin_role(db, user) if admin_access else None

    return {
        "user_id": principal.user_id,
        "org_id": principal.org_id,
        "email": user.email,
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


@router.get("/oauth/{provider}/start")
def oauth_start(
    provider: str,
    request: Request,
    invite_token: str | None = None,
    org_id: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Start OAuth flow for a provider.

    - invite_token/org_id are optional context hints to preserve invite/tenant flows.
    """
    try:
        # Bind state to this browser using a nonce cookie (prevents login CSRF/replay).
        nonce = secrets.token_urlsafe(20)
        url = SocialOAuthService.build_authorize_url(db, provider=provider, nonce=nonce, invite_token=invite_token, org_id=org_id)
        res = RedirectResponse(url=url, status_code=302)
        secure = False
        try:
            secure = request.url.scheme == "https" if request else False
        except Exception:
            secure = False
        res.set_cookie(
            key="retover_oauth_nonce",
            value=nonce,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=10 * 60,
            path="/auth/oauth",
        )
        res.set_cookie(
            key="retover_oauth_provider",
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

    Redirects back to the public sign-in page with the normal FastAPI bearer token handed off in the URL hash.
    """
    settings = get_settings()
    base = settings.public_app_origin.rstrip("/")

    if error:
        msg = error_description or error
        q = httpx.QueryParams({"oauth_error": msg, "provider": provider})
        return RedirectResponse(url=f"{base}/signin?{q}", status_code=302)

    if not code or not state:
        q = httpx.QueryParams({"oauth_error": "Missing code/state", "provider": provider})
        return RedirectResponse(url=f"{base}/signin?{q}", status_code=302)

    try:
        # Validate nonce cookie matches state nonce (prevents login CSRF).
        nonce_cookie = None
        provider_cookie = None
        try:
            nonce_cookie = request.cookies.get("retover_oauth_nonce") if request else None
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

        token, org_id, user_id, is_new = await SocialOAuthService.handle_callback(db, provider=provider, code=code, state=state)

        if is_new:
            try:
                with get_sessionmaker()() as s2:
                    wel_email = s2.execute(select(User.email).where(User.id == user_id)).scalar_one_or_none()
                    org_name = s2.execute(select(Organisation.name).where(Organisation.id == org_id)).scalar_one_or_none()
                    if wel_email:
                        ProductEmailTriggers.send_new_user_welcome(
                            s2,
                            to_email=str(wel_email),
                            extra_variables={
                                "organisation_name": str(org_name or ""),
                                "user_name": str(wel_email).split("@")[0],
                                "first_name": str(wel_email).split("@")[0],
                            },
                        )
            except Exception:
                pass
    except Exception as e:
        q = httpx.QueryParams({"oauth_error": str(e) or "OAuth failed", "provider": provider})
        res = RedirectResponse(url=f"{base}/signin?{q}", status_code=302)
        # Clear cookies on failure too.
        res.delete_cookie("retover_oauth_nonce", path="/auth/oauth")
        res.delete_cookie("retover_oauth_provider", path="/auth/oauth")
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
    res = RedirectResponse(url=f"{base}/signin#{frag}", status_code=302)
    res.delete_cookie("retover_oauth_nonce", path="/auth/oauth")
    res.delete_cookie("retover_oauth_provider", path="/auth/oauth")
    return res


