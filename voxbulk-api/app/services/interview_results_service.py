"""Interview campaign results, ranking, shortlist, and scheduling links."""

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


def _format_transcript_lines(transcript: str) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for raw in str(transcript or "").splitlines():
        clean = raw.strip()
        if not clean:
            continue
        speaker = "Agent"
        text = clean
        if ":" in clean:
            head, rest = clean.split(":", 1)
            if head.strip().lower() in {"agent", "candidate", "user", "assistant"}:
                speaker = head.strip().title()
                if speaker.lower() == "user":
                    speaker = "Candidate"
                text = rest.strip()
        lines.append({"speaker": speaker, "text": text})
    return lines


def _ats_fields(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    from app.services.interview_ats_service import ats_display_for_recipient

    display = ats_display_for_recipient(recipient, position="")
    status = str(recipient.ats_status or "").strip().lower()
    return {
        "ats_score": display.get("ats_score"),
        "ats_status": status or None,
        "ats_label": display.get("ats_label") or "—",
    }


def _recording_play_path(order_id: str, recipient_id: str) -> str:
    return f"/service-orders/{order_id}/recipients/{recipient_id}/recording"


def _candidate_row(recipient: ServiceOrderRecipient, *, role: str, order_id: str) -> dict[str, Any]:
    base = ServiceOrderService.recipient_to_dict(recipient)
    parsed = _loads_json(recipient.result_json) or {}
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}

    score = analysis.get("score") or parsed.get("score")
    recommendation = analysis.get("recommendation") or parsed.get("recommendation")
    sentiment = analysis.get("sentiment") or base.get("sentiment") or parsed.get("sentiment")
    duration_seconds = parsed.get("duration_seconds") or base.get("duration_seconds")
    transcript = str(parsed.get("transcript") or "").strip()
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

    recording_url = str(parsed.get("recording_url") or "").strip()
    has_recording = bool(recording_url or parsed.get("call_control_id"))
    play_path = _recording_play_path(order_id, recipient.id) if has_recording or recipient.status == "completed" else None

    row = {
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
        "has_recording": has_recording or bool(play_path),
        "recording_play_url": play_path,
        "transcript": transcript or None,
        "transcript_preview": transcript[:240] if transcript else None,
        "short_summary": analysis.get("short_summary") or parsed.get("short_summary"),
        "scheduling_sent_at": parsed.get("scheduling_url_sent_at") or parsed.get("scheduling_sent_at"),
    }
    row.update(_ats_fields(recipient))
    from app.services.interview_activity_service import InterviewActivityService

    row["activity_status"] = InterviewActivityService.activity_status(recipient, parsed=parsed)
    return row


