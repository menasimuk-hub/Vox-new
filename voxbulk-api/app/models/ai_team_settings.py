from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiTeamSettings(Base):
    __tablename__ = "ai_team_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")

    # Apollo search profile
    search_sector: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    search_country: Mapped[str] = mapped_column(String(64), nullable=False, default="United Kingdom")
    search_company_size: Mapped[str] = mapped_column(String(64), nullable=False, default="10-50")
    search_title_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    search_city_region: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    search_max_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    search_min_score: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    followup_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_followups: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    # Email content (DeepSeek)
    sender_name: Mapped[str] = mapped_column(String(128), nullable=False, default="VoxBulk team")
    reply_to_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    from_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    writing_instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email_signature: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email_html_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_language: Mapped[str] = mapped_column(String(32), nullable=False, default="en-GB")
    email_max_words: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    email_tone: Mapped[str] = mapped_column(String(64), nullable=False, default="direct")

    # Promo defaults
    promo_code_prefix: Mapped[str] = mapped_column(String(32), nullable=False, default="TRIAL")
    promo_offer_type: Mapped[str] = mapped_column(String(32), nullable=False, default="survey_credits")
    promo_value: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    promo_expiry_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    promo_max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    promo_code_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="unique")

    # Outreach mailbox (optional SMTP for replies inbox)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    smtp_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    inbox_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")

    # Resend domain (stored here for admin UI; API key in provider_configs)
    resend_sending_domain: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # Agent behaviour
    run_schedule: Mapped[str] = mapped_column(String(64), nullable=False, default="daily_08")
    max_emails_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    sending_window: Mapped[str] = mapped_column(String(64), nullable=False, default="weekday_08_18")
    auto_fetch_prospects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_draft_emails: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_followup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    track_opens: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_promo_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_send_without_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    apollo_credit_alert_at: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    agent_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_agent_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
