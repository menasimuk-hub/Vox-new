"""Interview campaign results, ranking, and Phase 3 shortlist (mock scheduling until Phase 5)."""

from __future__ import annotations

import json
import hashlib
import re
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import ServiceOrderService


def _loads_json(raw: str | None) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return None


def _seed_index(value: str) -> int:
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _mock_analysis(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    seed = _seed_index(str(recipient.id or recipient.name or "x"))
    score = 55 + (seed % 45)
    if score >= 85:
        recommendation = "Advance"
        sentiment = "Enthusiastic"
    elif score >= 70:
        recommendation = "Hold"
        sentiment = "Neutral"
    else:
        recommendation = "Decline"
        sentiment = "Hesitant"
    minutes = 5 + (seed % 4)
    seconds = seed % 60
    return {
        "score": score,
        "recommendation": recommendation,
        "sentiment": sentiment,
        "duration_seconds": minutes * 60 + seconds,
        "duration_label": f"{minutes}m {seconds:02d}s",
        "task": "Interview screening",
        "is_mock": True,
    }


def _candidate_row(recipient: ServiceOrderRecipient, *, role: str) -> dict[str, Any]:
    base = ServiceOrderService.recipient_to_dict(recipient)
    parsed = _loads_json(recipient.result_json) or {}
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}

    score = analysis.get("score") or parsed.get("score")
    recommendation = analysis.get("recommendation") or parsed.get("recommendation")
    sentiment = analysis.get("sentiment") or base.get("sentiment") or parsed.get("sentiment")
    duration_seconds = parsed.get("duration_seconds") or base.get("duration_seconds")
    is_mock = False

    if score is None or recommendation is None:
        mock = _mock_analysis(recipient)
        score = mock["score"]
        recommendation = mock["recommendation"]
        sentiment = sentiment or mock["sentiment"]
        duration_seconds = duration_seconds or mock["duration_seconds"]
        duration_label = mock["duration_label"]
        is_mock = True
    else:
        mins = int(duration_seconds or 0) // 60
        secs = int(duration_seconds or 0) % 60
        duration_label = f"{mins}m {secs:02d}s" if duration_seconds else "—"

    return {
        "id": recipient.id,
        "name": recipient.name or "Candidate",
        "phone": recipient.phone,
        "email": recipient.email,
        "status": recipient.status,
        "score": int(score or 0),
        "recommendation": recommendation or "Hold",
        "sentiment": sentiment or "Neutral",
        "duration_seconds": duration_seconds,
        "duration_label": duration_label,
        "task": role or "Interview screening",
        "cv_quality": base.get("cv_quality"),
        "is_mock": is_mock,
        "has_recording": bool(parsed.get("recording_url")),
        "transcript_preview": (parsed.get("transcript") or "")[:240] or None,
    }


def _mock_scheduling_links(order: ServiceOrder, candidate: dict[str, Any]) -> dict[str, str]:
    slug = str(candidate.get("id") or "")[:8]
    name = str(candidate.get("name") or "there")
    role = str(candidate.get("task") or "interview").replace(" ", "-").lower()
    sched_url = f"https://schedule.voxbulk.com/mock/{order.id}/{slug}"
    wa_text = f"Hi {name}, great speaking with you. Please book your follow-up slot: {sched_url}"
    phone_digits = re.sub(r"\D", "", str(candidate.get("phone") or ""))
    if phone_digits:
        whatsapp_mock = f"https://wa.me/{phone_digits}?text={quote(wa_text)}"
    else:
        whatsapp_mock = f"https://wa.me/?text={quote(wa_text)}"
    email = str(candidate.get("email") or "").strip()
    email_subject = f"Next step — {name}"
    email_body_mock = (
        f"Hi {name},\n\n"
        "Great speaking with you. Please book a follow-up slot:\n"
        f"{sched_url}\n\n"
        "Best regards"
    )
    email_mailto = ""
    if email:
        email_mailto = f"mailto:{quote(email)}?subject={quote(email_subject)}&body={quote(email_body_mock)}"
    return {
        "email_subject": email_subject,
        "email_body_mock": email_body_mock,
        "email_mailto": email_mailto,
        "whatsapp_mock": whatsapp_mock,
        "scheduling_url_mock": sched_url,
    }


class InterviewResultsService:
    @staticmethod
    def get_results(db: Session, order: ServiceOrder) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Results are only available for interview orders")

        config = _loads_json(order.config_json) or {}
        role = str(config.get("role") or order.title or "Interview campaign")
        recipients = ServiceOrderService.get_recipients(db, order.id)
        candidates: list[dict[str, Any]] = []
        for recipient in recipients:
            row = _candidate_row(recipient, role=role)
            row.update(_mock_scheduling_links(order, row))
            candidates.append(row)
        candidates.sort(key=lambda c: (c.get("score") or 0, c.get("name") or ""), reverse=True)

        shortlist_size = min(10, len(candidates))
        shortlist = candidates[:shortlist_size]

        called = sum(1 for r in recipients if r.status not in {None, "", "pending", "queued"})
        reached = sum(1 for r in recipients if r.status in {"completed", "answered", "success"})
        if not called and candidates:
            called = len(candidates)
            reached = len(candidates)
        recommended = sum(1 for c in candidates if c.get("recommendation") == "Advance")
        avg_duration = (
            round(sum(int(c.get("duration_seconds") or 0) for c in candidates) / len(candidates))
            if candidates
            else 0
        )
        avg_m, avg_s = divmod(avg_duration, 60)
        is_mock = any(c.get("is_mock") for c in candidates) or order.status in {"draft", "quoted", "awaiting_payment", "paid", "scheduled"}

        return {
            "order_id": order.id,
            "title": order.title,
            "role": role,
            "phase": 3,
            "is_mock": is_mock,
            "scheduling_mock": True,
            "kpis": {
                "called": called or len(candidates),
                "reached": reached or len(candidates),
                "reach_rate_pct": 100 if candidates else 0,
                "recommended_advance": recommended,
                "avg_duration_label": f"{avg_m}m {avg_s:02d}s" if candidates else "—",
            },
            "candidates": candidates,
            "shortlist": shortlist,
        }
