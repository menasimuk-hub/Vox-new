"""Add salesman mail fields and tables (labels, contacts, messages).

MySQL notes:
- TEXT columns cannot use DEFAULT '' (error 1101).
- FK to sales_reps.id / sales_customers.id must match charset/collation (error 3780).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0223_salesman_mail"
down_revision = "0222_support_requester_email"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def _column_collation(table: str, column: str) -> str | None:
    bind = op.get_bind()
    try:
        return bind.execute(
            sa.text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table AND COLUMN_NAME = :column "
                "LIMIT 1"
            ),
            {"table": table, "column": column},
        ).scalar()
    except Exception:
        return None


def _id_type(collation: str | None) -> sa.String:
    return sa.String(36, collation=collation) if collation else sa.String(36)


def _table_kwargs(collation: str | None) -> dict:
    if not collation:
        return {}
    return {"mysql_charset": "utf8mb4", "mysql_collate": collation}


def upgrade() -> None:
    # Mailbox fields on sales_reps (idempotent — may have failed mid-run earlier)
    _add_column_if_missing("sales_reps", sa.Column("smtp_host", sa.String(length=255), nullable=False, server_default=""))
    _add_column_if_missing("sales_reps", sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"))
    _add_column_if_missing("sales_reps", sa.Column("smtp_use_tls", sa.Boolean(), nullable=False, server_default="1"))
    _add_column_if_missing("sales_reps", sa.Column("smtp_use_ssl", sa.Boolean(), nullable=False, server_default="0"))
    _add_column_if_missing("sales_reps", sa.Column("smtp_username", sa.String(length=320), nullable=False, server_default=""))
    _add_column_if_missing("sales_reps", sa.Column("smtp_password_enc", sa.Text(), nullable=True))
    _add_column_if_missing("sales_reps", sa.Column("imap_host", sa.String(length=255), nullable=False, server_default=""))
    _add_column_if_missing("sales_reps", sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"))
    _add_column_if_missing("sales_reps", sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default="1"))
    _add_column_if_missing("sales_reps", sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default="0"))
    _add_column_if_missing("sales_reps", sa.Column("imap_username", sa.String(length=320), nullable=False, server_default=""))
    _add_column_if_missing("sales_reps", sa.Column("imap_password_enc", sa.Text(), nullable=True))

    # MySQL rejects DEFAULT on TEXT — add nullable, backfill, then NOT NULL
    if not _has_column("sales_reps", "email_signature"):
        op.add_column("sales_reps", sa.Column("email_signature", sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE sales_reps SET email_signature = '' WHERE email_signature IS NULL"))
    op.alter_column(
        "sales_reps",
        "email_signature",
        existing_type=sa.Text(),
        nullable=False,
    )

    rep_collation = _column_collation("sales_reps", "id")
    cust_collation = _column_collation("sales_customers", "id") or rep_collation
    rep_id = _id_type(rep_collation)
    cust_id = _id_type(cust_collation)
    table_kwargs = _table_kwargs(rep_collation)

    if not _has_table("sales_mail_labels"):
        op.create_table(
            "sales_mail_labels",
            sa.Column("id", rep_id, nullable=False),
            sa.Column("sales_rep_id", rep_id, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("color", sa.String(length=32), nullable=False, server_default="#3b82f6"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["sales_rep_id"], ["sales_reps.id"], name="fk_sales_mail_labels_sales_rep_id"),
            sa.PrimaryKeyConstraint("id"),
            **table_kwargs,
        )
        op.create_index("ix_sales_mail_labels_sales_rep_id", "sales_mail_labels", ["sales_rep_id"])

    if not _has_table("sales_mail_contacts"):
        op.create_table(
            "sales_mail_contacts",
            sa.Column("id", rep_id, nullable=False),
            sa.Column("sales_rep_id", rep_id, nullable=False),
            sa.Column("sales_customer_id", cust_id, nullable=True),
            sa.Column("email", sa.String(length=320), nullable=False, server_default=""),
            sa.Column("name", sa.String(length=200), nullable=True),
            sa.Column("company", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["sales_rep_id"], ["sales_reps.id"], name="fk_sales_mail_contacts_sales_rep_id"),
            sa.ForeignKeyConstraint(
                ["sales_customer_id"], ["sales_customers.id"], name="fk_sales_mail_contacts_sales_customer_id"
            ),
            sa.PrimaryKeyConstraint("id"),
            **table_kwargs,
        )
        op.create_index("ix_sales_mail_contacts_sales_rep_id", "sales_mail_contacts", ["sales_rep_id"])
        op.create_index("ix_sales_mail_contacts_sales_customer_id", "sales_mail_contacts", ["sales_customer_id"])
        op.create_index("ix_sales_mail_contacts_email", "sales_mail_contacts", ["email"])

    if not _has_table("sales_mail_messages"):
        op.create_table(
            "sales_mail_messages",
            sa.Column("id", rep_id, nullable=False),
            sa.Column("sales_rep_id", rep_id, nullable=False),
            sa.Column("folder", sa.String(length=120), nullable=False, server_default="INBOX"),
            sa.Column("uid", sa.String(length=40), nullable=True),
            sa.Column("message_id", sa.String(length=320), nullable=True),
            sa.Column("from_email", sa.String(length=320), nullable=False, server_default=""),
            sa.Column("from_name", sa.String(length=200), nullable=True),
            sa.Column("to_email", sa.Text(), nullable=True),
            sa.Column("cc_email", sa.Text(), nullable=True),
            sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("body_text", sa.Text(), nullable=True),
            sa.Column("body_html", sa.Text(), nullable=True),
            sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("direction", sa.String(length=16), nullable=False, server_default="received"),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_starred", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("labels_json", sa.Text(), nullable=True),
            sa.Column("date", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["sales_rep_id"], ["sales_reps.id"], name="fk_sales_mail_messages_sales_rep_id"),
            sa.PrimaryKeyConstraint("id"),
            **table_kwargs,
        )
        op.create_index("ix_sales_mail_messages_sales_rep_id", "sales_mail_messages", ["sales_rep_id"])
        op.create_index("ix_sales_mail_messages_folder", "sales_mail_messages", ["folder"])
        op.create_index("ix_sales_mail_messages_uid", "sales_mail_messages", ["uid"])
        op.create_index("ix_sales_mail_messages_message_id", "sales_mail_messages", ["message_id"])
        op.create_index("ix_sales_mail_messages_direction", "sales_mail_messages", ["direction"])
        op.create_index("ix_sales_mail_messages_date", "sales_mail_messages", ["date"])


def downgrade() -> None:
    if _has_table("sales_mail_messages"):
        op.drop_index("ix_sales_mail_messages_date", table_name="sales_mail_messages")
        op.drop_index("ix_sales_mail_messages_direction", table_name="sales_mail_messages")
        op.drop_index("ix_sales_mail_messages_message_id", table_name="sales_mail_messages")
        op.drop_index("ix_sales_mail_messages_uid", table_name="sales_mail_messages")
        op.drop_index("ix_sales_mail_messages_folder", table_name="sales_mail_messages")
        op.drop_index("ix_sales_mail_messages_sales_rep_id", table_name="sales_mail_messages")
        op.drop_table("sales_mail_messages")

    if _has_table("sales_mail_contacts"):
        op.drop_index("ix_sales_mail_contacts_email", table_name="sales_mail_contacts")
        op.drop_index("ix_sales_mail_contacts_sales_customer_id", table_name="sales_mail_contacts")
        op.drop_index("ix_sales_mail_contacts_sales_rep_id", table_name="sales_mail_contacts")
        op.drop_table("sales_mail_contacts")

    if _has_table("sales_mail_labels"):
        op.drop_index("ix_sales_mail_labels_sales_rep_id", table_name="sales_mail_labels")
        op.drop_table("sales_mail_labels")

    for col in (
        "email_signature",
        "imap_password_enc",
        "imap_username",
        "imap_use_tls",
        "imap_use_ssl",
        "imap_port",
        "imap_host",
        "smtp_password_enc",
        "smtp_username",
        "smtp_use_ssl",
        "smtp_use_tls",
        "smtp_port",
        "smtp_host",
    ):
        if _has_column("sales_reps", col):
            op.drop_column("sales_reps", col)
