"""Append-only consent ledger for Customer Feedback callback + marketing."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FeedbackConsentEvent,
    FeedbackLocation,
    FeedbackMarketingSubscriber,
    FeedbackSession,
)
from app.services.org_opt_out_service import OrgOptOutService

CALLBACK_QUESTION = "Yes, call me back / No, don't call me (number used only for this feedback follow-up)."
MARKETING_QUESTION = "Yes — I want occasional offers from this business on WhatsApp."
CALLBACK_VERSION = "callback_v2"
MARKETING_VERSION = "marketing_v1"


class FeedbackConsentEventsService:
    @staticmethod
    def record(
        db: Session,
        *,
        org_id: str,
        phone_e164: str,
        purpose: str,
        consent_given: bool,
        method: str,
        source_event: str | None = None,
        session_id: str | None = None,
        location_id: str | None = None,
        question_text_snapshot: str | None = None,
        question_version_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        created_by_user_id: str | None = None,
        commit: bool = True,
    ) -> FeedbackConsentEvent:
        phone = str(phone_e164 or "").strip()
        if not phone or phone.startswith("web:"):
            raise ValueError("A real phone number is required for consent records")
        purpose_clean = str(purpose or "").strip().lower()
        if purpose_clean not in {"callback_call", "marketing"}:
            raise ValueError("Invalid consent purpose")
        method_clean = str(method or "web_form").strip().lower() or "web_form"
        event_type = str(source_event or ("grant" if consent_given else "revoke")).strip().lower()
        if event_type not in {"grant", "revoke"}:
            event_type = "grant" if consent_given else "revoke"
        if purpose_clean == "callback_call":
            snapshot = question_text_snapshot or CALLBACK_QUESTION
            version = question_version_id or CALLBACK_VERSION
        else:
            snapshot = question_text_snapshot or MARKETING_QUESTION
            version = question_version_id or MARKETING_VERSION
        row = FeedbackConsentEvent(
            id=str(uuid.uuid4()),
            org_id=org_id,
            session_id=session_id,
            location_id=location_id,
            purpose=purpose_clean,
            consent_given=bool(consent_given),
            phone_e164=phone,
            question_text_snapshot=snapshot,
            question_version_id=version,
            method=method_clean,
            source_event=event_type,
            ip_address=(str(ip_address).strip()[:64] if ip_address else None),
            user_agent=(str(user_agent).strip()[:512] if user_agent else None),
            created_by_user_id=created_by_user_id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
        return row

    @staticmethod
    def list_consents(
        db: Session,
        org_id: str,
        *,
        purpose: str | None = "callback_call",
        consent_given: bool | None = True,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        # Load recent events (newest first), then keep the latest per phone+purpose
        # so a later STOP/admin revoke correctly removes them from the Yes list.
        q = select(FeedbackConsentEvent).where(FeedbackConsentEvent.org_id == org_id)
        if purpose:
            q = q.where(FeedbackConsentEvent.purpose == str(purpose).strip().lower())
        q = q.order_by(FeedbackConsentEvent.created_at.desc()).limit(5000)
        rows = list(db.execute(q).scalars().all())

        latest_by_key: dict[tuple[str, str], FeedbackConsentEvent] = {}
        for row in rows:
            key = (str(row.phone_e164), str(row.purpose))
            if key not in latest_by_key:
                latest_by_key[key] = row

        items: list[dict[str, Any]] = []
        loc_ids = {str(r.location_id) for r in latest_by_key.values() if r.location_id}
        locs = (
            {
                str(loc.id): loc
                for loc in db.execute(
                    select(FeedbackLocation).where(FeedbackLocation.id.in_(list(loc_ids)))
                )
                .scalars()
                .all()
            }
            if loc_ids
            else {}
        )
        for row in latest_by_key.values():
            given = bool(row.consent_given) and str(row.source_event or "") != "revoke"
            if consent_given is True and not given:
                continue
            if consent_given is False and given:
                continue
            loc = locs.get(str(row.location_id or ""))
            items.append(
                {
                    "id": row.id,
                    "org_id": row.org_id,
                    "session_id": row.session_id,
                    "location_id": row.location_id,
                    "location_name": loc.name if loc else None,
                    "purpose": row.purpose,
                    "consent_given": given,
                    "phone_number": row.phone_e164,
                    "question_text_snapshot": row.question_text_snapshot,
                    "question_version_id": row.question_version_id,
                    "method": row.method,
                    "source_event": row.source_event,
                    "ip_address": row.ip_address,
                    "user_agent": row.user_agent,
                    "timestamp": row.created_at.isoformat() if row.created_at else None,
                }
            )
        items.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
        return items[: max(1, min(int(limit or 500), 2000))]

    @staticmethod
    def export_csv(
        db: Session,
        org_id: str,
        *,
        purpose: str | None = "callback_call",
        consent_given: bool | None = True,
    ) -> str:
        items = FeedbackConsentEventsService.list_consents(
            db, org_id, purpose=purpose, consent_given=consent_given, limit=5000
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "timestamp",
                "phone_number",
                "purpose",
                "consent_given",
                "location",
                "method",
                "source_event",
                "question",
                "question_version",
                "session_id",
                "ip_address",
                "user_agent",
            ]
        )
        for row in items:
            writer.writerow(
                [
                    row.get("timestamp") or "",
                    row.get("phone_number") or "",
                    row.get("purpose") or "",
                    "Yes" if row.get("consent_given") else "No",
                    row.get("location_name") or "",
                    row.get("method") or "",
                    row.get("source_event") or "",
                    row.get("question_text_snapshot") or "",
                    row.get("question_version_id") or "",
                    row.get("session_id") or "",
                    row.get("ip_address") or "",
                    row.get("user_agent") or "",
                ]
            )
        return buf.getvalue()

    @staticmethod
    def admin_opt_out(
        db: Session,
        *,
        org_id: str,
        phone_e164: str,
        user_id: str | None,
        session_id: str | None = None,
        location_id: str | None = None,
        purpose: str = "callback_call",
    ) -> dict[str, Any]:
        phone = str(phone_e164 or "").strip()
        if not phone:
            raise ValueError("phone_number required")
        purpose_clean = str(purpose or "callback_call").strip().lower()
        FeedbackConsentEventsService.record(
            db,
            org_id=org_id,
            phone_e164=phone,
            purpose=purpose_clean,
            consent_given=False,
            method="admin",
            source_event="revoke",
            session_id=session_id,
            location_id=location_id,
            created_by_user_id=user_id,
            commit=False,
        )
        # Clear callback consent on matching sessions.
        sessions = list(
            db.execute(
                select(FeedbackSession).where(
                    FeedbackSession.org_id == org_id,
                    FeedbackSession.visitor_phone == phone,
                )
            )
            .scalars()
            .all()
        )
        for sess in sessions:
            sess.callback_consent = False
            db.add(sess)
        # Deactivate marketing subscribers for this phone.
        subs = list(
            db.execute(
                select(FeedbackMarketingSubscriber).where(
                    FeedbackMarketingSubscriber.org_id == org_id,
                    FeedbackMarketingSubscriber.phone_e164 == phone,
                    FeedbackMarketingSubscriber.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        now = datetime.utcnow()
        for sub in subs:
            sub.is_active = False
            sub.opted_out_at = now
            db.add(sub)
            FeedbackConsentEventsService.record(
                db,
                org_id=org_id,
                phone_e164=phone,
                purpose="marketing",
                consent_given=False,
                method="admin",
                source_event="revoke",
                session_id=sub.session_id,
                location_id=sub.location_id,
                created_by_user_id=user_id,
                commit=False,
            )
        OrgOptOutService.add_opt_out(
            db,
            org_id=org_id,
            phone=phone,
            reason="admin_opt_out",
            created_by_user_id=user_id,
        )
        db.commit()
        return {"ok": True, "phone_number": phone, "opted_out": True}
