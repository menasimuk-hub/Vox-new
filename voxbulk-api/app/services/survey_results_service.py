from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_analysis_service import _recipient_result, is_ai_call_survey_order
from app.services.survey_wa_open_text_service import answer_has_pending_transcription, resolve_answer_text
from app.services.survey_whatsapp_conversation_service import is_whatsapp_survey_order


_WA_TERMINAL_RECIPIENT_STATUSES = frozenset({"completed", "done"})


def is_wa_survey_response_complete(recipient: ServiceOrderRecipient) -> bool:
    """True when a WhatsApp respondent finished (status or conversation marker)."""
    status = str(recipient.status or "").lower()
    if status in _WA_TERMINAL_RECIPIENT_STATUSES:
        return True
    result = _recipient_result(recipient)
    conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
    if conv.get("completed_at"):
        return True
    return False


def _recipient_is_complete_for_results(order: ServiceOrder, recipient: ServiceOrderRecipient) -> bool:
    if is_whatsapp_survey_order(order):
        return is_wa_survey_response_complete(recipient)
    return str(recipient.status or "").lower() == "completed"


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


_NEGATIVE_ANSWER_VALUES = frozenset(
    {
        "bad",
        "no",
        "poor",
        "negative",
        "below standard",
        "not clean",
        "stressful",
        "unacceptable",
        "terrible",
        "awful",
        "dissatisfied",
        "very poor",
        "slow",
        "avg",
        "maybe",
    }
)
_NEGATIVE_ANSWER_FRAGMENTS = (
    "poor",
    "below standard",
    "not clean",
    "stressful",
    "unacceptable",
    "terrible",
    "awful",
    "dissatisf",
    "not happy",
    "unhappy",
)


def _is_negative_answer_value(raw: str) -> bool:
    text = str(raw or "").strip().lower()
    if not text:
        return False
    if text in _NEGATIVE_ANSWER_VALUES:
        return True
    return any(fragment in text for fragment in _NEGATIVE_ANSWER_FRAGMENTS)


def _derive_needs_follow_up(recipient: ServiceOrderRecipient) -> bool:
    result = _recipient_result(recipient)
    if result.get("needs_follow_up"):
        return True
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    if analysis.get("needs_follow_up"):
        return True
    wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
    return bool(wa_conv.get("needs_follow_up"))


def _is_unhappy_respondent(recipient: ServiceOrderRecipient) -> bool:
    if _derive_needs_follow_up(recipient):
        return True
    result = _recipient_result(recipient)
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    sentiment = str(analysis.get("sentiment") or result.get("sentiment") or "").strip().lower()
    if sentiment == "negative":
        return True
    wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
    for item in wa_conv.get("answers") or []:
        if not isinstance(item, dict):
            continue
        for key in ("answer", "answer_text", "normalized_value"):
            if _is_negative_answer_value(str(item.get(key) or "")):
                return True
    extracted = (
        analysis.get("extracted_answers")
        or analysis.get("answers")
        or result.get("extracted_answers")
        or []
    )
    for item in extracted:
        if isinstance(item, dict) and _is_negative_answer_value(str(item.get("answer") or item.get("value") or "")):
            return True
    recommend_score = analysis.get("recommend_score", result.get("recommend_score"))
    if recommend_score is not None:
        try:
            if float(recommend_score) < 7:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _rating_label_from_answers(wa_answers: list[Any]) -> str | None:
    for item in wa_answers or []:
        if not isinstance(item, dict):
            continue
        ans = str(item.get("answer") or item.get("answer_text") or "").strip().lower()
        if ans == "bad":
            return "Poor"
        if ans == "excellent":
            return "Excellent"
        if ans == "good":
            return "Good"
    return None


def _count_unhappy_respondents(recipients: list[ServiceOrderRecipient]) -> int:
    return sum(
        1
        for row in recipients
        if str(row.status or "").lower() == "completed" and _is_unhappy_respondent(row)
    )


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


def _parse_numeric_score(raw: str) -> int | None:
    text = str(raw or "").strip()
    if not text or not text.isdigit():
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    if 0 <= value <= 10:
        return value
    return None


def _rating_score_from_item(item: dict[str, Any]) -> int | None:
    """Extract a 0–10 score from a WA answer row (answer, answer_text, or normalized_value)."""
    for key in ("answer", "answer_text", "normalized_value"):
        score = _parse_numeric_score(str(item.get(key) or ""))
        if score is not None:
            return score
    return None


def _nps_bucket(score: int) -> str:
    if score >= 9:
        return "promoter"
    if score >= 7:
        return "passive"
    return "detractor"


def _sentiment_bucket_for_score(score: int) -> str:
    if score >= 9:
        return "positive"
    if score >= 7:
        return "neutral"
    return "negative"


def _is_rating_answer(item: dict[str, Any]) -> bool:
    role = str(item.get("step_role") or "").lower()
    if role in {"reason", "final_feedback_text", "followup", "tell_us_more", "improvement"}:
        return False
    if role == "rating":
        return _rating_score_from_item(item) is not None
    return _rating_score_from_item(item) is not None


def _normalize_answer_source(item: dict[str, Any]) -> str:
    source = str(item.get("answer_source") or "").strip().lower()
    if source == "voice_note":
        return "voice"
    return "text"


