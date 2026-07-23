"""Partner marketplace auth, screening intake, webhooks, and admin ops."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.encryption import get_encryptor
from app.models.organisation import Organisation
from app.models.partner import PartnerApiKey, PartnerProvider, PartnerScreening
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_intake_service import create_new_interview_draft, intake_contacts_merge
from app.services.platform_catalog_service import ServiceOrderService

logger = logging.getLogger(__name__)

PROVIDER_CATALOG: list[dict[str, Any]] = [
    {"key": "zoho", "label": "Zoho Marketplace", "commission_pct": 18.0},
    {"key": "breezy", "label": "Breezy HR", "commission_pct": 20.0},
    {"key": "workable", "label": "Workable", "commission_pct": 18.0},
    {"key": "bullhorn", "label": "Bullhorn Marketplace", "commission_pct": 22.0},
    {"key": "zapier", "label": "Zapier", "commission_pct": 18.0},
]


def _now() -> datetime:
    return datetime.utcnow()


def _new_id() -> str:
    return str(uuid.uuid4())


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_raw_api_key(*, provider_key: str, environment: str) -> str:
    token = secrets.token_urlsafe(32)
    return f"vb_{provider_key}_{environment}_{token}"


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "") if raw else default
    except Exception:
        return default


def recommendation_to_status(recommendation: str | None, score: int | None) -> str:
    rec = str(recommendation or "").strip().lower()
    if rec in {"advance", "pass", "passed", "hire"}:
        return "passed"
    if rec in {"decline", "reject", "rejected"}:
        return "rejected"
    if rec in {"hold", "review", "maybe"}:
        return "review"
    if score is None:
        return "review"
    if score >= 75:
        return "passed"
    if score < 50:
        return "rejected"
    return "review"


@dataclass
class PartnerPrincipal:
    provider: PartnerProvider
    api_key: PartnerApiKey
    partner_name: str
    environment: str
    org_id: str


class PartnerService:
    @staticmethod
    def ensure_providers(db: Session) -> list[PartnerProvider]:
        out: list[PartnerProvider] = []
        for item in PROVIDER_CATALOG:
            row = db.execute(select(PartnerProvider).where(PartnerProvider.key == item["key"])).scalar_one_or_none()
            if row is None:
                row = PartnerProvider(
                    id=_new_id(),
                    key=item["key"],
                    label=item["label"],
                    enabled=False,
                    mode="sandbox",
                    commission_pct=float(item["commission_pct"]),
                    created_at=_now(),
                    updated_at=_now(),
                )
                db.add(row)
                db.flush()
            out.append(row)
        db.commit()
        for row in out:
            db.refresh(row)
        return out

    @staticmethod
    def get_provider(db: Session, key: str) -> PartnerProvider | None:
        PartnerService.ensure_providers(db)
        return db.execute(select(PartnerProvider).where(PartnerProvider.key == str(key or "").strip().lower())).scalar_one_or_none()

    @staticmethod
    def authenticate(
        db: Session,
        *,
        api_key: str | None,
        partner_name: str | None,
    ) -> PartnerPrincipal:
        raw_key = str(api_key or "").strip()
        name = str(partner_name or "").strip().lower()
        if not raw_key or not name:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key or X-Partner-Name",
            )
        provider = PartnerService.get_provider(db, name)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown partner")
        if not provider.enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Partner is disabled")
        key_row = db.execute(
            select(PartnerApiKey).where(
                PartnerApiKey.provider_id == provider.id,
                PartnerApiKey.key_hash == hash_api_key(raw_key),
                PartnerApiKey.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if key_row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        if key_row.environment != provider.mode:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Key environment '{key_row.environment}' does not match provider mode '{provider.mode}'",
            )
        if not provider.mapped_org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Partner has no mapped VoxBulk organisation",
            )
        org = db.get(Organisation, provider.mapped_org_id)
        if org is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mapped organisation not found")
        key_row.last_used_at = _now()
        db.add(key_row)
        db.commit()
        return PartnerPrincipal(
            provider=provider,
            api_key=key_row,
            partner_name=provider.key,
            environment=key_row.environment,
            org_id=str(provider.mapped_org_id),
        )

    @staticmethod
    def _org_owner_user_id(db: Session, org_id: str) -> str:
        from app.models.membership import OrganisationMembership

        owner = db.execute(
            select(OrganisationMembership.user_id)
            .where(
                OrganisationMembership.org_id == org_id,
                OrganisationMembership.role.in_(["owner", "manager"]),
            )
            .limit(1)
        ).scalar_one_or_none()
        if owner:
            return str(owner)
        any_member = db.execute(
            select(OrganisationMembership.user_id).where(OrganisationMembership.org_id == org_id).limit(1)
        ).scalar_one_or_none()
        if any_member:
            return str(any_member)
        user = db.execute(select(User.id).limit(1)).scalar_one_or_none()
        if user:
            return str(user)
        raise HTTPException(status_code=400, detail="No user available to own partner screening order")

    @staticmethod
    def create_screening(
        db: Session,
        principal: PartnerPrincipal,
        *,
        partner_reference_id: str,
        job_title: str,
        screening_questions: list[str],
        candidate_name: str,
        candidate_phone: str,
        preferred_language: str,
        callback_url: str | None = None,
        job_description: str | None = None,
        candidate_email: str | None = None,
    ) -> PartnerScreening:
        lang = "ar" if str(preferred_language or "").lower().startswith("ar") else "en"
        questions = [str(q).strip() for q in (screening_questions or []) if str(q).strip()]
        user_id = PartnerService._org_owner_user_id(db, principal.org_id)
        order = create_new_interview_draft(db, org_id=principal.org_id, user_id=user_id)
        cfg = _loads(getattr(order, "config_json", None), {})
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["role"] = job_title
        cfg["title"] = job_title
        cfg["criteria"] = "\n".join(f"- {q}" for q in questions) if questions else (job_description or "")
        cfg["interview_language"] = lang
        cfg["script_language_code"] = lang
        cfg["delivery"] = "ai_call"
        cfg["require_booking"] = True
        cfg["booking_flow"] = "whatsapp_slot"
        cfg["partner"] = {
            "provider": principal.provider.key,
            "partner_reference_id": partner_reference_id,
            "environment": principal.environment,
            "screening_id": None,
        }
        if job_description:
            cfg["job_description"] = job_description
        order.config_json = json.dumps(cfg)
        order.title = f"Partner · {job_title}"[:200]

        # Partner traffic is metered via partner ledger — mark order launchable.
        now = _now()
        order.payment_method = "partner"
        order.payment_status = "approved"
        order.status = "paid"
        order.payment_note = f"Partner {principal.provider.key} screening ({principal.environment})"
        order.scheduled_start_at = now
        order.scheduled_end_at = now + timedelta(days=7)
        cfg["calling_window_start_at"] = now.isoformat()
        cfg["calling_window_end_at"] = order.scheduled_end_at.isoformat()
        order.config_json = json.dumps(cfg)
        db.add(order)
        db.flush()

        email = str(candidate_email or "").strip()
        intake_contacts_merge(
            db,
            order,
            [
                {
                    "name": candidate_name,
                    "phone": candidate_phone,
                    "email": email,
                }
            ],
        )
        recipients = (
            db.execute(
                select(ServiceOrderRecipient)
                .where(ServiceOrderRecipient.order_id == order.id)
                .order_by(ServiceOrderRecipient.row_number.asc())
            )
            .scalars()
            .all()
        )
        recipient = recipients[-1] if recipients else None
        if recipient is None:
            raise HTTPException(status_code=500, detail="Failed to create candidate recipient")

        from app.services.interview_booking_service import (
            InterviewBookingService,
            booking_url_for_token,
            ensure_full_day_booking_window,
        )

        order = ensure_full_day_booking_window(db, order)
        token_row = InterviewBookingService.ensure_token(db, order, recipient)
        screening_link = booking_url_for_token(token_row.token)

        # Persist booking URL on recipient for reminders / dashboard.
        try:
            merged = _loads(getattr(recipient, "result_json", None), {})
            if not isinstance(merged, dict):
                merged = {}
            merged.update(
                {
                    "booking_token": token_row.token,
                    "booking_url": screening_link,
                    "partner_screening": True,
                }
            )
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)
        except Exception:
            pass

        invite_errors: list[str] = []
        try:
            invite_result = InterviewBookingService.send_invites(
                db,
                order,
                recipient_ids=[recipient.id],
                channels=["whatsapp", "email"] if email else ["whatsapp"],
                force_resend=True,
                force_email=True,
            )
            invite_errors = [str(e) for e in (invite_result or {}).get("errors") or []]
        except Exception as exc:
            logger.exception("partner screening invite failed")
            invite_errors = [str(exc)[:300]]

        try:
            ServiceOrderService.schedule_order(db, order)
        except Exception:
            logger.exception("partner screening schedule_order failed")

        screening_id = _new_id()
        cb = str(callback_url or principal.provider.result_webhook_url or "").strip()
        row = PartnerScreening(
            id=screening_id,
            provider_id=principal.provider.id,
            partner_reference_id=str(partner_reference_id).strip(),
            environment=principal.environment,
            org_id=principal.org_id,
            order_id=order.id,
            recipient_id=recipient.id,
            job_title=job_title.strip(),
            candidate_name=candidate_name.strip(),
            candidate_phone=candidate_phone.strip(),
            preferred_language=lang,
            screening_questions_json=json.dumps(questions),
            callback_url=cb,
            status="invited" if screening_link else "accepted",
            screening_link=screening_link,
            estimated_completion_minutes=15,
            created_at=_now(),
            updated_at=_now(),
        )
        if invite_errors:
            row.webhook_last_error = ("Invite: " + "; ".join(invite_errors))[:500]
        db.add(row)
        db.flush()
        cfg = _loads(getattr(order, "config_json", None), {})
        if isinstance(cfg, dict):
            partner_meta = cfg.get("partner") if isinstance(cfg.get("partner"), dict) else {}
            partner_meta["screening_id"] = screening_id
            cfg["partner"] = partner_meta
            order.config_json = json.dumps(cfg)
            db.add(order)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def log_result(
        db: Session,
        principal: PartnerPrincipal,
        *,
        partner_reference_id: str,
        candidate_score: int,
        result_status: str,
        report_url: str | None = None,
        call_duration_minutes: float | None = None,
        total_charge_amount: float | None = None,
        screening_id: str | None = None,
    ) -> PartnerScreening:
        row = None
        if screening_id:
            row = db.get(PartnerScreening, screening_id)
        if row is None:
            row = db.execute(
                select(PartnerScreening)
                .where(
                    PartnerScreening.provider_id == principal.provider.id,
                    PartnerScreening.partner_reference_id == partner_reference_id,
                )
                .order_by(PartnerScreening.created_at.desc())
            ).scalars().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Screening not found for partner_reference_id")
        if row.provider_id != principal.provider.id:
            raise HTTPException(status_code=403, detail="Screening belongs to another partner")

        fee = float(principal.provider.connection_fee_gbp or 1.5)
        per_min = float(principal.provider.per_minute_gbp or 0.35)
        duration = float(call_duration_minutes) if call_duration_minutes is not None else None
        charge = total_charge_amount
        if charge is None and duration is not None:
            charge = round(fee + per_min * max(duration, 0), 2)

        row.candidate_score = int(candidate_score)
        row.result_status = result_status
        row.report_url = str(report_url or row.report_url or "")
        row.call_duration_minutes = duration
        row.total_charge_gbp = float(charge) if charge is not None else row.total_charge_gbp
        row.status = "completed"
        row.result_posted_at = _now()
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def deliver_result_webhook(db: Session, screening: PartnerScreening) -> bool:
        provider = db.get(PartnerProvider, screening.provider_id)
        url = str(screening.callback_url or (provider.result_webhook_url if provider else "") or "").strip()
        if not url:
            return False
        payload = {
            "partner_reference_id": screening.partner_reference_id,
            "screening_id": screening.id,
            "candidate_score": screening.candidate_score,
            "status": screening.result_status,
            "report_url": screening.report_url or None,
            "call_duration_minutes": screening.call_duration_minutes,
            "total_charge_amount": screening.total_charge_gbp,
            "provider": provider.key if provider else None,
        }
        headers = {"Content-Type": "application/json", "X-Voxbulk-Partner-Event": "screening.result"}
        secret = None
        if provider and provider.webhook_secret_enc:
            try:
                secret = get_encryptor().decrypt_str(provider.webhook_secret_enc)
            except Exception:
                secret = None
        body = json.dumps(payload, separators=(",", ":"))
        if secret:
            sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
            headers["X-Voxbulk-Signature"] = sig
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, content=body, headers=headers)
            if resp.status_code >= 400:
                screening.webhook_last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                db.add(screening)
                db.commit()
                return False
            screening.webhook_delivered_at = _now()
            screening.webhook_last_error = ""
            screening.updated_at = _now()
            db.add(screening)
            db.commit()
            return True
        except Exception as exc:
            logger.exception("partner webhook failed")
            screening.webhook_last_error = str(exc)[:500]
            db.add(screening)
            db.commit()
            return False

    @staticmethod
    def on_interview_analysis_complete(db: Session, *, order: ServiceOrder, recipient: ServiceOrderRecipient) -> None:
        """Called after interview analysis — push result to partner if this recipient is partner-sourced."""
        row = db.execute(
            select(PartnerScreening).where(PartnerScreening.recipient_id == recipient.id)
        ).scalar_one_or_none()
        if row is None:
            return
        parsed: dict[str, Any] = {}
        try:
            raw = recipient.result_json
            if isinstance(raw, dict):
                parsed = raw
            elif isinstance(raw, str) and raw.strip():
                parsed = json.loads(raw)
        except Exception:
            parsed = {}
        analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
        score_raw = analysis.get("score") if analysis else parsed.get("score")
        try:
            score = int(score_raw) if score_raw is not None else None
        except Exception:
            score = None
        recommendation = analysis.get("recommendation") if analysis else parsed.get("recommendation")
        result_status = recommendation_to_status(str(recommendation) if recommendation else None, score)

        duration = None
        for key in ("billable_minutes", "duration_minutes", "call_duration_minutes"):
            if parsed.get(key) is not None:
                try:
                    duration = float(parsed.get(key))
                    break
                except Exception:
                    pass
            if analysis.get(key) is not None:
                try:
                    duration = float(analysis.get(key))
                    break
                except Exception:
                    pass

        provider = db.get(PartnerProvider, row.provider_id)
        fee = float(provider.connection_fee_gbp if provider else 1.5)
        per_min = float(provider.per_minute_gbp if provider else 0.35)
        charge = round(fee + per_min * max(duration or 0, 0), 2) if duration is not None else round(fee, 2)

        report_url = f"https://dashboard.voxbulk.com/interview/orders/{order.id}/recipients/{recipient.id}"
        row.candidate_score = score if score is not None else row.candidate_score
        row.result_status = result_status
        row.report_url = report_url
        row.call_duration_minutes = duration
        row.total_charge_gbp = charge
        row.status = "completed"
        row.result_posted_at = _now()
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        PartnerService.deliver_result_webhook(db, row)

        # Real Zoho Recruit writeback when org is OAuth-connected.
        if provider and provider.key == "zoho" and row.org_id and row.partner_reference_id:
            try:
                from app.services.zoho_recruit_connection_service import write_screening_result

                partner_cfg = _loads(provider.config_json, {})
                write_screening_result(
                    db,
                    org_id=str(row.org_id),
                    candidate_id=str(row.partner_reference_id),
                    score=row.candidate_score,
                    result_status=row.result_status,
                    report_url=row.report_url,
                    partner_config=partner_cfg if isinstance(partner_cfg, dict) else {},
                )
            except Exception:
                logger.exception("zoho recruit writeback failed screening_id=%s", row.id)

    # ---- Admin ----

    @staticmethod
    def admin_kpi(db: Session) -> dict[str, Any]:
        providers = PartnerService.ensure_providers(db)
        rows_out = []
        totals = {
            "connected": 0,
            "total": len(providers),
            "jobs": 0,
            "completed": 0,
            "gross": 0.0,
            "remittance": 0.0,
            "profit": 0.0,
        }
        for p in providers:
            jobs = db.execute(
                select(func.count()).select_from(PartnerScreening).where(PartnerScreening.provider_id == p.id)
            ).scalar() or 0
            completed = db.execute(
                select(func.count())
                .select_from(PartnerScreening)
                .where(PartnerScreening.provider_id == p.id, PartnerScreening.status == "completed")
            ).scalar() or 0
            gross = db.execute(
                select(func.coalesce(func.sum(PartnerScreening.total_charge_gbp), 0.0)).where(
                    PartnerScreening.provider_id == p.id
                )
            ).scalar() or 0.0
            gross_f = float(gross or 0)
            remittance = gross_f * (100.0 - float(p.commission_pct or 0)) / 100.0
            cost = float(p.est_cost_per_completed_gbp or 5) * int(completed)
            profit = remittance - cost
            has_key = db.execute(
                select(func.count())
                .select_from(PartnerApiKey)
                .where(PartnerApiKey.provider_id == p.id, PartnerApiKey.is_active.is_(True))
            ).scalar() or 0
            if p.last_health_ok is False:
                connection = "error"
            elif p.enabled and has_key and p.mapped_org_id:
                connection = "connected" if p.mode == "live" else "sandbox"
            else:
                connection = "none"
            if connection in {"connected", "sandbox"}:
                totals["connected"] += 1
            last = db.execute(
                select(PartnerScreening.created_at)
                .where(PartnerScreening.provider_id == p.id)
                .order_by(PartnerScreening.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            rows_out.append(
                {
                    "key": p.key,
                    "label": p.label,
                    "connection": connection,
                    "mode": p.mode if p.enabled else None,
                    "enabled": bool(p.enabled),
                    "jobs": int(jobs),
                    "completed": int(completed),
                    "gross": round(gross_f, 2),
                    "commission": float(p.commission_pct or 0),
                    "remittance": round(remittance, 2),
                    "cost": round(cost, 2),
                    "profit": round(profit, 2),
                    "last_activity": last.isoformat() + "Z" if last else None,
                }
            )
            totals["jobs"] += int(jobs)
            totals["completed"] += int(completed)
            totals["gross"] += gross_f
            totals["remittance"] += remittance
            totals["profit"] += profit
        totals["gross"] = round(totals["gross"], 2)
        totals["remittance"] = round(totals["remittance"], 2)
        totals["profit"] = round(totals["profit"], 2)
        return {"totals": totals, "rows": rows_out}

    @staticmethod
    def admin_get_provider(db: Session, key: str) -> dict[str, Any]:
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        keys = (
            db.execute(select(PartnerApiKey).where(PartnerApiKey.provider_id == p.id).order_by(PartnerApiKey.created_at.desc()))
            .scalars()
            .all()
        )
        recent = (
            db.execute(
                select(PartnerScreening)
                .where(PartnerScreening.provider_id == p.id)
                .order_by(PartnerScreening.created_at.desc())
                .limit(25)
            )
            .scalars()
            .all()
        )
        partner_cfg = _loads(p.config_json, {})
        recruit = None
        if p.key == "zoho" and p.mapped_org_id:
            try:
                from app.services.zoho_recruit_connection_service import recruit_status

                recruit = recruit_status(
                    db,
                    str(p.mapped_org_id),
                    partner_config=partner_cfg if isinstance(partner_cfg, dict) else {},
                )
            except Exception:
                recruit = {"connected": False, "oauth_app_ready": False}
        return {
            "provider": PartnerService._provider_dict(p),
            "keys": [
                {
                    "id": k.id,
                    "environment": k.environment,
                    "key_prefix": k.key_prefix,
                    "is_active": bool(k.is_active),
                    "created_at": k.created_at.isoformat() + "Z" if k.created_at else None,
                    "last_used_at": k.last_used_at.isoformat() + "Z" if k.last_used_at else None,
                    "revoked_at": k.revoked_at.isoformat() + "Z" if k.revoked_at else None,
                }
                for k in keys
            ],
            "recent_jobs": [
                {
                    "id": s.id,
                    "partner_reference_id": s.partner_reference_id,
                    "job_title": s.job_title,
                    "candidate_name": s.candidate_name,
                    "candidate_phone": s.candidate_phone,
                    "preferred_language": s.preferred_language,
                    "status": s.status,
                    "result_status": s.result_status,
                    "candidate_score": s.candidate_score,
                    "total_charge_gbp": s.total_charge_gbp,
                    "screening_link": s.screening_link,
                    "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
                }
                for s in recent
            ],
            "endpoints": {
                "inbound": "https://api.voxbulk.com/partner/v1/screenings",
                "results": "https://api.voxbulk.com/partner/v1/results",
                "health": "https://api.voxbulk.com/partner/v1/health",
                "oauth_callback": "https://api.voxbulk.com/partner/v1/oauth/zoho/callback",
            },
            "recruit": recruit,
        }

    @staticmethod
    def _provider_dict(p: PartnerProvider) -> dict[str, Any]:
        return {
            "key": p.key,
            "label": p.label,
            "enabled": bool(p.enabled),
            "mode": p.mode,
            "mapped_org_id": p.mapped_org_id,
            "result_webhook_url": p.result_webhook_url,
            "webhook_secret_set": bool(p.webhook_secret_enc),
            "connection_fee_gbp": float(p.connection_fee_gbp or 0),
            "per_minute_gbp": float(p.per_minute_gbp or 0),
            "commission_pct": float(p.commission_pct or 0),
            "est_cost_per_completed_gbp": float(p.est_cost_per_completed_gbp or 0),
            "config": _loads(p.config_json, {}),
            "last_health_at": p.last_health_at.isoformat() + "Z" if p.last_health_at else None,
            "last_health_ok": p.last_health_ok,
            "last_health_message": p.last_health_message,
            "partner_name_header": p.key,
        }

    @staticmethod
    def admin_update_provider(db: Session, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        if "enabled" in payload and payload["enabled"] is not None:
            p.enabled = bool(payload["enabled"])
        if payload.get("mode") in {"sandbox", "live"}:
            p.mode = payload["mode"]
        if "mapped_org_id" in payload:
            org_id = payload["mapped_org_id"]
            if org_id:
                if db.get(Organisation, org_id) is None:
                    raise HTTPException(status_code=400, detail="Organisation not found")
                p.mapped_org_id = org_id
            else:
                p.mapped_org_id = None
        if "result_webhook_url" in payload and payload["result_webhook_url"] is not None:
            p.result_webhook_url = str(payload["result_webhook_url"] or "").strip()
        if payload.get("webhook_secret"):
            p.webhook_secret_enc = get_encryptor().encrypt_str(str(payload["webhook_secret"]))
        for field, attr in (
            ("connection_fee_gbp", "connection_fee_gbp"),
            ("per_minute_gbp", "per_minute_gbp"),
            ("commission_pct", "commission_pct"),
            ("est_cost_per_completed_gbp", "est_cost_per_completed_gbp"),
        ):
            if payload.get(field) is not None:
                setattr(p, attr, float(payload[field]))
        if isinstance(payload.get("config"), dict):
            existing = _loads(p.config_json, {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update(payload["config"])
            p.config_json = json.dumps(existing)
        p.updated_at = _now()
        db.add(p)
        db.commit()
        db.refresh(p)
        return PartnerService.admin_get_provider(db, key)

    @staticmethod
    def admin_generate_key(db: Session, key: str, *, environment: str) -> dict[str, Any]:
        if environment not in {"sandbox", "live"}:
            raise HTTPException(status_code=400, detail="environment must be sandbox or live")
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        # revoke previous active keys for this env
        existing = (
            db.execute(
                select(PartnerApiKey).where(
                    PartnerApiKey.provider_id == p.id,
                    PartnerApiKey.environment == environment,
                    PartnerApiKey.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        for row in existing:
            row.is_active = False
            row.revoked_at = _now()
            db.add(row)
        raw = generate_raw_api_key(provider_key=p.key, environment=environment)
        key_row = PartnerApiKey(
            id=_new_id(),
            provider_id=p.id,
            environment=environment,
            key_prefix=raw[:12],
            key_hash=hash_api_key(raw),
            is_active=True,
            created_at=_now(),
        )
        db.add(key_row)
        p.updated_at = _now()
        db.add(p)
        db.commit()
        return {
            "api_key": raw,
            "environment": environment,
            "partner_name": p.key,
            "key_prefix": key_row.key_prefix,
            "created_at": key_row.created_at.isoformat() + "Z",
            "warning": "Store this key now. It will not be shown again.",
        }

    @staticmethod
    def admin_create_test_screening(
        db: Session,
        key: str,
        *,
        partner_reference_id: str,
        job_title: str,
        screening_questions: list[str],
        candidate_name: str,
        candidate_phone: str,
        preferred_language: str,
        callback_url: str | None = None,
        job_description: str | None = None,
        candidate_email: str | None = None,
    ) -> PartnerScreening:
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        if not p.enabled:
            raise HTTPException(status_code=400, detail="Enable the partner before sending a test")
        if not p.mapped_org_id:
            raise HTTPException(status_code=400, detail="Map a VoxBulk organisation first")
        key_row = db.execute(
            select(PartnerApiKey).where(
                PartnerApiKey.provider_id == p.id,
                PartnerApiKey.environment == p.mode,
                PartnerApiKey.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if key_row is None:
            raise HTTPException(status_code=400, detail=f"Generate an active {p.mode} API key first")
        principal = PartnerPrincipal(
            provider=p,
            api_key=key_row,
            partner_name=p.key,
            environment=key_row.environment,
            org_id=str(p.mapped_org_id),
        )
        return PartnerService.create_screening(
            db,
            principal,
            partner_reference_id=partner_reference_id,
            job_title=job_title,
            screening_questions=screening_questions,
            candidate_name=candidate_name,
            candidate_phone=candidate_phone,
            preferred_language=preferred_language,
            callback_url=callback_url,
            job_description=job_description,
            candidate_email=candidate_email,
        )

    @staticmethod
    def admin_oauth_start(db: Session, key: str) -> dict[str, Any]:
        if key != "zoho":
            raise HTTPException(status_code=400, detail="OAuth connect is only for Zoho Recruit")
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        if not p.mapped_org_id:
            raise HTTPException(status_code=400, detail="Map a VoxBulk organisation first")
        from app.services.zoho_recruit_connection_service import oauth_start

        cfg = _loads(p.config_json, {})
        url = oauth_start(org_id=str(p.mapped_org_id), partner_config=cfg if isinstance(cfg, dict) else {})
        return {"authorize_url": url}

    @staticmethod
    def admin_oauth_disconnect(db: Session, key: str) -> dict[str, Any]:
        if key != "zoho":
            raise HTTPException(status_code=400, detail="OAuth disconnect is only for Zoho Recruit")
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        if not p.mapped_org_id:
            raise HTTPException(status_code=400, detail="Map a VoxBulk organisation first")
        from app.services.zoho_recruit_connection_service import oauth_disconnect, recruit_status

        oauth_disconnect(db, str(p.mapped_org_id))
        cfg = _loads(p.config_json, {})
        return {
            "ok": True,
            "message": "Zoho Recruit disconnected",
            "recruit": recruit_status(db, str(p.mapped_org_id), partner_config=cfg if isinstance(cfg, dict) else {}),
        }

    @staticmethod
    def admin_test_recruit(db: Session, key: str) -> dict[str, Any]:
        """Call Zoho Recruit users API with the mapped org's OAuth token."""
        if key != "zoho":
            raise HTTPException(status_code=400, detail="Recruit test is only for Zoho")
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        if not p.mapped_org_id:
            raise HTTPException(status_code=400, detail="Map a VoxBulk organisation first")
        from app.services.zoho_recruit_connection_service import (
            _ensure_access_token,
            recruit_status,
        )

        cfg = _loads(p.config_json, {})
        partner_cfg = cfg if isinstance(cfg, dict) else {}
        status_info = recruit_status(db, str(p.mapped_org_id), partner_config=partner_cfg)
        if not status_info.get("connected"):
            return {"ok": False, "message": "Zoho Recruit is not connected — click Connect first", "recruit": status_info}
        try:
            import httpx

            token, api_domain = _ensure_access_token(db, str(p.mapped_org_id), partner_config=partner_cfg)
            headers = {"Authorization": f"Zoho-oauthtoken {token}"}
            name = ""
            with httpx.Client(timeout=20.0) as client:
                # Prefer users (needs ZohoRecruit.users.ALL). Fall back to Candidates
                # so older tokens still pass after we fixed the recruit.zoho.* host.
                user_res = client.get(
                    f"https://{api_domain}/recruit/v2/users",
                    headers=headers,
                    params={"type": "CurrentUser"},
                )
                if user_res.status_code < 400:
                    users = (user_res.json() or {}).get("users") or []
                    if users and isinstance(users[0], dict):
                        name = str(users[0].get("full_name") or users[0].get("email") or "").strip()
                else:
                    cand_res = client.get(
                        f"https://{api_domain}/recruit/v2/Candidates",
                        headers=headers,
                        params={"per_page": 1},
                    )
                    # 200/204 = authorized; 401 scope mismatch on users alone is not a hard fail.
                    if cand_res.status_code >= 400 and cand_res.status_code != 204:
                        detail = (user_res.text or cand_res.text or "")[:200]
                        if "OAUTH_SCOPE_MISMATCH" in (user_res.text or ""):
                            return {
                                "ok": False,
                                "message": (
                                    "Recruit host OK, but token is missing users/notes scopes — "
                                    "click Connect Zoho Recruit again and Accept the new permissions"
                                ),
                                "recruit": status_info,
                                "api_domain": api_domain,
                            }
                        return {
                            "ok": False,
                            "message": f"Zoho Recruit API error HTTP {cand_res.status_code}: {detail}",
                            "recruit": status_info,
                            "api_domain": api_domain,
                        }
            return {
                "ok": True,
                "message": f"Zoho Recruit OK{f' — {name}' if name else f' — {api_domain}'}",
                "recruit": status_info,
                "api_domain": api_domain,
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)[:300], "recruit": status_info}

    @staticmethod
    def admin_test_webhook(db: Session, key: str) -> dict[str, Any]:
        """POST a sample result payload to the configured result webhook URL."""
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        url = str(p.result_webhook_url or "").strip()
        if not url:
            return {"ok": False, "message": "Set Result webhook URL and Save first"}
        payload = {
            "partner_reference_id": "voxbulk-test-ref",
            "screening_id": "test",
            "candidate_score": 88,
            "status": "passed",
            "report_url": "https://dashboard.voxbulk.com/",
            "call_duration_minutes": 10.5,
            "total_charge_amount": 5.18,
            "provider": p.key,
            "test": True,
        }
        headers = {"Content-Type": "application/json", "X-Voxbulk-Partner-Event": "screening.result.test"}
        body = json.dumps(payload, separators=(",", ":"))
        if p.webhook_secret_enc:
            try:
                secret = get_encryptor().decrypt_str(p.webhook_secret_enc)
                sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
                headers["X-Voxbulk-Signature"] = sig
            except Exception:
                pass
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, content=body, headers=headers)
            if resp.status_code >= 400:
                return {"ok": False, "message": f"Webhook HTTP {resp.status_code}: {resp.text[:200]}"}
            return {"ok": True, "message": f"Webhook delivered (HTTP {resp.status_code})"}
        except Exception as exc:
            return {"ok": False, "message": str(exc)[:300]}

    @staticmethod
    def admin_ping_health(db: Session, key: str) -> dict[str, Any]:
        p = PartnerService.get_provider(db, key)
        if p is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        ok = bool(p.enabled and p.mapped_org_id)
        msg = "OK – partner configured" if ok else "Not ready – enable partner and map an organisation"
        has_key = db.execute(
            select(func.count())
            .select_from(PartnerApiKey)
            .where(
                PartnerApiKey.provider_id == p.id,
                PartnerApiKey.environment == p.mode,
                PartnerApiKey.is_active.is_(True),
            )
        ).scalar() or 0
        if ok and not has_key:
            ok = False
            msg = f"No active {p.mode} API key"
        p.last_health_at = _now()
        p.last_health_ok = ok
        p.last_health_message = msg
        p.updated_at = _now()
        db.add(p)
        db.commit()
        return {"ok": ok, "message": msg, "checked_at": p.last_health_at.isoformat() + "Z"}


def require_partner_principal(
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_partner_name: str | None = Header(default=None, alias="X-Partner-Name"),
) -> PartnerPrincipal:
    return PartnerService.authenticate(db, api_key=x_api_key, partner_name=x_partner_name)
