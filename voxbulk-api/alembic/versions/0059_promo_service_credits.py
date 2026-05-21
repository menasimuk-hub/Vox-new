"""Promo survey/interview credits for new-user signup offers.

Revision ID: 0059_promo_service_credits
Revises: 0058_billing_payment_modes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059_promo_service_credits"
down_revision = "0058_billing_payment_modes"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("promo_offers", "survey_contacts_included"):
        op.add_column(
            "promo_offers",
            sa.Column("survey_contacts_included", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("promo_offers", "interview_contacts_included"):
        op.add_column(
            "promo_offers",
            sa.Column("interview_contacts_included", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("organisations", "survey_credits_balance"):
        op.add_column(
            "organisations",
            sa.Column("survey_credits_balance", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("organisations", "interview_credits_balance"):
        op.add_column(
            "organisations",
            sa.Column("interview_credits_balance", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _has_column("organisations", "interview_credits_balance"):
        op.drop_column("organisations", "interview_credits_balance")
    if _has_column("organisations", "survey_credits_balance"):
        op.drop_column("organisations", "survey_credits_balance")
    if _has_column("promo_offers", "interview_contacts_included"):
        op.drop_column("promo_offers", "interview_contacts_included")
    if _has_column("promo_offers", "survey_contacts_included"):
        op.drop_column("promo_offers", "survey_contacts_included")
