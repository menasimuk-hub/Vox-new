"""Expo transactional emails — visitor catalogue delivery + exhibitor hot-lead notify."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.expo import ExpoBooth, ExpoLead
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.expo.offer_delivery_service import normalize_asset_purpose
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)

VISITOR_TEMPLATE = "expo_visitor_catalogue"
EXHIBITOR_TEMPLATE = "expo_exhibitor_lead_digest"


class ExpoEmailService:
    @staticmethod
    def _first_name(lead: ExpoLead) -> str:
        name = str(lead.name or "").strip()
        if name:
            return name.split()[0]
        return "there"

    @staticmethod
    def _asset_links_html(assets: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for a in assets:
            title = str(a.get("title") or "Download").strip()
            url = str(a.get("url") or "").strip()
            purpose = normalize_asset_purpose(a.get("purpose"))
            label = {
                "catalogue": "Catalogue",
                "price_list": "Price list",
                "product": "Product sheet",
            }.get(purpose, "File")
            if url:
                lines.append(f'<li><strong>{label}:</strong> <a href="{url}">{title}</a></li>')
            else:
                lines.append(f"<li><strong>{label}:</strong> {title}</li>")
        if not lines:
            return "<p>Your files are ready in the Expo chat.</p>"
        return "<ul>" + "".join(lines) + "</ul>"

    @staticmethod
    def _asset_list_text(assets: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for a in assets:
            title = str(a.get("title") or "File").strip()
            purpose = normalize_asset_purpose(a.get("purpose"))
            parts.append(f"{purpose}: {title}")
        return ", ".join(parts) if parts else "—"

    @staticmethod
    def send_visitor_catalogue(
        db: Session,
        *,
        booth: ExpoBooth,
        lead: ExpoLead,
        assets: list[dict[str, Any]],
    ) -> bool:
        email = str(lead.visitor_email or "").strip()
        if not email or "@" not in email:
            return False
        if not assets:
            return False
        company = str(booth.company_display_name or booth.name or "our team").strip()
        booth_name = str(booth.name or company).strip()
        variables = {
            "first_name": ExpoEmailService._first_name(lead),
            "company_name": company,
            "booth_name": booth_name,
            "asset_links": ExpoEmailService._asset_links_html(assets),
            "asset_list": ExpoEmailService._asset_list_text(assets),
        }
        try:
            ok, err = TransactionalEmailService.send_templated_optional(
                db,
                template_key=VISITOR_TEMPLATE,
                to_email=email,
                variables=variables,
            )
            if not ok:
                logger.warning("expo_visitor_email_failed lead=%s err=%s", lead.id, err)
            return bool(ok)
        except Exception:
            logger.exception("expo_visitor_email_exception lead=%s", lead.id)
            return False

    @staticmethod
    def _exhibitor_emails(db: Session, *, booth: ExpoBooth) -> list[str]:
        emails: list[str] = []
        if booth.created_by_user_id:
            user = db.get(User, booth.created_by_user_id)
            if user and user.email:
                emails.append(str(user.email).strip().lower())
        if not emails:
            memberships = (
                db.execute(
                    select(OrganisationMembership)
                    .where(OrganisationMembership.org_id == booth.org_id)
                    .order_by(OrganisationMembership.created_at.asc())
                    .limit(5)
                )
                .scalars()
                .all()
            )
            for m in memberships:
                role = str(getattr(m, "role", "") or "").lower()
                if role not in {"owner", "manager", "sales", ""}:
                    continue
                user = db.get(User, m.user_id)
                if user and user.email:
                    emails.append(str(user.email).strip().lower())
        # unique preserve order
        seen: set[str] = set()
        out: list[str] = []
        for e in emails:
            if e and e not in seen and "@" in e:
                seen.add(e)
                out.append(e)
        return out[:3]

    @staticmethod
    def notify_exhibitor_lead(
        db: Session,
        *,
        booth: ExpoBooth,
        lead: ExpoLead,
        assets: list[dict[str, Any]] | None = None,
    ) -> bool:
        recipients = ExpoEmailService._exhibitor_emails(db, booth=booth)
        if not recipients:
            return False
        assets = assets or []
        purposes = {normalize_asset_purpose(a.get("purpose")) for a in assets}
        settings = get_settings()
        dash = str(settings.dashboard_app_origin or "https://dashboard.voxbulk.com").rstrip("/")
        leads_url = f"{dash}/expo/leads"
        org = db.get(Organisation, booth.org_id)
        org_name = str(getattr(org, "name", None) or booth.company_display_name or "Your organisation")
        variables = {
            "organisation_name": org_name,
            "booth_name": str(booth.name or ""),
            "lead_name": str(lead.name or "Visitor"),
            "company": str(lead.company or "—"),
            "mobile": str(lead.visitor_phone or "—"),
            "email": str(lead.visitor_email or "—"),
            "catalogue_requested": "Yes" if lead.consent_acknowledged or "catalogue" in purposes else "No",
            "price_list_requested": "Yes" if "price_list" in purposes or lead.consent_acknowledged else "No",
            "asset_list": ExpoEmailService._asset_list_text(assets),
            "opened_summary": "Not opened yet",
            "leads_url": leads_url,
            "interest": str(lead.interest or "—"),
            "timeline": str(lead.buying_timeline or "—"),
        }
        any_ok = False
        for to_email in recipients:
            try:
                ok, err = TransactionalEmailService.send_templated_optional(
                    db,
                    template_key=EXHIBITOR_TEMPLATE,
                    to_email=to_email,
                    variables=variables,
                )
                any_ok = any_ok or bool(ok)
                if not ok:
                    logger.warning("expo_exhibitor_email_failed to=%s err=%s", to_email, err)
            except Exception:
                logger.exception("expo_exhibitor_email_exception to=%s", to_email)
        return any_ok
