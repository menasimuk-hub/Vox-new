"""Build and send weekly digest emails per organisation."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.models.user import User
from app.services.billing_access_service import BillingAccessService
from app.services.org_rbac import ORG_DIGEST_ROLES
from app.services.product_email_triggers import ProductEmailTriggers


def _week_label(now: datetime | None = None) -> str:
    ref = now or datetime.utcnow()
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"


def _week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    ref = now or datetime.utcnow()
    start = (ref - timedelta(days=ref.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)


def _empty_row(text: str) -> str:
    return f'<p style="margin:0;font-size:13px;color:#6b6560;">{text}</p>'


def _bullet_row(text: str) -> str:
    return f'<p style="margin:0 0 6px;font-size:13px;color:#3d3832;">• {text}</p>'


class WeeklyDigestService:
    @staticmethod
    def build_digest_variables(db: Session, *, org_id: str, user_email: str) -> dict[str, str]:
        settings = get_settings()
        org = db.get(Organisation, org_id)
        org_name = (org.name if org else "") or "Your organisation"
        em = (user_email or "").strip().lower()
        first = em.split("@")[0] if em and "@" in em else "there"
        dashboard = str(settings.dashboard_app_origin or "https://dashboard.voxbulk.com").rstrip("/")
        public = str(settings.public_app_origin or "https://voxbulk.com").rstrip("/")
        week_start, week_end = _week_bounds()

        survey_completed = int(
            db.scalar(
                select(func.count())
                .select_from(SurveySession)
                .where(
                    SurveySession.org_id == org_id,
                    SurveySession.completed_at.isnot(None),
                    SurveySession.completed_at >= week_start,
                    SurveySession.completed_at < week_end,
                )
            )
            or 0
        )
        interview_completed = int(
            db.scalar(
                select(func.count())
                .select_from(ServiceOrderRecipient)
                .join(ServiceOrder, ServiceOrder.id == ServiceOrderRecipient.order_id)
                .where(
                    ServiceOrder.org_id == org_id,
                    ServiceOrder.service_code == "interview",
                    ServiceOrderRecipient.status == "completed",
                    ServiceOrder.completed_at.isnot(None),
                    ServiceOrder.completed_at >= week_start,
                    ServiceOrder.completed_at < week_end,
                )
            )
            or 0
        )
        running_surveys = int(
            db.scalar(
                select(func.count())
                .select_from(ServiceOrder)
                .where(
                    ServiceOrder.org_id == org_id,
                    ServiceOrder.service_code == "survey",
                    ServiceOrder.status == "running",
                )
            )
            or 0
        )
        running_interviews = int(
            db.scalar(
                select(func.count())
                .select_from(ServiceOrder)
                .where(
                    ServiceOrder.org_id == org_id,
                    ServiceOrder.service_code == "interview",
                    ServiceOrder.status == "running",
                )
            )
            or 0
        )
        draft_campaigns = int(
            db.scalar(
                select(func.count())
                .select_from(ServiceOrder)
                .where(
                    ServiceOrder.org_id == org_id,
                    ServiceOrder.status == "draft",
                )
            )
            or 0
        )

        usage_lines = [
            _bullet_row(f"Survey responses completed: {survey_completed}"),
            _bullet_row(f"Interview sessions completed: {interview_completed}"),
            _bullet_row(f"Active survey campaigns: {running_surveys}"),
            _bullet_row(f"Active interview campaigns: {running_interviews}"),
        ]
        usage_summary_html = "".join(usage_lines)

        action_lines: list[str] = []
        if draft_campaigns:
            label = "campaign" if draft_campaigns == 1 else "campaigns"
            action_lines.append(_bullet_row(f"{draft_campaigns} draft {label} ready to launch"))
        if not action_lines:
            action_items = _empty_row("No action items this week.")
        else:
            action_items = "".join(action_lines)

        outstanding_minor = BillingAccessService.outstanding_invoice_minor(db, org_id)
        system_alerts = (
            _empty_row(f"You have outstanding invoices (£{outstanding_minor / 100:.2f} due).")
            if outstanding_minor > 0
            else _empty_row("No billing alerts this week.")
        )

        return {
            "organisation_name": org_name,
            "practice_name": org_name,
            "digest_week_date": _week_label(),
            "digest_greeting": f"Good morning, {first}",
            "message_html": "",
            "usage_summary_html": usage_summary_html,
            "action_items": action_items,
            "recovery_items": action_items,
            "system_alerts": system_alerts,
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
