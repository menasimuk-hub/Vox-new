"""Reporting for AI Appointment Manager."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment


def summary(db: Session, org_id: str) -> dict[str, Any]:
    rows = db.execute(select(Appointment.status, func.count()).where(Appointment.org_id == org_id).group_by(Appointment.status)).all()
    counts = {str(status): int(count) for status, count in rows}
    total = sum(counts.values())
    wa_sent = db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.wa_confirmation_sent_at.isnot(None),
        )
    ).scalar_one()
    calls = db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.call_triggered_at.isnot(None),
        )
    ).scalar_one()
    return {
        "total": total,
        "scheduled": counts.get("scheduled", 0),
        "confirmed": counts.get("confirmed", 0),
        "rescheduled": counts.get("rescheduled", 0),
        "cancelled": counts.get("cancelled", 0),
        "no_show": counts.get("no_show", 0),
        "wa_sent": int(wa_sent or 0),
        "calls_triggered": int(calls or 0),
    }


def daily_breakdown(db: Session, org_id: str, *, days: int = 30) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    rows = list(
        db.execute(
            select(Appointment.appointment_datetime, Appointment.status).where(
                Appointment.org_id == org_id,
                Appointment.appointment_datetime >= since,
            )
        ).all()
    )
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "confirmed": 0, "cancelled": 0, "no_show": 0})
    for appt_dt, status in rows:
        key = appt_dt.strftime("%Y-%m-%d") if appt_dt else "unknown"
        buckets[key]["total"] += 1
        st = str(status or "")
        if st == "confirmed":
            buckets[key]["confirmed"] += 1
        elif st == "cancelled":
            buckets[key]["cancelled"] += 1
        elif st == "no_show":
            buckets[key]["no_show"] += 1
    items = [{"date": k, **v} for k, v in sorted(buckets.items())]
    return {"items": items}


def pipeline_status(db: Session, org_id: str) -> dict[str, Any]:
    from app.services.appointment_settings_service import get_config

    cfg = get_config(db, org_id)
    now = datetime.utcnow()
    soon = now + timedelta(hours=24)
    at_risk = int(
        db.execute(
            select(func.count()).select_from(Appointment).where(
                Appointment.org_id == org_id,
                Appointment.status == "scheduled",
                Appointment.appointment_datetime <= soon,
                Appointment.appointment_datetime >= now,
            )
        ).scalar_one()
        or 0
    )
    awaiting_wa = int(
        db.execute(
            select(func.count()).select_from(Appointment).where(
                Appointment.org_id == org_id,
                Appointment.status == "scheduled",
                Appointment.wa_confirmation_sent_at.isnot(None),
                Appointment.confirmed_at.is_(None),
            )
        ).scalar_one()
        or 0
    )
    call_pending = int(
        db.execute(
            select(func.count()).select_from(Appointment).where(
                Appointment.org_id == org_id,
                Appointment.call_triggered_at.isnot(None),
                Appointment.call_outcome.is_(None),
            )
        ).scalar_one()
        or 0
    )
    rows = list(
        db.execute(select(Appointment.status, func.count()).where(Appointment.org_id == org_id).group_by(Appointment.status)).all()
    )
    counts = {str(s): int(c) for s, c in rows}
    items = [
        {"label": "Scheduled", "value": counts.get("scheduled", 0), "color": "#3b82f6"},
        {"label": "Confirmed", "value": counts.get("confirmed", 0), "color": "#22c55e"},
        {"label": "Unconfirmed (next 24h)", "value": at_risk, "color": "#f59e0b"},
        {"label": "Awaiting WA reply", "value": awaiting_wa, "color": "#8b5cf6"},
        {"label": "Call in progress", "value": call_pending, "color": "#06b6d4"},
        {"label": "Rescheduled", "value": counts.get("rescheduled", 0), "color": "#eab308"},
        {"label": "Cancelled", "value": counts.get("cancelled", 0), "color": "#94a3b8"},
        {"label": "No show", "value": counts.get("no_show", 0), "color": "#ef4444"},
    ]
    return {
        "items": [x for x in items if x["value"] > 0] or items[:3],
        "outreach_window_start": str(cfg.get("outreach_window_start") or "09:00"),
        "outreach_window_end": str(cfg.get("outreach_window_end") or "16:00"),
    }


def confirmation_methods(db: Session, org_id: str) -> dict[str, Any]:
    rows = list(
        db.execute(
            select(Appointment.confirmation_channel, func.count()).where(
                Appointment.org_id == org_id,
                Appointment.status == "confirmed",
            ).group_by(Appointment.confirmation_channel)
        ).all()
    )
    channel_map = {
        "whatsapp": ("WA confirmed", "#22c55e"),
        "wa": ("WA confirmed", "#22c55e"),
        "call": ("Call confirmed", "#3b82f6"),
        "manual": ("Manual confirmed", "#6366f1"),
    }
    items = []
    for channel, count in rows:
        key = str(channel or "unknown").lower()
        label, color = channel_map.get(key, (key.title(), "#94a3b8"))
        items.append({"name": label, "value": int(count), "color": color})
    unconfirmed = db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.status.in_(("scheduled", "no_show")),
        )
    ).scalar_one()
    if int(unconfirmed or 0) > 0:
        items.append({"name": "Not confirmed", "value": int(unconfirmed), "color": "#ef4444"})
    return {"items": items}


def by_crm(db: Session, org_id: str) -> dict[str, Any]:
    rows = list(
        db.execute(
            select(Appointment.crm_source, Appointment.status, func.count()).where(
                Appointment.org_id == org_id,
            ).group_by(Appointment.crm_source, Appointment.status)
        ).all()
    )
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "confirmed": 0})
    for source, status, count in rows:
        src = str(source or "manual")
        totals[src]["total"] += int(count)
        if str(status) == "confirmed":
            totals[src]["confirmed"] += int(count)
    items = []
    for src, data in sorted(totals.items()):
        total = data["total"] or 1
        rate = round(100 * data["confirmed"] / total)
        items.append({"crm": src.replace("_", " ").title(), "rate": rate, "total": data["total"]})
    return {"items": items}


def by_branch(db: Session, org_id: str) -> dict[str, Any]:
    rows = list(
        db.execute(
            select(Appointment.branch, Appointment.status, func.count()).where(
                Appointment.org_id == org_id,
            ).group_by(Appointment.branch, Appointment.status)
        ).all()
    )
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "confirmed": 0})
    for branch, status, count in rows:
        key = str(branch or "Unknown")
        totals[key]["total"] += int(count)
        if str(status) == "confirmed":
            totals[key]["confirmed"] += int(count)
    items = []
    for branch, data in sorted(totals.items(), key=lambda x: -x[1]["total"]):
        total = data["total"] or 1
        rate = round(100 * data["confirmed"] / total)
        items.append({"branch": branch, "total": data["total"], "rate": rate, "spark": [rate] * 6})
    return {"items": items}


def summary_metrics(db: Session, org_id: str) -> dict[str, Any]:
    confirmed = list(
        db.execute(
            select(Appointment.created_at, Appointment.confirmed_at, Appointment.call_outcome).where(
                Appointment.org_id == org_id,
                Appointment.confirmed_at.isnot(None),
            )
        ).all()
    )
    hours: list[float] = []
    for created, confirmed_at, _outcome in confirmed:
        if created and confirmed_at:
            hours.append((confirmed_at - created).total_seconds() / 3600.0)
    avg_hours = round(sum(hours) / len(hours), 1) if hours else None

    wa_sent = db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.wa_confirmation_sent_at.isnot(None),
        )
    ).scalar_one()
    calls = list(
        db.execute(
            select(Appointment.call_outcome).where(
                Appointment.org_id == org_id,
                Appointment.call_triggered_at.isnot(None),
            )
        ).all()
    )
    answered = sum(1 for (o,) in calls if str(o) in {"confirmed", "rescheduled"})
    call_rate = round(100 * answered / len(calls), 1) if calls else None

    rescheduled = db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.status == "rescheduled",
        )
    ).scalar_one()
    kept = db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.status == "confirmed",
            Appointment.rescheduled_from_id.isnot(None),
        )
    ).scalar_one()
    kept_rate = round(100 * int(kept or 0) / int(rescheduled or 1), 1) if int(rescheduled or 0) else None

    return {
        "avg_hours_to_confirm": avg_hours,
        "wa_sent": int(wa_sent or 0),
        "calls_made": len(calls),
        "call_answer_rate": call_rate,
        "rescheduled_kept_rate": kept_rate,
    }
