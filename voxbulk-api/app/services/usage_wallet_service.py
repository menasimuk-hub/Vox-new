from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.promo_offer import PromoOffer
from app.models.subscription import Subscription
from app.models.user import User
from app.models.membership import OrganisationMembership
from app.services.billing_event_email_service import BillingEventEmailService


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
    def summary_dict(row: OrgUsagePeriod) -> dict:
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

        overage_calls = max(0, calls_used - calls_included)
        wa_overage_units = max(0, wa_used - wa_included)
        est_overage_pence = overage_calls * int(row.overage_per_min_pence or 0) + wa_overage_units * 49

        return {
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "status": row.status,
            "plan_code": row.plan_code,
            "promo_code": row.promo_code,
            "calls": {"used": calls_used, "included": calls_included, "percent": pct(calls_used, calls_included)},
            "whatsapp": {"used": wa_used, "included": wa_included, "percent": pct(wa_used, wa_included)},
            "sms": {"used": sms_used, "included": sms_included, "percent": pct(sms_used, sms_included)},
            "cv_scans": {"used": cv_used, "included": cv_included, "percent": pct(cv_used, cv_included)},
            "pack_credits": {
                "used": pack_used,
                "included": pack_included,
                "expires_at": row.pack_credits_expires_at.isoformat() if row.pack_credits_expires_at else None,
            },
            "overage_per_min_pence": int(row.overage_per_min_pence or 0),
            "estimated_overage_gbp": round(est_overage_pence / 100, 2),
            "warn_at_80": any(
                pct(x, y) >= 80 for x, y in ((calls_used, calls_included), (wa_used, wa_included), (sms_used, sms_included))
            ),
        }

    @staticmethod
    def _calc_overage_pence(row: OrgUsagePeriod, db: Session | None = None, org_id: str | None = None) -> int:
        calls_overage = max(0, int(row.calls_used or 0) - int(row.calls_included or 0))
        call_pence = calls_overage * int(row.overage_per_min_pence or 0)
        wa_used = int(row.whatsapp_used or 0)
        wa_included = int(row.whatsapp_included or 0)
        wa_overage_units = max(0, wa_used - wa_included)
        wa_extra_pence = 49
        if db is not None and org_id:
            try:
                from app.services.voxbulk_pricing_service import VoxbulkPricingService

                rates = VoxbulkPricingService.resolve_rates_for_org(db, org_id)
                wa_extra_pence = int(rates.get("wa_survey_extra_pence") or 49)
            except Exception:
                pass
        return call_pence + wa_overage_units * wa_extra_pence

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
    def _channels_at_or_above(row: OrgUsagePeriod, threshold: float = 80.0) -> list[tuple[str, int, int, float]]:
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
    def maybe_send_80_warning(db: Session, *, org_id: str, row: OrgUsagePeriod | None = None) -> bool:
        row = row or UsageWalletService.get_current(db, org_id)
        if row is None or row.warned_at_80:
            return False

        hot = UsageWalletService._channels_at_or_above(row, 80.0)
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
            UsageWalletService.maybe_invoice_overage(db, org_id=org_id, client_email=em, row=row)
        UsageWalletService.maybe_send_80_warning(db, org_id=org_id, row=row)

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
            return 1
        return max(1, int(math.ceil(secs / 60)))

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
        """Create + email an internal invoice for uninvoiced call overage."""
        em = (client_email or "").strip().lower()
        if not em:
            return None
        row = row or UsageWalletService.get_current(db, org_id)
        if row is None:
            return None

        total_overage = UsageWalletService._calc_overage_pence(row, db, org_id)
        already = int(row.overage_invoiced_pence or 0)
        delta = total_overage - already
        if delta < int(min_invoice_pence):
            return None

        org = db.get(Organisation, org_id)
        org_label = (org.name if org else org_id)[:20].replace(" ", "")
        ext_id = f"OVG-{org_label}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        invoice_row, created, sent = BillingEventEmailService.create_invoice(
            db,
            provider="internal_overage",
            external_invoice_id=ext_id,
            org_id=org_id,
            client_email=em,
            amount_gbp_pence=delta,
            currency="GBP",
            status="issued",
            variables={
                "invoice_id": ext_id,
                "amount_gbp_pence": str(delta),
                "amount": f"£{delta / 100:.2f}",
                "currency": "GBP",
                "invoice_status": "issued",
                "message": f"Usage overage invoice for {org.name if org else 'your organisation'}",
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
            "created": created,
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
                    created_at=now,
                    updated_at=now,
                )
            )
            stats["opened"] += 1

        db.commit()
        return stats
