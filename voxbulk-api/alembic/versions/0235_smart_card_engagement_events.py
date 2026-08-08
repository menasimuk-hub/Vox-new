"""Add smart_card_engagement_events for public card click KPIs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0235_smart_card_engagement_events"
down_revision = "0234_qr_style_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "smart_card_engagement_events" in tables:
        return
    op.create_table(
        "smart_card_engagement_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column(
            "representative_id",
            sa.String(length=36),
            sa.ForeignKey("smart_card_representatives.id"),
            nullable=False,
        ),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sc_eng_events_org_id", "smart_card_engagement_events", ["org_id"])
    op.create_index("ix_sc_eng_events_rep_id", "smart_card_engagement_events", ["representative_id"])
    op.create_index("ix_sc_eng_events_lead_id", "smart_card_engagement_events", ["lead_id"])
    op.create_index("ix_sc_eng_events_type", "smart_card_engagement_events", ["event_type"])
    op.create_index("ix_sc_eng_events_created", "smart_card_engagement_events", ["created_at"])
    op.create_index(
        "ix_sc_eng_events_org_rep_type_created",
        "smart_card_engagement_events",
        ["org_id", "representative_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "smart_card_engagement_events" not in tables:
        return
    op.drop_index("ix_sc_eng_events_org_rep_type_created", table_name="smart_card_engagement_events")
    op.drop_index("ix_sc_eng_events_created", table_name="smart_card_engagement_events")
    op.drop_index("ix_sc_eng_events_type", table_name="smart_card_engagement_events")
    op.drop_index("ix_sc_eng_events_lead_id", table_name="smart_card_engagement_events")
    op.drop_index("ix_sc_eng_events_rep_id", table_name="smart_card_engagement_events")
    op.drop_index("ix_sc_eng_events_org_id", table_name="smart_card_engagement_events")
    op.drop_table("smart_card_engagement_events")
