"""Appointment Manager: CRM appointments, logs, org settings, agent flags, call_logs FK."""

from alembic import op
import sqlalchemy as sa

revision = "0129_appointment_manager_foundation"
down_revision = "0128_rename_dentally_appointments"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(i.get("name") == index_name for i in insp.get_indexes(table))


def upgrade() -> None:
    if not _table_exists("appointments"):
        op.create_table(
            "appointments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("contact_name", sa.String(255), nullable=False),
            sa.Column("contact_phone", sa.String(32), nullable=False),
            sa.Column("contact_email", sa.String(320), nullable=True),
            sa.Column("appointment_datetime", sa.DateTime(), nullable=False),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/London"),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("branch", sa.String(255), nullable=True),
            sa.Column("service_type", sa.String(255), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
            sa.Column("crm_source", sa.String(32), nullable=False, server_default="manual"),
            sa.Column("crm_record_id", sa.String(128), nullable=True),
            sa.Column("wa_confirmation_sent_at", sa.DateTime(), nullable=True),
            sa.Column("wa_confirmation_status", sa.String(32), nullable=True),
            sa.Column("call_triggered_at", sa.DateTime(), nullable=True),
            sa.Column("call_outcome", sa.String(32), nullable=True),
            sa.Column("rescheduled_to_datetime", sa.DateTime(), nullable=True),
            sa.Column("rescheduled_from_id", sa.String(36), sa.ForeignKey("appointments.id"), nullable=True),
            sa.Column("confirmation_channel", sa.String(32), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("org_id", "crm_source", "crm_record_id", name="uq_appointments_org_crm_record"),
        )
        op.create_index("ix_appointments_org_id", "appointments", ["org_id"])
        op.create_index("ix_appointments_contact_phone", "appointments", ["contact_phone"])
        op.create_index("ix_appointments_appointment_datetime", "appointments", ["appointment_datetime"])
        op.create_index("ix_appointments_status", "appointments", ["status"])
        op.create_index("ix_appointments_crm_source", "appointments", ["crm_source"])
        op.create_index("ix_appointments_crm_record_id", "appointments", ["crm_record_id"])
        op.create_index("ix_appointments_branch", "appointments", ["branch"])
        op.create_index("ix_appointments_wa_confirmation_sent_at", "appointments", ["wa_confirmation_sent_at"])
        op.create_index("ix_appointments_rescheduled_from_id", "appointments", ["rescheduled_from_id"])

    if not _table_exists("appointment_logs"):
        op.create_table(
            "appointment_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("appointment_id", sa.String(36), sa.ForeignKey("appointments.id"), nullable=False),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("detail_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_appointment_logs_appointment_id", "appointment_logs", ["appointment_id"])
        op.create_index("ix_appointment_logs_event_type", "appointment_logs", ["event_type"])

    if _table_exists("organisations") and not _column_exists("organisations", "appointment_manager_config_json"):
        op.add_column("organisations", sa.Column("appointment_manager_config_json", sa.Text(), nullable=True))

    if _table_exists("call_logs") and not _column_exists("call_logs", "appointment_id"):
        op.add_column(
            "call_logs",
            sa.Column("appointment_id", sa.String(36), sa.ForeignKey("appointments.id"), nullable=True),
        )
        if not _index_exists("call_logs", "ix_call_logs_appointment_id"):
            op.create_index("ix_call_logs_appointment_id", "call_logs", ["appointment_id"])

    if _table_exists("agent_definitions"):
        for col, col_type in (
            ("supports_appointment", sa.Boolean()),
            ("service_appointment_role", sa.Text()),
            ("is_default_appointment", sa.Boolean()),
            ("disclosure_for_appointment", sa.Boolean()),
        ):
            if not _column_exists("agent_definitions", col):
                kwargs = {"nullable": False, "server_default": sa.false()} if "bool" in str(col_type).lower() or col.startswith("supports") or col.startswith("is_") or col.startswith("disclosure") else {"nullable": True}
                if col == "supports_appointment" or col == "is_default_appointment" or col == "disclosure_for_appointment":
                    op.add_column("agent_definitions", sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.false()))
                else:
                    op.add_column("agent_definitions", sa.Column(col, sa.Text(), nullable=True))


def downgrade() -> None:
    if _table_exists("agent_definitions"):
        for col in ("disclosure_for_appointment", "is_default_appointment", "service_appointment_role", "supports_appointment"):
            if _column_exists("agent_definitions", col):
                op.drop_column("agent_definitions", col)

    if _column_exists("call_logs", "appointment_id"):
        op.drop_index("ix_call_logs_appointment_id", table_name="call_logs")
        op.drop_column("call_logs", "appointment_id")

    if _column_exists("organisations", "appointment_manager_config_json"):
        op.drop_column("organisations", "appointment_manager_config_json")

    if _table_exists("appointment_logs"):
        op.drop_table("appointment_logs")

    if _table_exists("appointments"):
        op.drop_table("appointments")
