"""Interview batch reports — aggregates across finished campaigns (Phase 4)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.services.interview_results_service import InterviewResultsService
from app.services.platform_catalog_service import ServiceOrderService

PERIOD_LABELS = {
    "today": "Today",
    "week": "This week",
    "month": "This month",
    "last_month": "Last month",
    "all": "All time",
}


def period_bounds(period: str) -> tuple[datetime | None, datetime | None]:
    now = datetime.utcnow()
    day_start = datetime(now.year, now.month, now.day)
    key = str(period or "month").strip().lower()
    if key == "today":
        return day_start, now
    if key == "week":
        week_start = day_start - timedelta(days=day_start.weekday())
        return week_start, now
    if key == "last_month":
        first_this = datetime(now.year, now.month, 1)
        last_end = first_this - timedelta(seconds=1)
        last_start = datetime(last_end.year, last_end.month, 1)
        return last_start, last_end
    if key == "all":
        return None, None
    return datetime(now.year, now.month, 1), now


def _order_period_ts(order: ServiceOrder) -> datetime | None:
    raw = order.completed_at or order.started_at or order.updated_at or order.created_at
    return raw if isinstance(raw, datetime) else None


def _in_period(order: ServiceOrder, start: datetime | None, end: datetime | None) -> bool:
    ts = _order_period_ts(order)
    if ts is None:
        return False
    if start and ts < start:
        return False
    if end and ts > end:
        return False
    return True


def _reportable_orders(db: Session, org_id: str) -> list[ServiceOrder]:
    rows = db.execute(
        select(ServiceOrder)
        .where(
            ServiceOrder.org_id == org_id,
            ServiceOrder.service_code == "interview",
            ServiceOrder.status.in_(("completed", "cancelled")),
            ServiceOrder.recipient_count > 0,
        )
        .order_by(ServiceOrder.completed_at.desc(), ServiceOrder.updated_at.desc())
    ).scalars().all()
    return list(rows)


def _batch_summary(db: Session, order: ServiceOrder) -> dict[str, Any]:
    results = InterviewResultsService.get_results(db, order)
    candidates = results.get("candidates") or []
    kpis = results.get("kpis") or {}
    advance = sum(1 for c in candidates if c.get("recommendation") == "Advance")
    hold = sum(1 for c in candidates if c.get("recommendation") == "Hold")
    decline = sum(1 for c in candidates if c.get("recommendation") == "Decline")
    scores = [int(c.get("score") or 0) for c in candidates if c.get("score") is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    ts = _order_period_ts(order)
    return {
        "order_id": order.id,
        "campaign_id": order.campaign_id,
        "reference_id": order.reference_id,
        "title": order.title,
        "role": results.get("role"),
        "status": order.status,
        "status_label": ServiceOrderService.interview_status_label(order),
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        "period_at": ts.isoformat() if ts else None,
        "candidate_count": len(candidates) or int(order.recipient_count or 0),
        "called": int(kpis.get("called") or 0),
        "reached": int(kpis.get("reached") or 0),
        "reach_rate_pct": int(kpis.get("reach_rate_pct") or 0),
        "advance_count": advance,
        "hold_count": hold,
        "decline_count": decline,
        "avg_score": avg_score,
        "quote_total_gbp": f"£{int(order.quote_total_pence or 0) / 100:.2f}",
        "quote_total_pence": int(order.quote_total_pence or 0),
        "is_mock": bool(results.get("is_mock")),
    }


def _overview_from_batches(batches: list[dict[str, Any]]) -> dict[str, Any]:
    total_candidates = sum(int(b.get("candidate_count") or 0) for b in batches)
    total_reached = sum(int(b.get("reached") or 0) for b in batches)
    total_advance = sum(int(b.get("advance_count") or 0) for b in batches)
    total_cost_pence = sum(int(b.get("quote_total_pence") or 0) for b in batches)
    reach_pct = round((total_reached / total_candidates) * 100) if total_candidates else 0
    return {
        "batch_count": len(batches),
        "candidate_count": total_candidates,
        "reached": total_reached,
        "reach_rate_pct": reach_pct,
        "advance_count": total_advance,
        "total_cost_gbp": f"£{total_cost_pence / 100:.2f}",
        "total_cost_pence": total_cost_pence,
    }


class InterviewReportService:
    @staticmethod
    def list_batches(db: Session, org_id: str, *, period: str = "month") -> dict[str, Any]:
        start, end = period_bounds(period)
        batches: list[dict[str, Any]] = []
        for order in _reportable_orders(db, org_id):
            if not _in_period(order, start, end):
                continue
            batches.append(_batch_summary(db, order))
        overview = _overview_from_batches(batches)
        return {
            "period": period,
            "period_label": PERIOD_LABELS.get(period, PERIOD_LABELS["month"]),
            "overview": overview,
            "batches": batches,
        }

    @staticmethod
    def batch_detail(db: Session, order: ServiceOrder) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Batch reports are only available for interview orders")
        results = InterviewResultsService.get_results(db, order)
        summary = _batch_summary(db, order)
        return {
            "summary": summary,
            "kpis": results.get("kpis") or {},
            "candidates": results.get("candidates") or [],
            "shortlist": results.get("shortlist") or [],
            "is_mock": bool(results.get("is_mock")),
        }

    @staticmethod
    def export_batches_csv(payload: dict[str, Any]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Campaign ID",
                "Reference",
                "Title",
                "Role",
                "Status",
                "Completed",
                "Candidates",
                "Reached",
                "Reach %",
                "Advance",
                "Hold",
                "Decline",
                "Avg score",
                "Cost",
            ]
        )
        for batch in payload.get("batches") or []:
            writer.writerow(
                [
                    batch.get("campaign_id") or "",
                    batch.get("reference_id") or "",
                    batch.get("title") or "",
                    batch.get("role") or "",
                    batch.get("status_label") or batch.get("status") or "",
                    batch.get("completed_at") or batch.get("period_at") or "",
                    batch.get("candidate_count") or 0,
                    batch.get("reached") or 0,
                    batch.get("reach_rate_pct") or 0,
                    batch.get("advance_count") or 0,
                    batch.get("hold_count") or 0,
                    batch.get("decline_count") or 0,
                    batch.get("avg_score") if batch.get("avg_score") is not None else "",
                    batch.get("quote_total_gbp") or "",
                ]
            )
        return buf.getvalue()

    @staticmethod
    def export_batch_csv(detail: dict[str, Any]) -> str:
        summary = detail.get("summary") or {}
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Interview batch report"])
        writer.writerow(["Reference", summary.get("reference_id") or ""])
        writer.writerow(["Title", summary.get("title") or ""])
        writer.writerow(["Role", summary.get("role") or ""])
        writer.writerow([])
        writer.writerow(
            ["Name", "Phone", "Email", "Status", "Score", "Recommendation", "Sentiment", "Duration", "CV quality"]
        )
        for row in detail.get("candidates") or []:
            writer.writerow(
                [
                    row.get("name") or "",
                    row.get("phone") or "",
                    row.get("email") or "",
                    row.get("status") or "",
                    row.get("score") or "",
                    row.get("recommendation") or "",
                    row.get("sentiment") or "",
                    row.get("duration_label") or "",
                    row.get("cv_quality") or "",
                ]
            )
        return buf.getvalue()
