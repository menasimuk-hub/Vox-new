from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.membership import OrganisationMembership
from app.models.oauth_identity import OAuthIdentity
from app.models.organisation import Organisation
from app.models.organisation_invite import OrganisationInvite
from app.models.user import User
from app.services.provider_settings import ProviderSettingsService
from app.services.org_invite_service import (
    attach_pending_invites,
    consume_invite_for_user,
    ensure_personal_org,
    organisations_for_user,
    setup_new_invited_user,
)

logger = logging.getLogger(__name__)


class OAuthFlowError(RuntimeError):
    pass


class OAuthOrgSelectionRequired(OAuthFlowError):
    def __init__(self, *, user_id: str, organisations: list[dict[str, object]]) -> None:
        super().__init__("org_selection_required")
        self.user_id = user_id
        self.organisations = organisations


@dataclass(frozen=True)
class OAuthCallbackResult:
    access_token: str | None = None
    org_id: str | None = None
    user_id: str | None = None
    is_new: bool = False
    org_selection_token: str | None = None
    organisations: list[dict[str, object]] | None = None


@dataclass(frozen=True)
class ProviderUser:
    provider: str
    provider_user_id: str
    email: str | None
    email_verified: bool


def _require_config(provider: str, cfg: dict[str, Any] | None, enabled: bool) -> dict[str, str]:
    if not enabled or not cfg:
        raise OAuthFlowError("Provider is disabled or not configured")
    client_id = str(cfg.get("client_id") or "").strip()
    redirect_uri = str(cfg.get("redirect_uri") or "").strip()

    if provider == "apple":
        team_id = str(cfg.get("team_id") or "").strip()
        key_id = str(cfg.get("key_id") or "").strip()
        private_key = str(cfg.get("private_key") or "").strip()
        if not client_id or not redirect_uri or not team_id or not key_id or not private_key:
            raise OAuthFlowError("Provider settings incomplete")
        return {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "team_id": team_id,
            "key_id": key_id,
            "private_key": private_key,
        }

    client_secret = str(cfg.get("client_secret") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise OAuthFlowError("Provider settings incomplete")
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}


def _normalize_apple_private_key(private_key: str) -> str:
    key = private_key.strip().replace("\\n", "\n")
    if "BEGIN PRIVATE KEY" in key:
        return key
    compact = "".join(key.split())
    wrapped = "\n".join(compact[i : i + 64] for i in range(0, len(compact), 64))
    return f"-----BEGIN PRIVATE KEY-----\n{wrapped}\n-----END PRIVATE KEY-----"


def _apple_client_secret(conf: dict[str, str]) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    headers = {"kid": conf["key_id"], "alg": "ES256"}
    payload = {
        "iss": conf["team_id"],
        "iat": now,
        "exp": now + 15777000,
        "aud": "https://appleid.apple.com",
        "sub": conf["client_id"],
    }
    key = _normalize_apple_private_key(conf["private_key"])
    return jwt.encode(payload, key, algorithm="ES256", headers=headers)


