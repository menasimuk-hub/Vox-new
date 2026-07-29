"""Finish WA survey recipient bilingual scan (order_id FK)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.database import get_sessionmaker


def main() -> None:
    db = get_sessionmaker()()
    since = datetime.utcnow() - timedelta(days=14)
    print("UTC_NOW", datetime.utcnow().isoformat())

    recs = db.execute(
        text(
            """
            SELECT r.id, r.phone, r.status, r.result_json
            FROM service_order_recipients r
            JOIN service_orders o ON o.id = r.order_id
            WHERE o.service_code = 'survey'
              AND r.status IN ('completed','in_progress','responded','answered')
              AND r.result_json IS NOT NULL
              AND r.created_at >= :since
            ORDER BY r.created_at DESC
            LIMIT 120
            """
        ),
        {"since": since},
    ).mappings().all()

    stats = {
        "sampled": 0,
        "openish_answers": 0,
        "with_translated_text": 0,
        "arabic_orig": 0,
        "arabic_missing_en": 0,
        "voice_pending_stt": 0,
        "tr_pending_failed": 0,
        "answer_still_arabic_with_en": 0,
    }
    examples = []
    for rec in recs:
        try:
            data = json.loads(rec["result_json"] or "{}")
        except Exception:
            continue
        stats["sampled"] += 1
        answers = (data.get("wa_conversation") or {}).get("answers") or data.get("answers") or []
        if not isinstance(answers, list):
            continue
        for a in answers:
            if not isinstance(a, dict):
                continue
            orig = str(a.get("original_text") or a.get("answer_text") or a.get("answer") or "")
            en = str(a.get("translated_text") or "")
            display = str(a.get("answer") or a.get("answer_text") or "")
            tr = str(a.get("translation_status") or "")
            stt = str(a.get("transcription_status") or "")
            role = str(a.get("step_role") or a.get("role") or "")
            src = str(a.get("answer_source") or "")
            is_open = (
                "tell" in role
                or "final_feedback" in role
                or "open" in role
                or src == "voice"
                or bool(a.get("voice_note_job_id"))
                or len(orig) > 40
            )
            if not is_open:
                continue
            stats["openish_answers"] += 1
            if en:
                stats["with_translated_text"] += 1
            if _has_arabic(orig):
                stats["arabic_orig"] += 1
                if not en or en == orig:
                    stats["arabic_missing_en"] += 1
                    if len(examples) < 12:
                        examples.append({"kind": "arabic_missing_en", "rid": rec["id"], "phone": rec["phone"], "a": _slim(a)})
                elif _has_arabic(display) and en and not _has_arabic(en):
                    stats["answer_still_arabic_with_en"] += 1
                    if len(examples) < 12:
                        examples.append({"kind": "display_arabic_en_exists", "rid": rec["id"], "phone": rec["phone"], "a": _slim(a)})
            if stt in {"pending", "failed", "retrying", "transcribing"}:
                stats["voice_pending_stt"] += 1
            if tr in {"pending", "failed"}:
                stats["tr_pending_failed"] += 1
                if len(examples) < 12:
                    examples.append({"kind": "tr_" + tr, "rid": rec["id"], "phone": rec["phone"], "a": _slim(a)})

    print("STATS", stats)
    for ex in examples:
        print(ex)

    print("\n=== DEFERRED HOURS ===")
    deferred = db.execute(
        text(
            """
            SELECT r.status, COUNT(*) n
            FROM service_order_recipients r
            JOIN service_orders o ON o.id = r.order_id
            WHERE o.service_code='survey'
              AND r.result_json LIKE '%outside_wa_survey_hours%'
            GROUP BY 1
            """
        )
    ).mappings().all()
    print([dict(r) for r in deferred])

    print("\n=== CAMPAIGN VB-CMP-41904A02 ===")
    camp = db.execute(
        text(
            """
            SELECT o.id, o.campaign_id, o.status, r.id rid, r.phone, r.status rstatus
            FROM service_orders o
            JOIN service_order_recipients r ON r.order_id=o.id
            WHERE o.campaign_id='VB-CMP-41904A02'
            """
        )
    ).mappings().all()
    for r in camp:
        print(dict(r))
        full = db.execute(
            text("SELECT result_json FROM service_order_recipients WHERE id=:id"),
            {"id": r["rid"]},
        ).scalar()
        try:
            data = json.loads(full or "{}")
        except Exception:
            continue
        answers = (data.get("wa_conversation") or {}).get("answers") or []
        for a in answers:
            if not isinstance(a, dict):
                continue
            if (
                a.get("voice_note_job_id")
                or a.get("original_text")
                or a.get("translated_text")
                or "tell" in str(a.get("step_role") or "")
                or "final_feedback" in str(a.get("step_role") or "")
            ):
                print("  ans", _slim(a))

    print("\n=== CF SESSION CHANNEL HINTS ===")
    rows = db.execute(
        text(
            """
            SELECT
              status,
              SUM(CASE WHEN session_state_json LIKE '%\"channel\":\"web\"%' OR session_state_json LIKE '%web_survey%' THEN 1 ELSE 0 END) webish,
              SUM(CASE WHEN visitor_phone IS NOT NULL AND visitor_phone <> '' THEN 1 ELSE 0 END) with_phone,
              COUNT(*) n
            FROM feedback_sessions
            WHERE started_at >= :since
            GROUP BY status
            """
        ),
        {"since": since},
    ).mappings().all()
    for r in rows:
        print(dict(r))

    # Smoke: enqueue path import + create pending helpers
    print("\n=== CODE PATH SMOKE ===")
    from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService
    from app.services.customer_feedback.web_survey_service import FeedbackWebSurveyService
    from app.services.customer_feedback import feedback_voice_note_service as fvn

    assert hasattr(FeedbackWhatsappService, "_handle_voice_inbound_async")
    assert hasattr(FeedbackWebSurveyService, "submit_voice")
    assert callable(fvn.enqueue_feedback_voice_job)
    assert callable(fvn.process_voice_job)
    print("CF async voice handlers present")

    from app.services.survey_wa_translation_service import SurveyWaTranslationService

    merged = SurveyWaTranslationService.merge_preserved_translations(
        {
            "wa_conversation": {
                "answers": [
                    {
                        "voice_note_job_id": "job-a",
                        "answer": "Hello flowers",
                        "original_text": "الورود",
                        "translated_text": "Hello flowers",
                        "translation_status": "completed",
                    }
                ]
            }
        },
        {
            "wa_conversation": {
                "answers": [
                    {"voice_note_job_id": "job-a", "answer": "الورود", "answer_text": "الورود"}
                ]
            }
        },
    )
    a0 = merged["wa_conversation"]["answers"][0]
    print("merge_smoke", a0.get("answer"), a0.get("translated_text"), a0.get("translation_status"))
    assert a0["answer"] == "Hello flowers"

    db.close()
    print("DONE")


def _has_arabic(s: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in s)


def _slim(a: dict) -> dict:
    keys = (
        "answer",
        "answer_text",
        "original_text",
        "translated_text",
        "translation_status",
        "transcription_status",
        "voice_note_job_id",
        "step_role",
        "answer_source",
    )
    out = {k: a.get(k) for k in keys if a.get(k) is not None}
    for k, v in list(out.items()):
        if isinstance(v, str) and len(v) > 90:
            out[k] = v[:90] + "…"
    return out


if __name__ == "__main__":
    main()
