"""WA Survey types + Telnyx template extensions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086_wa_survey_types"
down_revision = "0085_agent_missed_call_email"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_table("survey_types"):
        op.create_table(
            "survey_types",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("slug", sa.String(64), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("default_length", sa.String(16), nullable=False, server_default="standard"),
            sa.Column("min_length", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("max_length", sa.Integer(), nullable=False, server_default="6"),
            sa.Column("supports_anonymous", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_survey_types_slug", "survey_types", ["slug"], unique=True)

    cols = [
        ("survey_type_id", sa.String(36)),
        ("variant_type", sa.String(16)),
        ("parent_template_id", sa.Integer()),
        ("display_name", sa.String(128)),
        ("draft_components_json", sa.Text()),
        ("example_values_json", sa.Text()),
        ("local_sync_status", sa.String(32)),
        ("active_for_survey", sa.Boolean()),
        ("last_pushed_at", sa.DateTime()),
        ("last_push_error", sa.Text()),
        ("remote_content_hash", sa.String(64)),
    ]
    for col_name, col_type in cols:
        if not _has_column("telnyx_whatsapp_templates", col_name):
            kwargs = {"nullable": True}
            if col_name == "local_sync_status":
                kwargs = {"nullable": False, "server_default": "draft"}
            if col_name == "active_for_survey":
                kwargs = {"nullable": False, "server_default": sa.text("1")}
            op.add_column("telnyx_whatsapp_templates", sa.Column(col_name, col_type, **kwargs))

    if _has_table("survey_types") and _has_column("telnyx_whatsapp_templates", "survey_type_id"):
        try:
            op.create_foreign_key(
                "fk_telnyx_wa_tpl_survey_type",
                "telnyx_whatsapp_templates",
                "survey_types",
                ["survey_type_id"],
                ["id"],
            )
        except Exception:
            pass
        try:
            op.create_foreign_key(
                "fk_telnyx_wa_tpl_parent",
                "telnyx_whatsapp_templates",
                "telnyx_whatsapp_templates",
                ["parent_template_id"],
                ["id"],
            )
        except Exception:
            pass


def downgrade() -> None:
    for fk in ("fk_telnyx_wa_tpl_parent", "fk_telnyx_wa_tpl_survey_type"):
        try:
            op.drop_constraint(fk, "telnyx_whatsapp_templates", type_="foreignkey")
        except Exception:
            pass
    for col in (
        "remote_content_hash",
        "last_push_error",
        "last_pushed_at",
        "active_for_survey",
        "local_sync_status",
        "example_values_json",
        "draft_components_json",
        "display_name",
        "parent_template_id",
        "variant_type",
        "survey_type_id",
    ):
        if _has_column("telnyx_whatsapp_templates", col):
            op.drop_column("telnyx_whatsapp_templates", col)
    if _has_table("survey_types"):
        op.drop_index("ix_survey_types_slug", table_name="survey_types")
        op.drop_table("survey_types")
