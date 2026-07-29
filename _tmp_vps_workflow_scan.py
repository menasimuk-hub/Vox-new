"""Production scan: WA Survey + CF bilingual / voice workflow health."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import inspect, text

from app.core.database import get_sessionmaker
from app.workers.celery_app import celery_app

import app.workers.feedback_voice_note_tasks  # noqa: F401


def main() -> None:
    db = get_sessionmaker()()
    insp = inspect(db.bind)
    tables = set(insp.get_table_names())
    since = datetime.utcnow() - timedelta(days=14)
    print("UTC_NOW", datetime.utcnow().isoformat())

    print("\n=== CELERY TASKS (import) ===")
    for name in (
        "feedback.transcribe_voice_note",
        "survey.transcribe_voice_note",
        "survey.translate_wa_answer",
        "survey.retry_deferred_wa_starts",
    ):
        print(f"  {name}: {name in celery_app.tasks}")

    print("\n=== CF RESPONSE BILINGUAL (14d) ===")
    rows = db.execute(
        text(
            """
            SELECT
              COALESCE(answer_source,'text') AS src,
              COALESCE(transcription_status,'(null)') AS stt,
              COALESCE(translation_status,'(null)') AS tr,
              COUNT(*) AS n,
              SUM(CASE WHEN original_text IS NOT NULL AND TRIM(original_text)<>'' THEN 1 ELSE 0 END) AS has_orig,
              SUM(CASE WHEN answer_text_en IS NOT NULL AND TRIM(answer_text_en)<>'' THEN 1 ELSE 0 END) AS has_en,
              SUM(CASE WHEN original_text IS NOT NULL AND answer_text_en IS NOT NULL
                        AND TRIM(original_text)<>'' AND TRIM(answer_text_en)<>''
                        AND original_text <> answer_text_en THEN 1 ELSE 0 END) AS bilingual_diff
            FROM feedback_responses
            WHERE created_at >= :since
            GROUP BY 1,2,3
            ORDER BY n DESC
            """
        ),
        {"since": since},
    ).mappings().all()
    for r in rows[:40]:
        print(dict(r))

    print("\n=== CF ARABIC WITHOUT DISTINCT EN (14d open/voice) ===")
    ar_rows = db.execute(
        text(
            """
            SELECT id, question_key, answer_source, translation_status,
                   LEFT(original_text,100) orig,
                   LEFT(COALESCE(answer_text_en, answer_text),100) en,
                   created_at
            FROM feedback_responses
            WHERE created_at >= :since
              AND (
                question_key LIKE '%tell_us_more%'
                OR question_key LIKE '%low_reason%'
                OR question_key = 'open_question'
                OR COALESCE(answer_source,'') = 'voice'
              )
              AND original_text IS NOT NULL
              AND original_text REGEXP '[؀-ۿ]'
              AND (
                answer_text_en IS NULL
                OR TRIM(answer_text_en)=''
                OR answer_text_en = original_text
              )
            ORDER BY created_at DESC
            LIMIT 30
            """
        ),
        {"since": since},
    ).mappings().all()
    print("count", len(ar_rows))
    for r in ar_rows:
        print(dict(r))

    if "feedback_voice_note_jobs" in tables:
        print("\n=== CF VOICE JOBS STATUS ===")
        jobs = db.execute(
            text(
                """
                SELECT transcription_status, COALESCE(translation_status,'(null)') tr, COUNT(*) n
                FROM feedback_voice_note_jobs
                GROUP BY 1,2
                """
            )
        ).mappings().all()
        print("groups", [dict(r) for r in jobs] or "empty_table")

    print("\n=== SURVEY VOICE JOBS (14d) ===")
    sv = db.execute(
        text(
            """
            SELECT transcription_status,
                   COALESCE(translation_status,'(null)') AS tr,
                   COUNT(*) n
            FROM survey_voice_note_jobs
            WHERE created_at >= :since
            GROUP BY 1,2
            ORDER BY n DESC
            """
        ),
        {"since": since},
    ).mappings().all()
    for r in sv:
        print(dict(r))

    print("\n=== SURVEY VOICE COMPLETED WITH ARABIC + NO EN ON JOB (14d) ===")
    ar_jobs = db.execute(
        text(
            """
            SELECT id, recipient_id, transcription_status, translation_status,
                   LEFT(COALESCE(original_text, answer_text),80) orig,
                   LEFT(COALESCE(translated_text,''),80) en,
                   created_at
            FROM survey_voice_note_jobs
            WHERE created_at >= :since
              AND transcription_status='completed'
              AND (
                COALESCE(original_text, answer_text) REGEXP '[؀-ۿ]'
              )
              AND (translated_text IS NULL OR TRIM(translated_text)='' OR translated_text = COALESCE(original_text, answer_text))
            ORDER BY created_at DESC
            LIMIT 25
            """
        ),
        {"since": since},
    ).mappings().all()
    print("count", len(ar_jobs))
    for r in ar_jobs:
        print(dict(r))

    # recipient columns
    rcols = [c["name"] for c in insp.get_columns("service_order_recipients")]
    time_col = "completed_at" if "completed_at" in rcols else ("created_at" if "created_at" in rcols else None)
    print("\n=== recipient time col", time_col, "cols sample", rcols[:20])

    print("\n=== WA SURVEY OPEN ANSWERS SAMPLE (14d) ===")
    order_sql = f"ORDER BY r.{time_col} DESC" if time_col else "ORDER BY r.id DESC"
    time_filter = f"AND r.{time_col} >= :since" if time_col else ""
    recs = db.execute(
        text(
            f"""
            SELECT r.id, r.phone, r.status, r.result_json
            FROM service_order_recipients r
            JOIN service_orders o ON o.id = r.service_order_id
            WHERE o.service_code = 'survey'
              AND r.status IN ('completed','in_progress','responded','answered')
              AND r.result_json IS NOT NULL
              {time_filter}
            {order_sql}
            LIMIT 100
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
                    if len(examples) < 15:
                        examples.append(
                            {
                                "kind": "arabic_missing_en",
                                "rid": rec["id"],
                                "phone": rec["phone"],
                                "status": rec["status"],
                                "a": _slim(a),
                            }
                        )
            if stt in {"pending", "failed", "retrying", "transcribing"}:
                stats["voice_pending_stt"] += 1
                if len(examples) < 15:
                    examples.append({"kind": "stt", "rid": rec["id"], "phone": rec["phone"], "a": _slim(a)})
            if tr in {"pending", "failed"}:
                stats["tr_pending_failed"] += 1
                if len(examples) < 15:
                    examples.append({"kind": "tr", "rid": rec["id"], "phone": rec["phone"], "a": _slim(a)})

    print(stats)
    for ex in examples:
        print(ex)

    print("\n=== DEFERRED / HOURS BLOCKS ===")
    # Search result_json / error fields
    err_col = "error_message" if "error_message" in rcols else None
    if err_col:
        deferred = db.execute(
            text(
                f"""
                SELECT r.status, COUNT(*) n
                FROM service_order_recipients r
                JOIN service_orders o ON o.id = r.service_order_id
                WHERE o.service_code='survey'
                  AND (r.{err_col} LIKE '%outside_wa_survey_hours%' OR r.result_json LIKE '%outside_wa_survey_hours%')
                GROUP BY 1
                """
            )
        ).mappings().all()
        print("by_status", [dict(r) for r in deferred])
    else:
        deferred = db.execute(
            text(
                """
                SELECT r.status, COUNT(*) n
                FROM service_order_recipients r
                JOIN service_orders o ON o.id = r.service_order_id
                WHERE o.service_code='survey'
                  AND r.result_json LIKE '%outside_wa_survey_hours%'
                GROUP BY 1
                """
            )
        ).mappings().all()
        print("by_status", [dict(r) for r in deferred])

    print("\n=== CF SESSIONS 14d ===")
    sess = db.execute(
        text(
            """
            SELECT status, COUNT(*) n
            FROM feedback_sessions
            WHERE started_at >= :since
            GROUP BY 1
            """
        ),
        {"since": since},
    ).mappings().all()
    for r in sess:
        print(dict(r))

    print("\n=== CF VOICE RESPONSES 14d ===")
    voice_cf = db.execute(
        text(
            """
            SELECT id, question_key, transcription_status, translation_status,
                   LEFT(original_text,80) orig, LEFT(answer_text_en,80) en, created_at
            FROM feedback_responses
            WHERE answer_source='voice' AND created_at >= :since
            ORDER BY created_at DESC
            LIMIT 20
            """
        ),
        {"since": since},
    ).mappings().all()
    print("count", len(voice_cf))
    for r in voice_cf:
        print(dict(r))

    print("\n=== CAMPAIGN 41904A02 SPOT CHECK ===")
    camp = db.execute(
        text(
            """
            SELECT o.id, o.campaign_id, o.status, r.id rid, r.phone, r.status rstatus
            FROM service_orders o
            JOIN service_order_recipients r ON r.service_order_id=o.id
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
            if a.get("voice_note_job_id") or a.get("original_text") or a.get("translated_text") or "tell" in str(a.get("step_role") or ""):
                print("  ans", _slim(a))

    db.close()
    print("\nDONE")


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
