"""Expo transactional emails — visitor catalogue, exhibitor digest, day/end summary."""

from __future__ import annotations

import html
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.expo import ExpoBooth, ExpoLead
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.expo.expo_mailbox_settings_service import ExpoMailboxSettingsService
from app.services.expo.offer_delivery_service import normalize_asset_purpose
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)

VISITOR_TEMPLATE = "expo_visitor_catalogue"
EXHIBITOR_TEMPLATE = "expo_exhibitor_lead_digest"
DAY_SUMMARY_TEMPLATE = "expo_visitor_day_summary"

# Keep under typical SMTP / mailbox limits; oversized files stay as download links.
MAX_EMAIL_ATTACHMENT_BYTES = 8 * 1024 * 1024

_DOCUMENT_SUFFIX_MEDIA = {
    ".pdf": ("application", "pdf"),
    ".xls": ("application", "vnd.ms-excel"),
    ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".csv": ("text", "csv"),
    ".doc": ("application", "msword"),
    ".docx": ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def _email_attachments(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read stored catalogue files into SMTP attachment dicts."""
    from pathlib import Path

    from app.services.expo.asset_storage_service import resolve_storage_abs_path

    out: list[dict[str, Any]] = []
    for asset in assets or []:
        abs_path = resolve_storage_abs_path(asset.get("storage_path"))
        if abs_path is None:
            logger.info(
                "expo_visitor_email_skip_attach_missing asset=%s path=%s",
                asset.get("id"),
                asset.get("storage_path"),
            )
            continue
        try:
            size = abs_path.stat().st_size
            if size > MAX_EMAIL_ATTACHMENT_BYTES:
                logger.info(
                    "expo_visitor_email_skip_attach_too_large asset=%s bytes=%s",
                    asset.get("id"),
                    size,
                )
                continue
            content = abs_path.read_bytes()
        except OSError:
            logger.warning("expo_visitor_email_attach_read_failed asset=%s", asset.get("id"), exc_info=True)
            continue
        maintype, subtype = _DOCUMENT_SUFFIX_MEDIA.get(
            abs_path.suffix.lower(), ("application", "octet-stream")
        )
        filename = str(asset.get("original_filename") or "").strip() or abs_path.name
        title = str(asset.get("title") or "").strip()
        if title and "." not in Path(filename).name:
            filename = f"{title[:200]}{abs_path.suffix or '.pdf'}"
        out.append(
            {
                "filename": Path(filename).name[:240],
                "content": content,
                "maintype": maintype,
                "subtype": subtype,
            }
        )
    return out


def _parse_offer_config(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip()
    if not title:
        return None
    return {
        "title": title[:255],
        "description": str(data.get("description") or "").strip()[:2000],
        "claim_url": str(data.get("claim_url") or "").strip()[:1024],
        "code": str(data.get("code") or "").strip()[:64],
        "ends_at": str(data.get("ends_at") or "").strip()[:64],
    }


class ExpoEmailService:
    @staticmethod
    def _smtp_from(db: Session) -> dict[str, str | None]:
        from app.services.platform_sender_email_service import PlatformSenderEmailService

        outbound = PlatformSenderEmailService.resolve_outbound(db, "expo")
        if outbound and outbound.get("from_email"):
            return {
                "from_name": outbound.get("from_name"),
                "from_email": outbound.get("from_email"),
                "smtp_username": outbound.get("smtp_username"),
                "smtp_password": outbound.get("smtp_password"),
            }
        from_name, from_email = ExpoMailboxSettingsService.from_address(db)
        pwd = ExpoMailboxSettingsService.get_decrypted_password(db)
        row = ExpoMailboxSettingsService.get_row(db)
        return {
            "from_name": from_name,
            "from_email": from_email,
            "smtp_username": (row.smtp_username or None),
            "smtp_password": pwd,
        }

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
                lines.append(
                    f'<li><strong>{html.escape(label)}:</strong> '
                    f'<a href="{html.escape(url)}">{html.escape(title)}</a></li>'
                )
            else:
                lines.append(f"<li><strong>{html.escape(label)}:</strong> {html.escape(title)}</li>")
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
    def _booth_contact_email(booth: ExpoBooth) -> str:
        email = str(getattr(booth, "visitor_contact_email", None) or "").strip()
        if email and "@" in email:
            return email
        # Fallback: first rep email (legacy booths)
        try:
            from app.services.expo.question_bank import parse_representative_contacts

            reps = parse_representative_contacts(getattr(booth, "representative_contacts_json", None))
            for r in reps:
                e = str(r.get("email") or "").strip()
                if e and "@" in e:
                    return e
        except Exception:
            pass
        return ""

    @staticmethod
    def _offer_block_html(booth: ExpoBooth, *, interested: bool) -> str:
        offer = _parse_offer_config(getattr(booth, "offer_config_json", None))
        if not offer or not interested:
            return ""
        title = html.escape(offer["title"])
        desc = html.escape(offer.get("description") or "")
        url = str(offer.get("claim_url") or "").strip()
        code = html.escape(offer.get("code") or "")
        parts = [f'<p style="margin-top:16px;"><strong>Trade-show offer:</strong> {title}</p>']
        if desc:
            parts.append(f"<p>{desc}</p>")
        if code:
            parts.append(f"<p>Code: <strong>{code}</strong></p>")
        if url:
            parts.append(f'<p><a href="{html.escape(url)}">Claim this offer</a></p>')
        return "".join(parts)

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
        if not assets and not bool(getattr(lead, "offer_interested", False)):
            return False
        company = str(booth.company_display_name or booth.name or "our team").strip()
        booth_name = str(booth.name or company).strip()
        contact = ExpoEmailService._booth_contact_email(booth)
        phone = str(getattr(booth, "notify_mobile", None) or "").strip()
        website = str(getattr(booth, "company_website", None) or "").strip()
        interested = bool(getattr(lead, "offer_interested", False))
        variables = {
            "first_name": ExpoEmailService._first_name(lead),
            "company_name": company,
            "booth_name": booth_name,
            "asset_links": ExpoEmailService._asset_links_html(assets) if assets else "<p>No files this time.</p>",
            "asset_list": ExpoEmailService._asset_list_text(assets),
            "contact_email": contact or "—",
            "contact_phone_line": f"Phone: {html.escape(phone)}<br />" if phone else "",
            "company_website_line": (
                f'Website: <a href="{html.escape(website)}">{html.escape(website)}</a>' if website else ""
            ),
            "offer_block": ExpoEmailService._offer_block_html(booth, interested=interested),
        }
        smtp = ExpoEmailService._smtp_from(db)
        attachments = _email_attachments(assets) if assets else []
        if assets and not attachments:
            logger.warning(
                "expo_visitor_email_no_attachments lead=%s asset_count=%s (links only)",
                lead.id,
                len(assets),
            )
        try:
            ok, err = TransactionalEmailService.send_templated_optional(
                db,
                template_key=VISITOR_TEMPLATE,
                to_email=email,
                variables=variables,
                attachments=attachments or None,
                from_email=smtp["from_email"],
                from_name=smtp["from_name"],
                smtp_username=smtp["smtp_username"],
                smtp_password=smtp["smtp_password"],
            )
            if not ok:
                logger.warning("expo_visitor_email_failed lead=%s err=%s", lead.id, err)
            else:
                logger.info(
                    "expo_visitor_email_sent lead=%s to=%s attachments=%s",
                    lead.id,
                    email,
                    len(attachments),
                )
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
        # Stand representatives — product owners often expect the digest here.
        try:
            from app.services.expo.question_bank import parse_representative_contacts

            for r in parse_representative_contacts(getattr(booth, "representative_contacts_json", None)):
                e = str(r.get("email") or "").strip().lower()
                if e and "@" in e:
                    emails.append(e)
        except Exception:
            pass
        booth_contact = ExpoEmailService._booth_contact_email(booth)
        if booth_contact:
            emails.append(booth_contact.strip().lower())
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
        seen: set[str] = set()
        out: list[str] = []
        for e in emails:
            if e and e not in seen and "@" in e:
                seen.add(e)
                out.append(e)
        return out[:8]

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
            "offer_interested": "Yes" if getattr(lead, "offer_interested", False) else "No",
            "asset_list": ExpoEmailService._asset_list_text(assets),
            "opened_summary": "Not opened yet",
            "leads_url": leads_url,
            "interest": str(lead.interest or "—"),
            "timeline": str(lead.buying_timeline or "—"),
        }
        smtp = ExpoEmailService._smtp_from(db)
        any_ok = False
        for to_email in recipients:
            try:
                ok, err = TransactionalEmailService.send_templated_optional(
                    db,
                    template_key=EXHIBITOR_TEMPLATE,
                    to_email=to_email,
                    variables=variables,
                    from_email=smtp["from_email"],
                    from_name=smtp["from_name"],
                    smtp_username=smtp["smtp_username"],
                    smtp_password=smtp["smtp_password"],
                )
                any_ok = any_ok or bool(ok)
                if not ok:
                    logger.warning("expo_exhibitor_email_failed to=%s err=%s", to_email, err)
            except Exception:
                logger.exception("expo_exhibitor_email_exception to=%s", to_email)
        return any_ok

    @staticmethod
    def build_day_summary_variables(
        *,
        first_name: str,
        exhibition_name: str,
        venue: str,
        summary_date: str,
        is_final: bool,
        stands: list[dict[str, Any]],
    ) -> dict[str, str]:
        stands_visited = len(stands)
        catalogues = sum(1 for s in stands if s.get("catalogue_requested"))
        offers = sum(1 for s in stands if s.get("offer_interested"))
        kpi_html = (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;margin:16px 0;">'
            "<tr>"
            f'<td style="padding:12px;background:#f7f5f2;border-radius:10px;text-align:center;width:33%;">'
            f'<div style="font-size:22px;font-weight:700;">{stands_visited}</div>'
            f'<div style="font-size:12px;color:#6b6560;">Stands visited</div></td>'
            f'<td style="width:8px;"></td>'
            f'<td style="padding:12px;background:#f7f5f2;border-radius:10px;text-align:center;width:33%;">'
            f'<div style="font-size:22px;font-weight:700;">{catalogues}</div>'
            f'<div style="font-size:12px;color:#6b6560;">Catalogues</div></td>'
            f'<td style="width:8px;"></td>'
            f'<td style="padding:12px;background:#f7f5f2;border-radius:10px;text-align:center;width:33%;">'
            f'<div style="font-size:22px;font-weight:700;">{offers}</div>'
            f'<div style="font-size:12px;color:#6b6560;">Offers</div></td>'
            "</tr></table>"
        )
        blocks: list[str] = []
        text_lines: list[str] = []
        for s in stands:
            company = html.escape(str(s.get("company_name") or "Stand"))
            booth = html.escape(str(s.get("booth_name") or ""))
            contact = html.escape(str(s.get("contact_email") or "—"))
            assets = html.escape(str(s.get("asset_list") or "—"))
            offer_line = ""
            if s.get("offer_interested") and s.get("offer_title"):
                claim = str(s.get("offer_claim_url") or "").strip()
                offer_line = f"<br /><strong>Offer:</strong> {html.escape(str(s.get('offer_title')))}"
                if claim:
                    offer_line += f' — <a href="{html.escape(claim)}">Claim</a>'
            blocks.append(
                f'<div style="margin:12px 0;padding:14px 16px;border:1px solid #e8e4de;border-radius:12px;">'
                f'<div style="font-weight:600;">{company}</div>'
                f'<div style="font-size:13px;color:#6b6560;">{booth}</div>'
                f'<div style="margin-top:8px;font-size:14px;">Contact: '
                f'<a href="mailto:{contact}">{contact}</a></div>'
                f'<div style="font-size:13px;color:#6b6560;margin-top:4px;">Files: {assets}</div>'
                f"{offer_line}</div>"
            )
            text_lines.append(f"- {s.get('company_name')}: {s.get('contact_email')} ({s.get('asset_list')})")
        heading = "Your Expo summary" if is_final else "Your Expo day"
        intro = (
            f"Here is your full visit summary for <strong>{html.escape(exhibition_name)}</strong>."
            if is_final
            else f"Here is what you requested on <strong>{html.escape(summary_date)}</strong> at "
            f"<strong>{html.escape(exhibition_name)}</strong>."
        )
        return {
            "first_name": first_name or "there",
            "exhibition_name": exhibition_name,
            "venue": venue or "—",
            "summary_date": summary_date,
            "is_final": "true" if is_final else "false",
            "stands_visited": str(stands_visited),
            "catalogues_requested": str(catalogues),
            "offers_claimed": str(offers),
            "kpi_html": kpi_html,
            "stands_html": "".join(blocks) or "<p>No stands recorded.</p>",
            "stands_list_text": "\n".join(text_lines) or "—",
            "summary_heading": heading,
            "summary_intro": intro,
            "organisation_name": "VOXBULK",
        }

    @staticmethod
    def send_visitor_day_summary(
        db: Session,
        *,
        to_email: str,
        variables: dict[str, str],
    ) -> bool:
        email = str(to_email or "").strip().lower()
        if not email or "@" not in email:
            return False
        smtp = ExpoEmailService._smtp_from(db)
        try:
            ok, err = TransactionalEmailService.send_templated_optional(
                db,
                template_key=DAY_SUMMARY_TEMPLATE,
                to_email=email,
                variables=variables,
                from_email=smtp["from_email"],
                from_name=smtp["from_name"],
                smtp_username=smtp["smtp_username"],
                smtp_password=smtp["smtp_password"],
            )
            if not ok:
                logger.warning("expo_day_summary_failed to=%s err=%s", email, err)
            return bool(ok)
        except Exception:
            logger.exception("expo_day_summary_exception to=%s", email)
            return False
