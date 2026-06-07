from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_analysis_service import _recipient_result, is_ai_call_survey_order
from app.services.survey_wa_open_text_service import answer_has_pending_transcription, resolve_answer_text
from app.services.survey_whatsapp_conversation_service import is_whatsapp_survey_order


def _parse_report(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.report_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _format_duration(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
        return "—"
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _initials(name: str) -> str:
    parts = [p for p in str(name or "").strip().split() if p]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return (parts[0][:2] if parts else "??").upper()


def _avatar_class(name: str) -> str:
    return "av-g" if sum(ord(c) for c in name) % 2 == 0 else "av-p"


def _sentiment_label(sentiment: str | None) -> str:
    clean = str(sentiment or "neutral").strip().lower()
    mapping = {
        "positive": "Positive",
        "neutral": "Neutral",
        "negative": "Negative",
        "mixed": "Mixed",
    }
    return mapping.get(clean, "Neutral")


def _stars_html(score_10: float | None) -> str:
    if score_10 is None:
        return '<span style="color:var(--t3);font-size:11px">—</span>'
    filled = max(0, min(5, round(float(score_10) / 2)))
    stars = []
    for i in range(5):
        stars.append(f'<i class="ti ti-star star{" e" if i >= filled else ""}"></i>')
    return f'<div class="stars">{"".join(stars)}</div>'


def _status_badge(status: str) -> str:
    clean = str(status or "pending").lower()
    if clean == "completed":
        return '<span class="bdg bg">Completed</span>'
    if clean == "opted_out":
        return '<span class="bdg br">Opted out</span>'
    if clean in {"no_answer", "busy"}:
        return '<span class="bdg ba">No answer</span>'
    if clean == "failed":
        return '<span class="bdg br">Failed</span>'
    if clean == "calling":
        return '<span class="bdg bb">Calling</span>'
    if clean == "cancelled":
        return '<span class="bdg ba">Cancelled</span>'
    return f'<span class="bdg ba">{clean.replace("_", " ").title()}</span>'


def _recommend_pct(recommend_scores: list[float]) -> int | None:
    if not recommend_scores:
        return None
    promoters = sum(1 for s in recommend_scores if s >= 7)
    return round((promoters / len(recommend_scores)) * 100)


def normalize_nps_display(raw_nps: float | int | None) -> dict[str, Any]:
    """Map standard NPS (-100..100) to a 0..100 customer-facing score."""
    if raw_nps is None:
        return {"score": None, "label": None, "raw": None}
    try:
        raw = float(raw_nps)
    except (TypeError, ValueError):
        return {"score": None, "label": None, "raw": None}
    score = max(0, min(100, round((raw + 100) / 2)))
    label = "Good" if score >= 50 else "Unhappy"
    return {"score": score, "label": label, "raw": round(raw, 1)}


def _recommendations_fingerprint(summary: dict[str, Any], aggregates: list[dict[str, Any]]) -> str:
    import hashlib

    blob = json.dumps(
        {
            "completed": summary.get("completed_count"),
            "nps": summary.get("nps_score"),
            "aggregates": aggregates,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def ensure_action_recommendations(
    db: Session,
    order: ServiceOrder,
    *,
    goal: str,
    org_name: str,
    summary: dict[str, Any],
    aggregates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    from datetime import datetime

    from app.services.survey_action_recommendations import (
        fallback_action_recommendations,
        generate_ai_action_recommendations,
    )

    report = _parse_report(order)
    fingerprint = _recommendations_fingerprint(summary, aggregates)
    cached = report.get("ai_recommendations") if isinstance(report.get("ai_recommendations"), dict) else {}
    if cached.get("fingerprint") == fingerprint and cached.get("items"):
        return list(cached["items"])

    items = generate_ai_action_recommendations(
        db,
        goal=goal,
        org_name=org_name,
        summary=summary,
        aggregates=aggregates,
    )
    if not items:
        items = fallback_action_recommendations(summary=summary, aggregates=aggregates)

    report["ai_recommendations"] = {
        "fingerprint": fingerprint,
        "items": items,
        "generated_at": datetime.utcnow().isoformat(),
    }
    order.report_json = json.dumps(report, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    return items


def derive_survey_recommendations(
    *,
    top_issues: list[dict[str, Any]],
    top_tags: list[dict[str, Any]],
    completed_count: int,
) -> list[dict[str, str]]:
    """Lightweight deterministic recommendations from aggregated analysis."""
    recs: list[dict[str, str]] = []
    total = max(1, int(completed_count or 0))

    for item in top_issues[:4]:
        label = str(item.get("label") or "").strip()
        count = int(item.get("count") or 0)
        if not label or count <= 0:
            continue
        pct = round((count / total) * 100)
        recs.append(
            {
                "text": (
                    f"Review {label} — raised by {count} respondent{'s' if count != 1 else ''} "
                    f"({pct}% of completed calls). Consider a targeted operational follow-up."
                ),
                "source": "issue",
                "label": label,
            }
        )

    for item in top_tags[:2]:
        label = str(item.get("label") or "").strip()
        count = int(item.get("count") or 0)
        if not label or count <= 0:
            continue
        if any(r.get("label") == label for r in recs):
            continue
        recs.append(
            {
                "text": (
                    f"Theme: {label.replace('_', ' ')} — mentioned in {count} call{'s' if count != 1 else ''}. "
                    "Review related messaging or process steps."
                ),
                "source": "tag",
                "label": label,
            }
        )

    if not recs and completed_count:
        recs.append(
            {
                "text": "No recurring issues detected yet. Review individual transcripts for qualitative insights.",
                "source": "default",
                "label": "",
            }
        )
    return recs[:5]


def build_answer_aggregates(recipients: list[ServiceOrderRecipient]) -> list[dict[str, Any]]:
    """Anonymous roll-up of extracted answers — no respondent names."""
    buckets: dict[str, Counter[str]] = {}

    for row in recipients:
        if str(row.status or "").lower() != "completed":
            continue
        result = _recipient_result(row)
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
        wa_answers = wa_conv.get("answers") if isinstance(wa_conv.get("answers"), list) else []
        answers = (
            analysis.get("extracted_answers")
            or analysis.get("answers")
            or result.get("extracted_answers")
            or wa_answers
            or []
        )
        if not isinstance(answers, list):
            continue
        for item in answers:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "General").strip()
            if answer_has_pending_transcription(item):
                continue
            answer = resolve_answer_text(item)
            if not question or not answer:
                continue
            buckets.setdefault(question, Counter())[answer] += 1

    aggregates: list[dict[str, Any]] = []
    for question, counter in buckets.items():
        total = sum(counter.values())
        responses = [{"answer": label, "count": count} for label, count in counter.most_common(12)]
        aggregates.append({"question": question, "total": total, "responses": responses})

    aggregates.sort(key=lambda row: (-int(row.get("total") or 0), str(row.get("question") or "")))
    return aggregates


def build_survey_results_csv(payload: dict[str, Any]) -> str:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Survey", payload.get("order", {}).get("title", "Survey")])
    summary = payload.get("summary") or {}
    writer.writerow(["Completed responses", summary.get("completed_count", 0)])
    writer.writerow(["Response rate %", summary.get("response_rate_pct", 0)])
    writer.writerow(["Average satisfaction /5", summary.get("average_satisfaction_5", "")])
    writer.writerow(["NPS", (summary.get("nps_score") if isinstance(summary.get("nps_score"), dict) else summary.get("nps_score")) or ""])
    writer.writerow([])
    writer.writerow(["Question", "Answer", "Count"])
    for block in payload.get("aggregates") or []:
        question = block.get("question") or "Question"
        for row in block.get("responses") or []:
            writer.writerow([question, row.get("answer"), row.get("count")])
    writer.writerow([])
    writer.writerow(["Final additional feedback (per respondent)"])
    writer.writerow(["Respondent", "Yes/No", "Additional feedback"])
    for row in payload.get("respondents") or []:
        if not isinstance(row, dict):
            continue
        writer.writerow(
            [
                row.get("name") or row.get("id") or "",
                row.get("final_feedback_yes_no") or "",
                row.get("final_additional_feedback") or "",
            ]
        )
    writer.writerow([])
    writer.writerow(["Voice note answers"])
    writer.writerow(
        [
            "Respondent",
            "Question",
            "Transcript",
            "Answer source",
            "Language",
            "Transcription status",
            "Audio path",
        ]
    )
    for row in payload.get("respondents") or []:
        if not isinstance(row, dict):
            continue
        for ans in row.get("wa_answers") or []:
            if not isinstance(ans, dict) or str(ans.get("answer_source") or "") != "voice_note":
                continue
            writer.writerow(
                [
                    row.get("name") or row.get("id") or "",
                    ans.get("question") or "",
                    resolve_answer_text(ans),
                    ans.get("answer_source") or "voice_note",
                    ans.get("detected_language") or "",
                    ans.get("transcription_status") or "",
                    ans.get("audio_file_path") or "",
                ]
            )
    return buf.getvalue()


def build_survey_results_html(payload: dict[str, Any]) -> str:
    from app.services.survey_report_template import build_survey_results_html as render_report_html

    return render_report_html(payload)


def build_survey_results_pdf(payload: dict[str, Any]) -> bytes:
    from app.services.invoice_pdf_service import render_html_to_pdf_bytes

    html = build_survey_results_html(payload)
    return render_html_to_pdf_bytes(html)


def recipient_summary_row(recipient: ServiceOrderRecipient, *, goal: str) -> dict[str, Any]:
    result = _recipient_result(recipient)
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
    duration_seconds = result.get("duration_seconds")
    try:
        duration_seconds = int(duration_seconds) if duration_seconds is not None else None
    except (TypeError, ValueError):
        duration_seconds = None

    satisfaction = analysis.get("satisfaction_score", result.get("satisfaction_score"))
    sentiment = analysis.get("sentiment", result.get("sentiment"))
    short_summary = analysis.get("short_summary", result.get("short_summary"))

    return {
        "id": recipient.id,
        "name": recipient.name,
        "initials": _initials(recipient.name),
        "avatar_class": _avatar_class(recipient.name),
        "status": recipient.status,
        "status_label": str(recipient.status or "pending").replace("_", " ").title(),
        "duration_seconds": duration_seconds,
        "duration_label": _format_duration(duration_seconds),
        "goal": goal,
        "satisfaction_score": satisfaction,
        "sentiment": sentiment,
        "sentiment_label": _sentiment_label(str(sentiment or "")),
        "short_summary": str(short_summary or "").strip() or None,
        "has_transcript": bool(str(result.get("transcript") or "").strip()),
        "has_analysis": bool(result.get("analysis_saved_at")),
        "final_additional_feedback": str(
            result.get("final_additional_feedback") or wa_conv.get("final_additional_feedback") or ""
        ).strip()
        or None,
        "final_feedback_yes_no": result.get("final_feedback_yes_no") or wa_conv.get("final_feedback_yes_no"),
        "wa_answers": wa_conv.get("answers") or [],
    }


def recipient_detail_payload(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    result = _recipient_result(recipient)
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
    duration_seconds = result.get("duration_seconds")
    try:
        duration_seconds = int(duration_seconds) if duration_seconds is not None else None
    except (TypeError, ValueError):
        duration_seconds = None

    return {
        "id": recipient.id,
        "name": recipient.name,
        "initials": _initials(recipient.name),
        "avatar_class": _avatar_class(recipient.name),
        "status": recipient.status,
        "duration_seconds": duration_seconds,
        "duration_label": _format_duration(duration_seconds),
        "transcript": str(result.get("transcript") or "").strip() or None,
        "call_summary": str(result.get("call_summary") or "").strip() or None,
        "analysis": analysis or None,
        "extracted_answers": analysis.get("extracted_answers") or analysis.get("answers") or result.get("extracted_answers") or [],
        "wa_answers": wa_conv.get("answers") or [],
        "final_additional_feedback": str(
            result.get("final_additional_feedback") or wa_conv.get("final_additional_feedback") or ""
        ).strip()
        or None,
        "final_feedback_yes_no": result.get("final_feedback_yes_no") or wa_conv.get("final_feedback_yes_no"),
        "issues": analysis.get("issues") or result.get("issues") or [],
        "tags": analysis.get("tags") or result.get("tags") or [],
        "short_summary": str(analysis.get("short_summary") or result.get("short_summary") or "").strip() or None,
        "sentiment": analysis.get("sentiment") or result.get("sentiment"),
        "sentiment_label": _sentiment_label(str(analysis.get("sentiment") or result.get("sentiment") or "")),
        "satisfaction_score": analysis.get("satisfaction_score", result.get("satisfaction_score")),
        "recommend_score": analysis.get("recommend_score", result.get("recommend_score")),
        "call_control_id": result.get("call_control_id"),
        "telnyx_conversation_id": result.get("telnyx_conversation_id"),
        "analysis_error": result.get("analysis_error"),
    }


def build_whatsapp_survey_results_payload(
    db: Session,
    order: ServiceOrder,
    *,
    include_respondents: bool = True,
) -> dict[str, Any]:
    config = _order_config(order)
    goal = str(config.get("goal") or "Survey").strip()
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "").strip()
    report = _parse_report(order)
    recipients = ServiceOrderService.get_recipients(db, order.id)
    completed = [r for r in recipients if str(r.status or "").lower() == "completed"]
    total = len(recipients)
    completed_count = len(completed)
    response_rate = round((completed_count / total) * 100) if total else 0
    aggregates = build_answer_aggregates(recipients)
    summary = {
        "total_recipients": total,
        "completed_count": completed_count,
        "response_rate_pct": response_rate,
        "average_satisfaction_10": None,
        "average_satisfaction_5": None,
        "average_recommend_score": None,
        "recommend_pct": None,
        "nps_score": None,
        "nps_label": None,
        "nps_score_raw": None,
        "nps_promoters_pct": 0,
        "nps_passives_pct": 0,
        "nps_detractors_pct": 0,
        "nps_promoters": 0,
        "nps_passives": 0,
        "nps_detractors": 0,
        "average_call_duration_seconds": None,
        "average_call_duration_label": None,
        "sentiment_counts": {},
        "top_issues": [],
        "top_tags": [],
        "analyzed_count": completed_count,
        "pending_analysis": max(0, total - completed_count),
        "channel_note": report.get("note") or "WhatsApp survey",
    }
    recommendations = ensure_action_recommendations(
        db,
        order,
        goal=goal,
        org_name=org_name,
        summary=summary,
        aggregates=aggregates,
    )
    return {
        "ok": True,
        "order": {
            "id": order.id,
            "title": order.title,
            "status": order.status,
            "goal": goal,
            "organisation_name": org_name or None,
            "channel": "whatsapp",
            "scheduled_start_at": order.scheduled_start_at.isoformat() if order.scheduled_start_at else None,
            "scheduled_end_at": order.scheduled_end_at.isoformat() if order.scheduled_end_at else None,
            "started_at": order.started_at.isoformat() if order.started_at else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        },
        "summary": summary,
        "aggregates": aggregates,
        "respondents": [recipient_summary_row(r, goal=goal) for r in recipients] if include_respondents else [],
        "recommendations": recommendations,
    }


def build_survey_results_payload(
    db: Session,
    order: ServiceOrder,
    *,
    include_respondents: bool = True,
) -> dict[str, Any]:
    if order.service_code != "survey":
        raise ValueError("Not a survey order")
    if is_whatsapp_survey_order(order):
        return build_whatsapp_survey_results_payload(db, order, include_respondents=include_respondents)
    if not is_ai_call_survey_order(order):
        raise ValueError("Survey results are available for AI-call surveys only")

    config = _order_config(order)
    goal = str(config.get("goal") or "Survey").strip()
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "").strip()
    report = _parse_report(order)
    analysis = report.get("analysis") if isinstance(report.get("analysis"), dict) else {}

    recipients = ServiceOrderService.get_recipients(db, order.id)
    completed = [r for r in recipients if str(r.status or "").lower() == "completed"]

    durations: list[int] = []
    recommend_scores: list[float] = []
    for row in completed:
        result = _recipient_result(row)
        dur = result.get("duration_seconds")
        try:
            if dur is not None:
                durations.append(int(dur))
        except (TypeError, ValueError):
            pass
        rec = result.get("recommend_score")
        if rec is None and isinstance(result.get("analysis"), dict):
            rec = result["analysis"].get("recommend_score")
        if rec is not None:
            try:
                recommend_scores.append(float(rec))
            except (TypeError, ValueError):
                pass

    total = len(recipients)
    completed_count = int(report.get("completed") or len(completed))
    response_rate = round((completed_count / total) * 100) if total else 0

    avg_sat_10 = analysis.get("average_satisfaction")
    avg_sat_5 = round(float(avg_sat_10) / 2, 1) if avg_sat_10 is not None else None

    avg_duration = round(sum(durations) / len(durations)) if durations else None
    nps = analysis.get("nps") if isinstance(analysis.get("nps"), dict) else {}
    recommend_pct = _recommend_pct(recommend_scores)
    nps_display = normalize_nps_display(nps.get("score"))
    nps_responses = max(0, int(nps.get("responses") or 0))
    nps_promoters = int(nps.get("promoters") or 0)
    nps_passives = int(nps.get("passives") or 0)
    nps_detractors = int(nps.get("detractors") or 0)
    nps_den = max(1, nps_responses or (nps_promoters + nps_passives + nps_detractors) or completed_count or 1)

    summary = {
        "total_recipients": total,
        "completed_count": completed_count,
        "response_rate_pct": response_rate,
        "average_satisfaction_10": avg_sat_10,
        "average_satisfaction_5": avg_sat_5,
        "average_recommend_score": analysis.get("average_recommend_score"),
        "recommend_pct": recommend_pct,
        "nps_score": nps_display["score"],
        "nps_label": nps_display["label"],
        "nps_score_raw": nps_display["raw"],
        "nps_promoters_pct": round((nps_promoters / nps_den) * 100),
        "nps_passives_pct": round((nps_passives / nps_den) * 100),
        "nps_detractors_pct": round((nps_detractors / nps_den) * 100),
        "nps_promoters": nps_promoters,
        "nps_passives": nps_passives,
        "nps_detractors": nps_detractors,
        "average_call_duration_seconds": avg_duration,
        "average_call_duration_label": _format_duration(avg_duration),
        "sentiment_counts": analysis.get("sentiment_counts") or {},
        "top_issues": analysis.get("top_issues") or [],
        "top_tags": analysis.get("top_tags") or [],
        "analyzed_count": analysis.get("analyzed_count") or 0,
        "pending_analysis": analysis.get("pending_analysis") or 0,
    }

    aggregates = build_answer_aggregates(recipients)
    recommendations = ensure_action_recommendations(
        db,
        order,
        goal=goal,
        org_name=org_name,
        summary=summary,
        aggregates=aggregates,
    )

    return {
        "ok": True,
        "order": {
            "id": order.id,
            "title": order.title,
            "status": order.status,
            "goal": goal,
            "organisation_name": org_name or None,
            "channel": PlatformCatalogService.resolve_survey_channel(config),
            "scheduled_start_at": order.scheduled_start_at.isoformat() if order.scheduled_start_at else None,
            "scheduled_end_at": order.scheduled_end_at.isoformat() if order.scheduled_end_at else None,
            "started_at": order.started_at.isoformat() if order.started_at else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        },
        "summary": summary,
        "aggregates": aggregates,
        "respondents": [recipient_summary_row(r, goal=goal) for r in recipients] if include_respondents else [],
        "recommendations": recommendations,
    }


class SurveyResultsService:
    @staticmethod
    def get_results(db: Session, order: ServiceOrder, *, anonymous: bool = False) -> dict[str, Any]:
        return build_survey_results_payload(db, order, include_respondents=not anonymous)

    @staticmethod
    def export_results_csv(db: Session, order: ServiceOrder) -> str:
        payload = build_survey_results_payload(db, order, include_respondents=False)
        return build_survey_results_csv(payload)

    @staticmethod
    def export_results_pdf(db: Session, order: ServiceOrder) -> bytes:
        payload = build_survey_results_payload(db, order, include_respondents=False)
        return build_survey_results_pdf(payload)

    @staticmethod
    def get_recipient_detail(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> dict[str, Any]:
        if recipient.order_id != order.id:
            raise ValueError("Recipient does not belong to this order")
        if not is_ai_call_survey_order(order) and not is_whatsapp_survey_order(order):
            raise ValueError("Survey results are available for AI-call or WhatsApp surveys only")
        return {"ok": True, "recipient": recipient_detail_payload(recipient)}
