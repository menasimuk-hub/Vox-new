#!/usr/bin/env python3
"""Re-queue STT + English translation for a WA survey campaign's open answers.

Usage on VPS:
  cd /www/voxbulk/voxbulk-api
  PYTHONPATH=. .venv/bin/python scripts/retranslate_wa_campaign_answers.py VB-CMP-9C69115D
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text

from app.core.database import get_sessionmaker
from app.services.survey_wa_translation_service import SurveyWaTranslationService
from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService


def main() -> int:
    campaign = (sys.argv[1] if len(sys.argv) > 1 else "VB-CMP-9C69115D").strip()
    db = get_sessionmaker()()
    order = db.execute(
        text("SELECT id FROM service_orders WHERE campaign_id=:c OR id=:c LIMIT 1"),
        {"c": campaign},
    ).mappings().first()
    if not order:
        print("ORDER_NOT_FOUND", campaign)
        return 1
    oid = order["id"]
    print("ORDER", oid)

    # Re-run Whisper (large-v3) for all voice notes on this order.
    # Transcription completion re-enqueues translation automatically.
    jobs = db.execute(
        text(
            "SELECT id, transcription_status FROM survey_voice_note_jobs WHERE order_id=:o ORDER BY created_at"
        ),
        {"o": oid},
    ).mappings().all()
    voice_retried = []
    for job in jobs:
        try:
            SurveyWaVoiceNoteService.retry_job(db, str(job["id"]))
            voice_retried.append(str(job["id"]))
        except Exception as exc:
            print("VOICE_RETRY_FAIL", job["id"], exc)
    print("VOICE_RETRY", voice_retried)

    recs = db.execute(
        text("SELECT id, name, phone, result_json FROM service_order_recipients WHERE order_id=:o"),
        {"o": oid},
    ).mappings().all()
    for rec in recs:
        try:
            payload = json.loads(rec["result_json"] or "{}")
        except Exception:
            payload = {}
        answers = ((payload.get("wa_conversation") or {}).get("answers") or []) if isinstance(payload, dict) else []
        # Text open answers only — voice will translate after STT completes.
        text_indexes: list[int] = []
        for idx, a in enumerate(answers):
            if not isinstance(a, dict):
                continue
            if str(a.get("voice_note_job_id") or "").strip():
                continue
            if not SurveyWaTranslationService.resolve_source_text(a):
                continue
            text_indexes.append(idx)
        if not text_indexes:
            print("SKIP_TEXT", rec["name"], rec["phone"], "voice_only_or_empty")
            continue
        out = SurveyWaTranslationService.retranslate_recipient_open_answers(
            db, str(rec["id"]), force=True, include_voice=False
        )
        print("TRANSLATE", rec["name"], rec["phone"], out.get("attempted"), out.get("results"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