def _voice_audio_api_path(order_id: str, job_id: str | None) -> str | None:
    clean = str(job_id or "").strip()
    if not clean or not order_id:
        return None
    return f"/service-orders/{order_id}/survey-voice-notes/{clean}/audio"


def _voice_answer_placeholder(item: dict[str, Any]) -> str | None:
    if _normalize_answer_source(item) != "voice":
        return None
    status = str(item.get("transcription_status") or "").strip().lower()
    if status in {"pending", "retrying", "transcribing"}:
        return "[Voice note — transcription pending]"
    if status == "failed":
        err = str(item.get("transcription_error") or "").strip()
        return f"[Voice note — transcription failed{': ' + err[:120] if err else ''}]"
    if not resolve_answer_text(item):
        return "[Voice note]"
    return None


def _serialize_open_answer(item: dict[str, Any], *, order_id: str | None = None) -> dict[str, Any]:
    transcript = resolve_answer_text(item) or _voice_answer_placeholder(item)
    source = _normalize_answer_source(item)
    job_id = str(item.get("voice_note_job_id") or "").strip() or None
    original_text = str(item.get("original_text") or resolve_answer_text(item) or "").strip() or None
    translated_text = str(item.get("translated_text") or "").strip() or None
    display_text = translated_text or transcript
    return {
        "question": str(item.get("question") or "Feedback").strip(),
        "step_role": str(item.get("step_role") or "").strip() or None,
        "answer_source": source,
        "transcript": display_text or transcript or None,
        "transcription_status": str(item.get("transcription_status") or "").strip() or None,
        "transcription_error": str(item.get("transcription_error") or "").strip() or None,
        "detected_language": str(item.get("detected_language") or "").strip() or None,
        "translation_status": str(item.get("translation_status") or "").strip() or None,
        "original_text": original_text,
        "translated_text": translated_text,
        "voice_note_job_id": job_id,
        "audio_url": _voice_audio_api_path(order_id or "", job_id) if order_id and source == "voice" else None,
        "text": display_text or transcript or None,
        "created_at": str(item.get("transcribed_at") or item.get("processed_at") or "").strip() or None,
    }


def _collect_open_feedback(recipient: ServiceOrderRecipient, *, order_id: str | None = None) -> list[dict[str, Any]]:
    result = _recipient_result(recipient)
    wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
    answers = wa_conv.get("answers") if isinstance(wa_conv.get("answers"), list) else []
    out: list[dict[str, Any]] = []
    open_roles = {"reason", "final_feedback_text", "followup", "tell_us_more"}
    for item in answers:
        if not isinstance(item, dict):
            continue
        role = str(item.get("step_role") or "").lower()
        reply_type = str(item.get("reply_type") or "").lower()
        if role not in open_roles and reply_type not in {"long_text", "text"}:
            continue
        source = _normalize_answer_source(item)
        if answer_has_pending_transcription(item) and source != "voice":
            continue
        text = resolve_answer_text(item)
        if not text and source != "voice":
            continue
        row = _serialize_open_answer(item, order_id=order_id)
        if row.get("transcript") or source == "voice":
            out.append(row)
    return out


def compute_wa_survey_metrics(recipients: list[ServiceOrderRecipient]) -> dict[str, Any]:
    promoters = passives = detractors = 0
    sentiment_counts: Counter[str] = Counter()
    recommend_scores: list[float] = []

    for row in recipients:
        if str(row.status or "").lower() != "completed":
            continue
        result = _recipient_result(row)
        wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
        answers = wa_conv.get("answers") if isinstance(wa_conv.get("answers"), list) else []
        rating_score: int | None = None
        for item in answers:
            if not isinstance(item, dict) or not _is_rating_answer(item):
                continue
            if answer_has_pending_transcription(item):
                continue
            score = _rating_score_from_item(item)
            if score is None:
                continue
            rating_score = score
            bucket = _nps_bucket(score)
            if bucket == "promoter":
                promoters += 1
            elif bucket == "passive":
                passives += 1
            else:
                detractors += 1
            sentiment_counts[_sentiment_bucket_for_score(score)] += 1
            recommend_scores.append(float(score))
        if rating_score is None:
            for key in ("recommend_score", "satisfaction_score"):
                raw = result.get(key)
                if raw is None and isinstance(result.get("analysis"), dict):
                    raw = result["analysis"].get(key)
                if raw is None:
                    continue
                try:
                    score = int(float(raw))
                except (TypeError, ValueError):
                    continue
                if 0 <= score <= 10:
                    rating_score = score
                    bucket = _nps_bucket(score)
                    if bucket == "promoter":
                        promoters += 1
                    elif bucket == "passive":
                        passives += 1
                    else:
                        detractors += 1
                    sentiment_counts[_sentiment_bucket_for_score(score)] += 1
                    recommend_scores.append(float(score))
                    break

    nps_responses = promoters + passives + detractors
    raw_nps = None
    if nps_responses:
        raw_nps = round(((promoters - detractors) / nps_responses) * 100, 1)
    nps_display = normalize_nps_display(raw_nps)
    nps_den = max(1, nps_responses)
    avg_recommend = round(sum(recommend_scores) / len(recommend_scores), 1) if recommend_scores else None
    return {
        "nps_score": nps_display["score"],
        "nps_label": nps_display["label"],
        "nps_score_raw": nps_display["raw"],
        "nps_promoters_pct": round((promoters / nps_den) * 100) if nps_responses else 0,
        "nps_passives_pct": round((passives / nps_den) * 100) if nps_responses else 0,
        "nps_detractors_pct": round((detractors / nps_den) * 100) if nps_responses else 0,
        "nps_promoters": promoters,
        "nps_passives": passives,
        "nps_detractors": detractors,
        "average_recommend_score": avg_recommend,
        "recommend_pct": _recommend_pct(recommend_scores),
        "sentiment_counts": dict(sentiment_counts),
    }


