#!/usr/bin/env python3
"""Cancel active Customer Feedback + legacy WA survey state for a test phone.

Customer Feedback WhatsApp is synchronous (no background queue). This script:
- Marks active feedback_sessions as cancelled
- Marks active survey_sessions / in-flight recipients as cancelled
- Optionally marks pending survey voice-note jobs as skipped

Usage (VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/clear_feedback_wa_state.py --phone +447954823445
  python scripts/clear_feedback_wa_state.py --phone +447954823445 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from sqlalchemy import or_, select

from app.core.database import get_sessionmaker


def _norm_phone(raw: str) -> str:
    phone = str(raw or "").strip()
    if not phone:
        raise ValueError("phone is required")
    if not phone.startswith("+"):
        phone = f"+{phone.lstrip('+')}"
    return phone


def clear_feedback_sessions(db, phone: str, *, dry_run: bool) -> int:
    from app.models.customer_feedback import FeedbackSession

    rows = list(
        db.execute(
            select(FeedbackSession).where(
                FeedbackSession.visitor_phone == phone,
                FeedbackSession.status == "active",
            )
        ).scalars().all()
    )
    now = datetime.utcnow()
    for row in rows:
        print(
            f"feedback_session id={row.id} org={row.org_id} step={row.current_step} started={row.started_at}"
        )
        if not dry_run:
            row.status = "cancelled"
            row.completed_at = now
            db.add(row)
    return len(rows)


def clear_wa_survey_state(db, phone: str, *, dry_run: bool) -> tuple[int, int]:
    from app.models.service_order import ServiceOrderRecipient
    from app.models.survey_session import SurveySession
    from app.models.survey_voice_note_job import SurveyVoiceNoteJob

    recipients = list(
        db.execute(
            select(ServiceOrderRecipient).where(
                or_(
                    ServiceOrderRecipient.phone == phone,
                    ServiceOrderRecipient.phone == phone.lstrip("+"),
                )
            )
        ).scalars().all()
    )
    recipient_ids = [r.id for r in recipients]
    if not recipient_ids:
        return 0, 0

    sessions = list(
        db.execute(
            select(SurveySession).where(
                SurveySession.recipient_id.in_(recipient_ids),
                SurveySession.status == "active",
            )
        ).scalars().all()
    )
    now = datetime.utcnow()
    for sess in sessions:
        print(f"survey_session id={sess.id} order={sess.order_id} step={sess.current_step}")
        if not dry_run:
            sess.status = "cancelled"
            sess.completed_at = now
            sess.updated_at = now
            db.add(sess)

    in_flight = {"pending", "queued", "running", "in_progress", "invited", "sent"}
    recipient_count = 0
    for rec in recipients:
        status = str(rec.status or "").lower()
        if status in {"completed", "cancelled", "opted_out"}:
            continue
        if status not in in_flight and status not in {"active", "started", "surveying"}:
            continue
        print(f"survey_recipient id={rec.id} order={rec.order_id} status={rec.status}")
        if not dry_run:
            rec.status = "cancelled"
            db.add(rec)
        recipient_count += 1

    jobs = list(
        db.execute(
            select(SurveyVoiceNoteJob).where(
                SurveyVoiceNoteJob.recipient_id.in_(recipient_ids),
                SurveyVoiceNoteJob.transcription_status.in_(("pending", "processing", "queued")),
            )
        ).scalars().all()
    )
    for job in jobs:
        print(f"voice_note_job id={job.id} status={job.transcription_status}")
        if not dry_run:
            job.transcription_status = "skipped"
            job.processed_at = now
            db.add(job)

    return len(sessions), recipient_count + len(jobs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear active feedback / survey WhatsApp state for a phone")
    parser.add_argument("--phone", required=True, help="E.164 phone, e.g. +447954823445")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args()

    phone = _norm_phone(args.phone)
    dry_run = bool(args.dry_run)
    if dry_run:
        print("DRY RUN — no database writes")

    with get_sessionmaker()() as db:
        fb = clear_feedback_sessions(db, phone, dry_run=dry_run)
        survey_sessions, survey_other = clear_wa_survey_state(db, phone, dry_run=dry_run)
        if not dry_run and (fb or survey_sessions or survey_other):
            db.commit()
        print(
            f"done phone={phone} feedback_sessions={fb} "
            f"survey_sessions={survey_sessions} survey_recipients_or_jobs={survey_other}"
        )
        if fb == 0 and survey_sessions == 0 and survey_other == 0:
            print("nothing active found — if WhatsApp still fails, check Telnyx opt-out (send UNSTOP) and template approval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
