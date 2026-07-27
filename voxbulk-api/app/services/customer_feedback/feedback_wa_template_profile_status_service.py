"""Upsert Customer Feedback per-profile WhatsApp template status (silent ledger)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.connection_profile import ConnectionProfile
from app.models.feedback_wa_template_profile_status import FeedbackWaTemplateProfileStatus

logger = logging.getLogger(__name__)


class FeedbackWaTemplateProfileStatusService:
    @staticmethod
    def upsert_from_push(
        db: Session,
        *,
        feedback_template_id: str,
        connection_profile_id: str | None,
        status: str | None = None,
        meta_template_name: str | None = None,
        remote_record_id: str | None = None,
        category: str | None = None,
        last_push_error: str | None = None,
        mark_pushed: bool = True,
        commit: bool = False,
    ) -> FeedbackWaTemplateProfileStatus | None:
        pid = str(connection_profile_id or "").strip()
        tid = str(feedback_template_id or "").strip()
        if not pid or not tid:
            return None

        profile = db.get(ConnectionProfile, pid)
        label = None
        provider = None
        if profile is not None:
            label = str(profile.label or profile.name or "").strip() or None
            provider = str(profile.provider or "").strip() or None

        entry = db.execute(
            select(FeedbackWaTemplateProfileStatus).where(
                FeedbackWaTemplateProfileStatus.feedback_template_id == tid,
                FeedbackWaTemplateProfileStatus.connection_profile_id == pid,
            )
        ).scalar_one_or_none()
        if entry is None:
            entry = FeedbackWaTemplateProfileStatus(
                feedback_template_id=tid,
                connection_profile_id=pid,
            )
            db.add(entry)

        now = datetime.utcnow()
        entry.provider = provider or entry.provider
        entry.profile_label = label or entry.profile_label
        if status:
            entry.status = str(status).strip().upper() or entry.status
        if meta_template_name is not None:
            entry.meta_template_name = str(meta_template_name).strip() or None
        if remote_record_id is not None:
            entry.remote_record_id = str(remote_record_id).strip() or None
        if category is not None:
            entry.category = str(category).strip() or None
        entry.last_push_error = (str(last_push_error).strip() or None) if last_push_error is not None else entry.last_push_error
        entry.last_synced_at = now
        entry.updated_at = now
        if mark_pushed:
            entry.last_pushed_at = now

        if commit:
            try:
                db.commit()
            except Exception:  # noqa: BLE001 — never break push for ledger
                logger.exception(
                    "feedback_wa_template_profile_status_commit_failed template_id=%s profile=%s",
                    tid,
                    pid,
                )
                db.rollback()
                return None
        return entry

    @staticmethod
    def upsert_from_push_result(
        db: Session,
        *,
        feedback_template_id: str,
        connection_profile_id: str | None,
        result: dict[str, Any],
    ) -> None:
        if not connection_profile_id:
            return
        try:
            status = "LINKED" if result.get("linked") or result.get("skipped_push") else "SUBMITTED"
            if result.get("ok") is False:
                status = "ERROR"
            FeedbackWaTemplateProfileStatusService.upsert_from_push(
                db,
                feedback_template_id=feedback_template_id,
                connection_profile_id=connection_profile_id,
                status=status,
                meta_template_name=result.get("meta_name"),
                remote_record_id=result.get("telnyx_record_id"),
                category=result.get("category"),
                last_push_error=None if result.get("ok") is not False else str(result.get("message") or "")[:500],
                mark_pushed=True,
                commit=False,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "feedback_wa_template_profile_status_upsert_failed template_id=%s",
                feedback_template_id,
            )
