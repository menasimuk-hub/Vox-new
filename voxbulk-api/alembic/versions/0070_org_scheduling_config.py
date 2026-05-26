"""Organisation scheduling config for Calendly/Cronofy."""

from alembic import op
import sqlalchemy as sa

revision = "0070_org_scheduling_config"
down_revision = "0069_career_mailbox_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("organisations")}
    if "scheduling_config_json" not in cols:
        op.add_column("organisations", sa.Column("scheduling_config_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("organisations")}
    if "scheduling_config_json" in cols:
        op.drop_column("organisations", "scheduling_config_json")
