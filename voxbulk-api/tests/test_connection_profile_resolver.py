from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.core.database import get_sessionmaker
from app.models.connection_profile import (
    CHANNEL_WHATSAPP,
    PROVIDER_META,
    PROVIDER_TELNYX,
    ConnectionProfile,
    ConnectionProfileOrg,
    ConnectionProfileService,
)
from app.services.connection.constants import SERVICE_SURVEY
from app.services.connection.config_resolver import resolve_whatsapp_config, whatsapp_provider_is_meta
from app.services.connection.resolver import ConnectionProfileResolver


@pytest.fixture
def db():
    Session = get_sessionmaker()
    session = Session()
    try:
        session.query(ConnectionProfileService).delete()
        session.query(ConnectionProfileOrg).delete()
        session.query(ConnectionProfile).delete()
        session.commit()
        yield session
    finally:
        session.rollback()
        session.close()


def _profile(
    *,
    is_default: bool = False,
    provider: str = PROVIDER_TELNYX,
    name: str = "Test",
) -> ConnectionProfile:
    now = datetime.utcnow()
    return ConnectionProfile(
        id=str(uuid.uuid4()),
        name=name,
        channel=CHANNEL_WHATSAPP,
        provider=provider,
        is_default=is_default,
        is_active=True,
        telnyx_number="+447822002055",
        created_at=now,
        updated_at=now,
    )


def test_resolver_prefers_assigned_org_over_default(db):
    default = _profile(is_default=True, name="Default")
    assigned = _profile(is_default=False, name="Assigned")
    db.add(default)
    db.add(assigned)
    db.flush()
    org_id = str(uuid.uuid4())
    db.add(ConnectionProfileOrg(id=str(uuid.uuid4()), profile_id=assigned.id, org_id=org_id, created_at=datetime.utcnow()))
    for profile_id in (default.id, assigned.id):
        db.add(
            ConnectionProfileService(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                service_code=SERVICE_SURVEY,
                enabled=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
    db.commit()

    resolved = ConnectionProfileResolver.resolve_whatsapp(db, org_id=org_id, service_code=SERVICE_SURVEY)
    assert resolved is not None
    assert resolved.id == assigned.id


def test_resolver_falls_back_to_default(db):
    default = _profile(is_default=True, name="Default")
    db.add(default)
    db.flush()
    db.add(
        ConnectionProfileService(
            id=str(uuid.uuid4()),
            profile_id=default.id,
            service_code=SERVICE_SURVEY,
            enabled=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()

    resolved = ConnectionProfileResolver.resolve_whatsapp(db, org_id=str(uuid.uuid4()), service_code=SERVICE_SURVEY)
    assert resolved is not None
    assert resolved.id == default.id


def test_resolver_meta_profile_when_assigned(db):
    telnyx_default = _profile(is_default=True, name="Telnyx default")
    meta = _profile(is_default=False, provider=PROVIDER_META, name="Meta org")
    db.add(telnyx_default)
    db.add(meta)
    db.flush()
    org_id = str(uuid.uuid4())
    db.add(ConnectionProfileOrg(id=str(uuid.uuid4()), profile_id=meta.id, org_id=org_id, created_at=datetime.utcnow()))
    for profile_id in (telnyx_default.id, meta.id):
        db.add(
            ConnectionProfileService(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                service_code=SERVICE_SURVEY,
                enabled=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
    db.commit()

    resolved = ConnectionProfileResolver.resolve_whatsapp(db, org_id=org_id, service_code=SERVICE_SURVEY)
    assert resolved is not None
    assert resolved.provider == PROVIDER_META


def test_resolve_whatsapp_config_uses_org_profile(db):
    telnyx_default = _profile(is_default=True, name="Telnyx default")
    meta = _profile(is_default=False, provider=PROVIDER_META, name="Meta org")
    meta.meta_waba_id = "waba-1"
    meta.meta_phone_number_id = "phone-1"
    db.add(telnyx_default)
    db.add(meta)
    db.flush()
    org_id = str(uuid.uuid4())
    db.add(ConnectionProfileOrg(id=str(uuid.uuid4()), profile_id=meta.id, org_id=org_id, created_at=datetime.utcnow()))
    for profile_id in (telnyx_default.id, meta.id):
        db.add(
            ConnectionProfileService(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                service_code=SERVICE_SURVEY,
                enabled=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
    db.commit()

    route = resolve_whatsapp_config(db, org_id=org_id, service_code=SERVICE_SURVEY)
    assert route is not None
    assert route.is_meta
    assert route.profile is not None
    assert route.profile.id == meta.id
    assert whatsapp_provider_is_meta(db, org_id=org_id, service_code=SERVICE_SURVEY)


def test_resolve_whatsapp_config_default_telnyx(db):
    default = _profile(is_default=True, name="Default Telnyx")
    db.add(default)
    db.flush()
    db.add(
        ConnectionProfileService(
            id=str(uuid.uuid4()),
            profile_id=default.id,
            service_code=SERVICE_SURVEY,
            enabled=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()

    route = resolve_whatsapp_config(db, org_id=str(uuid.uuid4()), service_code=SERVICE_SURVEY)
    assert route is not None
    assert route.is_telnyx
    assert route.profile is not None
    assert route.profile.id == default.id
