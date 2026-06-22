from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import safe_log_extra
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.promo_offer import PromoOffer
from app.models.subscription import Subscription
from app.models.user import User
from app.models.membership import OrganisationMembership
from app.services.billing_event_email_service import BillingEventEmailService

logger = logging.getLogger(__name__)


class UsageWalletService:
    @staticmethod
    def get_current(db: Session, org_id: str) -> OrgUsagePeriod | None:
        now = datetime.utcnow()
        return (
            db.execute(
                select(OrgUsagePeriod)
                .where(OrgUsagePeriod.org_id == org_id, OrgUsagePeriod.period_end >= now)
                .order_by(OrgUsagePeriod.period_end.desc(), OrgUsagePeriod.updated_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    @staticmethod
    def bootstrap_from_promo(db: Session, *, org_id: str, promo: PromoOffer, subscription: Subscription) -> OrgUsagePeriod:
        now = datetime.utcnow()
        existing = UsageWalletService.get_current(db, org_id)
        if existing is not None:
            return existing

        plan = db.execute(select(Plan).where(Plan.id == subscription.plan_id)).scalar_one_or_none()
        trial_days = int(promo.trial_days or 0)
        period_end = subscription.current_period_end or (now + timedelta(days=max(trial_days, 30)))

        calls = int(promo.calls_included or (plan.calls_included if plan else 0))
        wa = int(promo.whatsapp_included or (plan.whatsapp_included if plan else 0))
        sms = int(promo.sms_included or (plan.sms_included if plan else 0))
        cv_scans = int(getattr(plan, "cv_scans_included", 0) or 0) if plan else 0
        overage = int(promo.overage_per_min_pence or (plan.overage_per_min_pence if plan else 20))
        pack_credits = int(promo.free_call_credits or 0)
        pack_expires = now + timedelta(days=90) if pack_credits > 0 else None

        row = OrgUsagePeriod(
            org_id=org_id,
            period_start=now,
            period_end=period_end,
            status="trial" if subscription.status == "trial" else "active",
            plan_code=(plan.code if plan else promo.plan_code),
            promo_code=promo.code,
            calls_included=calls,
            whatsapp_included=wa,
            sms_included=sms,
            cv_scans_included=cv_scans,
            pack_credits_included=pack_credits,
            pack_credits_expires_at=pack_expires,
            overage_per_min_pence=overage,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def bootstrap_from_plan(db: Session, *, org_id: str, subscription: Subscription) -> OrgUsagePeriod:
        plan = db.execute(select(Plan).where(Plan.id == subscription.plan_id)).scalar_one_or_none()
        if plan is None:
            raise ValueError("Plan not found")
        fake = PromoOffer(
            code="",
            name=plan.name,
            offer_type="dental_plan",
            plan_code=plan.code,
            trial_days=int(plan.trial_days_default or 0),
            calls_included=int(plan.calls_included or 0),
            whatsapp_included=int(plan.whatsapp_included or 0),
            sms_included=int(plan.sms_included or 0),
            overage_per_min_pence=int(plan.overage_per_min_pence or 0),
        )
        return UsageWalletService.bootstrap_from_promo(db, org_id=org_id, promo=fake, subscription=subscription)

    @staticmethod
    def summary_dict(row: OrgUsagePeriod, db: Session | None = None, org_id: str | None = None) -> dict:
        def pct(used: int, included: int) -> float:
            if included <= 0:
                return 0.0
            return round((used / included) * 100, 1)

        calls_used = int(row.calls_used or 0)
        calls_included = int(row.calls_included or 0)
        wa_used = int(row.whatsapp_used or 0)
        wa_included = int(row.whatsapp_included or 0)
        sms_used = int(row.sms_used or 0)
        sms_included = int(row.sms_included or 0)
        cv_used = int(getattr(row, "cv_scans_used", 0) or 0)
        cv_included = int(getattr(row, "cv_scans_included", 0) or 0)
        pack_used = int(row.pack_credits_used or 0)
        pack_included = int(row.pack_credits_included or 0)

        breakdown = UsageWalletService._overage_breakdown_pence(row, db, org_id)
        est_overage_pence = int(breakdown.get("total_overage_pence") or 0)

        summary = {
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "status": row.status,
            "plan_code": row.plan_code,
            "promo_code": row.promo_code,
            "calls": {
                "used": calls_used,
                "included": calls_included,
                "remaining": max(0, calls_included - calls_used),
                "percent": pct(calls_used, calls_included),
            },
            "whatsapp": {
                "used": wa_used,
                "included": wa_included,
                "remaining": max(0, wa_included - wa_used),
                "percent": pct(wa_used, wa_included),
            },
            "sms": {
                "used": sms_used,
                "included": sms_included,
                "remaining": max(0, sms_included - sms_used),
                "percent": pct(sms_used, sms_included),
            },
            "cv_scans": {
                "used": cv_used,
                "included": cv_included,
                "remaining": max(0, cv_included - cv_used),
                "percent": pct(cv_used, cv_included),
            },
            "pack_credits": {
                "used": pack_used,
                "included": pack_included,
                "remaining": max(0, pack_included - pack_used),
                "expires_at": row.pack_credits_expires_at.isoformat() if row.pack_credits_expires_at else None,
            },
            "overage_per_min_pence": int(row.overage_per_min_pence or 0),
            "wa_overage_unit_pence": int(breakdown.get("wa_extra_pence") or 49),
            "estimated_overage_gbp": round(est_overage_pence / 100, 2),
            "estimated_overage_pence": est_overage_pence,
            "warn_at_80": any(
                pct(x, y) >= 80 for x, y in ((calls_used, calls_included), (wa_used, wa_included), (sms_used, sms_included))
            ),
        }
        if db is not None and org_id:
            from app.services.package_entitlement_service import PackageEntitlementService

            ent = PackageEntitlementService.for_usage_row(row, plan_code=row.plan_code)
            summary = PackageEntitlementService.merge_into_summary(summary, ent)
            if ent.get("shared_package_pool"):
                summary["warn_at_80"] = float(ent.get("package_percent") or 0) >= 80
        return summary

    @staticmethod
    def _overage_breakdown_pence(row: OrgUsagePeriod, db: Session | None = None, org_id: str | None = None) -> dict[str, int]:
        from app.services.package_entitlement_service import PackageEntitlementService

        wa_extra_pence = 49
        if db is not None and org_id:
            try:
                from app.models.organisation import Organisation
                from app.services.plan_price_service import PlanPriceService

                org = db.get(Organisation, org_id)
                if org is not None:
                    rates = PlanPriceService.rates_for_org(db, org)
                    wa_extra_pence = int(rates.get("wa_extra_minor") or 49)
            except Exception:
                pass

        if PackageEntitlementService.shared_pool_active(row, row.plan_code):
            included = PackageEntitlementService.package_included_units(row)
            calls_used = int(row.calls_used or 0)
            wa_used = int(row.whatsapp_used or 0)
            wa_covered = min(wa_used, included)
            calls_covered = min(calls_used, max(0, included - wa_covered))
            calls_overage = max(0, calls_used - calls_covered)
            wa_overage_units = max(0, wa_used - wa_covered)
            call_pence = calls_overage * int(row.overage_per_min_pence or 0)
            wa_pence = wa_overage_units * wa_extra_pence
            return {
                "call_minutes_overage": calls_overage,
                "call_overage_pence": call_pence,
                "wa_recipient_overage": wa_overage_units,
                "wa_overage_pence": wa_pence,
                "total_overage_pence": call_pence + wa_pence,
                "wa_extra_pence": wa_extra_pence,
            }

        calls_overage = max(0, int(row.calls_used or 0) - int(row.calls_included or 0))
        call_pence = calls_overage * int(row.overage_per_min_pence or 0)
        wa_used = int(row.whatsapp_used or 0)
        wa_included = int(row.whatsapp_included or 0)
        wa_overage_units = max(0, wa_used - wa_included)
        wa_pence = wa_overage_units * wa_extra_pence
        return {
            "call_minutes_overage": calls_overage,
            "call_overage_pence": call_pence,
            "wa_recipient_overage": wa_overage_units,
            "wa_overage_pence": wa_pence,
            "total_overage_pence": call_pence + wa_pence,
            "wa_extra_pence": wa_extra_pence,
        }

    @staticmethod
    def _calc_overage_pence(row: OrgUsagePeriod, db: Session | None = None, org_id: str | None = None) -> int:
        breakdown = UsageWalletService._overage_breakdown_pence(row, db, org_id)
        return int(breakdown["total_overage_pence"])

    @staticmethod
    def _overage_breakdown_pence_from_invoiced(
        invoiced_pence: int,
        wa_extra_pence: int,
        overage_per_min_pence: int,
    ) -> dict[str, int]:
        """Best-effort split of already-invoiced overage (WA priced first, then call minutes)."""
        remaining = max(0, int(invoiced_pence or 0))
        wa_unit = max(1, int(wa_extra_pence or 49))
        wa_units = remaining // wa_unit if remaining >= wa_unit else 0
        wa_pence = wa_units * wa_unit
        remaining -= wa_pence
        rate = max(0, int(overage_per_min_pence or 0))
        call_mins = remaining // rate if rate > 0 and remaining >= rate else 0
        call_pence = call_mins * rate
        return {
            "wa_recipient_overage": wa_units,
            "wa_overage_pence": wa_pence,
            "call_minutes_overage": call_mins,
            "call_overage_pence": call_pence,
        }

    @staticmethod
    def get_org_billing_email(db: Session, org_id: str) -> str | None:
        em = db.execute(
            select(User.email)
            .join(OrganisationMembership, OrganisationMembership.user_id == User.id)
            .where(OrganisationMembership.org_id == org_id, User.is_active.is_(True))
            .order_by(User.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        return str(em).strip().lower() if em else None

    @staticmethod
    def sync_plan_limits(db: Session, *, org_id: str, plan: Plan, subscription: Subscription) -> OrgUsagePeriod | None:
        row = UsageWalletService.get_current(db, org_id)
        now = datetime.utcnow()
        if row is None:
            return UsageWalletService.bootstrap_from_plan(db, org_id=org_id, subscription=subscription)
        row.plan_code = plan.code
        row.calls_included = int(plan.calls_included or 0)
        row.whatsapp_included = int(plan.whatsapp_included or 0)
        row.sms_included = int(plan.sms_included or 0)
        row.cv_scans_included = int(getattr(plan, "cv_scans_included", 0) or 0)
        row.overage_per_min_pence = int(plan.overage_per_min_pence or 0)
        row.status = "trial" if subscription.status == "trial" else "active"
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _usage_percent(used: int, included: int) -> float:
        if included <= 0:
            return 0.0
        return round((used / included) * 100, 1)

    @staticmethod
    def _channels_at_or_above(
        row: OrgUsagePeriod,
        threshold: float = 80.0,
        *,
        db: Session | None = None,
        org_id: str | None = None,
    ) -> list[tuple[str, int, int, float]]:
        from app.services.package_entitlement_service import PackageEntitlementService

        if PackageEntitlementService.shared_pool_active(row, row.plan_code):
            included = PackageEntitlementService.package_included_units(row)
            used = PackageEntitlementService.package_used_units(row)
            if included <= 0:
                return []
            pct = UsageWalletService._usage_percent(used, included)
            if pct >= threshold:
                return [("Package (WA + AI)", used, included, pct)]
            return []

        out: list[tuple[str, int, int, float]] = []
        checks = (
            ("Calls", int(row.calls_used or 0), int(row.calls_included or 0)),
            ("WhatsApp", int(row.whatsapp_used or 0), int(row.whatsapp_included or 0)),
            ("SMS", int(row.sms_used or 0), int(row.sms_included or 0)),
        )
        for label, used, included in checks:
            if included <= 0:
                continue
            pct = UsageWalletService._usage_percent(used, included)
            if pct >= threshold:
                out.append((label, used, included, pct))
        return out

    @staticmethod
    def maybe_send_100_warning(db: Session, *, org_id: str, row: OrgUsagePeriod | None = None) -> bool:
        row = row or UsageWalletService.get_current(db, org_id)
        if row is None or row.warned_at_100:
            return False

        hot = UsageWalletService._channels_at_or_above(row, 100.0, db=db, org_id=org_id)
        if not hot:
            return False

        em = UsageWalletService.get_org_billing_email(db, org_id)
        if not em:
            return False

        org = db.get(Organisation, org_id)
        org_name = (org.name if org else "Your organisation") or "Your organisation"
        lines = [
            f"<div><strong>{label}</strong>: {used} of {included} ({pct}%)</div>"
            for label, used, included, pct in hot
        ]
        summary = ", ".join(f"{label} {pct}%" for label, _, _, pct in hot)
        variables = {
            "organisation_name": org_name,
            "plan_code": str(row.plan_code or "your plan"),
            "usage_summary": summary,
            "usage_details_html": "".join(lines),
            "period_end": row.period_end.strftime("%d %b %Y") if row.period_end else "",
            "message": f"Allowance fully used: {summary}",
        }

        from app.services.transactional_email_service import TransactionalEmailService

        sent, _err = TransactionalEmailService.send_templated_optional(
            db,
            template_key="usage_warning_100",
            to_email=em,
            variables=variables,
        )
        if sent:
            row.warned_at_100 = True
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            return True
        return False

    @staticmethod
    def maybe_send_80_warning(db: Session, *, org_id: str, row: OrgUsagePeriod | None = None) -> bool:
        row = row or UsageWalletService.get_current(db, org_id)
        if row is None or row.warned_at_80:
            return False

        hot = UsageWalletService._channels_at_or_above(row, 80.0, db=db, org_id=org_id)
        if not hot:
            return False

        em = UsageWalletService.get_org_billing_email(db, org_id)
        if not em:
            return False

        org = db.get(Organisation, org_id)
        org_name = (org.name if org else "Your organisation") or "Your organisation"
        lines = [
            f"<div><strong>{label}</strong>: {used} of {included} ({pct}%)</div>"
            for label, used, included, pct in hot
        ]
        summary = ", ".join(f"{label} {pct}%" for label, _, _, pct in hot)
        variables = {
            "organisation_name": org_name,
            "plan_code": str(row.plan_code or "your plan"),
            "usage_summary": summary,
            "usage_details_html": "".join(lines),
            "period_end": row.period_end.strftime("%d %b %Y") if row.period_end else "",
            "message": f"Usage alert: {summary}",
        }

        from app.services.transactional_email_service import TransactionalEmailService

        sent, _err = TransactionalEmailService.send_templated_optional(
            db,
            template_key="usage_warning",
            to_email=em,
            variables=variables,
        )
        if sent:
            row.warned_at_80 = True
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            return True
        return False

    @staticmethod
    def _after_usage_increment(db: Session, *, org_id: str, row: OrgUsagePeriod, client_email: str | None = None) -> None:
        em = (client_email or "").strip().lower() or UsageWalletService.get_org_billing_email(db, org_id) or ""
        if em:
            try:
                UsageWalletService.maybe_invoice_overage(db, org_id=org_id, client_email=em, row=row)
            except Exception as exc:
                logger.warning(
                    "usage_overage_invoice_failed",
                    extra=safe_log_extra(org_id=org_id, error=str(exc)[:500]),
                )
        try:
            UsageWalletService.maybe_send_80_warning(db, org_id=org_id, row=row)
            UsageWalletService.maybe_send_100_warning(db, org_id=org_id, row=row)
        except Exception as exc:
            logger.warning(
                "usage_warning_email_failed",
                extra=safe_log_extra(org_id=org_id, error=str(exc)[:500]),
            )

    @staticmethod
    def record_call_usage(
        db: Session,
        *,
        org_id: str,
        units: int = 1,
        client_email: str | None = None,
        commit: bool = True,
    ) -> OrgUsagePeriod | None:
        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return None
        row.calls_used = int(row.calls_used or 0) + max(0, int(units))
        row.updated_at = datetime.utcnow()
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
            UsageWalletService._after_usage_increment(db, org_id=org_id, row=row, client_email=client_email)
        return row

    @staticmethod
    def record_whatsapp_usage(
        db: Session,
        *,
        org_id: str,
        units: int = 1,
        client_email: str | None = None,
        commit: bool = True,
    ) -> OrgUsagePeriod | None:
        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return None
        row.whatsapp_used = int(row.whatsapp_used or 0) + max(0, int(units))
        row.updated_at = datetime.utcnow()
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
            UsageWalletService._after_usage_increment(db, org_id=org_id, row=row, client_email=client_email)
        return row

    @staticmethod
    def record_cv_scan_usage(
        db: Session,
        *,
        org_id: str,
        units: int = 1,
        client_email: str | None = None,
        commit: bool = True,
    ) -> OrgUsagePeriod | None:
        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return None
        row.cv_scans_used = int(getattr(row, "cv_scans_used", 0) or 0) + max(0, int(units))
        row.updated_at = datetime.utcnow()
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
            UsageWalletService._after_usage_increment(db, org_id=org_id, row=row, client_email=client_email)
        return row

    @staticmethod
    def _call_usage_minutes(
        db: Session,
        call_log_id: int | None,
        duration_seconds: int | None = None,
    ) -> int:
        import math

        secs = duration_seconds
        if call_log_id is not None and secs is None:
            from app.models.call_log import CallLog

            log = db.get(CallLog, call_log_id)
            if log is not None:
                if log.started_at and log.ended_at:
                    secs = int((log.ended_at - log.started_at).total_seconds())
                elif log.answered_at and log.ended_at:
                    secs = int((log.ended_at - log.answered_at).total_seconds())
        if secs is None or secs <= 0:
            return 0
        from app.services.billing_call_minutes import billable_call_minutes

        return billable_call_minutes(secs)

    @staticmethod
    def on_call_completed(
        db: Session,
        *,
        org_id: str,
        call_log_id: int | None = None,
        duration_seconds: int | None = None,
    ) -> None:
        from app.models.call_log import CallLog

        if call_log_id is not None:
            log = db.get(CallLog, call_log_id)
            if log is not None and log.usage_metered:
                return
        try:
            units = UsageWalletService._call_usage_minutes(db, call_log_id, duration_seconds)
            UsageWalletService.record_call_usage(db, org_id=org_id, units=units)
            if call_log_id is not None:
                log = db.get(CallLog, call_log_id)
                if log is not None and not log.usage_metered:
                    log.usage_metered = True
                    db.add(log)
                    db.commit()
        except Exception:
            pass

    @staticmethod
    def maybe_invoice_overage(
        db: Session,
        *,
        org_id: str,
        client_email: str,
        row: OrgUsagePeriod | None = None,
        min_invoice_pence: int = 100,
    ) -> dict | None:
        """Invoice uninvoiced usage overage — GoCardless DD when available, else internal invoice email."""
        em = (client_email or "").strip().lower()
        if not em:
            return None
        row = row or UsageWalletService.get_current(db, org_id)
        if row is None:
            return None

        org = db.get(Organisation, org_id)
        if org is not None and not bool(getattr(org, "allow_overage", True)):
            return None

        total_overage = UsageWalletService._calc_overage_pence(row, db, org_id)
        already = int(row.overage_invoiced_pence or 0)
        delta = total_overage - already
        if delta < int(min_invoice_pence):
            return None

        breakdown = UsageWalletService._overage_breakdown_pence(row, db, org_id)
        already_breakdown = UsageWalletService._overage_breakdown_pence_from_invoiced(
            already, breakdown["wa_extra_pence"], int(row.overage_per_min_pence or 0)
        )
        call_delta = max(0, breakdown["call_overage_pence"] - already_breakdown["call_overage_pence"])
        wa_delta = max(0, breakdown["wa_overage_pence"] - already_breakdown["wa_overage_pence"])
        line_items: list[dict[str, Any]] = []
        if wa_delta > 0:
            wa_units = breakdown["wa_recipient_overage"] - already_breakdown.get("wa_recipient_overage", 0)
            unit = int(breakdown["wa_extra_pence"] or 49)
            line_items.append(
                {
                    "description": f"WA survey overage ({max(1, wa_units)} extra recipient{'s' if wa_units != 1 else ''} × £{unit / 100:.2f})",
                    "quantity": max(1, wa_units),
                    "unit_pence": unit,
                    "total_pence": wa_delta,
                    "kind": "wa_survey",
                }
            )
        if call_delta > 0:
            mins = breakdown["call_minutes_overage"] - already_breakdown.get("call_minutes_overage", 0)
            rate = int(row.overage_per_min_pence or 0)
            line_items.append(
                {
                    "description": f"AI call minutes overage ({max(1, mins)} min × £{rate / 100:.2f}/min)",
                    "quantity": max(1, mins),
                    "unit_pence": rate,
                    "total_pence": call_delta,
                    "kind": "call_minutes",
                }
            )
        if not line_items:
            line_items = [
                {
                    "description": "Plan usage overage (WA survey recipients & call minutes)",
                    "quantity": 1,
                    "unit_pence": delta,
                    "total_pence": delta,
                    "kind": "combined",
                }
            ]

        org = db.get(Organisation, org_id)
        org_name = (org.name if org else "your organisation") or "your organisation"
        org_label = org_name[:20].replace(" ", "")
        description = f"VOXBULK usage overage — {org_name}"[:255]

        gc_result: dict[str, Any] | None = None
        try:
            from app.services.gocardless_service import BillingService

            gc_result = BillingService.collect_mandate_payment(
                db,
                org_id=org_id,
                amount_pence=delta,
                description=description,
                metadata={"billing": "overage"},
            )
        except Exception as exc:
            logger.warning(
                "usage_overage_gocardless_collect_failed",
                extra=safe_log_extra(org_id=org_id, amount_pence=delta, error=str(exc)[:500]),
            )

        payment_id = str((gc_result or {}).get("payment_id") or "").strip()
        if payment_id:
            from app.services.invoice_service import InvoiceService

            payment_status = str((gc_result or {}).get("status") or "pending_submission").lower()
            invoice_status = "paid" if payment_status == "confirmed" else "pending"
            invoice_row, invoice_was_new, emailed = InvoiceService.issue_from_payment(
                db,
                org_id=org_id,
                client_email=em,
                subtotal_pence=delta,
                currency="GBP",
                description=description,
                provider="gocardless",
                external_invoice_id=payment_id,
                payment_reference=payment_id,
                payment_method="gocardless",
                status=invoice_status,
                line_items=line_items,
            )
            row.overage_invoiced_pence = already + delta
            row.last_overage_invoice_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            logger.info(
                "usage_overage_gocardless_invoiced",
                extra=safe_log_extra(
                    org_id=org_id,
                    invoice_id=invoice_row.id,
                    payment_id=payment_id,
                    amount_gbp_pence=delta,
                    invoice_was_new=invoice_was_new,
                    emailed=emailed,
                    payment_status=payment_status,
                ),
            )
            return {
                "invoice_id": invoice_row.id,
                "external_invoice_id": payment_id,
                "amount_gbp_pence": delta,
                "provider": "gocardless",
                "payment_id": payment_id,
                "payment_status": payment_status,
                "invoice_was_new": invoice_was_new,
                "emailed": emailed,
            }

        ext_id = f"OVG-{org_label}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        overage_desc = "Plan usage overage (WA survey recipients & call minutes)"
        invoice_row, invoice_was_new, sent = BillingEventEmailService.create_invoice(
            db,
            provider="internal_overage",
            external_invoice_id=ext_id,
            org_id=org_id,
            client_email=em,
            amount_gbp_pence=delta,
            currency="GBP",
            status="issued",
            description=overage_desc,
            line_items=line_items,
            payment_method="account_billing",
            payment_reference=ext_id,
            variables={
                "invoice_id": ext_id,
                "amount_gbp_pence": str(delta),
                "amount": f"£{delta / 100:.2f}",
                "currency": "GBP",
                "invoice_status": "issued",
                "message": f"Usage overage invoice for {org_name}",
            },
        )
        row.overage_invoiced_pence = already + delta
        row.last_overage_invoice_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return {
            "invoice_id": invoice_row.id,
            "external_invoice_id": ext_id,
            "amount_gbp_pence": delta,
            "provider": "internal_overage",
            "invoice_was_new": invoice_was_new,
            "emailed": sent,
        }

    @staticmethod
    def rollover_due_periods(db: Session, *, as_of: datetime | None = None) -> dict:
        """Close expired usage periods, invoice remaining overage, and open fresh periods."""
        now = as_of or datetime.utcnow()
        stats = {"closed": 0, "opened": 0, "overage_invoices": 0, "skipped": 0}

        expired = list(
            db.execute(
                select(OrgUsagePeriod).where(
                    OrgUsagePeriod.period_end <= now,
                    OrgUsagePeriod.status.in_(["active", "trial"]),
                )
            ).scalars().all()
        )

        for row in expired:
            em = UsageWalletService.get_org_billing_email(db, row.org_id)
            if em:
                inv = UsageWalletService.maybe_invoice_overage(db, org_id=row.org_id, client_email=em, row=row)
                if inv:
                    stats["overage_invoices"] += 1

            row.status = "closed"
            row.updated_at = now
            db.add(row)
            stats["closed"] += 1

            if UsageWalletService.get_current(db, row.org_id) is not None:
                continue

            sub = (
                db.execute(
                    select(Subscription)
                    .where(Subscription.org_id == row.org_id)
                    .order_by(Subscription.updated_at.desc(), Subscription.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if sub is None:
                stats["skipped"] += 1
                continue

            plan = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()
            if plan is None:
                stats["skipped"] += 1
                continue

            period_end = sub.current_period_end or (now + timedelta(days=30))
            if period_end <= now:
                period_end = now + timedelta(days=30)
                sub.current_period_end = period_end
                sub.updated_at = now
                db.add(sub)

            db.add(
                OrgUsagePeriod(
                    org_id=row.org_id,
                    period_start=now,
                    period_end=period_end,
                    status="trial" if sub.status == "trial" else "active",
                    plan_code=plan.code,
                    promo_code=None,
                    calls_included=int(plan.calls_included or 0),
                    whatsapp_included=int(plan.whatsapp_included or 0),
                    sms_included=int(plan.sms_included or 0),
                    overage_per_min_pence=int(plan.overage_per_min_pence or 0),
                    warned_at_80=False,
                    warned_at_100=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            stats["opened"] += 1

        db.commit()
        return stats
