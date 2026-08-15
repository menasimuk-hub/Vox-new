"""0255 — Seed plan_unit_rates for public Core catalog packages from currency settings.

Revision ID: 0255_seed_catalog_plan_unit_rates
Revises: 0254_pricing_fx_rates
Create Date: 2026-08-15
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0255_seed_catalog_plan_unit_rates"
down_revision = "0254_pricing_fx_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    plans = conn.execute(
        sa.text(
            """
            SELECT id FROM plans
            WHERE service_kind = 'voxbulk'
              AND COALESCE(is_private, 0) = 0
            """
        )
    ).fetchall()
    currencies = conn.execute(sa.text("SELECT currency, wa_package_fee_minor, wa_extra_minor, cv_scan_fee_minor FROM pricing_currency_settings")).fetchall()
    if not currencies:
        # Fallback defaults if currency settings not yet seeded
        currencies = [
            ("GBP", 50, 49, 75),
            ("EUR", 50, 49, 75),
            ("USD", 50, 49, 75),
            ("CAD", 50, 49, 75),
            ("AUD", 50, 49, 75),
        ]
    by_cur = {str(r[0]).upper(): r for r in currencies}
    for (plan_id,) in plans:
        for code in ("GBP", "EUR", "USD", "CAD", "AUD"):
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM plan_unit_rates WHERE plan_id = :pid AND currency = :cur LIMIT 1"
                ),
                {"pid": plan_id, "cur": code},
            ).fetchone()
            if exists:
                continue
            row = by_cur.get(code) or by_cur.get("GBP")
            if row is None:
                wa_pkg, wa_extra, cv = 50, 49, 75
            else:
                wa_pkg = int(row[1] or 50)
                wa_extra = int(row[2] or 49)
                cv = int(row[3] or 75)
            conn.execute(
                sa.text(
                    """
                    INSERT INTO plan_unit_rates (
                      id, plan_id, currency,
                      connection_fee_minor, interview_per_min_minor,
                      wa_package_fee_minor, wa_extra_minor, cv_scan_fee_minor,
                      created_at, updated_at
                    ) VALUES (
                      :id, :pid, :cur,
                      NULL, NULL,
                      :wa_pkg, :wa_extra, :cv,
                      UTC_TIMESTAMP(), UTC_TIMESTAMP()
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": plan_id,
                    "cur": code,
                    "wa_pkg": wa_pkg,
                    "wa_extra": wa_extra,
                    "cv": cv,
                },
            )


def downgrade() -> None:
    # Do not delete seeded rates — may have been edited; leave table intact.
    pass
