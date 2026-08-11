"""Sales consent ops: approval queue, dental purge, promo cleanup.

Revision ID: 0249_sales_consent_ops
Revises: 0248_ai_demo_voice_region
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0249_sales_consent_ops"
down_revision = "0248_ai_demo_voice_region"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # --- schema ---
    if not _has_column("demo_requests", "callback_consent"):
        op.add_column(
            "demo_requests",
            sa.Column("callback_consent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if not _has_column("lead_sales_tasks", "approved_at"):
        op.add_column("lead_sales_tasks", sa.Column("approved_at", sa.DateTime(), nullable=True))
    if not _has_column("lead_sales_tasks", "services_json"):
        op.add_column("lead_sales_tasks", sa.Column("services_json", sa.Text(), nullable=True))
    if not _has_column("lead_sales_tasks", "offer_queue_status"):
        op.add_column(
            "lead_sales_tasks",
            sa.Column("offer_queue_status", sa.String(32), nullable=True),
        )
    if not _has_column("lead_sales_tasks", "source_label"):
        op.add_column("lead_sales_tasks", sa.Column("source_label", sa.String(64), nullable=True))
    if not _has_column("sales_offer_templates", "service_code"):
        op.add_column("sales_offer_templates", sa.Column("service_code", sa.String(32), nullable=True))

    conn = op.get_bind()
    now = datetime.utcnow()

    # Cancel unfinished auto-scheduled tasks (no more auto-dial)
    conn.execute(
        sa.text(
            """
            UPDATE lead_sales_tasks
            SET status = 'cancelled', updated_at = :now, last_error = 'Cancelled: auto-dial disabled — admin Call now only'
            WHERE status IN ('scheduled', 'paused')
            """
        ),
        {"now": now},
    )
    # In-progress calling rows left alone; completed stay

    # Disable post-call auto offers
    conn.execute(
        sa.text(
            """
            UPDATE lead_sales_settings
            SET sales_automation_enabled = 0,
                sales_auto_plan_code = 'starter',
                sales_auto_offer_type = 'subscription_trial',
                updated_at = :now
            """
        ),
        {"now": now},
    )

    # Migrate orgs on dental plans → starter then delete dental plans
    starter = conn.execute(sa.text("SELECT id FROM plans WHERE code = 'starter' LIMIT 1")).fetchone()
    dental_ids = [
        r[0]
        for r in conn.execute(
            sa.text(
                """
                SELECT id FROM plans
                WHERE service_kind = 'dental'
                   OR code IN ('dental_1', 'dental_2', 'practice', 'group')
                """
            )
        ).fetchall()
    ]
    if starter and dental_ids:
        starter_id = starter[0]
        # subscriptions.plan_id may be string uuid
        for did in dental_ids:
            try:
                conn.execute(
                    sa.text("UPDATE subscriptions SET plan_id = :sid WHERE plan_id = :did"),
                    {"sid": starter_id, "did": did},
                )
            except Exception:
                pass
            try:
                conn.execute(
                    sa.text("UPDATE org_package_assignments SET plan_id = :sid WHERE plan_id = :did"),
                    {"sid": starter_id, "did": did},
                )
            except Exception:
                pass
        # Null out promo plan_code pointing at dental
        conn.execute(
            sa.text(
                """
                UPDATE promo_offers SET plan_code = 'starter'
                WHERE plan_code IN ('dental_1', 'dental_2', 'practice', 'group')
                """
            )
        )
        conn.execute(
            sa.text(
                """
                UPDATE sales_offer_templates SET plan_code = 'starter', offer_type = 'subscription_trial'
                WHERE plan_code IN ('dental_1', 'dental_2', 'practice', 'group')
                   OR offer_type = 'dental_trial'
                """
            )
        )
        for did in dental_ids:
            conn.execute(sa.text("DELETE FROM plans WHERE id = :id"), {"id": did})

    # Deactivate old Subscription sale 1 if still named that way pointing wrong — ensure 5 service templates
    templates = [
        {
            "id": str(uuid.uuid4()),
            "name": "Recruitment — 3 interview credits",
            "offer_type": "interview_credits",
            "service_code": "recruitment",
            "plan_code": None,
            "trial_days": 0,
            "survey": 0,
            "interview": 3,
            "sort": 10,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Surveys — 3 survey contacts",
            "offer_type": "survey_credits",
            "service_code": "surveys",
            "plan_code": None,
            "trial_days": 0,
            "survey": 3,
            "interview": 0,
            "sort": 20,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Feedback — Starter trial 14 days",
            "offer_type": "subscription_trial",
            "service_code": "feedback",
            "plan_code": "cf_starter_gb",
            "trial_days": 14,
            "survey": 0,
            "interview": 0,
            "sort": 30,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Expo — 3-day trial",
            "offer_type": "expo_trial",
            "service_code": "expo",
            "plan_code": "expo_day3",
            "trial_days": 3,
            "survey": 0,
            "interview": 0,
            "sort": 40,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Smart Card — 1 seat credit",
            "offer_type": "smart_card_credit",
            "service_code": "smart_card",
            "plan_code": "smart_card_seat",
            "trial_days": 0,
            "survey": 0,
            "interview": 0,
            "sort": 50,
        },
    ]
    for t in templates:
        exists = conn.execute(
            sa.text(
                "SELECT id FROM sales_offer_templates WHERE service_code = :sc AND is_active = 1 LIMIT 1"
            ),
            {"sc": t["service_code"]},
        ).fetchone()
        if exists:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO sales_offer_templates
                (id, name, offer_type, plan_code, trial_days, survey_contacts_included,
                 interview_contacts_included, free_call_credits, expires_in_days, is_active,
                 sort_order, created_at, updated_at, service_code)
                VALUES
                (:id, :name, :offer_type, :plan_code, :trial_days, :survey, :interview,
                 0, 30, 1, :sort, :now, :now, :service_code)
                """
            ),
            {
                **{k: t[k] for k in ("id", "name", "offer_type", "plan_code", "trial_days", "survey", "interview", "sort", "service_code")},
                "now": now,
            },
        )

    # Purge expired promos (all)
    conn.execute(sa.text("DELETE FROM promo_offers WHERE expires_at IS NOT NULL AND expires_at < UTC_TIMESTAMP()"))
    # Purge unused AI-team unique codes
    conn.execute(
        sa.text(
            """
            DELETE FROM promo_offers
            WHERE ai_team_prospect_id IS NOT NULL
              AND (redemption_count IS NULL OR redemption_count = 0)
            """
        )
    )


def downgrade() -> None:
    # Non-reversible data deletes; only drop new columns
    if _has_column("sales_offer_templates", "service_code"):
        op.drop_column("sales_offer_templates", "service_code")
    if _has_column("lead_sales_tasks", "source_label"):
        op.drop_column("lead_sales_tasks", "source_label")
    if _has_column("lead_sales_tasks", "offer_queue_status"):
        op.drop_column("lead_sales_tasks", "offer_queue_status")
    if _has_column("lead_sales_tasks", "services_json"):
        op.drop_column("lead_sales_tasks", "services_json")
    if _has_column("lead_sales_tasks", "approved_at"):
        op.drop_column("lead_sales_tasks", "approved_at")
    if _has_column("demo_requests", "callback_consent"):
        op.drop_column("demo_requests", "callback_consent")
