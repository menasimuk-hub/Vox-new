from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.models.frontpage_lead_call import FrontpageLeadCall
from app.models.lead_sales_task import LeadSalesTask
from app.services.frontpage_lead_service import lead_source_out
from app.services.lead_sales_service import lead_sales_task_out, sales_task_brief


def _csv_response(rows: list[list[Any]], filename: str) -> tuple[str, str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue(), filename


def lead_sources_csv(
    leads: list[FrontpageLeadCall],
    *,
    tasks_by_lead: dict[str, LeadSalesTask],
) -> tuple[str, str]:
    header = [
        "lead_code",
        "contact_name",
        "company_name",
        "email",
        "phone",
        "status",
        "voice_provider",
        "recommendation",
        "sentiment",
        "wants_sales_call",
        "scheduled_callback_at",
        "callback_timezone",
        "country",
        "callback_consent",
        "sales_task_status",
        "sales_outcome",
        "interest_summary",
        "duration_seconds",
        "completed_at",
        "created_at",
    ]
    rows: list[list[Any]] = [header]
    for lead in leads:
        task = tasks_by_lead.get(lead.id)
        brief = sales_task_brief(task)
        out = lead_source_out(lead, sales_task=brief)
        data = out.get("lead_data") if isinstance(out.get("lead_data"), dict) else {}
        rows.append(
            [
                out.get("lead_code"),
                out.get("contact_name"),
                out.get("company_name"),
                out.get("email"),
                out.get("phone"),
                out.get("status"),
                out.get("voice_provider"),
                out.get("recommendation"),
                out.get("sentiment"),
                out.get("wants_sales_call"),
                data.get("scheduled_callback_at") if isinstance(data, dict) else None,
                data.get("callback_timezone") if isinstance(data, dict) else None,
                data.get("country") if isinstance(data, dict) else None,
                data.get("callback_consent") if isinstance(data, dict) else None,
                brief.get("status") if brief else "",
                brief.get("outcome_label") if brief else "",
                data.get("interest_summary") if isinstance(data, dict) else "",
                out.get("duration_seconds"),
                out.get("completed_at"),
                out.get("created_at"),
            ]
        )
    return _csv_response(rows, "lead-sources.csv")


def lead_sales_tasks_csv(
    tasks: list[LeadSalesTask],
    *,
    lead_codes: dict[str, str],
    settings: Any,
) -> tuple[str, str]:
    header = [
        "id",
        "lead_code",
        "contact_name",
        "company_name",
        "email",
        "phone",
        "status",
        "status_label",
        "scheduled_at",
        "callback_timezone",
        "callback_consent",
        "outcome_label",
        "demo_agreed",
        "interested_to_buy",
        "deal_stage",
        "outcome_summary",
        "call_started_at",
        "call_completed_at",
        "last_error",
        "created_at",
    ]
    rows: list[list[Any]] = [header]
    from app.services.lead_sales_service import _table_status_label

    for task in tasks:
        if settings is None:
            from sqlalchemy.orm import object_session

            session = object_session(task)
            if session is not None:
                settings = get_lead_sales_settings(session)
        out = lead_sales_task_out(task, lead_code=lead_codes.get(task.lead_id))
        outcome = out.get("outcome") if isinstance(out.get("outcome"), dict) else {}
        label = _table_status_label(task, settings) if settings else out.get("status")
        rows.append(
            [
                out.get("id"),
                out.get("lead_code"),
                out.get("contact_name"),
                out.get("company_name"),
                out.get("email"),
                out.get("phone"),
                out.get("status"),
                label,
                out.get("scheduled_at"),
                out.get("callback_timezone"),
                out.get("callback_consent"),
                out.get("outcome_label"),
                outcome.get("demo_agreed"),
                outcome.get("interested_to_buy"),
                outcome.get("deal_stage"),
                outcome.get("outcome_summary"),
                out.get("call_started_at"),
                out.get("call_completed_at"),
                out.get("last_error"),
                out.get("created_at"),
            ]
        )
    return _csv_response(rows, "lead-sales.csv")
