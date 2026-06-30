"""Build and send weekly digest emails per organisation."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.billing_access_service import BillingAccessService
from app.services.org_rbac import ORG_DIGEST_ROLES
from app.services.product_email_triggers import ProductEmailTriggers


def _week_label(now: datetime | None = None) -> str:
    ref = now or datetime.utcnow()
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"


def _empty_row(text: str) -> str:
    return f'<p style="margin:0;font-size:13px;color:#6b6560;">{text}</p>'


class WeeklyDigestService:
    @staticmethod
    def build_digest_variables(db: Session, *, org_id: str, user_email: str) -> dict[str, str]:
        settings = get_settings()
        org = db.get(Organisation, org_id)
        em = (user_email or "").strip().lower()
        first = em.split("@")[0] if em and "@" in em else "there"
        dashboard = str(settings.dashboard_app_origin or "https://dashboard.voxbulk.com").rstrip("/")
        public = str(settings.public_app_origin or "https://voxbulk.com").rstrip("/")

        outstanding_minor = BillingAccessService.outstanding_invoice_minor(db, org_id)
        org_name = (org.name if org else "") or "Your organisation"

        open_tickets = 0
        try:
            from app.models.support_ticket import SupportTicket

            open_tickets = int(
                db.execute(
                    select(func.count())
                    .select_from(SupportTicket)
                    .where(
                        SupportTicket.org_id == org_id,
                        SupportTicket.status.in_(("open", "pending", "in_progress")),
                    )
                ).scalar_one()
                or 0
            )
        except Exception:
            open_tickets = 0

        survey_runs = interview_runs = 0
        try:
            from app.models.service_order import ServiceOrder

            week_start = datetime.utcnow() - timedelta(days=7)
            orders = list(
                db.execute(
                    select(ServiceOrder.service_code).where(
                        ServiceOrder.org_id == org_id,
                        ServiceOrder.updated_at >= week_start,
                    )
                ).all()
            )
            survey_runs = sum(1 for (code,) in orders if str(code or "") == "survey")
            interview_runs = sum(1 for (code,) in orders if str(code or "") == "interview")
        except Exception:
            pass

        usage_lines = [
            f"Survey campaigns active this week: {survey_runs}.",
            f"Interview campaigns active this week: {interview_runs}.",
        ]
        usage_summary_html = "".join(_empty_row(line) for line in usage_lines)

        alert_lines: list[str] = []
        if outstanding_minor > 0:
            alert_lines.append(f"Outstanding invoices: £{outstanding_minor / 100:.2f} due.")
        if open_tickets > 0:
            alert_lines.append(
                f"{open_tickets} open support ticket{'s' if open_tickets != 1 else ''} — "
                f'<a href="{dashboard}/account/support/tickets" style="color:#185fa5;">view tickets</a>.'
            )
        if not alert_lines:
            alert_lines.append("No billing or support alerts this week.")
        system_alerts = "".join(_empty_row(line) for line in alert_lines)

        return {
            "practice_name": org_name,
            "organisation_name": org_name,
            "digest_week_date": _week_label(),
            "digest_greeting": f"Good morning, {first}",
            "message_html": "",
            "recovery_items": _empty_row("Recovery outreach is managed from your Recovery module when enabled."),
            "usage_summary_html": usage_summary_html,
            "system_alerts": system_alerts,
            "interviews_recommended_percent": "",
            "satisfaction_score_percent": "",
            "recommend_percent": "",
            "dashboard_link": dashboard,
            "survey_results_link": f"{dashboard}/surveys/results",
            "interviews_results_link": f"{dashboard}/interviews/results",
            "privacy_link": f"{public}/privacy",
            "frequency_link": f"{dashboard}/settings/team",
            "unsubscribe_link": f"{dashboard}/settings/team",
        }

    @staticmethod
    def send_for_org(db: Session, *, org_id: str) -> int:
        rows = list(
            db.execute(
                select(User.email, OrganisationMembership.role)
                .join(OrganisationMembership, OrganisationMembership.user_id == User.id)
                .where(
                    OrganisationMembership.org_id == org_id,
                    User.is_active.is_(True),
                )
            ).all()
        )
        sent = 0
        for email, role in rows:
            role_norm = str(role or "member").strip().lower()
            if role_norm not in ORG_DIGEST_ROLES:
                continue
            em = str(email or "").strip().lower()
            if not em:
                continue
            vars_ = WeeklyDigestService.build_digest_variables(db, org_id=org_id, user_email=em)
            ok, _err = ProductEmailTriggers.send_weekly_digest(db, to_email=em, variables=vars_)
            if ok:
                sent += 1
        return sent

    @staticmethod
    def send_all_due(db: Session) -> int:
        org_ids = list(db.execute(select(Organisation.id).where(Organisation.is_suspended.is_(False))).scalars())
        total = 0
        for org_id in org_ids:
            total += WeeklyDigestService.send_for_org(db, org_id=str(org_id))
        return total
