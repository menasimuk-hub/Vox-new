from app.core.security import hash_password


def _seed_org(db, name="Org A"):
    from app.models.organisation import Organisation

    org = Organisation(name=name)
    db.add(org)
    db.flush()
    return org


def _seed_user(db, email="user@example.com"):
    from app.models.user import User

    u = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(u)
    db.flush()
    return u


def _seed_membership(db, user_id, org_id, role=None):
    from app.models.membership import OrganisationMembership

    m = OrganisationMembership(user_id=user_id, org_id=org_id, role=role)
    db.add(m)
    db.flush()
    return m


def test_linking_prefers_existing_identity(app_client):
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.oauth_identity import OAuthIdentity
    from app.services.social_oauth import SocialOAuthService

    with get_sessionmaker()() as db:
        org = _seed_org(db)
        user = _seed_user(db, email="linked@example.com")
        _seed_membership(db, user.id, org.id)
        db.add(OAuthIdentity(provider="google", provider_user_id="abc", user_id=user.id, email=user.email))
        db.commit()

        u2, resolved_org, is_new = SocialOAuthService.link_or_create_user(
            db,
            provider="google",
            provider_user_id="abc",
            email="linked@example.com",
            email_verified=True,
            invite_token=None,
            org_id_hint=None,
        )
        assert u2.id == user.id
        assert resolved_org == org.id
        assert is_new is False


def test_linking_by_verified_email_links_existing_user(app_client):
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.oauth_identity import OAuthIdentity
    from app.services.social_oauth import SocialOAuthService

    with get_sessionmaker()() as db:
        org = _seed_org(db)
        user = _seed_user(db, email="existing@example.com")
        _seed_membership(db, user.id, org.id)
        db.commit()

        u2, resolved_org, is_new = SocialOAuthService.link_or_create_user(
            db,
            provider="linkedin",
            provider_user_id="sub-1",
            email="existing@example.com",
            email_verified=True,
            invite_token=None,
            org_id_hint=None,
        )
        assert u2.id == user.id
        assert resolved_org == org.id
        assert is_new is False

        ident = db.execute(
            select(OAuthIdentity).where(OAuthIdentity.provider == "linkedin", OAuthIdentity.provider_user_id == "sub-1")
        ).scalar_one_or_none()
        assert ident is not None
        assert ident.user_id == user.id


def test_new_user_creates_org_and_membership(app_client):
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.membership import OrganisationMembership
    from app.models.oauth_identity import OAuthIdentity
    from app.models.organisation import Organisation
    from app.services.social_oauth import SocialOAuthService

    with get_sessionmaker()() as db:
        u, resolved_org, is_new = SocialOAuthService.link_or_create_user(
            db,
            provider="google",
            provider_user_id="sub-2",
            email="newclinic@example.com",
            email_verified=True,
            invite_token=None,
            org_id_hint=None,
        )
        assert is_new is True
        assert resolved_org

        org = db.execute(select(Organisation).where(Organisation.id == resolved_org)).scalar_one_or_none()
        assert org is not None

        mem = db.execute(
            select(OrganisationMembership.id).where(
                OrganisationMembership.user_id == u.id,
                OrganisationMembership.org_id == resolved_org,
            )
        ).scalar_one_or_none()
        assert mem is not None

        ident = db.execute(select(OAuthIdentity).where(OAuthIdentity.user_id == u.id)).scalar_one_or_none()
        assert ident is not None


def test_missing_email_is_rejected(app_client):
    from app.core.database import get_sessionmaker
    from app.services.social_oauth import SocialOAuthService, OAuthFlowError

    with get_sessionmaker()() as db:
        try:
            SocialOAuthService.link_or_create_user(
                db,
                provider="facebook",
                provider_user_id="x",
                email=None,
                email_verified=False,
                invite_token=None,
                org_id_hint=None,
            )
            assert False, "Expected error"
        except OAuthFlowError as e:
            assert "email" in str(e).lower()


def test_unverified_email_does_not_link_existing_account(app_client):
    from app.core.database import get_sessionmaker
    from app.services.social_oauth import SocialOAuthService, OAuthFlowError

    with get_sessionmaker()() as db:
        org = _seed_org(db)
        user = _seed_user(db, email="exists_fb@example.com")
        _seed_membership(db, user.id, org.id)
        db.commit()

        try:
            SocialOAuthService.link_or_create_user(
                db,
                provider="facebook",
                provider_user_id="fb-1",
                email="exists_fb@example.com",
                email_verified=False,
                invite_token=None,
                org_id_hint=None,
            )
            assert False, "Expected error"
        except OAuthFlowError as e:
            assert "already registered" in str(e).lower()

