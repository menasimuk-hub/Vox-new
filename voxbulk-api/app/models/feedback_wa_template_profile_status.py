"""Per-connection-profile status for Customer Feedback WhatsApp templates.

One ``feedback_wa_templates`` row holds shared content (name, body, language).
Meta 99 and Telnyx 55 each keep their own approval/remote id in this ledger.
Does not change send workflow — sends still use ``meta_template_name``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeedbackWaTemplateProfileStatus(Base):
    __tablename__ = "feedback_wa_template_profile_status"
    __table_args__ = (
        UniqueConstraint(
            "feedback_template_id",
            "connection_profile_id",
            name="uq_feedback_wa_tpl_profile_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("feedback_wa_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("connection_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    profile_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    meta_template_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    remote_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
