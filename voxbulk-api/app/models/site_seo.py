from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SiteSeoSettings(Base):
    __tablename__ = "site_seo_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    site_name: Mapped[str] = mapped_column(String(160), nullable=False, default="VoxBulk")
    title_template: Mapped[str] = mapped_column(String(200), nullable=False, default="%title% | %sitename%")
    default_meta_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_social_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    home_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    home_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    home_focus_keyword: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    home_tags: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # JSON map of path key → {title, description, keywords, og_description}
    # Keys: surveys, feedback, recruitment, pricing, contact
    marketing_pages_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    schema_organization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schema_website: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schema_breadcrumbs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schema_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    google_site_verification: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    google_analytics_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    meta_pixel_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    linkedin_partner_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    google_ads_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    x_pixel_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    tiktok_pixel_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    pinterest_tag_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    google_news_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    google_news_publication: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    google_news_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    gsc_property_url: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    gsc_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    gsc_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    psi_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    psi_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    moz_access_id_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    moz_secret_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    moz_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    indexnow_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    indexnow_last_pinged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    robots_txt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sitemap_last_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sitemap_last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bing_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    bing_site_url: Mapped[str] = mapped_column(String(300), nullable=False, default="https://voxbulk.com")
    bing_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bing_last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bing_last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    yandex_oauth_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    yandex_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    yandex_host_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    yandex_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    yandex_last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    yandex_last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auto_submit_weekly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_indexnow_on_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    engines_last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    engines_last_result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    keyword_ideas_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    google_last_submit_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    gsc_avg_position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gsc_avg_position_prev: Mapped[str | None] = mapped_column(String(32), nullable=True)
    moz_domain_authority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    moz_domain_authority_prev: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SiteSeoRedirect(Base):
    __tablename__ = "site_seo_redirects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    from_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    to_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=301)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SiteSeoHealthSnapshot(Base):
    __tablename__ = "site_seo_health_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="latest")
    site_health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lcp_ms: Mapped[str | None] = mapped_column(String(32), nullable=True)
    inp_ms: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cls: Mapped[str | None] = mapped_column(String(32), nullable=True)
    psi_score: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mobile_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    broken_links_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    structured_data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
