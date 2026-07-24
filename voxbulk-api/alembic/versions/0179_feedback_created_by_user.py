"""Add created_by_user_id to feedback locations and promo campaigns."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0179_feedback_created_by_user"
down_revision = "0178_breezy_hr_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback_locations",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_feedback_locations_created_by_user_id",
        "feedback_locations",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_feedback_locations_created_by_user_id_users",
        "feedback_locations",
        "users",
        ["created_by_user_id"],
        ["id"],
    )

    op.add_column(
        "feedback_promo_campaigns",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_feedback_promo_campaigns_created_by_user_id",
        "feedback_promo_campaigns",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_feedback_promo_campaigns_created_by_user_id_users",
        "feedback_promo_campaigns",
        "users",
        ["created_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_feedback_promo_campaigns_created_by_user_id_users",
        "feedback_promo_campaigns",
        type_="foreignkey",
    )
    op.drop_index("ix_feedback_promo_campaigns_created_by_user_id", table_name="feedback_promo_campaigns")
    op.drop_column("feedback_promo_campaigns", "created_by_user_id")

    op.drop_constraint(
        "fk_feedback_locations_created_by_user_id_users",
        "feedback_locations",
        type_="foreignkey",
    )
    op.drop_index("ix_feedback_locations_created_by_user_id", table_name="feedback_locations")
    op.drop_column("feedback_locations", "created_by_user_id")