def build_org_survey_weekly_trend(db: Session, order: ServiceOrder, *, weeks: int = 8) -> list[dict[str, Any]]:
    from datetime import datetime, timedelta

    from sqlalchemy import select

    since = datetime.utcnow() - timedelta(weeks=weeks)
    rows = list(
        db.execute(
            select(ServiceOrder)
            .where(
                ServiceOrder.org_id == order.org_id,
                ServiceOrder.service_code == "survey",
                ServiceOrder.created_at >= since,
            )
            .order_by(ServiceOrder.created_at.asc())
        ).scalars()
    )
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not row.created_at:
            continue
        week_start = row.created_at.date() - timedelta(days=row.created_at.weekday())
        label = week_start.strftime("%d %b")
        bucket = buckets.setdefault(
            label,
            {
                "week": label,
                "week_start": week_start.isoformat(),
                "surveys": 0,
                "completed_count": 0,
                "total_recipients": 0,
                "response_rate_pct": 0,
                "nps_score": None,
            },
        )
        bucket["surveys"] += 1
        recipients = ServiceOrderService.get_recipients(db, row.id)
        total = len(recipients)
        completed = sum(1 for r in recipients if str(r.status or "").lower() == "completed")
        bucket["completed_count"] += completed
        bucket["total_recipients"] += total
        metrics = compute_wa_survey_metrics(recipients)
        if metrics.get("nps_score_raw") is not None:
            bucket["nps_score"] = metrics["nps_score"]
        if metrics.get("average_recommend_score") is not None:
            bucket["csat_pct"] = round((float(metrics["average_recommend_score"]) / 10) * 100)
    trend: list[dict[str, Any]] = []
    for bucket in buckets.values():
        total = int(bucket.get("total_recipients") or 0)
        completed = int(bucket.get("completed_count") or 0)
        bucket["response_rate_pct"] = round((completed / total) * 100) if total else 0
        trend.append(bucket)
    trend.sort(key=lambda item: str(item.get("week_start") or ""))
    return trend[-weeks:]


