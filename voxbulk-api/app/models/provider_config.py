from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProviderConfig(Base):
    """
    Encrypted provider configuration record.

    - Secrets are stored encrypted in `encrypted_json`.
    - Never return decrypted secrets from any API response.
    """

    __tablename__ = "provider_configs"
    __table_args__ = (
        UniqueConstraint("scope", "org_id", "provider", name="uq_provider_config_scope_org_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # scope: "platform" (admin-wide) or "tenant" (per-organisation). Phase: default platform only.
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="platform", index=True)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=True, index=True)

    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # twilio/dentally/vapi/gocardless
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    visible_to_orgs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    encrypted_json: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

