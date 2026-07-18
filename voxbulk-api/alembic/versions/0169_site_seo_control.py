"""0169 — SEO Control: settings, redirects, health, content SEO columns.

Revision ID: 0169_site_seo_control
Revises: 0168_site_blog_news
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0169_site_seo_control"
down_revision = "0168_site_blog_news"
branch_labels = None
depends_on = None

DEFAULT_ROBOTS = """User-agent: *
Allow: /
Disallow: /onboarding
Disallow: /signin

Sitemap: https://voxbulk.com/sitemap.xml
"""

DEFAULT_DESC = (
    "VoxBulk is an AI assistant platform that automates conversations, "
    "workflows and data collection for modern businesses."
)


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return (base or "faq-item")[:160]


def upgrade() -> None:
    op.create_table(
        "site_seo_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_name", sa.String(160), nullable=False, server_default="VoxBulk"),
        sa.Column("title_template", sa.String(200), nullable=False, server_default="%title% | %sitename%"),
        sa.Column("default_meta_description", sa.Text(), nullable=False),
        sa.Column("default_social_image_url", sa.String(500), nullable=True),
        sa.Column("home_title", sa.String(300), nullable=False, server_default=""),
        sa.Column("home_description", sa.Text(), nullable=False),
        sa.Column("home_focus_keyword", sa.String(200), nullable=False, server_default=""),
        sa.Column("home_tags", sa.String(500), nullable=False, server_default=""),
        sa.Column("schema_organization", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schema_website", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schema_breadcrumbs", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schema_content", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("google_site_verification", sa.String(200), nullable=False, server_default=""),
        sa.Column("google_analytics_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("meta_pixel_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("linkedin_partner_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("google_ads_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("x_pixel_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("tiktok_pixel_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("pinterest_tag_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("google_news_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("google_news_publication", sa.String(200), nullable=False, server_default=""),
        sa.Column("google_news_language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("gsc_property_url", sa.String(300), nullable=False, server_default=""),
        sa.Column("gsc_refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("gsc_connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("psi_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("psi_connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("moz_access_id_encrypted", sa.Text(), nullable=True),
        sa.Column("moz_secret_key_encrypted", sa.Text(), nullable=True),
        sa.Column("moz_connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("indexnow_key", sa.String(80), nullable=False, server_default=""),
        sa.Column("indexnow_last_pinged_at", sa.DateTime(), nullable=True),
        sa.Column("robots_txt", sa.Text(), nullable=False),
        sa.Column("sitemap_last_generated_at", sa.DateTime(), nullable=True),
        sa.Column("sitemap_last_submitted_at", sa.DateTime(), nullable=True),
        sa.Column("gsc_avg_position", sa.String(32), nullable=True),
        sa.Column("gsc_avg_position_prev", sa.String(32), nullable=True),
        sa.Column("moz_domain_authority", sa.String(32), nullable=True),
        sa.Column("moz_domain_authority_prev", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "site_seo_redirects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_path", sa.String(500), nullable=False),
        sa.Column("to_path", sa.String(500), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="301"),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("from_path", name="uq_site_seo_redirects_from_path"),
    )
    op.create_index("ix_site_seo_redirects_from_path", "site_seo_redirects", ["from_path"])
    op.create_table(
        "site_seo_health_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_health_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lcp_ms", sa.String(32), nullable=True),
        sa.Column("inp_ms", sa.String(32), nullable=True),
        sa.Column("cls", sa.String(32), nullable=True),
        sa.Column("psi_score", sa.String(32), nullable=True),
        sa.Column("mobile_note", sa.Text(), nullable=False),
        sa.Column("broken_links_json", sa.Text(), nullable=False),
        sa.Column("structured_data_json", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.add_column("site_blog_news_items", sa.Column("meta_title", sa.String(300), nullable=False, server_default=""))
    op.add_column("site_blog_news_items", sa.Column("meta_description", sa.Text(), nullable=False))
    op.add_column("site_blog_news_items", sa.Column("canonical_url", sa.String(500), nullable=False, server_default=""))
    op.add_column(
        "site_blog_news_items",
        sa.Column("robots", sa.String(64), nullable=False, server_default="index,follow"),
    )
    op.add_column("site_blog_news_items", sa.Column("focus_keyword", sa.String(200), nullable=False, server_default=""))
    op.add_column("site_blog_news_items", sa.Column("tags", sa.String(500), nullable=False, server_default=""))
    op.add_column("site_blog_news_items", sa.Column("social_title", sa.String(300), nullable=False, server_default=""))
    op.add_column("site_blog_news_items", sa.Column("social_description", sa.Text(), nullable=False))
    op.add_column("site_blog_news_items", sa.Column("social_image_url", sa.String(500), nullable=True))
    op.add_column(
        "site_blog_news_items",
        sa.Column("index_status", sa.String(32), nullable=False, server_default="pending"),
    )
    op.add_column("site_blog_news_items", sa.Column("index_requested_at", sa.DateTime(), nullable=True))
    op.add_column("site_blog_news_items", sa.Column("seo_updated_at", sa.DateTime(), nullable=True))

    op.add_column("faq_items", sa.Column("slug", sa.String(180), nullable=False, server_default=""))
    op.add_column("faq_items", sa.Column("meta_title", sa.String(300), nullable=False, server_default=""))
    op.add_column("faq_items", sa.Column("meta_description", sa.Text(), nullable=False))
    op.add_column("faq_items", sa.Column("canonical_url", sa.String(500), nullable=False, server_default=""))
    op.add_column("faq_items", sa.Column("robots", sa.String(64), nullable=False, server_default="index,follow"))
    op.add_column("faq_items", sa.Column("focus_keyword", sa.String(200), nullable=False, server_default=""))
    op.add_column("faq_items", sa.Column("tags", sa.String(500), nullable=False, server_default=""))
    op.add_column("faq_items", sa.Column("social_title", sa.String(300), nullable=False, server_default=""))
    op.add_column("faq_items", sa.Column("social_description", sa.Text(), nullable=False))
    op.add_column("faq_items", sa.Column("social_image_url", sa.String(500), nullable=True))
    op.add_column("faq_items", sa.Column("author", sa.String(120), nullable=False, server_default=""))
    op.add_column("faq_items", sa.Column("published_at", sa.DateTime(), nullable=True))
    op.add_column("faq_items", sa.Column("index_status", sa.String(32), nullable=False, server_default="pending"))
    op.add_column("faq_items", sa.Column("index_requested_at", sa.DateTime(), nullable=True))
    op.add_column("faq_items", sa.Column("seo_updated_at", sa.DateTime(), nullable=True))
    op.create_index("ix_faq_items_slug", "faq_items", ["slug"])

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO site_seo_settings ("
            "id, site_name, title_template, default_meta_description, home_title, home_description, "
            "home_focus_keyword, home_tags, schema_organization, schema_website, schema_breadcrumbs, "
            "schema_content, google_site_verification, google_analytics_id, meta_pixel_id, "
            "linkedin_partner_id, google_ads_id, x_pixel_id, tiktok_pixel_id, pinterest_tag_id, "
            "google_news_enabled, google_news_publication, google_news_language, gsc_property_url, "
            "gsc_connected, psi_connected, moz_connected, indexnow_key, robots_txt, updated_at"
            ") VALUES ("
            "'default', 'VoxBulk', '%title% | %sitename%', :desc, '', '', '', '', 1, 1, 1, 1, "
            "'', '', '', '', '', '', '', '', 0, '', 'en', '', 0, 0, 0, '', :robots, UTC_TIMESTAMP())"
        ),
        {"desc": DEFAULT_DESC, "robots": DEFAULT_ROBOTS},
    )
    conn.execute(
        sa.text(
            "INSERT INTO site_seo_health_snapshots ("
            "id, site_health_score, mobile_note, broken_links_json, structured_data_json, updated_at"
            ") VALUES ('latest', 0, '', '[]', '{}', UTC_TIMESTAMP())"
        )
    )

    rows = conn.execute(sa.text("SELECT id, question FROM faq_items")).fetchall()
    used: set[str] = set()
    for row in rows:
        rid, question = row[0], row[1]
        slug = _slugify(str(question or ""))
        base = slug
        n = 2
        while slug in used:
            slug = f"{base}-{n}"[:180]
            n += 1
        used.add(slug)
        conn.execute(
            sa.text(
                "UPDATE faq_items SET slug=:slug, "
                "published_at=COALESCE(published_at, created_at), "
                "index_status=CASE WHEN is_published=1 THEN 'pending' ELSE 'excluded' END "
                "WHERE id=:id"
            ),
            {"slug": slug, "id": rid},
        )

    conn.execute(
        sa.text(
            "UPDATE site_blog_news_items SET "
            "index_status=CASE WHEN is_visible=0 OR robots LIKE 'noindex%' THEN 'excluded' ELSE 'pending' END, "
            "meta_title=CASE WHEN meta_title='' THEN title ELSE meta_title END, "
            "meta_description=CASE WHEN meta_description IS NULL OR meta_description='' "
            "THEN excerpt ELSE meta_description END, "
            "social_description=CASE WHEN social_description IS NULL THEN '' ELSE social_description END"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE faq_items SET meta_description=CASE WHEN meta_description IS NULL THEN '' ELSE meta_description END, "
            "social_description=CASE WHEN social_description IS NULL THEN '' ELSE social_description END"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_faq_items_slug", table_name="faq_items")
    for col in [
        "seo_updated_at",
        "index_requested_at",
        "index_status",
        "published_at",
        "author",
        "social_image_url",
        "social_description",
        "social_title",
        "tags",
        "focus_keyword",
        "robots",
        "canonical_url",
        "meta_description",
        "meta_title",
        "slug",
    ]:
        op.drop_column("faq_items", col)
    for col in [
        "seo_updated_at",
        "index_requested_at",
        "index_status",
        "social_image_url",
        "social_description",
        "social_title",
        "tags",
        "focus_keyword",
        "robots",
        "canonical_url",
        "meta_description",
        "meta_title",
    ]:
        op.drop_column("site_blog_news_items", col)
    op.drop_table("site_seo_health_snapshots")
    op.drop_index("ix_site_seo_redirects_from_path", table_name="site_seo_redirects")
    op.drop_table("site_seo_redirects")
    op.drop_table("site_seo_settings")