def _scheduling_links(order: ServiceOrder, candidate: dict[str, Any], *, parsed: dict[str, Any]) -> dict[str, str]:
    slug = str(candidate.get("id") or "")[:8]
    name = str(candidate.get("name") or "there")
    role = str(candidate.get("task") or "interview").replace(" ", "-").lower()
    sched_url = str(parsed.get("scheduling_url") or parsed.get("join_url") or "").strip()
    if not sched_url:
        sched_url = f"https://schedule.voxbulk.com/mock/{order.id}/{slug}"
    scheduling_mock = not bool(parsed.get("scheduling_url") or parsed.get("join_url"))
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
        "scheduling_url": sched_url,
        "scheduling_url_mock": sched_url if scheduling_mock else sched_url,
        "scheduling_mock": scheduling_mock,
        "scheduling_sent_at": parsed.get("scheduling_url_sent_at"),
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
        saved_ids = [str(x) for x in (config.get("top_10_recipient_ids") or []) if str(x).strip()]

        for recipient in recipients:
            parsed = _loads_json(recipient.result_json) or {}
            row = _candidate_row(recipient, role=role, order_id=order.id)
            row.update(_scheduling_links(order, row, parsed=parsed if isinstance(parsed, dict) else {}))
            row["shortlist_selected"] = recipient.id in saved_ids
            candidates.append(row)
        candidates.sort(key=lambda c: (c.get("score") or 0, c.get("name") or ""), reverse=True)

        if saved_ids:
            id_set = set(saved_ids)
            shortlist = [c for c in candidates if c.get("id") in id_set]
        else:
            shortlist = candidates[: min(10, len(candidates))]

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
        is_mock = any(c.get("is_mock") for c in candidates)
        scheduling_mock = any(c.get("scheduling_mock") for c in candidates)

        return {
            "order_id": order.id,
            "title": order.title,
            "role": role,
            "phase": 5,
            "is_mock": is_mock,
            "scheduling_mock": scheduling_mock,
            "top_10_recipient_ids": saved_ids,
            "order": {
                "id": order.id,
                "reference_id": order.reference_id,
                "campaign_id": order.campaign_id,
                "status": order.status,
                "status_label": ServiceOrderService.interview_status_label(order),
                "is_live": ServiceOrderService.is_live_interview(order),
                "is_finished": ServiceOrderService.is_finished_interview(order),
                "scheduled_start_at": order.scheduled_start_at.isoformat() if order.scheduled_start_at else None,
                "scheduled_end_at": order.scheduled_end_at.isoformat() if order.scheduled_end_at else None,
                "started_at": order.started_at.isoformat() if order.started_at else None,
                "completed_at": order.completed_at.isoformat() if order.completed_at else None,
                "recipient_count": order.recipient_count,
            },
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

    @staticmethod
    def get_recipient_detail(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> dict[str, Any]:
        if recipient.order_id != order.id:
            raise ValueError("Recipient does not belong to this order")
        if order.service_code != "interview":
            raise ValueError("Interview detail is only available for interview orders")
        config = _loads_json(order.config_json) or {}
        role = str(config.get("role") or order.title or "Interview campaign")
        row = _candidate_row(recipient, role=role, order_id=order.id)
        parsed = _loads_json(recipient.result_json) or {}
        if isinstance(parsed, dict):
            row.update(_scheduling_links(order, row, parsed=parsed))
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        transcript = str(parsed.get("transcript") or "").strip()
        return {
            "ok": True,
            "candidate": row,
            "transcript": transcript,
            "transcript_lines": _format_transcript_lines(transcript),
            "analysis": analysis,
            "recording_play_url": row.get("recording_play_url"),
            "provider": "telnyx_voice",
        }

    @staticmethod
    def export_results_csv(db: Session, order: ServiceOrder) -> str:
        import csv
        import io

        payload = InterviewResultsService.get_results(db, order)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Interview", payload.get("title")])
        writer.writerow(["Role", payload.get("role")])
        writer.writerow([])
        writer.writerow(["Candidate", "Score", "Recommendation", "Sentiment", "Duration", "Status"])
        for c in payload.get("candidates") or []:
            writer.writerow(
                [
                    c.get("name"),
                    c.get("score"),
                    c.get("recommendation"),
                    c.get("sentiment"),
                    c.get("duration_label"),
                    c.get("status"),
                ]
            )
        return buf.getvalue()

    @staticmethod
    def export_results_pdf(db: Session, order: ServiceOrder) -> bytes:
        from app.services.invoice_pdf_service import render_html_to_pdf_bytes

        payload = InterviewResultsService.get_results(db, order)
        rows = "".join(
            f"<tr><td>{c.get('name')}</td><td>{c.get('score')}</td><td>{c.get('recommendation')}</td>"
            f"<td>{c.get('sentiment')}</td><td>{c.get('duration_label')}</td></tr>"
            for c in (payload.get("candidates") or [])
        )
        html = f"""<html><body>
        <h1>Interview results — {payload.get('title')}</h1>
        <p>Role: {payload.get('role')}</p>
        <table border="1" cellpadding="6"><tr><th>Candidate</th><th>Score</th><th>Recommendation</th><th>Sentiment</th><th>Duration</th></tr>
        {rows}</table></body></html>"""
        return render_html_to_pdf_bytes(html)
