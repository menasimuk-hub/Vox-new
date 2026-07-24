"""Alembic migration: integration Test group + Testing/Live release mode + FAQ link."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0177_integration_release_testers"
down_revision = "0176_zoho_recruit_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_testers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_admin_user_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_integration_testers_email"),
    )
    op.create_index("ix_integration_testers_email", "integration_testers", ["email"])

    op.add_column(
        "provider_configs",
        sa.Column("release_mode", sa.String(length=16), nullable=False, server_default="testing"),
    )
    op.execute(
        "UPDATE provider_configs SET release_mode = 'live' WHERE visible_to_orgs = 1 OR visible_to_orgs = true"
    )

    op.add_column(
        "partner_providers",
        sa.Column("release_mode", sa.String(length=16), nullable=False, server_default="testing"),
    )
    op.execute(
        "UPDATE partner_providers SET release_mode = 'live' WHERE enabled = 1 OR enabled = true"
    )

    op.add_column(
        "faq_items",
        sa.Column("linked_provider", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_faq_items_linked_provider", "faq_items", ["linked_provider"])
    # Link Zoho Recruit marketing FAQs (category/slug patterns) when present.
    op.execute(
        """
        UPDATE faq_items
        SET linked_provider = 'zoho_recruit'
        WHERE linked_provider IS NULL
          AND (
            LOWER(slug) LIKE 'zoho%'
            OR LOWER(question) LIKE '%zoho recruit%'
            OR category_id IN (
              SELECT id FROM faq_categories
              WHERE LOWER(name) LIKE '%zoho%' OR LOWER(slug) LIKE '%zoho%'
            )
          )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_faq_items_linked_provider", table_name="faq_items")
    op.drop_column("faq_items", "linked_provider")
    op.drop_column("partner_providers", "release_mode")
    op.drop_column("provider_configs", "release_mode")
    op.drop_index("ix_integration_testers_email", table_name="integration_testers")
    op.drop_table("integration_testers")
