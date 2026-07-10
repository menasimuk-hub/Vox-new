"""0160 — telnyx_destination_rates (country voice/SMS rate card for allowlists)."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0160_telnyx_destination_rates"
down_revision = "0159_custom_org_feedback_plan"
branch_labels = None
depends_on = None

_TABLE = "telnyx_destination_rates"

# minor = 1/10000 major currency (USD). 50 = $0.0050. Placeholders until CSV import.
_SEED = [
    # iso, name, dial, voice_out, voice_in, sms_out, sms_in, notes
    ("GB", "United Kingdom", "44", 50, 32, 40, 0, "Seed approx — import Telnyx sheet"),
    ("US", "United States", "1", 50, 32, 40, 0, "Seed approx — import Telnyx sheet"),
    ("CA", "Canada", "1", 50, 32, 40, 0, "Seed approx — import Telnyx sheet"),
    ("AU", "Australia", "61", 80, 40, 50, 0, "Seed approx — import Telnyx sheet"),
    ("CN", "China", "86", 350, 80, 120, 0, "Seed approx — often prefix-dependent"),
    ("EG", "Egypt", "20", 1800, 200, 150, 0, "Seed approx — verify before enabling"),
    ("SA", "Saudi Arabia", "966", 1200, 150, 100, 0, "Seed approx — import Telnyx sheet"),
    ("AE", "United Arab Emirates", "971", 900, 120, 90, 0, "Seed approx — import Telnyx sheet"),
    ("IN", "India", "91", 200, 60, 60, 0, "Seed approx — import Telnyx sheet"),
    ("PS", "Palestine", "970", 1500, 200, 120, 0, "Seed approx — import Telnyx sheet"),
    ("DE", "Germany", "49", 60, 35, 45, 0, "Seed approx — import Telnyx sheet"),
    ("FR", "France", "33", 60, 35, 45, 0, "Seed approx — import Telnyx sheet"),
    ("IE", "Ireland", "353", 70, 40, 50, 0, "Seed approx — import Telnyx sheet"),
    ("NZ", "New Zealand", "64", 90, 45, 55, 0, "Seed approx — import Telnyx sheet"),
    ("PK", "Pakistan", "92", 400, 100, 80, 0, "Seed approx — import Telnyx sheet"),
    ("BD", "Bangladesh", "880", 450, 100, 80, 0, "Seed approx — import Telnyx sheet"),
    ("PH", "Philippines", "63", 300, 80, 70, 0, "Seed approx — import Telnyx sheet"),
    ("NG", "Nigeria", "234", 1600, 200, 120, 0, "Seed approx — verify before enabling"),
    ("ZA", "South Africa", "27", 250, 80, 70, 0, "Seed approx — import Telnyx sheet"),
    ("TR", "Turkey", "90", 200, 70, 60, 0, "Seed approx — import Telnyx sheet"),
]


def _has_table(bind) -> bool:
    return sa.inspect(bind).has_table(_TABLE)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        op.create_table(
            _TABLE,
            sa.Column("country_iso", sa.String(length=2), nullable=False),
            sa.Column("country_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("dial_code", sa.String(length=8), nullable=False, server_default=""),
            sa.Column("voice_outbound_per_min_minor", sa.Integer(), nullable=True),
            sa.Column("voice_inbound_per_min_minor", sa.Integer(), nullable=True),
            sa.Column("sms_outbound_per_msg_minor", sa.Integer(), nullable=True),
            sa.Column("sms_inbound_per_msg_minor", sa.Integer(), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="seed"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("country_iso"),
        )
        op.create_index("ix_telnyx_destination_rates_country_name", _TABLE, ["country_name"])

    now = datetime.utcnow()
    existing = {
        r[0]
        for r in bind.execute(sa.text(f"SELECT country_iso FROM {_TABLE}")).fetchall()
    }
    insert_sql = sa.text(
        f"""
        INSERT INTO {_TABLE} (
            country_iso, country_name, dial_code,
            voice_outbound_per_min_minor, voice_inbound_per_min_minor,
            sms_outbound_per_msg_minor, sms_inbound_per_msg_minor,
            currency, notes, source, created_at, updated_at
        ) VALUES (
            :country_iso, :country_name, :dial_code,
            :voice_outbound_per_min_minor, :voice_inbound_per_min_minor,
            :sms_outbound_per_msg_minor, :sms_inbound_per_msg_minor,
            :currency, :notes, :source, :created_at, :updated_at
        )
        """
    )
    for iso, name, dial, vo, vi, so, si, notes in _SEED:
        if iso in existing:
            continue
        bind.execute(
            insert_sql,
            {
                "country_iso": iso,
                "country_name": name,
                "dial_code": dial,
                "voice_outbound_per_min_minor": vo,
                "voice_inbound_per_min_minor": vi,
                "sms_outbound_per_msg_minor": so,
                "sms_inbound_per_msg_minor": si,
                "currency": "USD",
                "notes": notes,
                "source": "seed",
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        return
    op.drop_index("ix_telnyx_destination_rates_country_name", table_name=_TABLE)
    op.drop_table(_TABLE)
