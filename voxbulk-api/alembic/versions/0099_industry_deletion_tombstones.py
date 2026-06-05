"""Track admin-deleted industry slugs so seeders do not recreate them."""

from alembic import op
import sqlalchemy as sa

revision = "0099_industry_deletion_tombstones"
down_revision = "0098_survey_system_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "industry_deletion_tombstones",
        sa.Column("slug", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("industry_deletion_tombstones")
