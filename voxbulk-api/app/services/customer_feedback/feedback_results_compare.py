"""Compare Customer Feedback results across multiple locations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackLocation
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.feedback_results_aggregate import build_aggregates, build_weekly_trend
from app.services.customer_feedback.location_service import location_to_dict
from app.services.customer_feedback.results_service import FeedbackResultsService

LOCATION_COLORS = ("#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4", "#f97316", "#22c55e")


def _positive_pct_from_aggregate(block: dict[str, Any]) -> int | None:
    breakdown = block.get("breakdown") or []
    if not breakdown:
        return None
    keys = {str(b.get("key") or "").lower() for b in breakdown}
    if keys & {"excellent", "good", "poor"}:
        excellent = next((int(b.get("pct") or 0) for b in breakdown if b.get("key") == "excellent"), 0)
        good = next((int(b.get("pct") or 0) for b in breakdown if b.get("key") == "good"), 0)
        return excellent + good
    if keys & {"yes", "no"}:
        return next((int(b.get("pct") or 0) for b in breakdown if b.get("key") == "yes"), None)
    return None


def _short_question_title(title: str) -> str:
    text = str(title or "").strip()
    if len(text) <= 14:
        return text
    words = text.split()
    if len(words) <= 2:
        return text[:14]
    return " ".join(words[:2])


def compare_locations(
    db: Session,
    org_id: str,
    location_ids: list[str],
) -> dict[str, Any]:
    max_loc = FeedbackBillingService.max_locations(db, org_id)
    if max_loc <= 1:
        raise ValueError(
            "Compare locations is available on multi-location Customer feedback plans. Upgrade to Pro or Business."
        )
    if not location_ids:
        return {"ok": True, "locations": [], "shared_questions": [], "all_questions": []}

    rows: list[dict[str, Any]] = []
    per_loc_questions: list[set[str]] = []
    all_question_meta: dict[str, dict[str, str]] = {}

    for idx, loc_id in enumerate(location_ids):
        loc = db.get(FeedbackLocation, loc_id)
        if loc is None or loc.org_id != org_id:
            continue
        data = FeedbackResultsService._load_scoped_data(db, org_id, location_id=loc_id)
        summary = data["summary"]
        aggregates = build_aggregates(data["all_responses"], data["templates"])
        weekly = build_weekly_trend(data["sessions"], data["responses_by_session"])

        sentiment = summary.get("sentiment_counts") or {}
        sent_total = sum(int(v or 0) for v in sentiment.values()) or 1
        per_question: dict[str, int] = {}
        qkeys: set[str] = set()
        for block in aggregates:
            role = str(block.get("step_role") or "").lower()
            if role in {"final_feedback_text", "tell_us_more", "open", "reason"}:
                continue
            if block.get("visualization") not in {"sentiment_breakdown", None} and not block.get("breakdown"):
                continue
            qk = str(block.get("question_key") or "")
            if not qk:
                continue
            pct = _positive_pct_from_aggregate(block)
            if pct is None:
                continue
            per_question[qk] = pct
            qkeys.add(qk)
            title = str(block.get("question") or qk)
            all_question_meta[qk] = {"title": title, "short": _short_question_title(title)}

        per_loc_questions.append(qkeys)
        trend_vals = [w.get("satisfaction") for w in weekly if w.get("satisfaction") is not None]
        if len(trend_vals) < 8:
            trend_vals = [
                w.get("satisfaction") if w.get("satisfaction") is not None else None for w in weekly
            ]
        while len(trend_vals) < 8:
            trend_vals.insert(0, trend_vals[0] if trend_vals else None)
        trend_vals = trend_vals[-8:]
        trend_numeric = [int(v) if v is not None else 0 for v in trend_vals]

        loc_dict = location_to_dict(db, loc)
        rows.append(
            {
                "id": loc.id,
                "name": loc.name,
                "color": LOCATION_COLORS[idx % len(LOCATION_COLORS)],
                "responses": int(summary.get("completed_sessions") or 0),
                "invited": int(summary.get("total_scans") or loc.scan_count or 0),
                "satisfaction_pct": summary.get("satisfaction_pct"),
                "recommend_pct": summary.get("recommend_pct"),
                "sentiment_pct": {
                    "happy": round(int(sentiment.get("happy") or 0) / sent_total * 100),
                    "neutral": round(int(sentiment.get("neutral") or 0) / sent_total * 100),
                    "unhappy": round(int(sentiment.get("unhappy") or 0) / sent_total * 100),
                },
                "weekly_trend": trend_numeric,
                "per_question": per_question,
                "industry_name": loc_dict.get("industry_name"),
            }
        )

    shared_keys: set[str] = set.intersection(*per_loc_questions) if per_loc_questions else set()
    shared_questions = [
        {"key": k, "title": all_question_meta[k]["title"], "short": all_question_meta[k]["short"]}
        for k in sorted(shared_keys)
    ]
    all_questions = [
        {"key": k, "title": v["title"], "short": v["short"]}
        for k, v in sorted(all_question_meta.items(), key=lambda x: x[1]["title"])
    ]

    return {
        "ok": True,
        "locations": rows,
        "shared_questions": shared_questions,
        "all_questions": all_questions,
    }
