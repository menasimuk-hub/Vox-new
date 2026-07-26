"""Silent Expo 3-day company-email signup trial.

Revision ID: 0191_expo_signup_company_trial
Revises: 0189_expo_asset_purpose_opened
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0191_expo_signup_company_trial"
down_revision = "0189_expo_asset_purpose_opened"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expo_company_domain_claims",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email_domain", sa.String(length=255), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("claimed_email", sa.String(length=320), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("entitlement_consumed_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_booth_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint("email_domain", name="uq_expo_company_domain_claims_email_domain"),
    )
    op.create_index("ix_expo_company_domain_claims_email_domain", "expo_company_domain_claims", ["email_domain"])
    op.create_index("ix_expo_company_domain_claims_org_id", "expo_company_domain_claims", ["org_id"])
    op.create_index("ix_expo_company_domain_claims_user_id", "expo_company_domain_claims", ["user_id"])

    op.create_table(
        "expo_signup_entitlements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("remaining", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_domain", sa.String(length=255), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_booth_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint("org_id", name="uq_expo_signup_entitlements_org"),
    )
    op.create_index("ix_expo_signup_entitlements_org_id", "expo_signup_entitlements", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_expo_signup_entitlements_org_id", table_name="expo_signup_entitlements")
    op.drop_table("expo_signup_entitlements")
    op.drop_index("ix_expo_company_domain_claims_user_id", table_name="expo_company_domain_claims")
    op.drop_index("ix_expo_company_domain_claims_org_id", table_name="expo_company_domain_claims")
    op.drop_index("ix_expo_company_domain_claims_email_domain", table_name="expo_company_domain_claims")
    op.drop_table("expo_company_domain_claims")
