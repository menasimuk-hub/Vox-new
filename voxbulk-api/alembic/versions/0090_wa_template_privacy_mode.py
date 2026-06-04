"""Add privacy_mode to WA survey templates and template pack metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0090_wa_template_privacy_mode"
down_revision = "0089_wa_survey_template_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_template_packs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("survey_type_id", sa.String(36), sa.ForeignKey("survey_types.id"), nullable=False),
        sa.Column("privacy_mode", sa.String(8), nullable=False, server_default="off"),
        sa.Column("template_count", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("service_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("theme_variant", sa.String(128), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_survey_template_packs_survey_type_id", "survey_template_packs", ["survey_type_id"])
    op.create_index("ix_survey_template_packs_privacy_mode", "survey_template_packs", ["privacy_mode"])

    op.add_column(
        "telnyx_whatsapp_templates",
        sa.Column("privacy_mode", sa.String(8), nullable=False, server_default="off"),
    )
    op.add_column(
        "telnyx_whatsapp_templates",
        sa.Column("pack_id", sa.String(36), sa.ForeignKey("survey_template_packs.id"), nullable=True),
    )
    op.create_index("ix_telnyx_whatsapp_templates_privacy_mode", "telnyx_whatsapp_templates", ["privacy_mode"])
    op.create_index("ix_telnyx_whatsapp_templates_pack_id", "telnyx_whatsapp_templates", ["pack_id"])

    op.add_column(
        "survey_type_templates",
        sa.Column("privacy_mode", sa.String(8), nullable=False, server_default="off"),
    )
    op.create_index("ix_survey_type_templates_privacy_mode", "survey_type_templates", ["privacy_mode"])

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE telnyx_whatsapp_templates SET privacy_mode = 'on' "
            "WHERE LOWER(COALESCE(variant_type, '')) = 'anonymous'"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE survey_type_templates SET privacy_mode = 'on' "
            "WHERE usable_as_anonymous = 1 AND usable_as_standard = 0"
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE survey_type_templates st
            INNER JOIN telnyx_whatsapp_templates t ON t.id = st.template_id
            SET st.privacy_mode = 'on'
            WHERE LOWER(COALESCE(t.variant_type, '')) = 'anonymous'
              AND st.privacy_mode = 'off'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_survey_type_templates_privacy_mode", table_name="survey_type_templates")
    op.drop_column("survey_type_templates", "privacy_mode")

    op.drop_index("ix_telnyx_whatsapp_templates_pack_id", table_name="telnyx_whatsapp_templates")
    op.drop_index("ix_telnyx_whatsapp_templates_privacy_mode", table_name="telnyx_whatsapp_templates")
    op.drop_column("telnyx_whatsapp_templates", "pack_id")
    op.drop_column("telnyx_whatsapp_templates", "privacy_mode")

    op.drop_index("ix_survey_template_packs_privacy_mode", table_name="survey_template_packs")
    op.drop_index("ix_survey_template_packs_survey_type_id", table_name="survey_template_packs")
    op.drop_table("survey_template_packs")
