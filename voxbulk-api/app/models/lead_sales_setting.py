from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LeadSalesSetting(Base):
    __tablename__ = "lead_sales_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    telnyx_assistant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    telnyx_greeting: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_file_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    calling_hour_start: Mapped[int] = mapped_column(nullable=False, default=9)
    calling_hour_end: Mapped[int] = mapped_column(nullable=False, default=18)
    calling_days: Mapped[str] = mapped_column(String(32), nullable=False, default="1,2,3,4,5")
    sales_automation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sales_auto_plan_code: Mapped[str] = mapped_column(String(64), nullable=False, default="dental_1")
    sales_auto_trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    sales_auto_offer_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dental_trial")
    sales_auto_survey_contacts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    sales_auto_interview_contacts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    sales_template_subscription_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sales_template_survey_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sales_template_interview_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sales_followup_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