def _build_state(
    *,
    provider: str,
    nonce: str,
    invite_token: str | None,
    org_id: str | None,
    return_to: str | None = None,
    promo_code: str | None = None,
) -> str:
    # Signed, short-lived state token (JWT) to prevent CSRF and preserve context.
    settings = get_settings()
    now = datetime.now(timezone.utc)
    promo_clean = str(promo_code or "").strip().upper() or None
    payload = {
        "provider": provider,
        "nonce": nonce,
        "invite_token": invite_token,
        "org_id": org_id,
        "promo_code": promo_clean,
        "return_to": str(return_to or "").strip().lower() or None,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "typ": "oauth_state",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_state(state: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise OAuthFlowError("Invalid state token") from e
    if payload.get("typ") != "oauth_state":
        raise OAuthFlowError("Invalid state token")
    return payload


class SocialOAuthService:
    PROVIDERS = {"google", "apple", "linkedin"}

    @staticmethod
    def build_authorize_url(
        db: Session,
        *,
        provider: str,
        nonce: str,
        invite_token: str | None,
        org_id: str | None,
        return_to: str | None = None,
        promo_code: str | None = None,
    ) -> str:
        provider = provider.lower().strip()
        if provider not in SocialOAuthService.PROVIDERS:
            raise OAuthFlowError("Unknown provider")
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider=provider)
        conf = _require_config(provider, cfg, enabled)
        state = _build_state(
            provider=provider,
            nonce=nonce,
            invite_token=invite_token,
            org_id=org_id,
            return_to=return_to,
            promo_code=promo_code,
        )

        if provider == "google":
            params = {
                "client_id": conf["client_id"],
                "redirect_uri": conf["redirect_uri"],
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "online",
                "prompt": "select_account",
                "state": state,
            }
            url = httpx.URL("https://accounts.google.com/o/oauth2/v2/auth")
            for k, v in params.items():
                url = url.copy_add_param(k, v)
            return str(url)

        if provider == "apple":
            params = {
                "client_id": conf["client_id"],
                "redirect_uri": conf["redirect_uri"],
                "response_type": "code",
                "scope": "name email",
                "response_mode": "form_post",
                "state": state,
            }
            url = httpx.URL("https://appleid.apple.com/auth/authorize")
            for k, v in params.items():
                url = url.copy_add_param(k, v)
            return str(url)

        if provider == "linkedin":
            params = {
                "client_id": conf["client_id"],
                "redirect_uri": conf["redirect_uri"],
                "response_type": "code",
                "scope": "openid profile email",
                "state": state,
            }
            url = httpx.URL("https://www.linkedin.com/oauth/v2/authorization")
            for k, v in params.items():
                url = url.copy_add_param(k, v)
            return str(url)

        raise OAuthFlowError("Unknown provider")

    @staticmethod
    async def _exchange_code_for_token(*, provider: str, conf: dict[str, str], code: str) -> dict[str, Any]:
        timeout = httpx.Timeout(10.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider == "google":
                r = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": conf["client_id"],
                        "client_secret": conf["client_secret"],
                        "redirect_uri": conf["redirect_uri"],
                        "grant_type": "authorization_code",
                        "code": code,
                    },
                    headers={"Accept": "application/json"},
                )
                r.raise_for_status()
                return r.json()

            if provider == "apple":
                client_secret = _apple_client_secret(conf)
                r = await client.post(
                    "https://appleid.apple.com/auth/token",
                    data={
                        "client_id": conf["client_id"],
                        "client_secret": client_secret,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": conf["redirect_uri"],
                    },
                    headers={"Accept": "application/json"},
                )
                r.raise_for_status()
                return r.json()

            if provider == "linkedin":
                r = await client.post(
                    "https://www.linkedin.com/oauth/v2/accessToken",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": conf["redirect_uri"],
                        "client_id": conf["client_id"],
                        "client_secret": conf["client_secret"],
                    },
                    headers={"Accept": "application/json"},
                )
                r.raise_for_status()
                return r.json()

        raise OAuthFlowError("Unknown provider")

    @staticmethod
    def _provider_user_from_apple_id_token(id_token: str) -> ProviderUser:
        try:
            data = jwt.get_unverified_claims(id_token)
        except JWTError as e:
            raise OAuthFlowError("Invalid Apple id_token") from e
        email = str(data.get("email") or "") or None
        return ProviderUser(
            provider="apple",
            provider_user_id=str(data.get("sub") or ""),
            email=email,
            email_verified=bool(data.get("email_verified", False)),
        )

    @staticmethod
    async def _fetch_provider_user(*, provider: str, access_token: str) -> ProviderUser:
        timeout = httpx.Timeout(10.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider == "google":
                r = await client.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                return ProviderUser(
                    provider="google",
                    provider_user_id=str(data.get("sub") or ""),
                    email=str(data.get("email") or "") or None,
                    email_verified=bool(data.get("email_verified", False)),
                )

            if provider == "linkedin":
                # LinkedIn OIDC userinfo endpoint (requires openid scope)
                r = await client.get(
                    "https://api.linkedin.com/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                # LinkedIn uses "sub" for subject. OIDC userinfo may include email and email_verified.
                email = str(data.get("email") or "") or None
                return ProviderUser(
                    provider="linkedin",
                    provider_user_id=str(data.get("sub") or ""),
                    email=email,
                    email_verified=bool(data.get("email_verified", False)),
                )

        raise OAuthFlowError("Unknown provider")

    @staticmethod
    def _resolve_org_for_user(db: Session, *, user_id: str, org_id_hint: str | None) -> str:
        if org_id_hint:
            chk = db.execute(
                select(OrganisationMembership.id).where(
                    OrganisationMembership.user_id == user_id,
                    OrganisationMembership.org_id == org_id_hint,
                )
            ).scalar_one_or_none()
            if chk is None:
                raise OAuthFlowError("Tenant access denied")
            return org_id_hint

        org_ids = list(
            db.execute(select(OrganisationMembership.org_id).where(OrganisationMembership.user_id == user_id)).scalars()
        )
        if len(org_ids) == 0:
            raise OAuthFlowError("No organisation membership")
        if len(org_ids) != 1:
            orgs = organisations_for_user(db, user_id=user_id)
            raise OAuthOrgSelectionRequired(user_id=user_id, organisations=orgs)
        return str(org_ids[0])

    @staticmethod
    def _finalize_oauth_user(db: Session, *, user: User, org_id_hint: str | None) -> str:
        attach_pending_invites(db, user=user)
        return SocialOAuthService._resolve_org_for_user(db, user_id=user.id, org_id_hint=org_id_hint)

    @staticmethod
    def _ensure_membership(db: Session, *, user_id: str, org_id: str) -> None:
        chk = db.execute(
            select(OrganisationMembership.id).where(
                OrganisationMembership.user_id == user_id,
                OrganisationMembership.org_id == org_id,
            )
        ).scalar_one_or_none()
        if chk is None:
            db.add(OrganisationMembership(org_id=org_id, user_id=user_id))
            db.commit()

    @staticmethod
    def link_or_create_user(
        db: Session,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None,
        email_verified: bool,
        invite_token: str | None,
        org_id_hint: str | None,
    ) -> tuple[User, str, bool]:
        """
        Returns: (user, resolved_org_id, is_new_user)
        """
        provider = provider.lower().strip()
        if provider not in SocialOAuthService.PROVIDERS:
            raise OAuthFlowError("Unknown provider")
        if not provider_user_id:
            raise OAuthFlowError("Missing provider user id")

        # 1) Already-linked identity → log in that user.
        ident = db.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == provider,
                OAuthIdentity.provider_user_id == provider_user_id,
            )
        ).scalar_one_or_none()
        if ident is not None:
            user = db.execute(select(User).where(User.id == ident.user_id)).scalar_one_or_none()
            if user is None:
                raise OAuthFlowError("Linked user not found")
            resolved_org = SocialOAuthService._finalize_oauth_user(db, user=user, org_id_hint=org_id_hint)
            return user, resolved_org, False

        email_norm = (email or "").strip().lower() or None

        # Invite acceptance: must match invited email (prevents taking someone else's invite).
        if invite_token:
            inv = db.execute(select(OrganisationInvite).where(OrganisationInvite.token == invite_token)).scalar_one_or_none()
            if inv is None:
                raise OAuthFlowError("Invite not found")
            if inv.consumed_at is not None:
                raise OAuthFlowError("Invite already used")
            if inv.expires_at < datetime.utcnow():
                raise OAuthFlowError("Invite expired")
            if not email_norm or email_norm != inv.email.strip().lower():
                raise OAuthFlowError("Invite email does not match this account")

            user = db.execute(select(User).where(User.email == email_norm)).scalar_one_or_none()
            created = False
            if user is None:
                pwd = secrets.token_urlsafe(32)
                user = User(email=email_norm, password_hash=hash_password(pwd), is_active=True, is_superuser=False)
                db.add(user)
                db.flush()
                created = True
                setup_new_invited_user(db, user=user, email=email_norm, inv=inv)
            else:
                consume_invite_for_user(db, inv=inv, user=user)

            db.add(OAuthIdentity(provider=provider, provider_user_id=provider_user_id, user_id=user.id, email=email_norm))
            db.commit()
            db.refresh(user)
            return user, str(inv.org_id), created

        # 2) Verified email matches existing internal user → link and log in.
        if email_norm and email_verified:
            existing = db.execute(select(User).where(User.email == email_norm)).scalar_one_or_none()
            if existing is not None:
                db.add(OAuthIdentity(provider=provider, provider_user_id=provider_user_id, user_id=existing.id, email=email_norm))
                db.commit()
                resolved_org = SocialOAuthService._finalize_oauth_user(db, user=existing, org_id_hint=org_id_hint)
                return existing, resolved_org, False

        # 3) Create new internal user and continue normal onboarding/signup flow.
        if not email_norm:
            raise OAuthFlowError("Provider did not return an email address")

        # If email exists but it is NOT verified, do NOT auto-link to an existing account (prevents account takeover).
        # User should sign in with email/password first, then link identities in a controlled flow (future).
        existing = db.execute(select(User).where(User.email == email_norm)).scalar_one_or_none()
        if existing is not None:
            if not email_verified:
                raise OAuthFlowError("Email already registered. Sign in with email to link this provider.")
            db.add(OAuthIdentity(provider=provider, provider_user_id=provider_user_id, user_id=existing.id, email=email_norm))
            db.commit()
            resolved_org = SocialOAuthService._finalize_oauth_user(db, user=existing, org_id_hint=org_id_hint)
            return existing, resolved_org, False

        pwd = secrets.token_urlsafe(32)
        user = User(email=email_norm, password_hash=hash_password(pwd), is_active=True, is_superuser=False)
        db.add(user)
        db.flush()

        if org_id_hint:
            org = db.execute(select(Organisation).where(Organisation.id == org_id_hint)).scalar_one_or_none()
            if org is None:
                raise OAuthFlowError("Organisation not found")
            db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="member"))
        else:
            ensure_personal_org(db, user=user, email=email_norm)

        db.add(OAuthIdentity(provider=provider, provider_user_id=provider_user_id, user_id=user.id, email=email_norm))
        db.commit()
        db.refresh(user)
        resolved_org_id = SocialOAuthService._finalize_oauth_user(db, user=user, org_id_hint=org_id_hint or None)
        return user, resolved_org_id, True

    @staticmethod
    def _oauth_org_selection_token(*, user_id: str, organisations: list[dict[str, object]]) -> str:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "typ": "oauth_org_select",
            "user_id": user_id,
            "organisations": organisations,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    async def handle_callback(db: Session, *, provider: str, code: str, state: str) -> OAuthCallbackResult:
        provider = provider.lower().strip()
        if provider not in SocialOAuthService.PROVIDERS:
            raise OAuthFlowError("Unknown provider")

        state_payload = _decode_state(state)
        if state_payload.get("provider") != provider:
            raise OAuthFlowError("State/provider mismatch")
        invite_token = state_payload.get("invite_token") or None
        org_id_hint = state_payload.get("org_id") or None
        promo_code = str(state_payload.get("promo_code") or "").strip().upper() or None

        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider=provider)
        conf = _require_config(provider, cfg, enabled)

        token_payload = await SocialOAuthService._exchange_code_for_token(provider=provider, conf=conf, code=code)
        if provider == "apple":
            id_token = str(token_payload.get("id_token") or "")
            if not id_token:
                raise OAuthFlowError("Missing id_token")
            puser = SocialOAuthService._provider_user_from_apple_id_token(id_token)
        else:
            access_token = str(token_payload.get("access_token") or "")
            if not access_token:
                raise OAuthFlowError("Missing access token")
            puser = await SocialOAuthService._fetch_provider_user(provider=provider, access_token=access_token)
        try:
            user, resolved_org_id, is_new = SocialOAuthService.link_or_create_user(
                db,
                provider=provider,
                provider_user_id=puser.provider_user_id,
                email=puser.email,
                email_verified=bool(puser.email_verified),
                invite_token=str(invite_token) if invite_token else None,
                org_id_hint=str(org_id_hint) if org_id_hint else None,
            )
        except OAuthOrgSelectionRequired as sel:
            sel_token = SocialOAuthService._oauth_org_selection_token(user_id=sel.user_id, organisations=sel.organisations)
            return OAuthCallbackResult(
                org_selection_token=sel_token,
                organisations=sel.organisations,
                user_id=sel.user_id,
            )

        # Respect suspension for non-superusers.
        if not user.is_superuser:
            org_ent = db.execute(select(Organisation).where(Organisation.id == resolved_org_id)).scalar_one_or_none()
            if org_ent is not None and bool(org_ent.is_suspended):
                raise OAuthFlowError("Organisation suspended")

        if is_new and promo_code and resolved_org_id and not invite_token:
            try:
                from app.services.promo_offer_service import PromoOfferError, PromoOfferService

                PromoOfferService.redeem_for_org(
                    db,
                    org_id=str(resolved_org_id),
                    user_id=user.id,
                    promo_code=promo_code,
                )
            except PromoOfferError:
                pass
            except Exception:
                logger.exception("oauth promo redeem failed user=%s promo=%s", user.id, promo_code)

        token = create_access_token(subject=user.id, org_id=resolved_org_id)
        return OAuthCallbackResult(
            access_token=token,
            org_id=resolved_org_id,
            user_id=user.id,
            is_new=is_new,
        )


def oauth_http_error(e: Exception) -> HTTPException:
    msg = str(e) if str(e) else "OAuth failed"
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

