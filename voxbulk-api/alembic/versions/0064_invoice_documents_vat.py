"""Invoice document fields + country VAT rates.

Revision ID: 0064_invoice_documents_vat
Revises: 0063_sales_wa_button_templates
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0064_invoice_documents_vat"
down_revision = "0063_sales_wa_button_templates"
branch_labels = None
depends_on = None

DEFAULT_VAT_ROWS = [
    ("GB", "United Kingdom", 20.0),
    ("IE", "Ireland", 23.0),
    ("US", "United States", 0.0),
    ("CA", "Canada", 5.0),
    ("AU", "Australia", 10.0),
    ("NZ", "New Zealand", 15.0),
    ("SG", "Singapore", 9.0),
    ("AE", "United Arab Emirates", 5.0),
    ("SA", "Saudi Arabia", 15.0),
    ("QA", "Qatar", 0.0),
    ("BH", "Bahrain", 10.0),
    ("KW", "Kuwait", 0.0),
    ("OM", "Oman", 5.0),
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "country_vat_rates" not in tables:
        op.create_table(
            "country_vat_rates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("country_code", sa.String(2), nullable=False),
            sa.Column("country_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("vat_rate_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("notes", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("country_code", name="uq_country_vat_rates_code"),
        )
        now = datetime.utcnow()
        for code, name, rate in DEFAULT_VAT_ROWS:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO country_vat_rates
                    (country_code, country_name, vat_rate_percent, is_enabled, created_at, updated_at)
                    VALUES (:code, :name, :rate, 1, :now, :now)
                    """
                ),
                {"code": code, "name": name, "rate": rate, "now": now},
            )

    if "billing_invoices" in tables:
        cols = {c["name"] for c in insp.get_columns("billing_invoices")}
        additions = [
            ("invoice_number", sa.String(32)),
            ("description", sa.Text()),
            ("country_code", sa.String(2)),
            ("subtotal_pence", sa.Integer()),
            ("tax_pence", sa.Integer()),
            ("tax_rate_percent", sa.Numeric(5, 2)),
            ("line_items_json", sa.Text()),
            ("payment_reference", sa.String(128)),
            ("payment_method", sa.String(40)),
        ]
        for name, col_type in additions:
            if name not in cols:
                op.add_column("billing_invoices", sa.Column(name, col_type, nullable=True))
        if "invoice_number" not in cols:
            op.create_index("ix_billing_invoices_invoice_number", "billing_invoices", ["invoice_number"], unique=True)

    if "email_templates" in tables:
        from app.data.invoice_document_default import INVOICE_DOCUMENT_BODY, INVOICE_DOCUMENT_SUBJECT, NEW_INVOICE_EMAIL_BODY

        bind.execute(
            sa.text(
                """
                INSERT INTO email_templates (template_key, title, subject, body, is_enabled, created_at, updated_at)
                SELECT :key, :title, :subject, :body, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (SELECT 1 FROM email_templates WHERE template_key = :key)
                """
            ),
            {
                "key": "invoice_document",
                "title": "Invoice document (PDF)",
                "subject": INVOICE_DOCUMENT_SUBJECT,
                "body": INVOICE_DOCUMENT_BODY,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE email_templates SET body = :body, updated_at = CURRENT_TIMESTAMP WHERE template_key = 'new_invoice'"
            ),
            {"body": NEW_INVOICE_EMAIL_BODY},
        )


def downgrade() -> None:
    pass