def _aggregate_breakdown(question: str, counter: Counter[str], meta_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not meta_items or not all(_is_rating_answer(item) for item in meta_items):
        return None
    groups = {"positive": 0, "neutral": 0, "negative": 0}
    for item in meta_items:
        if answer_has_pending_transcription(item):
            continue
        score = _parse_numeric_score(str(item.get("answer") or ""))
        if score is None:
            continue
        groups[_sentiment_bucket_for_score(score)] += 1
    total = sum(groups.values())
    if total <= 0:
        return None
    return {
        "type": "sentiment_breakdown",
        "groups": [
            {"label": "Positive", "key": "positive", "count": groups["positive"], "pct": round((groups["positive"] / total) * 100)},
            {"label": "Neutral", "key": "neutral", "count": groups["neutral"], "pct": round((groups["neutral"] / total) * 100)},
            {"label": "Negative", "key": "negative", "count": groups["negative"], "pct": round((groups["negative"] / total) * 100)},
        ],
        "total": total,
        "question": question,
    }


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


def _collect_negative_feedback_excerpts(
    recipients: list[ServiceOrderRecipient],
    *,
    order_id: str | None = None,
) -> list[dict[str, Any]]:
    excerpts: list[dict[str, Any]] = []
    for recipient in recipients:
        if str(recipient.status or "").lower() != "completed":
            continue
        if not _is_unhappy_respondent(recipient):
            continue
        for row in _collect_open_feedback(recipient, order_id=order_id):
            text = str(
                row.get("translated_text") or row.get("transcript") or row.get("text") or ""
            ).strip()
            if not text or text.startswith("[Voice note"):
                continue
            excerpts.append(
                {
                    "source": "negative_feedback",
                    "respondent_id": recipient.id,
                    "question": row.get("question"),
                    "excerpt": text[:500],
                    "response_type": row.get("answer_source"),
                }
            )
    return excerpts[:20]


def _dedupe_recommendation_items(
    items: list[dict[str, str]],
    *,
    negative_feedback: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    for excerpt in negative_feedback or []:
        quote = str(excerpt.get("excerpt") or "").strip()
        question = str(excerpt.get("question") or "Feedback").strip()
        if not quote:
            continue
        items.append(
            {
                "title": f"Address: {question[:60]}",
                "text": quote,
                "source": "negative_feedback",
                "impact": "High",
            }
        )

    seen_titles: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in items:
        title = str(item.get("title") or "").strip().lower()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        deduped.append(item)
    return deduped[:8]


def generate_and_store_action_recommendations(db: Session, order: ServiceOrder) -> dict[str, Any]:
    """Generate AI recommendations and persist on order.report_json (Celery / completion hook)."""
    from datetime import datetime

    from app.services.survey_action_recommendations import (
        fallback_action_recommendations,
        generate_ai_action_recommendations,
    )

    if order.service_code != "survey":
        return {"ok": False, "error": "not_survey"}
    try:
        payload = build_survey_results_payload(db, order, include_respondents=False, include_recommendations=False)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    aggregates = payload.get("aggregates") if isinstance(payload.get("aggregates"), list) else []
    goal = str((payload.get("order") or {}).get("goal") or "Survey")
    org_name = str((payload.get("order") or {}).get("organisation_name") or "Your business")
    negative_feedback = _collect_negative_feedback_excerpts(
        ServiceOrderService.get_recipients(db, order.id),
        order_id=order.id,
    )

    report = _parse_report(order)
    fingerprint = _recommendations_fingerprint(summary, aggregates)
    cached = report.get("ai_recommendations") if isinstance(report.get("ai_recommendations"), dict) else {}
    if cached.get("fingerprint") == fingerprint and cached.get("items"):
        return {"ok": True, "skipped": True, "count": len(cached["items"])}

    items = generate_ai_action_recommendations(
        db,
        goal=goal,
        org_name=org_name,
        summary=summary,
        aggregates=aggregates,
        negative_feedback=negative_feedback,
    )
    if not items:
        items = fallback_action_recommendations(summary=summary, aggregates=aggregates)
    items = _dedupe_recommendation_items(items, negative_feedback=negative_feedback)

    report["ai_recommendations"] = {
        "fingerprint": fingerprint,
        "items": items,
        "generated_at": datetime.utcnow().isoformat(),
    }
    report.pop("ai_recommendations_pending", None)
    order.report_json = json.dumps(report, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    return {"ok": True, "count": len(items)}


def ensure_action_recommendations(
    db: Session,
    order: ServiceOrder,
    *,
    goal: str,
    org_name: str,
    summary: dict[str, Any],
    aggregates: list[dict[str, Any]],
    negative_feedback: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    from app.services.survey_action_recommendations import fallback_action_recommendations

    report = _parse_report(order)
    fingerprint = _recommendations_fingerprint(summary, aggregates)
    cached = report.get("ai_recommendations") if isinstance(report.get("ai_recommendations"), dict) else {}
    if cached.get("fingerprint") == fingerprint and cached.get("items"):
        return list(cached["items"])

    items = fallback_action_recommendations(summary=summary, aggregates=aggregates)
    return _dedupe_recommendation_items(items, negative_feedback=negative_feedback)


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


def _answer_sort_key(item: dict[str, Any]) -> int:
    for key in ("answer_index", "step_index", "sequence"):
        try:
            val = item.get(key)
            if val is not None:
                return int(val)
        except (TypeError, ValueError):
            continue
    return 9999


def sort_survey_answer_items(items: list[Any]) -> list[dict[str, Any]]:
    """Preserve survey step order in results (not alphabetical or random append order)."""
    indexed: list[tuple[int, int, dict[str, Any]]] = []
    for pos, raw in enumerate(items or []):
        if isinstance(raw, dict):
            indexed.append((_answer_sort_key(raw), pos, raw))
    indexed.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in indexed]


def build_extracted_answer_entries(answers: list[Any]) -> list[dict[str, Any]]:
    """Mirror wa_conversation.answers for reporting with original + English fields."""
    out: list[dict[str, Any]] = []
    for item in sort_survey_answer_items(answers):
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        display = resolve_answer_text(item) or _voice_answer_placeholder(item) or str(item.get("answer") or "").strip()
        entry: dict[str, Any] = {"question": question, "answer": display}
        original = str(item.get("original_text") or "").strip()
        translated = str(item.get("translated_text") or "").strip()
        if original:
            entry["original_text"] = original
        if translated:
            entry["translated_text"] = translated
        if item.get("answer_index") is not None:
            entry["answer_index"] = item.get("answer_index")
        if item.get("step_index") is not None:
            entry["step_index"] = item.get("step_index")
        if item.get("step_role"):
            entry["step_role"] = item.get("step_role")
        if item.get("answer_source"):
            entry["answer_source"] = item.get("answer_source")
        out.append(entry)
    return out


def build_answer_aggregates(recipients: list[ServiceOrderRecipient]) -> list[dict[str, Any]]:
    """Anonymous roll-up of extracted answers — no respondent names."""
    buckets: dict[str, Counter[str]] = {}
    meta: dict[str, list[dict[str, Any]]] = {}
    question_order: dict[str, int] = {}

    for row in recipients:
        if str(row.status or "").lower() != "completed":
            continue
        result = _recipient_result(row)
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
        wa_answers = sort_survey_answer_items(wa_conv.get("answers") if isinstance(wa_conv.get("answers"), list) else [])
        answers = (
            analysis.get("extracted_answers")
            or analysis.get("answers")
            or result.get("extracted_answers")
            or wa_answers
            or []
        )
        if not isinstance(answers, list):
            continue
        answers = sort_survey_answer_items(answers)
        for item in answers:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "General").strip()
            source = _normalize_answer_source(item)
            if answer_has_pending_transcription(item) and source != "voice":
                continue
            answer = resolve_answer_text(item) or _voice_answer_placeholder(item) or ""
            if not question:
                continue
            order_key = _answer_sort_key(item)
            if question not in question_order or order_key < question_order[question]:
                question_order[question] = order_key
            if _is_rating_answer(item):
                score = _parse_numeric_score(str(item.get("answer") or answer))
                if score is None:
                    continue
                label = str(score)
                buckets.setdefault(question, Counter())[label] += 1
                meta.setdefault(question, []).append(item)
                continue
            if not answer:
                continue
            buckets.setdefault(question, Counter())[answer] += 1
            meta.setdefault(question, []).append(item)

    aggregates: list[dict[str, Any]] = []
    for question, counter in buckets.items():
        total = sum(counter.values())
        responses = [{"answer": label, "count": count} for label, count in counter.most_common(12)]
        block: dict[str, Any] = {
            "question": question,
            "total": total,
            "responses": responses,
            "visualization": "choice",
        }
        breakdown = _aggregate_breakdown(question, counter, meta.get(question) or [])
        if breakdown:
            block["visualization"] = "sentiment_breakdown"
            block["breakdown"] = breakdown["groups"]
            block["step_role"] = str((meta.get(question) or [{}])[0].get("step_role") or "rating")
        aggregates.append(block)

    aggregates.sort(
        key=lambda row: (
            question_order.get(str(row.get("question") or ""), 9999),
            str(row.get("question") or ""),
        )
    )
    return aggregates


def build_survey_results_csv(payload: dict[str, Any], *, anonymous: bool = False) -> str:
    from app.services.survey_results_export_service import build_survey_results_csv as render_csv

    return render_csv(payload, anonymous=anonymous)


def build_survey_results_xlsx(payload: dict[str, Any], *, anonymous: bool = False) -> bytes:
    from app.services.survey_results_export_service import build_survey_results_xlsx as render_xlsx

    return render_xlsx(payload, anonymous=anonymous)


def build_survey_results_html(payload: dict[str, Any]) -> str:
    from app.services.survey_report_template import build_survey_results_html as render_report_html

    return render_report_html(payload)


def build_survey_results_pdf(payload: dict[str, Any]) -> bytes:
    from app.services.invoice_pdf_service import render_html_to_pdf_bytes
    from app.services.survey_results_export_service import build_survey_results_export_html

    html = build_survey_results_export_html(payload)
    return render_html_to_pdf_bytes(html)


def build_hubspot_sync_respondents(
    recipients: list[ServiceOrderRecipient],
    *,
    goal: str,
    order_id: str,
) -> list[dict[str, Any]]:
    """Minimal completed-respondent rows for CRM manual sync (even when anonymous UI hides names)."""
    rows: list[dict[str, Any]] = []
    for recipient in recipients:
        if str(recipient.status or "").lower() != "completed":
            continue
        summary = recipient_summary_row(recipient, goal=goal, order_id=order_id)
        rows.append(
            {
                "id": summary.get("id"),
                "name": summary.get("name"),
                "email": summary.get("email"),
                "phone": summary.get("phone"),
                "status_label": summary.get("status_label"),
                "completed_at": summary.get("completed_at"),
                "sentiment_label": summary.get("sentiment_label"),
                "short_summary": summary.get("short_summary"),
            }
        )
    return rows


def _ai_followup_jobs_payload(db: Session, order_id: str) -> list[dict[str, Any]]:
    try:
        from app.services.survey_ai_followup_service import job_to_report_dict, jobs_for_order

        return [job_to_report_dict(job) for job in jobs_for_order(db, order_id)]
    except Exception:
        return []


def _attach_ai_followup_to_respondents(
    db: Session,
    respondents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not respondents:
        return respondents
    try:
        from app.services.survey_ai_followup_service import job_to_report_dict, jobs_by_recipient_ids

        ids = [str(r.get("id") or "") for r in respondents if r.get("id")]
        by_id = jobs_by_recipient_ids(db, ids)
        for row in respondents:
            job = by_id.get(str(row.get("id") or ""))
            if job is not None:
                report = job_to_report_dict(job)
                row["ai_follow_up"] = report
                row["ai_follow_up_status"] = report.get("status")
            else:
                row["ai_follow_up"] = None
                row["ai_follow_up_status"] = None
    except Exception:
        for row in respondents:
            row.setdefault("ai_follow_up", None)
            row.setdefault("ai_follow_up_status", None)
    return respondents


def recipient_summary_row(
    recipient: ServiceOrderRecipient,
    *,
    goal: str,
    order_id: str | None = None,
) -> dict[str, Any]:
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
    open_feedback = _collect_open_feedback(recipient, order_id=order_id)
    quote = str(short_summary or "").strip()
    if not quote and open_feedback:
        quote = str(open_feedback[0].get("transcript") or open_feedback[0].get("text") or "").strip()
    if not quote:
        quote = str(
            result.get("final_additional_feedback") or wa_conv.get("final_additional_feedback") or ""
        ).strip()

    recommend_score = analysis.get("recommend_score", result.get("recommend_score"))
    wa_answers = sort_survey_answer_items(wa_conv.get("answers") or [])
    if recommend_score is None:
        for item in wa_answers:
            if isinstance(item, dict) and _is_rating_answer(item):
                score = _parse_numeric_score(str(item.get("answer") or ""))
                if score is not None:
                    recommend_score = score
                    break
    rating_label = _rating_label_from_answers(wa_answers)
    extracted_answers = sort_survey_answer_items(
        analysis.get("extracted_answers")
        or analysis.get("answers")
        or result.get("extracted_answers")
        or build_extracted_answer_entries(wa_answers)
        or []
    )
    completed_raw = getattr(recipient, "completed_at", None) or result.get("completed_at")
    if completed_raw and hasattr(completed_raw, "isoformat"):
        completed_at = completed_raw.isoformat()
    elif completed_raw:
        completed_at = str(completed_raw)
    elif str(recipient.status or "").lower() == "completed":
        stamp = getattr(recipient, "updated_at", None) or getattr(recipient, "created_at", None)
        completed_at = stamp.isoformat() if stamp and hasattr(stamp, "isoformat") else None
    else:
        completed_at = None

    return {
        "id": recipient.id,
        "name": recipient.name,
        "phone": recipient.phone,
        "email": recipient.email,
        "initials": _initials(recipient.name),
        "avatar_class": _avatar_class(recipient.name),
        "status": recipient.status,
        "status_label": str(recipient.status or "pending").replace("_", " ").title(),
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "duration_label": _format_duration(duration_seconds),
        "goal": goal,
        "satisfaction_score": satisfaction,
        "recommend_score": recommend_score,
        "rating_label": rating_label,
        "sentiment": sentiment,
        "sentiment_label": _sentiment_label(str(sentiment or "")),
        "short_summary": str(short_summary or "").strip() or None,
        "quote": quote or None,
        "theme": _sentiment_label(str(sentiment or "")),
        "needs_follow_up": _derive_needs_follow_up(recipient),
        "is_unhappy": _is_unhappy_respondent(recipient),
        "has_transcript": bool(str(result.get("transcript") or "").strip()),
        "has_analysis": bool(result.get("analysis_saved_at")),
        "final_additional_feedback": str(
            result.get("final_additional_feedback") or wa_conv.get("final_additional_feedback") or ""
        ).strip()
        or None,
        "final_feedback_yes_no": result.get("final_feedback_yes_no") or wa_conv.get("final_feedback_yes_no"),
        "wa_answers": wa_answers,
        "extracted_answers": extracted_answers,
        "open_feedback": open_feedback,
        "voice_responses": [row for row in open_feedback if row.get("answer_source") == "voice"],
        "primary_response_type": (
            "voice"
            if any(row.get("answer_source") == "voice" for row in open_feedback)
            else "text"
            if open_feedback
            else None
        ),
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

    wa_answers = sort_survey_answer_items(wa_conv.get("answers") or [])
    return {
        "id": recipient.id,
        "name": recipient.name,
        "phone": recipient.phone,
        "email": recipient.email,
        "initials": _initials(recipient.name),
        "avatar_class": _avatar_class(recipient.name),
        "status": recipient.status,
        "completed_at": (
            getattr(recipient, "completed_at", None).isoformat()
            if getattr(recipient, "completed_at", None)
            else str(result.get("completed_at") or "") or None
        ),
        "duration_seconds": duration_seconds,
        "duration_label": _format_duration(duration_seconds),
        "needs_follow_up": _derive_needs_follow_up(recipient),
        "is_unhappy": _is_unhappy_respondent(recipient),
        "rating_label": _rating_label_from_answers(wa_answers),
        "open_feedback": _collect_open_feedback(recipient, order_id=recipient.order_id),
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
    include_recommendations: bool = True,
) -> dict[str, Any]:
    config = _order_config(order)
    goal = str(config.get("goal") or "Survey").strip()
    from app.services.survey_wa_org_context_service import resolve_survey_organisation_name

    org_name = resolve_survey_organisation_name(db, org_id=str(order.org_id), config=config)
    report = _parse_report(order)
    recipients = ServiceOrderService.get_recipients(db, order.id)
    completed = [r for r in recipients if _recipient_is_complete_for_results(order, r)]
    total = len(recipients)
    completed_count = len(completed)
    response_rate = round((completed_count / total) * 100) if total else 0
    aggregates = build_answer_aggregates(recipients)
    wa_metrics = compute_wa_survey_metrics(recipients)
    voice_feedback: list[dict[str, Any]] = []
    for recipient in completed:
        for row in _collect_open_feedback(recipient, order_id=order.id):
            voice_feedback.append({"respondent_id": recipient.id, "respondent_initials": _initials(recipient.name), **row})
    sentiment_counts = wa_metrics.get("sentiment_counts") or {}
    top_issues = [
        f"{str(label).strip().title()} responses"
        for label, count in sorted(
            sentiment_counts.items(),
            key=lambda item: (-int(item[1] or 0), str(item[0])),
        )
        if int(count or 0) > 0
    ][:4]
    summary = {
        "total_recipients": total,
        "completed_count": completed_count,
        "response_rate_pct": response_rate,
        "average_satisfaction_10": wa_metrics.get("average_recommend_score"),
        "average_satisfaction_5": round(float(wa_metrics["average_recommend_score"]) / 2, 1)
        if wa_metrics.get("average_recommend_score") is not None
        else None,
        "average_recommend_score": wa_metrics.get("average_recommend_score"),
        "recommend_pct": wa_metrics.get("recommend_pct"),
        "nps_score": wa_metrics.get("nps_score"),
        "nps_label": wa_metrics.get("nps_label"),
        "nps_score_raw": wa_metrics.get("nps_score_raw"),
        "nps_promoters_pct": wa_metrics.get("nps_promoters_pct", 0),
        "nps_passives_pct": wa_metrics.get("nps_passives_pct", 0),
        "nps_detractors_pct": wa_metrics.get("nps_detractors_pct", 0),
        "nps_promoters": wa_metrics.get("nps_promoters", 0),
        "nps_passives": wa_metrics.get("nps_passives", 0),
        "nps_detractors": wa_metrics.get("nps_detractors", 0),
        "average_call_duration_seconds": None,
        "average_call_duration_label": "WhatsApp survey",
        "sentiment_counts": sentiment_counts,
        "top_issues": top_issues,
        "top_tags": [],
        "analyzed_count": completed_count,
        "pending_analysis": max(0, total - completed_count),
        "channel_note": report.get("note") or "WhatsApp survey",
        "voice_feedback_count": len([row for row in voice_feedback if row.get("answer_source") == "voice"]),
        "open_feedback_count": len(voice_feedback),
        "unhappy_count": _count_unhappy_respondents(recipients),
    }
    negative_feedback = _collect_negative_feedback_excerpts(recipients, order_id=order.id)
    recommendations: list[dict[str, str]] = []
    if include_recommendations:
        recommendations = ensure_action_recommendations(
            db,
            order,
            goal=goal,
            org_name=org_name,
            summary=summary,
            aggregates=aggregates,
            negative_feedback=negative_feedback,
        )
    return {
        "ok": True,
        "order": {
            "id": order.id,
            "title": order.title,
            "survey_name": order.title,
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
        "weekly_trend": build_org_survey_weekly_trend(db, order),
        "voice_feedback": voice_feedback,
        "respondents": _attach_ai_followup_to_respondents(
            db,
            [recipient_summary_row(r, goal=goal, order_id=order.id) for r in recipients]
            if include_respondents
            else [],
        ),
        "ai_follow_up_jobs": _ai_followup_jobs_payload(db, order.id) if include_respondents else [],
        "hubspot_sync_respondents": build_hubspot_sync_respondents(recipients, goal=goal, order_id=order.id),
        "recommendations": recommendations,
    }


def build_survey_results_payload(
    db: Session,
    order: ServiceOrder,
    *,
    include_respondents: bool = True,
    include_recommendations: bool = True,
) -> dict[str, Any]:
    if order.service_code != "survey":
        raise ValueError("Not a survey order")
    if is_whatsapp_survey_order(order):
        return build_whatsapp_survey_results_payload(
            db,
            order,
            include_respondents=include_respondents,
            include_recommendations=include_recommendations,
        )
    if not is_ai_call_survey_order(order):
        raise ValueError("Survey results are available for AI-call surveys only")

    config = _order_config(order)
    goal = str(config.get("goal") or "Survey").strip()
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "").strip()
    report = _parse_report(order)
    analysis = report.get("analysis") if isinstance(report.get("analysis"), dict) else {}

    recipients = ServiceOrderService.get_recipients(db, order.id)
    completed = [r for r in recipients if _recipient_is_complete_for_results(order, r)]

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
        "unhappy_count": _count_unhappy_respondents(recipients),
    }

    aggregates = build_answer_aggregates(recipients)
    negative_feedback = _collect_negative_feedback_excerpts(recipients, order_id=order.id)
    recommendations: list[dict[str, str]] = []
    if include_recommendations:
        recommendations = ensure_action_recommendations(
            db,
            order,
            goal=goal,
            org_name=org_name,
            summary=summary,
            aggregates=aggregates,
            negative_feedback=negative_feedback,
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
        "respondents": [
            recipient_summary_row(r, goal=goal, order_id=order.id) for r in recipients
        ]
        if include_respondents
        else [],
        "hubspot_sync_respondents": build_hubspot_sync_respondents(recipients, goal=goal, order_id=order.id),
        "recommendations": recommendations,
    }


class SurveyResultsService:
    @staticmethod
    def get_results(db: Session, order: ServiceOrder, *, anonymous: bool = False) -> dict[str, Any]:
        return build_survey_results_payload(db, order, include_respondents=not anonymous)

    @staticmethod
    def _export_payload(db: Session, order: ServiceOrder) -> tuple[dict[str, Any], bool]:
        config = _order_config(order)
        anonymous = bool(config.get("anonymous_responses"))
        payload = build_survey_results_payload(db, order, include_respondents=True)
        return payload, anonymous

    @staticmethod
    def export_results_csv(db: Session, order: ServiceOrder) -> str:
        payload, anonymous = SurveyResultsService._export_payload(db, order)
        return build_survey_results_csv(payload, anonymous=anonymous)

    @staticmethod
    def export_results_xlsx(db: Session, order: ServiceOrder) -> bytes:
        payload, anonymous = SurveyResultsService._export_payload(db, order)
        return build_survey_results_xlsx(payload, anonymous=anonymous)

    @staticmethod
    def export_results_pdf(db: Session, order: ServiceOrder) -> bytes:
        payload, _anonymous = SurveyResultsService._export_payload(db, order)
        return build_survey_results_pdf(payload)

    @staticmethod
    def get_recipient_detail(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> dict[str, Any]:
        if recipient.order_id != order.id:
            raise ValueError("Recipient does not belong to this order")
        if not is_ai_call_survey_order(order) and not is_whatsapp_survey_order(order):
            raise ValueError("Survey results are available for AI-call or WhatsApp surveys only")
        return {"ok": True, "recipient": recipient_detail_payload(recipient)}


def _survey_recipient_when(recipient: ServiceOrderRecipient) -> datetime | None:
    result = _recipient_result(recipient)
    for key in ("completed_at", "call_completed_at", "updated_at", "analysis_saved_at"):
        raw = result.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
    return recipient.created_at


def survey_home_feedback_snapshot(
    db: Session,
    *,
    org_id: str,
    limit_recent: int = 8,
    limit_unhappy: int = 6,
) -> dict[str, Any]:
    """Aggregate survey respondents for dashboard home (sentiment, follow-up, activity)."""
    from sqlalchemy import select

    from app.models.service_order import ServiceOrder
    from app.services.platform_catalog_service import PlatformCatalogService

    sentiment = {"excellent": 0, "good": 0, "poor": 0}
    unhappy: list[dict[str, Any]] = []
    recent_candidates: list[tuple[datetime, dict[str, Any]]] = []

    orders = list(
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.org_id == org_id,
                ServiceOrder.service_code == "survey",
            )
        ).scalars()
    )

    def _classify(recipient: ServiceOrderRecipient) -> str | None:
        result = _recipient_result(recipient)
        wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
        label = _rating_label_from_answers(wa_conv.get("answers") or [])
        if label == "Excellent":
            return "excellent"
        if label == "Good":
            return "good"
        if label == "Poor":
            return "poor"
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        sat = str(analysis.get("sentiment") or result.get("sentiment") or "").lower()
        if sat == "negative":
            return "poor"
        if sat == "positive":
            return "excellent"
        for item in analysis.get("extracted_answers") or result.get("extracted_answers") or []:
            if not isinstance(item, dict):
                continue
            ans = str(item.get("answer") or item.get("value") or "").lower()
            if ans == "excellent":
                return "excellent"
            if ans == "good":
                return "good"
            if ans == "bad":
                return "poor"
        if str(recipient.status or "").lower() == "completed":
            return "good"
        return None

    for order in orders:
        try:
            cfg = json.loads(order.config_json or "{}")
        except json.JSONDecodeError:
            cfg = {}
        channel = PlatformCatalogService.resolve_survey_channel(cfg)
        channel_label = "WhatsApp survey" if channel == "whatsapp" else "AI call survey"
        recipients = ServiceOrderService.get_recipients(db, order.id)
        for recipient in recipients:
            if str(recipient.status or "").lower() != "completed":
                continue
            bucket = _classify(recipient)
            if bucket:
                sentiment[bucket] += 1
            when_dt = _survey_recipient_when(recipient)
            when_iso = when_dt.isoformat() if when_dt else None
            result = _recipient_result(recipient)
            analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
            chip = (
                _rating_label_from_answers(
                    (result.get("wa_conversation") or {}).get("answers") if isinstance(result.get("wa_conversation"), dict) else []
                )
                or str(analysis.get("sentiment") or "Response").title()
            )
            tone = "bad" if _is_unhappy_respondent(recipient) else "ok" if bucket in {"excellent", "good"} else "info"
            if _derive_needs_follow_up(recipient) or _is_unhappy_respondent(recipient):
                issue = ""
                for item in analysis.get("issues") or result.get("issues") or []:
                    issue = str(item).strip()
                    if issue:
                        break
                if not issue:
                    issue = "Negative survey response — follow up required"
                unhappy.append(
                    {
                        "id": f"{order.id}:{recipient.id}",
                        "reason": issue[:120],
                        "branch": order.title or channel_label,
                        "when": when_iso,
                    }
                )
            recent_candidates.append(
                (
                    when_dt or datetime.utcnow(),
                    {
                        "svc": "surveys",
                        "who": recipient.name or "Member",
                        "what": f"completed {channel_label.lower()}",
                        "chip": chip[:24],
                        "tone": tone,
                        "when": when_iso,
                    },
                )
            )

    unhappy.sort(key=lambda row: row.get("when") or "", reverse=True)
    recent_candidates.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "qr_scans_today": 0,
        "total_scans": sum(sentiment.values()),
        "sentiment": sentiment,
        "unhappy": unhappy[:limit_unhappy],
        "recent": [item for _, item in recent_candidates[:limit_recent]],
    }
