"""Extend agent_definitions for voice/Telnyx survey workflow.

Revision ID: 0067_voice_agent_extensions
Revises: 0066_telnyx_whatsapp_template_sync
"""

from alembic import op
import sqlalchemy as sa

revision = "0067_voice_agent_extensions"
down_revision = "0066_telnyx_whatsapp_template_sync"
branch_labels = None
depends_on = None

DEFAULT_DISCLOSURE = (
    "Hello, this is {agent_name}, the AI assistant calling from {company_name}. "
    "This call is recorded for quality and service purposes."
)


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in set(inspector.get_table_names())


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "voice_agent_platform_settings"):
        # MySQL does not allow DEFAULT on TEXT columns — insert default row after create.
        op.create_table(
            "voice_agent_platform_settings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("global_compliance_role", sa.Text(), nullable=True),
            sa.Column("opening_disclosure_template", sa.Text(), nullable=False),
            sa.Column("disclosure_mandatory", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("disclosure_for_survey", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("disclosure_for_interview", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.execute(
            sa.text(
                "INSERT INTO voice_agent_platform_settings (id, global_compliance_role, opening_disclosure_template, "
                "disclosure_mandatory, disclosure_for_survey, disclosure_for_interview, updated_at) "
                "VALUES ('default', NULL, :tpl, 1, 1, 1, CURRENT_TIMESTAMP)"
            ).bindparams(tpl=DEFAULT_DISCLOSURE)
        )

    cols = [
        ("voice_label", sa.String(120)),
        ("voice_type_label", sa.String(64)),
        ("telnyx_assistant_id", sa.String(128)),
        ("base_role", sa.Text()),
        ("service_survey_role", sa.Text()),
        ("service_interview_role", sa.Text()),
        ("service_lead_sales_role", sa.Text()),
        ("opening_disclosure_template", sa.Text()),
        ("retry_policy_notes", sa.Text()),
        ("interruption_behavior_notes", sa.Text()),
        ("voicemail_behavior", sa.String(32)),
        ("opt_out_policy_notes", sa.Text()),
    ]
    for name, col_type in cols:
        if not _has_column(inspector, "agent_definitions", name):
            op.add_column("agent_definitions", sa.Column(name, col_type, nullable=True))

    for name in (
        "supports_survey",
        "supports_interview",
        "supports_lead_sales",
        "is_default_survey",
        "is_default_interview",
        "is_default_lead_sales",
        "disclosure_for_survey",
        "disclosure_for_interview",
        "disclosure_mandatory",
    ):
        if not _has_column(inspector, "agent_definitions", name):
            op.add_column(
                "agent_definitions",
                sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )

    if _has_column(sa.inspect(bind), "agent_definitions", "disclosure_mandatory"):
        op.execute("UPDATE agent_definitions SET disclosure_mandatory = 1 WHERE disclosure_mandatory = 0")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for name in (
        "disclosure_mandatory",
        "disclosure_for_interview",
        "disclosure_for_survey",
        "is_default_lead_sales",
        "is_default_interview",
        "is_default_survey",
        "supports_lead_sales",
        "supports_interview",
        "supports_survey",
        "opt_out_policy_notes",
        "voicemail_behavior",
        "interruption_behavior_notes",
        "retry_policy_notes",
        "opening_disclosure_template",
        "service_lead_sales_role",
        "service_interview_role",
        "service_survey_role",
        "base_role",
        "telnyx_assistant_id",
        "voice_type_label",
        "voice_label",
    ):
        if _has_table(inspector, "agent_definitions") and _has_column(inspector, "agent_definitions", name):
            op.drop_column("agent_definitions", name)

    if _has_table(inspector, "voice_agent_platform_settings"):
        op.drop_table("voice_agent_platform_settings")
