"""Aggregate Customer Feedback responses for the results dashboard."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FeedbackLocation,
    FeedbackResponse,
    FeedbackSession,
    FeedbackSurveyType,
    FeedbackWaTemplate,
)
from app.services.customer_feedback.feedback_answer_service import POOR_ANSWERS
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES

EXCELLENT_ANSWERS = frozenset({"excellent", "great", "very good", "amazing", "outstanding"})
GOOD_ANSWERS = frozenset({"good", "fair", "okay", "ok", "average"})
YES_ANSWERS = frozenset({"yes", "yes please", "yes, please", "yes definitely", "yes, definitely"})
NO_ANSWERS = frozenset({"no", "no thanks", "no thank you", "no, thanks"})
OPEN_STEP_ROLES = frozenset({"tell_us_more", "final_feedback_text", "reason"})


def _norm(answer: str | None) -> str:
    return str(answer or "").strip().lower()


def _template_lookup(
    templates: dict[tuple[str, str], FeedbackWaTemplate],
) -> dict[tuple[str, str], FeedbackWaTemplate]:
    return templates


def load_template_index(
    db: Session,
    *,
    survey_type_ids: set[str],
) -> dict[tuple[str, str], FeedbackWaTemplate]:
    if not survey_type_ids:
        return {}
    rows = (
        db.query(FeedbackWaTemplate)
        .filter(FeedbackWaTemplate.survey_type_id.in_(list(survey_type_ids)))
        .filter(FeedbackWaTemplate.is_active.is_(True))
        .all()
    )
    by_key: dict[tuple[str, str], list[FeedbackWaTemplate]] = defaultdict(list)
    for row in rows:
        if row.survey_type_id and row.template_key:
            by_key[(str(row.survey_type_id), str(row.template_key))].append(row)

    out: dict[tuple[str, str], FeedbackWaTemplate] = {}
    for key, group in by_key.items():
        en = next((t for t in group if str(t.language or "") in ENGLISH_TEMPLATE_LANGUAGES), None)
        out[key] = en or group[0]
    return out


def template_meta(
    templates: dict[tuple[str, str], FeedbackWaTemplate],
    *,
    survey_type_id: str,
    question_key: str,
) -> tuple[str, str | None]:
    tpl = templates.get((survey_type_id, question_key))
    if tpl is None:
        label = question_key.replace("-", " ").replace("_", " ").strip().title()
        return label, None
    body = str(tpl.body_text or "").strip()
    label = body.split("{{")[0].strip() if body else question_key
    if len(label) > 120:
        label = label[:117] + "..."
    return label or question_key, tpl.step_role


def classify_pge(answer: str) -> str | None:
    a = _norm(answer)
    if not a:
        return None
    if a in EXCELLENT_ANSWERS or "excellent" in a:
        return "excellent"
    if a in GOOD_ANSWERS or a == "good":
        return "good"
    if a in POOR_ANSWERS or "poor" in a:
        return "poor"
    return None


def classify_yn(answer: str) -> str | None:
    a = _norm(answer)
    if a in YES_ANSWERS:
        return "yes"
    if a in NO_ANSWERS:
        return "no"
    return None


def is_open_text_step(step_role: str | None, answer: str, buttons: list[str] | None = None) -> bool:
    role = _norm(step_role)
    if role in OPEN_STEP_ROLES:
        return True
    if buttons:
        return False
    a = str(answer or "").strip()
    return len(a) > 24 and classify_pge(a) is None and classify_yn(a) is None


def _session_sentiment(answers: list[dict[str, Any]]) -> str:
    poor = 0
    positive = 0
    for item in answers:
        text = _norm(item.get("answer"))
        pge = classify_pge(text)
        yn = classify_yn(text)
        if pge == "poor" or yn == "no":
            poor += 1
        elif pge in {"excellent", "good"} or yn == "yes":
            positive += 1
    if poor >= 2 or (poor >= 1 and positive == 0):
        return "unhappy"
    if positive >= 2 and poor == 0:
        return "happy"
    return "neutral"


def _is_unhappy(answers: list[dict[str, Any]]) -> bool:
    poor = 0
    for item in answers:
        text = _norm(item.get("answer"))
        if classify_pge(text) == "poor" or classify_yn(text) == "no":
            poor += 1
    return poor >= 2 or (
        poor >= 1
        and not any(classify_pge(_norm(a.get("answer"))) == "excellent" for a in answers)
    )


def build_aggregates(
    responses: list[FeedbackResponse],
    templates: dict[tuple[str, str], FeedbackWaTemplate],
) -> list[dict[str, Any]]:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    meta: dict[str, dict[str, Any]] = {}

    for row in responses:
        answer = str(row.answer_text_en or row.answer_text or "").strip()
        if not answer:
            continue
        question_key = str(row.question_key or "")
        survey_type_id = str(row.survey_type_id or "")
        question, step_role = template_meta(templates, survey_type_id=survey_type_id, question_key=question_key)
        tpl = templates.get((survey_type_id, question_key))
        buttons = None
        if tpl and tpl.buttons_json:
            try:
                import json

                parsed = json.loads(tpl.buttons_json)
                buttons = parsed if isinstance(parsed, list) else None
            except json.JSONDecodeError:
                buttons = None

        bucket_key = f"{survey_type_id}::{question_key}"
        if step_role in {"yes_no", "marketing_opt_in"} or classify_yn(answer):
            label = classify_yn(answer) or answer.lower()
            buckets[bucket_key][label] += 1
            meta[bucket_key] = {"question": question, "step_role": step_role or "yes_no", "scale": "YN"}
        elif step_role == "rating" or classify_pge(answer):
            label = classify_pge(answer) or answer.lower()
            buckets[bucket_key][label] += 1
            meta[bucket_key] = {"question": question, "step_role": step_role or "rating", "scale": "PGE"}
        elif is_open_text_step(step_role, answer, buttons):
            buckets[bucket_key][answer[:200]] += 1
            meta[bucket_key] = {"question": question, "step_role": step_role or "open", "scale": "OPEN"}
        else:
            buckets[bucket_key][answer[:120]] += 1
            meta[bucket_key] = {"question": question, "step_role": step_role, "scale": "choice"}

    aggregates: list[dict[str, Any]] = []
    for bucket_key, counter in buckets.items():
        info = meta.get(bucket_key) or {}
        total = sum(counter.values())
        scale = info.get("scale") or "choice"
        block: dict[str, Any] = {
            "question_key": bucket_key.split("::", 1)[-1],
            "question": info.get("question") or bucket_key,
            "step_role": info.get("step_role"),
            "total": total,
            "visualization": "choice",
            "responses": [{"answer": k, "count": v} for k, v in counter.most_common(12)],
        }
        if scale == "PGE":
            excellent = sum(v for k, v in counter.items() if classify_pge(k) == "excellent")
            good = sum(v for k, v in counter.items() if classify_pge(k) == "good")
            poor = sum(v for k, v in counter.items() if classify_pge(k) == "poor")
            base = excellent + good + poor or total or 1
            block["visualization"] = "sentiment_breakdown"
            block["breakdown"] = [
                {"label": "Excellent", "key": "excellent", "count": excellent, "pct": round(excellent / base * 100)},
                {"label": "Good", "key": "good", "count": good, "pct": round(good / base * 100)},
                {"label": "Poor", "key": "poor", "count": poor, "pct": round(poor / base * 100)},
            ]
        elif scale == "YN":
            yes = sum(v for k, v in counter.items() if classify_yn(k) == "yes")
            no = sum(v for k, v in counter.items() if classify_yn(k) == "no")
            base = yes + no or total or 1
            block["visualization"] = "sentiment_breakdown"
            block["breakdown"] = [
                {"label": "Yes", "key": "yes", "count": yes, "pct": round(yes / base * 100)},
                {"label": "No", "key": "no", "count": no, "pct": round(no / base * 100)},
            ]
        aggregates.append(block)

    aggregates.sort(key=lambda r: (-int(r.get("total") or 0), str(r.get("question") or "")))
    return aggregates


def build_weekly_trend(
    sessions: list[FeedbackSession],
    responses_by_session: dict[str, list[FeedbackResponse]],
) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    weeks: list[dict[str, Any]] = []
    for offset in range(7, -1, -1):
        week_end = now - timedelta(days=offset * 7)
        week_start = week_end - timedelta(days=7)
        label = week_end.strftime("W%W")
        completed_in_week = [
            s
            for s in sessions
            if str(s.status) == "completed"
            and s.completed_at
            and week_start <= s.completed_at < week_end
        ]
        positive = 0
        rated = 0
        recommend_yes = 0
        recommend_total = 0
        for sess in completed_in_week:
            for resp in responses_by_session.get(sess.id, []):
                text = _norm(resp.answer_text_en or resp.answer_text)
                pge = classify_pge(text)
                if pge:
                    rated += 1
                    if pge in {"excellent", "good"}:
                        positive += 1
                yn = classify_yn(text)
                qk = _norm(resp.question_key)
                if yn or "recommend" in qk:
                    if yn:
                        recommend_total += 1
                        if yn == "yes":
                            recommend_yes += 1
        satisfaction = round(positive / rated * 100) if rated else None
        recommend_pct = round(recommend_yes / recommend_total * 100) if recommend_total else None
        weeks.append(
            {
                "week": label,
                "satisfaction": satisfaction,
                "positive": recommend_pct if recommend_pct is not None else satisfaction,
                "responses": len(completed_in_week),
            }
        )
    return weeks


def build_respondents(
    sessions: list[FeedbackSession],
    responses_by_session: dict[str, list[FeedbackResponse]],
    templates: dict[tuple[str, str], FeedbackWaTemplate],
    locations: dict[str, FeedbackLocation],
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    def _session_sort_key(sess: FeedbackSession) -> tuple[int, float]:
        dt = sess.completed_at or sess.started_at
        ts = -dt.timestamp() if dt else 0.0
        priority = 0 if str(sess.status) == "completed" else 1
        return (priority, ts)

    with_responses = [s for s in sessions if responses_by_session.get(s.id)]
    with_responses.sort(key=_session_sort_key)
    rows: list[dict[str, Any]] = []
    for sess in with_responses[:limit]:
        answers_raw = responses_by_session.get(sess.id, [])
        if not answers_raw:
            continue
        answers: list[dict[str, Any]] = []
        quote = ""
        for resp in sorted(answers_raw, key=lambda r: r.step_order):
            answer = str(resp.answer_text_en or resp.answer_text or "").strip()
            question, step_role = template_meta(
                templates,
                survey_type_id=str(resp.survey_type_id),
                question_key=str(resp.question_key),
            )
            answers.append(
                {
                    "question": question,
                    "answer": answer,
                    "step_role": step_role,
                    "answer_source": getattr(resp, "answer_source", None) or "text",
                }
            )
            if not quote and step_role in OPEN_STEP_ROLES and answer:
                quote = answer[:200]
        loc = locations.get(sess.location_id)
        sentiment = _session_sentiment(answers)
        unhappy = _is_unhappy(answers)
        rows.append(
            {
                "id": sess.id,
                "phone": sess.visitor_phone,
                "location_id": sess.location_id,
                "location_name": loc.name if loc else None,
                "completed_at": sess.completed_at.isoformat() if sess.completed_at else None,
                "started_at": sess.started_at.isoformat() if sess.started_at else None,
                "session_status": str(sess.status or ""),
                "is_unhappy": unhappy,
                "flagged": unhappy,
                "sentiment_label": sentiment,
                "answers": answers,
                "quote": quote or None,
            }
        )
    return rows


def build_open_comments(
    responses: list[FeedbackResponse],
    templates: dict[tuple[str, str], FeedbackWaTemplate],
    *,
    themes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    theme_labels = [str(t.get("label") or "") for t in (themes or []) if t.get("label")]
    rows: list[dict[str, Any]] = []
    for resp in responses:
        answer = str(resp.answer_text_en or resp.answer_text or "").strip()
        if not answer:
            continue
        question, step_role = template_meta(
            templates,
            survey_type_id=str(resp.survey_type_id),
            question_key=str(resp.question_key),
        )
        source = getattr(resp, "answer_source", None) or "text"
        tpl = templates.get((str(resp.survey_type_id), str(resp.question_key)))
        buttons = None
        if tpl and tpl.buttons_json:
            try:
                import json

                parsed = json.loads(tpl.buttons_json)
                buttons = parsed if isinstance(parsed, list) else None
            except json.JSONDecodeError:
                buttons = None
        if source != "voice" and not is_open_text_step(step_role, answer, buttons):
            continue
        theme = ""
        lower = answer.lower()
        for label in theme_labels:
            if label.lower() in lower or any(w in lower for w in label.lower().split()[:2]):
                theme = label
                break
        sentiment = "neutral"
        if classify_pge(answer) == "poor" or classify_yn(answer) == "no":
            sentiment = "negative"
        elif classify_pge(answer) in {"excellent", "good"} or classify_yn(answer) == "yes":
            sentiment = "positive"
        rows.append(
            {
                "id": resp.id,
                "session_id": resp.session_id,
                "text": answer,
                "original_text": resp.original_text,
                "answer_source": source,
                "theme": theme or None,
                "sentiment": sentiment,
                "created_at": resp.created_at.isoformat() if resp.created_at else None,
            }
        )
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows[:120]


def compute_summary(
    *,
    sessions: list[FeedbackSession],
    responses: list[FeedbackResponse],
    locations: list[FeedbackLocation],
    respondents: list[dict[str, Any]],
    location_id: str | None,
) -> dict[str, Any]:
    completed = sum(1 for s in sessions if str(s.status) == "completed")
    scans = sum(int(loc.scan_count or 0) for loc in locations)
    if location_id:
        scans = next((int(loc.scan_count or 0) for loc in locations if loc.id == location_id), scans)

    positive = 0
    rated = 0
    recommend_yes = 0
    recommend_total = 0
    for resp in responses:
        text = _norm(resp.answer_text_en or resp.answer_text)
        pge = classify_pge(text)
        if pge:
            rated += 1
            if pge in {"excellent", "good"}:
                positive += 1
        qk = _norm(resp.question_key)
        if "recommend" in qk or classify_yn(text):
            yn = classify_yn(text)
            if yn:
                recommend_total += 1
                if yn == "yes":
                    recommend_yes += 1

    unhappy = sum(1 for r in respondents if r.get("is_unhappy"))
    sentiment_counts = {"unhappy": 0, "neutral": 0, "happy": 0}
    for r in respondents:
        label = str(r.get("sentiment_label") or "neutral")
        if label in sentiment_counts:
            sentiment_counts[label] += 1

    satisfaction_pct = round(positive / rated * 100) if rated else None
    recommend_pct = round(recommend_yes / recommend_total * 100) if recommend_total else None
    completion_rate_pct = round(completed / scans * 100) if scans else None

    return {
        "sessions": len(sessions),
        "completed_sessions": completed,
        "responses": len(responses),
        "total_scans": scans,
        "satisfaction_pct": satisfaction_pct,
        "recommend_pct": recommend_pct,
        "completion_rate_pct": min(completion_rate_pct, 100) if completion_rate_pct is not None else None,
        "sentiment_counts": sentiment_counts,
        "unhappy_count": unhappy,
    }


def survey_types_for_locations(
    db: Session,
    locations: list[FeedbackLocation],
) -> list[dict[str, Any]]:
    ids: set[str] = set()
    for loc in locations:
        ids.add(str(loc.survey_type_id))
        if loc.selected_survey_type_ids_json:
            try:
                import json

                parsed = json.loads(loc.selected_survey_type_ids_json)
                if isinstance(parsed, list):
                    ids.update(str(x) for x in parsed if x)
            except json.JSONDecodeError:
                pass
    if not ids:
        return []
    types = db.query(FeedbackSurveyType).filter(FeedbackSurveyType.id.in_(list(ids))).all()
    return [{"id": t.id, "name": t.name, "slug": t.slug} for t in types]
