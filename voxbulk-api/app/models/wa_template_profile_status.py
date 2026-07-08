"""Per-connection-profile approval status for a WhatsApp template.

One ``telnyx_whatsapp_templates`` row stores a single global Meta approval
status. A template can, however, be pushed to more than one connection profile
(e.g. Meta 99 and Telnyx 55) and each profile keeps its own approval state and
remote IDs. This registry keeps one row per ``(template_id, profile_key)`` so
the admin can see, per profile, whether a template is Approved / Pending /
Rejected / Local — without duplicating template content.

The single template row remains the runtime source of truth for the *last*
synced profile; this table is an additive status ledger populated as each
profile is pulled/pushed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Sentinel profile key used when a sync ran against the platform default
# WhatsApp integration and no explicit connection profile was selected.
PLATFORM_PROFILE_KEY = "platform"


class WaTemplateProfileStatus(Base):
    __tablename__ = "wa_template_profile_status"
    __table_args__ = (
        UniqueConstraint("template_id", "profile_key", name="uq_wa_tpl_profile_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("telnyx_whatsapp_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Profile UUID, or PLATFORM_PROFILE_KEY when the platform default was used.
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    connection_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("connection_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    profile_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    waba_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
