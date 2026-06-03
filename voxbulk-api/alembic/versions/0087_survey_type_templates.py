"""Survey type ↔ WhatsApp template many-to-many mappings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0087_survey_type_templates"
down_revision = "0086_wa_survey_types"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    if not _has_table("survey_type_templates"):
        op.create_table(
            "survey_type_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("survey_type_id", sa.String(36), sa.ForeignKey("survey_types.id"), nullable=False),
            sa.Column("template_id", sa.Integer(), sa.ForeignKey("telnyx_whatsapp_templates.id"), nullable=False),
            sa.Column("usable_as_standard", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("usable_as_anonymous", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_default_standard", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_default_anonymous", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("survey_type_id", "template_id", name="uq_survey_type_template_map"),
        )
        op.create_index("ix_survey_type_templates_survey_type_id", "survey_type_templates", ["survey_type_id"])
        op.create_index("ix_survey_type_templates_template_id", "survey_type_templates", ["template_id"])

    if _has_table("telnyx_whatsapp_templates") and _has_table("survey_type_templates"):
        conn = op.get_bind()
        rows = conn.execute(
            sa.text(
                """
                SELECT id, survey_type_id, variant_type
                FROM telnyx_whatsapp_templates
                WHERE survey_type_id IS NOT NULL
                """
            )
        ).fetchall()
        now = sa.text("CURRENT_TIMESTAMP")
        seen_defaults: dict[tuple[str, str], bool] = {}
        for row in rows:
            template_id = row[0]
            survey_type_id = row[1]
            variant = str(row[2] or "standard").lower()
            usable_standard = variant == "standard"
            usable_anonymous = variant == "anonymous"
            default_std_key = (survey_type_id, "standard")
            default_anon_key = (survey_type_id, "anonymous")
            is_default_standard = usable_standard and default_std_key not in seen_defaults
            is_default_anonymous = usable_anonymous and default_anon_key not in seen_defaults
            if is_default_standard:
                seen_defaults[default_std_key] = True
            if is_default_anonymous:
                seen_defaults[default_anon_key] = True
            existing = conn.execute(
                sa.text(
                    """
                    SELECT id FROM survey_type_templates
                    WHERE survey_type_id = :st AND template_id = :tpl
                    """
                ),
                {"st": survey_type_id, "tpl": template_id},
            ).fetchone()
            if existing:
                continue
            conn.execute(
                sa.text(
                    """
                    INSERT INTO survey_type_templates (
                        survey_type_id, template_id,
                        usable_as_standard, usable_as_anonymous,
                        is_default_standard, is_default_anonymous,
                        created_at, updated_at
                    ) VALUES (
                        :survey_type_id, :template_id,
                        :usable_as_standard, :usable_as_anonymous,
                        :is_default_standard, :is_default_anonymous,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "survey_type_id": survey_type_id,
                    "template_id": template_id,
                    "usable_as_standard": usable_standard,
                    "usable_as_anonymous": usable_anonymous,
                    "is_default_standard": is_default_standard,
                    "is_default_anonymous": is_default_anonymous,
                },
            )


def downgrade() -> None:
    if _has_table("survey_type_templates"):
        op.drop_table("survey_type_templates")
