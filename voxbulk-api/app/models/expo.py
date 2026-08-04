"""VoxBulk Expo — WhatsApp exhibition lead capture (sibling product to Customer Feedback)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

EXPO_SERVICE_CODE = "expo"


class ExpoIndustry(Base):
    __tablename__ = "expo_industries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    addon_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoQuestionTemplate(Base):
    """Local Expo qualifying prompts (session text) — not Meta HSM templates."""

    __tablename__ = "expo_question_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    matches_products: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoPackage(Base):
    """Admin-configured per-exhibition package linked to a Plan (service_kind=expo)."""

    __tablename__ = "expo_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False, unique=True, index=True)
    market_zone: Mapped[str] = mapped_column(String(8), nullable=False, default="gb", index=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="day1", index=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_booths: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # Null = unlimited categories (7-day package).
    max_categories: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)
    lead_scoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    post_show_followup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    post_event_survey_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_summary_report_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoExhibition(Base):
    __tablename__ = "expo_exhibitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    industry_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("expo_industries.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/London")
    preferred_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoBooth(Base):
    __tablename__ = "expo_booths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    exhibition_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_exhibitions.id"), nullable=False, index=True)
    package_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("expo_packages.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    booth_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    scan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preview_tests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unpaid")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_intent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of {name, company_name, email, mobile, telephone, website?}
    representative_contacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Single visitor-facing contact email (catalogue / summary emails).
    visitor_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional trade-show offer: {title, description, claim_url, code?, ends_at?}
    offer_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_preview_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    company_website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notify_mobile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoBoothCategory(Base):
    """Product category grouping under a booth (package-capped)."""

    __tablename__ = "expo_booth_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    booth_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_booths.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    accent_color: Mapped[str] = mapped_column(String(32), nullable=False, default="#E8F0FE")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoBoothProduct(Base):
    """Product under a category — may have catalogue / sheet / price assets."""

    __tablename__ = "expo_booth_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    booth_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_booths.id"), nullable=False, index=True)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("expo_booth_categories.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoBoothAsset(Base):
    """Product / info pack (PDF, video link, brochure) for hybrid match-or-list delivery."""

    __tablename__ = "expo_booth_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    booth_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_booths.id"), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("expo_booth_products.id"), nullable=True, index=True
    )
    asset_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="pdf")
    # catalogue | product_sheet | price_list | product | other
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="product")
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoLead(Base):
    __tablename__ = "expo_leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    booth_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_booths.id"), nullable=False, index=True)
    exhibition_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_exhibitions.id"), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    visitor_phone: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    visitor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_card_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest: Mapped[str | None] = mapped_column(Text, nullable=True)
    buying_timeline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lead_score: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    consent_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    offer_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_interested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    offer_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assets_sent_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of {asset_id, asset_key, purpose, opened_at}
    assets_opened_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_status: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoSession(Base):
    __tablename__ = "expo_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    booth_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_booths.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="whatsapp")
    visitor_phone: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    visitor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    session_state_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoVisitorIdentity(Base):
    """Returning visitor at an exhibition — skip business card on later booth scans."""

    __tablename__ = "expo_visitor_identities"
    __table_args__ = (
        UniqueConstraint("exhibition_id", "visitor_token", name="uq_expo_visitor_exhibition_token"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    exhibition_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_exhibitions.id"), nullable=False, index=True)
    visitor_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    visitor_phone: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    visitor_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoOrgProfile(Base):
    """Org-level defaults for Expo Event step (contact email + representatives)."""

    __tablename__ = "expo_org_profiles"

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), primary_key=True)
    visitor_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    representatives_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notify_mobile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoVisitorSummarySend(Base):
    """Idempotency for daily / final visitor summary emails."""

    __tablename__ = "expo_visitor_summary_sends"
    __table_args__ = (
        UniqueConstraint(
            "exhibition_id",
            "visitor_email",
            "summary_date",
            "is_final",
            name="uq_expo_visitor_summary_send",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    exhibition_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_exhibitions.id"), nullable=False, index=True)
    visitor_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    summary_date: Mapped[str] = mapped_column(String(16), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoResponse(Base):
    __tablename__ = "expo_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_sessions.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    booth_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_booths.id"), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(String(128), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_text_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoVoiceNoteJob(Base):
    __tablename__ = "expo_voice_note_jobs"
    __table_args__ = (
        UniqueConstraint(
            "inbound_message_id",
            "provider_media_id",
            name="uq_expo_voice_note_inbound_media",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_sessions.id"), nullable=False, index=True)
    booth_id: Mapped[str] = mapped_column(String(36), ForeignKey("expo_booths.id"), nullable=False, index=True)
    response_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    inbound_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider_media_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoLibraryCategory(Base):
    """Org-level catalogue library (Add catalogues page) — not tied to a booth."""

    __tablename__ = "expo_library_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    accent_color: Mapped[str] = mapped_column(String(32), nullable=False, default="sky")
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoLibraryProduct(Base):
    __tablename__ = "expo_library_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("expo_library_categories.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ExpoLibraryAsset(Base):
    __tablename__ = "expo_library_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("expo_library_products.id"), nullable=True, index=True
    )
    category_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("expo_library_categories.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="pdf")
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="catalogue")
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
