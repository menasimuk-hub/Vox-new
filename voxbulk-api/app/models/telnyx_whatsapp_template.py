from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TelnyxWhatsappTemplate(Base):
    """Meta/Telnyx WhatsApp templates synced from Telnyx API (for send by template_id)."""

    __tablename__ = "telnyx_whatsapp_templates"
    __table_args__ = (UniqueConstraint("telnyx_record_id", name="uq_telnyx_wa_tpl_record"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telnyx_record_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en_US")
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    sales_template_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    components_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    waba_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("industries.id"), nullable=True, index=True)
    survey_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("survey_types.id"), nullable=True, index=True)
    variant_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    step_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    outcome_key: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    outcome_variables_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="off", index=True)
    pack_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("survey_template_packs.id"), nullable=True, index=True)
    parent_template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("telnyx_whatsapp_templates.id"), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    draft_components_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    active_for_survey: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
