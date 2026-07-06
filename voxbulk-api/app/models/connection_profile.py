from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_CALLING = "calling"

PROVIDER_TELNYX = "telnyx"
PROVIDER_META = "meta"


class ConnectionProfile(Base):
    __tablename__ = "connection_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    telnyx_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    telnyx_messaging_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telnyx_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    telnyx_connection_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telnyx_outbound_voice_profile_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    meta_waba_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_phone_number_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_business_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_app_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_webhook_verify_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_whatsapp_from: Mapped[str | None] = mapped_column(String(32), nullable=True)

    calling_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    regions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ConnectionProfileOrg(Base):
    __tablename__ = "connection_profile_orgs"
    __table_args__ = (UniqueConstraint("profile_id", "org_id", name="uq_connection_profile_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("connection_profiles.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ConnectionProfileService(Base):
    __tablename__ = "connection_profile_services"
    __table_args__ = (UniqueConstraint("profile_id", "service_code", name="uq_connection_profile_service"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("connection_profiles.id"), nullable=False, index=True)
    service_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
