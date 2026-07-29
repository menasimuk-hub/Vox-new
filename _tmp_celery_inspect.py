import json
from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.database import get_sessionmaker
from app.workers.celery_app import celery_app

db = get_sessionmaker()()
since = datetime.utcnow() - timedelta(days=14)
recs = db.execute(
    text(
        """
        SELECT r.id, r.phone, r.status, r.result_json
        FROM service_order_recipients r
        JOIN service_orders o ON o.id = r.order_id
        WHERE o.service_code = 'survey'
          AND r.result_json IS NOT NULL
          AND r.created_at >= :since
        ORDER BY r.created_at DESC
        LIMIT 120
        """
    ),
    {"since": since},
).mappings().all()
for rec in recs:
    data = json.loads(rec["result_json"] or "{}")
    for a in (data.get("wa_conversation") or {}).get("answers") or []:
        if not isinstance(a, dict):
            continue
        stt = str(a.get("transcription_status") or "")
        if stt in {"pending", "failed", "retrying", "transcribing"}:
            print(
                "PENDING_STT",
                rec["id"],
                rec["phone"],
                rec["status"],
                stt,
                a.get("voice_note_job_id"),
                a.get("step_role"),
            )

i = celery_app.control.inspect(timeout=5)
reg = i.registered() or {}
print("nodes", list(reg.keys()))
for node, tasks in reg.items():
    print(node, "HAS_feedback.transcribe", "feedback.transcribe_voice_note" in (tasks or []))
    hits = [t for t in (tasks or []) if any(x in t for x in ["feedback", "voice", "translate", "retry_deferred"])]
    print("hits", hits)
db.close()
