from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.appointment import Appointment
from app.models.call_log import CallLog
from app.models.patient import Patient
from app.models.whatsapp_log import WhatsAppLog
from app.schemas.dashboard import DashboardMetricsOut
from app.workers.sync_tasks import dentally_sync_tenant
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/metrics", response_model=DashboardMetricsOut)
def metrics(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org_id = principal.org_id

    total_patients = db.execute(select(func.count()).select_from(Patient).where(Patient.org_id == org_id)).scalar_one()
    total_appointments = db.execute(
        select(func.count()).select_from(Appointment).where(Appointment.org_id == org_id)
    ).scalar_one()
    total_call_logs = db.execute(select(func.count()).select_from(CallLog).where(CallLog.org_id == org_id)).scalar_one()
    total_whatsapp_logs = db.execute(
        select(func.count()).select_from(WhatsAppLog).where(WhatsAppLog.org_id == org_id)
    ).scalar_one()

    rows = db.execute(
        select(Appointment.status, func.count()).where(Appointment.org_id == org_id).group_by(Appointment.status)
    ).all()
    status_counts = {str(status): int(count) for status, count in rows}

    return DashboardMetricsOut(
        total_patients=int(total_patients),
        total_appointments=int(total_appointments),
        total_call_logs=int(total_call_logs),
        total_whatsapp_logs=int(total_whatsapp_logs),
        appointment_status_counts=status_counts,
    )


@router.get("/home-summary")
def home_summary(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """KPI blocks for dashboard home — interview, survey, recovery (when enabled)."""
    from app.models.service_order import ServiceOrder
    from app.services.org_enabled_services import org_service_maps
    from app.services.recovery_service import OrganisationService
    from app.services.platform_catalog_service import ServiceOrderService

    org = OrganisationService.get_org(db, principal.org_id)
    _, _, visible = org_service_maps(org, db) if org else ({}, {}, {})

    rows = list(
        db.execute(select(ServiceOrder).where(ServiceOrder.org_id == principal.org_id)).scalars().all()
    )
    interviews = [r for r in rows if r.service_code == "interview"]
    surveys = [r for r in rows if r.service_code == "survey"]

    int_live = sum(1 for r in interviews if ServiceOrderService.is_live_interview(r))
    int_finished = sum(1 for r in interviews if ServiceOrderService.is_finished_interview(r))
    int_archived = sum(1 for r in interviews if ServiceOrderService.is_archived_order(r))
    int_running = sum(1 for r in interviews if r.status == "running")
    int_candidates = sum(int(r.recipient_count or 0) for r in interviews if r.status in {"running", "completed"})
    int_calls_attempted = 0
    int_calls_completed = 0
    int_recommended_advance = 0
    for r in interviews:
        if r.status not in {"running", "completed"}:
            continue
        recipients = ServiceOrderService.get_recipients(db, r.id)
        for rec in recipients:
            st = str(rec.status or "").lower()
            if st not in {"", "pending", "queued", "skipped", "cancelled"}:
                int_calls_attempted += 1
            if st in {"completed", "done", "answered", "success"}:
                int_calls_completed += 1
            try:
                parsed = json.loads(rec.result_json or "{}")
            except Exception:
                parsed = {}
            analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
            if analysis.get("recommendation") == "Advance" and st in {"completed", "done", "answered", "success"}:
                int_recommended_advance += 1

    sur_live = sum(1 for r in surveys if ServiceOrderService.is_live_survey(r))
    sur_finished = sum(1 for r in surveys if ServiceOrderService.is_finished_survey(r))
    sur_archived = sum(1 for r in surveys if ServiceOrderService.is_archived_order(r))
    sur_running = sum(1 for r in surveys if r.status == "running")
    sur_paused = sum(1 for r in surveys if r.status == "paused")
    sur_responses = 0
    sur_sent = 0
    for r in surveys:
        try:
            report = json.loads(r.report_json or "{}")
        except Exception:
            report = {}
        if isinstance(report, dict):
            sur_responses += int(report.get("responded") or report.get("completed") or 0)
            sur_sent += int(report.get("sent") or report.get("reached") or r.recipient_count or 0)

    total_patients = db.execute(
        select(func.count()).select_from(Patient).where(Patient.org_id == principal.org_id)
    ).scalar_one()
    status_rows = db.execute(
        select(Appointment.status, func.count())
        .where(Appointment.org_id == principal.org_id)
        .group_by(Appointment.status)
    ).all()
    queue_pending = sum(
        int(c)
        for st, c in status_rows
        if str(st) in {"pending", "missed", "cancelled", "no_show"}
    )

    feedback_block: dict | None = None
    feedback_parts: list[dict] = []

    if visible.get("customer_feedback"):
        from app.models.customer_feedback import FeedbackLocation, FeedbackResponse, FeedbackSession
        from app.services.customer_feedback.feedback_answer_service import POOR_ANSWERS

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        scans_today = db.execute(
            select(func.count())
            .select_from(FeedbackSession)
            .where(
                FeedbackSession.org_id == principal.org_id,
                FeedbackSession.started_at >= today_start,
            )
        ).scalar_one()
        locations = list(
            db.execute(select(FeedbackLocation).where(FeedbackLocation.org_id == principal.org_id)).scalars().all()
        )
        responses = list(
            db.execute(
                select(FeedbackResponse)
                .where(FeedbackResponse.org_id == principal.org_id)
                .order_by(FeedbackResponse.created_at.desc())
                .limit(200)
            ).scalars().all()
        )
        sentiment = {"excellent": 0, "good": 0, "poor": 0}
        unhappy: list[dict] = []
        recent: list[dict] = []

        def _classify(answer: str) -> str | None:
            a = str(answer or "").strip().lower()
            if not a:
                return None
            if "excellent" in a or a in {"5", "5/5"}:
                return "excellent"
            if "good" in a or a in {"4", "4/5", "3", "3/5"}:
                return "good"
            if "poor" in a or a in POOR_ANSWERS or any(p in a for p in ("unhappy", "bad", "terrible")):
                return "poor"
            return None

        for r in responses:
            ans = str(r.answer_text_en or r.answer_text or "")
            bucket = _classify(ans)
            if bucket:
                sentiment[bucket] += 1
            loc = db.get(FeedbackLocation, r.location_id)
            branch = loc.name if loc else "Branch"
            when = r.created_at.isoformat() if r.created_at else None
            chip = ans[:24] if ans else "Response"
            tone = "bad" if bucket == "poor" else "ok" if bucket in {"excellent", "good"} else "info"
            if len(recent) < 8:
                recent.append(
                    {
                        "svc": "feedback",
                        "who": branch,
                        "what": f"left feedback — {chip}",
                        "chip": chip,
                        "tone": tone,
                        "when": when,
                    }
                )
            if bucket == "poor" and len(unhappy) < 6:
                unhappy.append(
                    {
                        "id": r.id,
                        "reason": ans[:80] or "Negative feedback",
                        "branch": branch,
                        "when": when,
                    }
                )

        feedback_parts.append(
            {
            "qr_scans_today": int(scans_today),
            "total_scans": sum(int(loc.scan_count or 0) for loc in locations),
            "sentiment": sentiment,
            "unhappy": unhappy,
            "recent": recent,
            }
        )

    if visible.get("survey"):
        from app.services.survey_results_service import survey_home_feedback_snapshot

        feedback_parts.append(survey_home_feedback_snapshot(db, org_id=principal.org_id))

    if visible.get("interview"):
        from app.services.interview_results_service import interview_home_activity_snapshot

        feedback_parts.append(interview_home_activity_snapshot(db, org_id=principal.org_id))

    if feedback_parts:
        feedback_block = {
            "qr_scans_today": 0,
            "total_scans": 0,
            "sentiment": {"excellent": 0, "good": 0, "poor": 0},
            "unhappy": [],
            "recent": [],
        }
        for part in feedback_parts:
            feedback_block["qr_scans_today"] += int(part.get("qr_scans_today") or 0)
            feedback_block["total_scans"] += int(part.get("total_scans") or 0)
            for key in ("excellent", "good", "poor"):
                feedback_block["sentiment"][key] += int((part.get("sentiment") or {}).get(key) or 0)
            feedback_block["unhappy"].extend(part.get("unhappy") or [])
            feedback_block["recent"].extend(part.get("recent") or [])
        feedback_block["unhappy"] = sorted(
            feedback_block["unhappy"],
            key=lambda row: row.get("when") or "",
            reverse=True,
        )[:6]
        feedback_block["recent"] = sorted(
            feedback_block["recent"],
            key=lambda row: row.get("when") or "",
            reverse=True,
        )[:8]

    return {
        "enabled_services": visible,
        "allowed_services": org_service_maps(org, db)[0] if org else {},
        "visible_services": visible,
        "interview": {
            "live": int_live,
            "finished": int_finished,
            "archived": int_archived,
            "running": int_running,
            "candidates": int_candidates,
            "calls_attempted": int_calls_attempted,
            "calls_completed": int_calls_completed,
            "recommended_advance": int_recommended_advance,
        },
        "survey": {
            "live": sur_live,
            "finished": sur_finished,
            "archived": sur_archived,
            "running": sur_running,
            "paused": sur_paused,
            "responses": sur_responses,
            "sent": sur_sent,
            "completion_rate": round((sur_responses / sur_sent) * 100) if sur_sent else 0,
        },
        "recovery": {
            "queue_pending": int(queue_pending),
            "total_calls": int(
                db.execute(select(func.count()).select_from(CallLog).where(CallLog.org_id == principal.org_id)).scalar_one()
            ),
            "whatsapp_sent": int(
                db.execute(select(func.count()).select_from(WhatsAppLog).where(WhatsAppLog.org_id == principal.org_id)).scalar_one()
            ),
        },
        "feedback": feedback_block,
        "total_patients": int(total_patients),
    }


@router.post("/dentally/sync")
def dentally_sync(principal=Depends(get_current_principal)):
    res = dentally_sync_tenant.delay(org_id=principal.org_id)
    return {"task_id": res.id}


@router.get("/dentally/sync/{task_id}")
def dentally_sync_status(task_id: str):
    res = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "state": res.state, "result": res.result if res.successful() else None}

