"""Store Telnyx/Meta WhatsApp templates synced from API.

Revision ID: 0066_telnyx_whatsapp_template_sync
Revises: 0065_telnyx_greeting_settings
"""

from alembic import op
import sqlalchemy as sa

revision = "0066_telnyx_whatsapp_template_sync"
down_revision = "0065_telnyx_greeting_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telnyx_whatsapp_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telnyx_record_id", sa.String(length=64), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="en_US"),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="UNKNOWN"),
        sa.Column("sales_template_key", sa.String(length=64), nullable=True),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("components_json", sa.Text(), nullable=True),
        sa.Column("waba_id", sa.String(length=64), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telnyx_record_id", name="uq_telnyx_wa_tpl_record"),
    )
    op.create_index("ix_telnyx_whatsapp_templates_name", "telnyx_whatsapp_templates", ["name"])
    op.create_index("ix_telnyx_whatsapp_templates_template_id", "telnyx_whatsapp_templates", ["template_id"])
    op.create_index("ix_telnyx_whatsapp_templates_sales_template_key", "telnyx_whatsapp_templates", ["sales_template_key"])


def downgrade() -> None:
    op.drop_index("ix_telnyx_whatsapp_templates_sales_template_key", table_name="telnyx_whatsapp_templates")
    op.drop_index("ix_telnyx_whatsapp_templates_template_id", table_name="telnyx_whatsapp_templates")
    op.drop_index("ix_telnyx_whatsapp_templates_name", table_name="telnyx_whatsapp_templates")
    op.drop_table("telnyx_whatsapp_templates")
