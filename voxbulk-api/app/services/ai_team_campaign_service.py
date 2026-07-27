from __future__ import annotations

import csv
import io
import logging
import re
import time
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_team_apify_run import AiTeamApifyRun
from app.models.ai_team_campaign import AiTeamCampaign, AiTeamCampaignRecipient
from app.models.ai_team_email_template import AiTeamEmailTemplate
from app.models.promo_offer import PromoOffer
from app.services.ai_team_service import AiTeamService, AiTeamServiceError
from app.services.promo_offer_service import PromoOfferError, PromoOfferService

logger = logging.getLogger(__name__)

# Shared Expo booth trial for Apify / AI Marketing outreach (register → 3 free Expo days).
DEFAULT_EXPO_PROMO_CODE = "EXPO3DAYS"

_DEFAULT_BODY = (
    "I noticed {{company}} at the show and thought a quick note might help.\n\n"
    "VoxBulk automates customer feedback by phone and WhatsApp so your team sees results faster.\n\n"
    "Start a free 3-day Expo trial with code {{promo_code}} — no card required."
)

_DEFAULT_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light">
</head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;background:#f4f6f8;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;border-collapse:collapse;background:#ffffff;border:1px solid #e5e7eb;">
          <tr>
            <td style="padding:28px 24px;font-size:15px;line-height:1.6;color:#1a1a1a;">
              <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#1a1a1a;">Hi {{first_name}},</p>
              {{body}}
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0 8px;border-collapse:collapse;">
                <tr>
                  <td align="center" bgcolor="#ffffff" style="border-radius:6px;background:#ffffff;border:1px solid #111111;">
                    <a href="{{trial_url}}" target="_blank"
                       style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:700;line-height:1.2;
                              color:#111111 !important;text-decoration:none;border-radius:6px;
                              background:#ffffff;mso-padding-alt:0;">
                      <!--[if mso]><i style="letter-spacing:28px;mso-font-width:-100%;mso-text-raise:21pt;">&nbsp;</i><![endif]-->
                      <span style="color:#111111 !important;text-decoration:none;">Start free trial</span>
                      <!--[if mso]><i style="letter-spacing:28px;mso-font-width:-100%;">&nbsp;</i><![endif]-->
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:12px 0 0;font-size:13px;line-height:1.5;color:#6b7280;">
                Code <strong style="color:#111111;font-family:monospace;">{{promo_code}}</strong> · 3-day Expo trial ·
                or open <a href="{{trial_url}}" style="color:#111111;text-decoration:underline;">{{trial_url}}</a>
              </p>
              <p style="margin:28px 0 0;font-size:12px;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:16px;">
                VoxBulk · voxbulk.com
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

MERGE_TAGS = [
    "first_name",
    "last_name",
    "company",
    "company_name",
    "job_title",
    "email",
    "sector",
    "country_code",
    "promo_code",
    "signup_url",
    "trial_url",
    "body",
]


class AiTeamCampaignService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _apply_merge(template: str, vars_map: dict[str, str]) -> str:
        out = str(template or "")
        for key, val in vars_map.items():
            out = out.replace("{{" + key + "}}", str(val or ""))
        return out

    @staticmethod
    def ensure_default_expo_promo(db: Session) -> PromoOffer:
        """Idempotent: shared EXPO3DAYS promo (3 free Expo days) for outreach CTAs."""
        code = DEFAULT_EXPO_PROMO_CODE
        existing = PromoOfferService.get_by_code(db, code)
        if existing is not None:
            return existing
        try:
            return PromoOfferService.create_admin(
                db,
                {
                    "code": code,
                    "name": "Apify outreach · 3-day Expo trial",
                    "benefit_kind": "free_usage",
                    "service_kind": "expo",
                    "usage_amount": 3,
                    "trial_days": 3,
                    "expires_in_days": 365,
                    "max_redemptions": 100000,
                    "redeem_mode": "anyone",
                },
            )
        except PromoOfferError:
            # Race: another worker created it
            row = PromoOfferService.get_by_code(db, code)
            if row is None:
                raise
            return row

    @staticmethod
    def resolve_promo_code(db: Session, raw: str | None = None) -> str:
        AiTeamCampaignService.ensure_default_expo_promo(db)
        code = str(raw or "").strip().upper()
        if code:
            return code[:64]
        return DEFAULT_EXPO_PROMO_CODE

    @staticmethod
    def _public_signin_url(promo_code: str | None = None) -> str:
        from app.core.config import get_settings

        base = str(
            get_settings().public_app_origin
            or get_settings().public_site_base_url
            or "https://voxbulk.com"
        ).rstrip("/")
        code = str(promo_code or "").strip()
        if code:
            return f"{base}/signin?promo={code}"
        return f"{base}/signin"

    @staticmethod
    def _tracked_trial_url(recipient_id: str) -> str:
        from app.services.brand_assets import api_public_origin

        api = api_public_origin().rstrip("/") or "https://api.voxbulk.com"
        return f"{api}/public/ai-team/c/{recipient_id}/trial"

    @staticmethod
    def _signup_url(promo_code: str | None = None, *, recipient_id: str | None = None) -> str:
        """Direct signup for previews; tracked redirect when sending to a recipient."""
        if recipient_id:
            return AiTeamCampaignService._tracked_trial_url(recipient_id)
        return AiTeamCampaignService._public_signin_url(promo_code)

    @staticmethod
    def record_trial_click_and_destination(db: Session, recipient_id: str) -> str:
        """Mark click on Start Free Trial and return the signup URL with promo."""
        rid = str(recipient_id or "").strip()
        promo = DEFAULT_EXPO_PROMO_CODE
        if rid:
            row = db.get(AiTeamCampaignRecipient, rid)
            if row is not None:
                now = AiTeamCampaignService._now()
                promo = AiTeamCampaignService.resolve_promo_code(db, row.promo_code)
                if not (row.promo_code or "").strip():
                    row.promo_code = promo
                row.click_count = int(row.click_count or 0) + 1
                if row.clicked_at is None:
                    row.clicked_at = now
                if row.opened_at is None:
                    row.opened_at = now
                row.updated_at = now
                db.add(row)
                campaign = db.get(AiTeamCampaign, row.campaign_id)
                if campaign is not None:
                    AiTeamCampaignService.refresh_counts(db, campaign)
                else:
                    db.commit()
        else:
            AiTeamCampaignService.ensure_default_expo_promo(db)
        return AiTeamCampaignService._public_signin_url(promo)

    @staticmethod
    def _prepare_email_html(html: str) -> str:
        """Preserve pasted HTML; add light email-client hints for tables/colours."""
        out = str(html or "")
        if not out.strip():
            return out
        lower = out.lower()
        if "color-scheme" not in lower:
            meta = (
                '<meta name="color-scheme" content="light only">'
                '<meta name="supported-color-schemes" content="light">'
            )
            if re.search(r"<head[^>]*>", out, re.I):
                out = re.sub(r"(<head[^>]*>)", r"\1" + meta, out, count=1, flags=re.I)
            elif re.search(r"<html[^>]*>", out, re.I):
                out = re.sub(r"(<html[^>]*>)", r"\1<head>" + meta + "</head>", out, count=1, flags=re.I)
            else:
                out = meta + out

        def _table_repl(match: re.Match[str]) -> str:
            tag = match.group(0)
            if "border-collapse" in tag.lower():
                return tag
            if re.search(r"\bstyle\s*=", tag, re.I):
                return re.sub(
                    r'\bstyle\s*=\s*(["\'])',
                    r'style=\1border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;',
                    tag,
                    count=1,
                    flags=re.I,
                )
            return tag[:-1] + ' style="border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;">'

        out = re.sub(r"<table\b[^>]*>", _table_repl, out, flags=re.I)
        # Keep CTA / link colours from the template (avoid client forcing blue).
        if "a[x-apple-data-detectors]" not in lower:
            style_block = (
                "<style type=\"text/css\">"
                "a,a:link,a:visited{text-decoration:none;}"
                "a[x-apple-data-detectors]{color:inherit!important;text-decoration:none!important;}"
                "</style>"
            )
            if re.search(r"<head[^>]*>", out, re.I):
                out = re.sub(r"(<head[^>]*>)", r"\1" + style_block, out, count=1, flags=re.I)
        return out

    @staticmethod
    def recipient_vars(row: AiTeamCampaignRecipient, *, db: Session | None = None) -> dict[str, str]:
        promo = str(row.promo_code or "").strip()
        if db is not None:
            promo = AiTeamCampaignService.resolve_promo_code(db, promo)
        elif not promo:
            promo = DEFAULT_EXPO_PROMO_CODE
        tracked = AiTeamCampaignService._signup_url(promo, recipient_id=row.id)
        direct = AiTeamCampaignService._public_signin_url(promo)
        return {
            "first_name": row.first_name or "there",
            "last_name": row.last_name or "",
            "company": row.company_name or "your company",
            "company_name": row.company_name or "your company",
            "job_title": row.job_title or "",
            "email": row.email or "",
            "sector": row.sector or "",
            "country_code": row.country_code or "GB",
            "promo_code": promo,
            "signup_url": tracked,
            "trial_url": tracked,
            "direct_signup_url": direct,
        }

    @staticmethod
    def campaign_to_dict(row: AiTeamCampaign) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "subject": row.subject,
            "body_text": row.body_text,
            "html_template": row.html_template,
            "template_id": getattr(row, "template_id", None),
            "total_count": int(row.total_count or 0),
            "sent_count": int(row.sent_count or 0),
            "failed_count": int(row.failed_count or 0),
            "opened_count": int(row.opened_count or 0),
            "clicked_count": int(getattr(row, "_clicked_count", 0) or 0),
            "replied_count": int(row.replied_count or 0),
            "last_error": row.last_error,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def recipient_to_dict(row: AiTeamCampaignRecipient) -> dict[str, Any]:
        return {
            "id": row.id,
            "campaign_id": row.campaign_id,
            "email": row.email,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "full_name": f"{row.first_name} {row.last_name}".strip() or row.email,
            "company_name": row.company_name,
            "job_title": row.job_title,
            "sector": row.sector,
            "country_code": row.country_code,
            "promo_code": row.promo_code,
            "status": row.status,
            "last_error": row.last_error,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "opened_at": row.opened_at.isoformat() if row.opened_at else None,
            "clicked_at": row.clicked_at.isoformat() if getattr(row, "clicked_at", None) else None,
            "click_count": int(getattr(row, "click_count", 0) or 0),
            "replied_at": row.replied_at.isoformat() if row.replied_at else None,
        }

    @staticmethod
    def list_campaigns(db: Session) -> list[AiTeamCampaign]:
        return list(
            db.execute(select(AiTeamCampaign).order_by(AiTeamCampaign.updated_at.desc())).scalars().all()
        )

    @staticmethod
    def get_campaign(db: Session, campaign_id: str) -> AiTeamCampaign:
        row = db.get(AiTeamCampaign, campaign_id)
        if row is None:
            raise AiTeamServiceError("Campaign not found")
        return row

    @staticmethod
    def create_campaign(db: Session, *, name: str) -> AiTeamCampaign:
        title = str(name or "").strip()
        if not title:
            raise AiTeamServiceError("Campaign name is required")
        AiTeamCampaignService.ensure_default_expo_promo(db)
        now = AiTeamCampaignService._now()
        row = AiTeamCampaign(
            name=title[:255],
            status="draft",
            subject="Quick idea for {{company}}",
            body_text=_DEFAULT_BODY,
            html_template=_DEFAULT_HTML_TEMPLATE,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_campaign(db: Session, campaign_id: str, payload: dict[str, Any]) -> AiTeamCampaign:
        row = AiTeamCampaignService.get_campaign(db, campaign_id)
        if row.status == "sending":
            raise AiTeamServiceError("Cannot edit a campaign while it is sending")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise AiTeamServiceError("Campaign name is required")
            row.name = name[:255]
        if "subject" in payload:
            row.subject = str(payload.get("subject") or "").strip()[:500]
        if "body_text" in payload:
            row.body_text = str(payload.get("body_text") or "")
        if "html_template" in payload:
            html = payload.get("html_template")
            row.html_template = str(html) if html is not None else None
        if "template_id" in payload:
            tid = str(payload.get("template_id") or "").strip() or None
            row.template_id = tid
        row.updated_at = AiTeamCampaignService._now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def template_to_dict(row: AiTeamEmailTemplate) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "subject": row.subject,
            "body_text": row.body_text,
            "html_template": row.html_template,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def list_templates(db: Session) -> list[AiTeamEmailTemplate]:
        AiTeamCampaignService.ensure_default_expo_promo(db)
        rows = list(
            db.execute(select(AiTeamEmailTemplate).order_by(AiTeamEmailTemplate.updated_at.desc())).scalars().all()
        )
        if rows:
            return rows
        # Seed one default so the Templates tab is never empty on first visit
        now = AiTeamCampaignService._now()
        seed = AiTeamEmailTemplate(
            name="Default expo outreach",
            subject="Quick idea for {{company}}",
            body_text=_DEFAULT_BODY,
            html_template=_DEFAULT_HTML_TEMPLATE,
            created_at=now,
            updated_at=now,
        )
        db.add(seed)
        db.commit()
        db.refresh(seed)
        return [seed]

    @staticmethod
    def get_template(db: Session, template_id: str) -> AiTeamEmailTemplate:
        row = db.get(AiTeamEmailTemplate, template_id)
        if row is None:
            raise AiTeamServiceError("Template not found")
        return row

    @staticmethod
    def create_template(db: Session, payload: dict[str, Any]) -> AiTeamEmailTemplate:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise AiTeamServiceError("Template name is required")
        AiTeamCampaignService.ensure_default_expo_promo(db)
        now = AiTeamCampaignService._now()
        row = AiTeamEmailTemplate(
            name=name[:255],
            subject=str(payload.get("subject") or "Quick idea for {{company}}").strip()[:500],
            body_text=str(payload.get("body_text") if payload.get("body_text") is not None else _DEFAULT_BODY),
            html_template=(
                str(payload["html_template"])
                if payload.get("html_template") is not None
                else _DEFAULT_HTML_TEMPLATE
            ),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_template(db: Session, template_id: str, payload: dict[str, Any]) -> AiTeamEmailTemplate:
        row = AiTeamCampaignService.get_template(db, template_id)
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise AiTeamServiceError("Template name is required")
            row.name = name[:255]
        if "subject" in payload:
            row.subject = str(payload.get("subject") or "").strip()[:500]
        if "body_text" in payload:
            row.body_text = str(payload.get("body_text") or "")
        if "html_template" in payload:
            html = payload.get("html_template")
            row.html_template = str(html) if html is not None else None
        row.updated_at = AiTeamCampaignService._now()
        db.add(row)
        # Keep linked campaigns (not currently sending) in sync with the saved template.
        linked = list(
            db.execute(
                select(AiTeamCampaign).where(AiTeamCampaign.template_id == row.id)
            ).scalars().all()
        )
        now = AiTeamCampaignService._now()
        for campaign in linked:
            if campaign.status == "sending":
                continue
            campaign.subject = row.subject or ""
            campaign.body_text = row.body_text or ""
            campaign.html_template = row.html_template
            campaign.updated_at = now
            db.add(campaign)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_template(db: Session, template_id: str) -> dict[str, Any]:
        row = AiTeamCampaignService.get_template(db, template_id)
        linked = list(
            db.execute(
                select(AiTeamCampaign).where(AiTeamCampaign.template_id == row.id)
            ).scalars().all()
        )
        for campaign in linked:
            campaign.template_id = None
            campaign.updated_at = AiTeamCampaignService._now()
            db.add(campaign)
        db.delete(row)
        db.commit()
        return {"ok": True, "deleted": 1}

    @staticmethod
    def preview_template_content(
        db: Session,
        *,
        subject: str | None = None,
        body_text: str | None = None,
        html_template: str | None = None,
    ) -> dict[str, str]:
        """Render a template draft with sample merge data (for Templates Preview)."""
        fake = AiTeamCampaign(
            name="preview",
            status="draft",
            subject=str(subject or "Quick idea for {{company}}").strip()[:500] or "Hello",
            body_text=str(body_text if body_text is not None else _DEFAULT_BODY),
            html_template=(
                str(html_template).strip()
                if html_template is not None
                else _DEFAULT_HTML_TEMPLATE
            ),
        )
        rendered = AiTeamCampaignService.render_for_recipient(db, fake, None, sample=True)
        return {**rendered, "sample": True}

    @staticmethod
    def apply_template_to_campaign(db: Session, campaign_id: str, template_id: str) -> AiTeamCampaign:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        if campaign.status == "sending":
            raise AiTeamServiceError("Cannot change template while sending")
        tpl = AiTeamCampaignService.get_template(db, template_id)
        campaign.template_id = tpl.id
        campaign.subject = tpl.subject or ""
        campaign.body_text = tpl.body_text or ""
        campaign.html_template = tpl.html_template
        campaign.updated_at = AiTeamCampaignService._now()
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign

    @staticmethod
    def delete_campaign(db: Session, campaign_id: str) -> dict[str, Any]:
        row = AiTeamCampaignService.get_campaign(db, campaign_id)
        if row.status == "sending":
            raise AiTeamServiceError("Cannot delete a campaign while it is sending — cancel first")
        recipients = list(
            db.execute(
                select(AiTeamCampaignRecipient).where(AiTeamCampaignRecipient.campaign_id == campaign_id)
            ).scalars().all()
        )
        for r in recipients:
            db.delete(r)
        db.delete(row)
        db.commit()
        return {"ok": True, "deleted": 1}

    @staticmethod
    def refresh_counts(db: Session, campaign: AiTeamCampaign) -> AiTeamCampaign:
        cid = campaign.id
        total = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == cid
            )
        ) or 0
        sent = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == cid,
                AiTeamCampaignRecipient.status == "sent",
            )
        ) or 0
        failed = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == cid,
                AiTeamCampaignRecipient.status == "failed",
            )
        ) or 0
        opened = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == cid,
                AiTeamCampaignRecipient.opened_at.is_not(None),
            )
        ) or 0
        clicked = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == cid,
                AiTeamCampaignRecipient.clicked_at.is_not(None),
            )
        ) or 0
        replied = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == cid,
                AiTeamCampaignRecipient.replied_at.is_not(None),
            )
        ) or 0
        campaign.total_count = int(total)
        campaign.sent_count = int(sent)
        campaign.failed_count = int(failed)
        campaign.opened_count = int(opened)
        campaign.replied_count = int(replied)
        campaign.updated_at = AiTeamCampaignService._now()
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        campaign._clicked_count = int(clicked)  # type: ignore[attr-defined]
        return campaign

    @staticmethod
    def tracking_overview(
        db: Session,
        *,
        status: str | None = None,
        campaign_id: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Cross-campaign send/click activity for the Apify Tracking tab."""
        campaigns = AiTeamCampaignService.list_campaigns(db)
        campaign_dicts: list[dict[str, Any]] = []
        sum_sent = sum_failed = sum_pending = sum_clicked = sum_opened = sum_recipients = 0
        for c in campaigns:
            clicked = int(
                db.scalar(
                    select(func.count()).select_from(AiTeamCampaignRecipient).where(
                        AiTeamCampaignRecipient.campaign_id == c.id,
                        AiTeamCampaignRecipient.clicked_at.is_not(None),
                    )
                )
                or 0
            )
            pending = int(
                db.scalar(
                    select(func.count()).select_from(AiTeamCampaignRecipient).where(
                        AiTeamCampaignRecipient.campaign_id == c.id,
                        AiTeamCampaignRecipient.status == "pending",
                    )
                )
                or 0
            )
            c._clicked_count = clicked  # type: ignore[attr-defined]
            d = AiTeamCampaignService.campaign_to_dict(c)
            d["clicked_count"] = clicked
            d["pending_count"] = pending
            campaign_dicts.append(d)
            sum_sent += int(c.sent_count or 0)
            sum_failed += int(c.failed_count or 0)
            sum_pending += pending
            sum_clicked += clicked
            sum_opened += int(c.opened_count or 0)
            sum_recipients += int(c.total_count or 0)

        stmt = (
            select(AiTeamCampaignRecipient, AiTeamCampaign.name)
            .join(AiTeamCampaign, AiTeamCampaign.id == AiTeamCampaignRecipient.campaign_id)
            .order_by(AiTeamCampaignRecipient.updated_at.desc())
            .limit(max(1, min(int(limit or 200), 1000)))
        )
        cid = str(campaign_id or "").strip()
        if cid:
            stmt = stmt.where(AiTeamCampaignRecipient.campaign_id == cid)
        st = str(status or "").strip().lower()
        if st == "sent":
            stmt = stmt.where(AiTeamCampaignRecipient.status == "sent")
        elif st == "failed":
            stmt = stmt.where(AiTeamCampaignRecipient.status == "failed")
        elif st == "pending":
            stmt = stmt.where(AiTeamCampaignRecipient.status == "pending")
        elif st == "clicked":
            stmt = stmt.where(AiTeamCampaignRecipient.clicked_at.is_not(None))
        elif st == "opened":
            stmt = stmt.where(AiTeamCampaignRecipient.opened_at.is_not(None))
        needle = str(q or "").strip().lower()
        if needle:
            like = f"%{needle}%"
            stmt = stmt.where(
                (AiTeamCampaignRecipient.email.ilike(like))
                | (AiTeamCampaignRecipient.company_name.ilike(like))
                | (AiTeamCampaignRecipient.first_name.ilike(like))
                | (AiTeamCampaignRecipient.last_name.ilike(like))
            )

        activity: list[dict[str, Any]] = []
        for row, camp_name in db.execute(stmt).all():
            item = AiTeamCampaignService.recipient_to_dict(row)
            item["campaign_name"] = camp_name or ""
            activity.append(item)

        return {
            "summary": {
                "campaigns": len(campaigns),
                "recipients": sum_recipients,
                "sent": sum_sent,
                "failed": sum_failed,
                "pending": sum_pending,
                "clicked": sum_clicked,
                "opened": sum_opened,
            },
            "campaigns": campaign_dicts,
            "activity": activity,
        }

    @staticmethod
    def list_recipients(
        db: Session,
        campaign_id: str,
        *,
        status: str | None = None,
        limit: int = 500,
    ) -> list[AiTeamCampaignRecipient]:
        AiTeamCampaignService.get_campaign(db, campaign_id)
        stmt = (
            select(AiTeamCampaignRecipient)
            .where(AiTeamCampaignRecipient.campaign_id == campaign_id)
            .order_by(AiTeamCampaignRecipient.created_at.asc())
            .limit(max(1, min(int(limit or 500), 5000)))
        )
        if status:
            stmt = stmt.where(AiTeamCampaignRecipient.status == status)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def clear_recipients(db: Session, campaign_id: str) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        if campaign.status == "sending":
            raise AiTeamServiceError("Cannot clear audience while sending")
        rows = list(
            db.execute(
                select(AiTeamCampaignRecipient).where(AiTeamCampaignRecipient.campaign_id == campaign_id)
            ).scalars().all()
        )
        for r in rows:
            db.delete(r)
        db.commit()
        AiTeamCampaignService.refresh_counts(db, campaign)
        return {"ok": True, "deleted": len(rows)}

    @staticmethod
    def _upsert_recipient_rows(
        db: Session,
        campaign: AiTeamCampaign,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if campaign.status == "sending":
            raise AiTeamServiceError("Cannot change audience while sending")
        existing = {
            r.email.lower(): r
            for r in db.execute(
                select(AiTeamCampaignRecipient).where(AiTeamCampaignRecipient.campaign_id == campaign.id)
            ).scalars().all()
        }
        created = 0
        skipped = 0
        now = AiTeamCampaignService._now()
        for raw in rows:
            email = str(raw.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue
            if email in existing:
                skipped += 1
                continue
            row = AiTeamCampaignRecipient(
                campaign_id=campaign.id,
                email=email,
                first_name=str(raw.get("first_name") or "").strip()[:120],
                last_name=str(raw.get("last_name") or "").strip()[:120],
                company_name=str(raw.get("company_name") or raw.get("company") or "").strip()[:255],
                job_title=str(raw.get("job_title") or "").strip()[:255],
                sector=str(raw.get("sector") or "").strip().lower()[:64],
                country_code=(str(raw.get("country_code") or raw.get("country") or "GB").strip().upper()[:8] or "GB"),
                promo_code=AiTeamCampaignService.resolve_promo_code(
                    db, str(raw.get("promo_code") or "").strip()
                )[:64],
                status="pending",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            existing[email] = row
            created += 1
        campaign.updated_at = now
        if campaign.status in {"sent", "failed", "cancelled"} and created:
            campaign.status = "draft"
            campaign.completed_at = None
        db.add(campaign)
        db.commit()
        AiTeamCampaignService.refresh_counts(db, campaign)
        return {"ok": True, "created": created, "skipped": skipped, "total": campaign.total_count}

    @staticmethod
    def import_csv(
        db: Session,
        campaign_id: str,
        raw: bytes,
        mapping: dict[str, str],
    ) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        email_col = str(mapping.get("email") or "").strip()
        if not email_col:
            raise AiTeamServiceError("Map which column contains email")
        from app.utils.text_decoding import decode_uploaded_text

        text = decode_uploaded_text(raw)
        reader = csv.DictReader(io.StringIO(text))

        def col(name: str) -> str:
            return str(mapping.get(name) or "").strip()

        rows: list[dict[str, Any]] = []
        for row in reader:
            email = str(row.get(email_col) or "").strip().lower()
            if not email or "@" not in email:
                continue
            rows.append(
                {
                    "email": email,
                    "first_name": str(row.get(col("first_name")) or "").strip(),
                    "last_name": str(row.get(col("last_name")) or "").strip(),
                    "company_name": str(row.get(col("company_name")) or row.get(col("company")) or "").strip(),
                    "job_title": str(row.get(col("job_title")) or "").strip(),
                    "sector": str(row.get(col("sector")) or "").strip().lower(),
                    "country_code": str(row.get(col("country_code")) or row.get(col("country")) or "GB").strip(),
                    "promo_code": str(row.get(col("promo_code")) or "").strip(),
                }
            )
        if not rows:
            raise AiTeamServiceError("No valid email rows found in the sheet")
        return AiTeamCampaignService._upsert_recipient_rows(db, campaign, rows)

    @staticmethod
    def import_from_scrape_run(db: Session, campaign_id: str, run_id: str) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        run = db.get(AiTeamApifyRun, run_id)
        if run is None:
            raise AiTeamServiceError("Scrape run not found")
        contacts = AiTeamService._builtin_run_contacts(run)
        if not contacts:
            # Fallback: Apify-style dataset preview path
            try:
                preview = AiTeamService.preview_apify_run(db, run_id, limit=5000)
                contacts = list(preview.get("preview") or [])
            except Exception:
                contacts = []
        rows: list[dict[str, Any]] = []
        for c in contacts:
            if not isinstance(c, dict):
                continue
            email = str(c.get("email") or "").strip().lower()
            if not email or "@" not in email:
                continue
            rows.append(
                {
                    "email": email,
                    "first_name": str(c.get("first_name") or "").strip(),
                    "last_name": str(c.get("last_name") or "").strip(),
                    "company_name": str(
                        c.get("company_name") or c.get("company") or c.get("stand_name") or ""
                    ).strip(),
                    "job_title": str(c.get("job_title") or "").strip(),
                    "sector": str(c.get("sector") or "expo").strip().lower(),
                    "country_code": str(c.get("country_code") or "GB").strip(),
                }
            )
        if not rows:
            raise AiTeamServiceError("No emails in this scrape run — export/view first or re-scrape")
        result = AiTeamCampaignService._upsert_recipient_rows(db, campaign, rows)
        result["run_id"] = run_id
        return result

    @staticmethod
    def render_for_recipient(
        db: Session,
        campaign: AiTeamCampaign,
        recipient: AiTeamCampaignRecipient | None = None,
        *,
        sample: bool = False,
    ) -> dict[str, str]:
        """Merge {{tags}} only — do not alter colours, sizes, tables, or wrappers."""
        AiTeamCampaignService.ensure_default_expo_promo(db)
        default_promo = DEFAULT_EXPO_PROMO_CODE
        if sample or recipient is None:
            promo = default_promo
            direct = AiTeamCampaignService._public_signin_url(promo)
            vars_map = {
                "first_name": "Alex",
                "last_name": "Taylor",
                "company": "Example Ltd",
                "company_name": "Example Ltd",
                "job_title": "Operations Director",
                "email": "alex@example.com",
                "sector": "expo",
                "country_code": "GB",
                "promo_code": promo,
                "signup_url": direct,
                "trial_url": direct,
                "direct_signup_url": direct,
            }
        else:
            vars_map = AiTeamCampaignService.recipient_vars(recipient, db=db)
            if not (recipient.promo_code or "").strip():
                recipient.promo_code = vars_map["promo_code"]
                recipient.updated_at = AiTeamCampaignService._now()
                db.add(recipient)
                db.commit()

        body_merged = AiTeamCampaignService._apply_merge(campaign.body_text or "", vars_map)
        subject = AiTeamCampaignService._apply_merge(campaign.subject or "", vars_map).strip() or "Hello"
        template = str(campaign.html_template or "").strip()

        if not template:
            # No HTML wrapper: use body as the document if it looks like HTML, else default shell.
            if body_merged and re.search(r"</?(?:html|body|table|div|a)\b", body_merged, re.I):
                template = body_merged
                vars_map["body"] = ""
            else:
                template = _DEFAULT_HTML_TEMPLATE
                vars_map["body"] = body_merged.replace("\n", "<br>") if body_merged else ""
        elif "{{body}}" in template:
            # Insert body text as-is (no colour/size wrappers).
            vars_map["body"] = body_merged
        else:
            # Full HTML document — ignore body for HTML output (plain text still returned).
            vars_map["body"] = ""

        html = AiTeamCampaignService._apply_merge(template, vars_map)
        html = re.sub(r"\{\{[a-zA-Z0-9_]+\}\}", "", html)
        # Intentionally no _prepare_email_html / no style or href rewriting.
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            text = body_merged
        return {"subject": subject, "html": html, "text": text, "body_text": body_merged}

    @staticmethod
    def preview(db: Session, campaign_id: str, *, recipient_id: str | None = None) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        recipient = None
        if recipient_id:
            recipient = db.get(AiTeamCampaignRecipient, recipient_id)
            if recipient is None or recipient.campaign_id != campaign_id:
                raise AiTeamServiceError("Recipient not found")
        else:
            recipient = db.execute(
                select(AiTeamCampaignRecipient)
                .where(AiTeamCampaignRecipient.campaign_id == campaign_id)
                .order_by(AiTeamCampaignRecipient.created_at.asc())
                .limit(1)
            ).scalar_one_or_none()
        rendered = AiTeamCampaignService.render_for_recipient(
            db, campaign, recipient, sample=recipient is None
        )
        return {
            "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
            "recipient": AiTeamCampaignService.recipient_to_dict(recipient) if recipient else None,
            "sample": recipient is None,
            **rendered,
        }

    @staticmethod
    def send_test(db: Session, campaign_id: str, to_email: str) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        dest = str(to_email or "").strip().lower()
        if not dest or "@" not in dest:
            raise AiTeamServiceError("Enter a valid test email address")
        settings = AiTeamService.get_settings(db)
        recipient = db.execute(
            select(AiTeamCampaignRecipient)
            .where(AiTeamCampaignRecipient.campaign_id == campaign_id)
            .order_by(AiTeamCampaignRecipient.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        rendered = AiTeamCampaignService.render_for_recipient(
            db, campaign, recipient, sample=recipient is None
        )
        AiTeamService._deliver_email(
            db,
            settings,
            to_email=dest,
            subject=f"[TEST] {rendered['subject']}",
            text=rendered["text"],
            html=rendered["html"],
        )
        return {"ok": True, "message": f"Test email sent to {dest}"}

    @staticmethod
    def start_send_all(db: Session, campaign_id: str) -> dict[str, Any]:
        campaign = AiTeamCampaignService.refresh_counts(
            db, AiTeamCampaignService.get_campaign(db, campaign_id)
        )
        if campaign.status == "sending":
            return {
                "ok": True,
                "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
                "message": "Campaign is already sending",
            }
        if not (campaign.subject or "").strip():
            raise AiTeamServiceError("Add a subject before sending")
        has_body = bool((campaign.body_text or "").strip())
        has_html = bool((campaign.html_template or "").strip())
        if not has_body and not has_html:
            raise AiTeamServiceError("Add email body or HTML template before sending")
        pending = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == campaign_id,
                AiTeamCampaignRecipient.status.in_(["pending", "failed"]),
            )
        ) or 0
        if int(pending) < 1:
            raise AiTeamServiceError("Upload an Excel audience (or import a scrape) before sending")
        settings = AiTeamService.get_settings(db)
        from_addr = AiTeamService._from_address(settings)
        if not from_addr or "@" not in from_addr:
            raise AiTeamServiceError("Configure From email in Settings before sending")

        # Reset failed → pending for retry
        for row in db.execute(
            select(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == campaign_id,
                AiTeamCampaignRecipient.status == "failed",
            )
        ).scalars().all():
            row.status = "pending"
            row.last_error = None
            row.updated_at = AiTeamCampaignService._now()
            db.add(row)

        now = AiTeamCampaignService._now()
        campaign.status = "sending"
        campaign.started_at = campaign.started_at or now
        campaign.completed_at = None
        campaign.last_error = None
        campaign.updated_at = now
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        from app.workers.ai_team_tasks import send_campaign_task

        send_campaign_task.apply_async(args=[campaign_id], queue="voxbulk")
        return {
            "ok": True,
            "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
            "pending": int(pending),
            "message": f"Sending {int(pending)} email(s) in the background…",
        }

    @staticmethod
    def cancel_send(db: Session, campaign_id: str) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        if campaign.status != "sending":
            raise AiTeamServiceError("Campaign is not sending")
        campaign.status = "cancelled"
        campaign.completed_at = AiTeamCampaignService._now()
        campaign.updated_at = campaign.completed_at
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return {
            "ok": True,
            "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
            "message": "Send cancelled — remaining pending emails will not be sent",
        }

    @staticmethod
    def process_send_job(campaign_id: str, *, pause_seconds: float = 0.35) -> dict[str, Any]:
        """Celery worker: send pending recipients one by one."""
        SessionLocal = __import__("app.core.database", fromlist=["get_sessionmaker"]).get_sessionmaker()
        sent = 0
        failed = 0
        with SessionLocal() as db:
            campaign = db.get(AiTeamCampaign, campaign_id)
            if campaign is None:
                return {"ok": False, "error": "Campaign not found"}
            settings = AiTeamService.get_settings(db)
            max_day = max(1, int(settings.max_emails_per_day or 200))
            day_start = AiTeamCampaignService._now().replace(hour=0, minute=0, second=0, microsecond=0)
            # Count campaign sends today + legacy prospect sends
            sent_today = int(
                db.scalar(
                    select(func.count()).select_from(AiTeamCampaignRecipient).where(
                        AiTeamCampaignRecipient.sent_at >= day_start
                    )
                )
                or 0
            )

            while True:
                db.refresh(campaign)
                if campaign.status == "cancelled":
                    break
                row = db.execute(
                    select(AiTeamCampaignRecipient)
                    .where(
                        AiTeamCampaignRecipient.campaign_id == campaign_id,
                        AiTeamCampaignRecipient.status == "pending",
                    )
                    .order_by(AiTeamCampaignRecipient.created_at.asc())
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    break
                if sent_today >= max_day:
                    campaign.last_error = f"Daily send limit reached ({max_day})"
                    campaign.status = "failed"
                    campaign.completed_at = AiTeamCampaignService._now()
                    campaign.updated_at = campaign.completed_at
                    db.add(campaign)
                    db.commit()
                    break
                try:
                    rendered = AiTeamCampaignService.render_for_recipient(db, campaign, row)
                    result = AiTeamService._deliver_email(
                        db,
                        settings,
                        to_email=row.email,
                        subject=rendered["subject"],
                        text=rendered["text"],
                        html=rendered["html"],
                    )
                    now = AiTeamCampaignService._now()
                    row.status = "sent"
                    row.sent_at = now
                    row.last_error = None
                    row.provider_message_id = result.get("email_id")
                    row.updated_at = now
                    db.add(row)
                    db.commit()
                    sent += 1
                    sent_today += 1
                except Exception as exc:
                    now = AiTeamCampaignService._now()
                    row.status = "failed"
                    row.last_error = str(exc)[:2000]
                    row.updated_at = now
                    db.add(row)
                    db.commit()
                    failed += 1
                    logger.warning("ai_team_campaign_send_failed campaign=%s email=%s err=%s", campaign_id, row.email, exc)
                AiTeamCampaignService.refresh_counts(db, campaign)
                if pause_seconds > 0:
                    time.sleep(pause_seconds)

            db.refresh(campaign)
            if campaign.status == "sending":
                pending_left = db.scalar(
                    select(func.count()).select_from(AiTeamCampaignRecipient).where(
                        AiTeamCampaignRecipient.campaign_id == campaign_id,
                        AiTeamCampaignRecipient.status == "pending",
                    )
                ) or 0
                campaign.status = "sent" if int(pending_left) == 0 else "failed"
                campaign.completed_at = AiTeamCampaignService._now()
                campaign.updated_at = campaign.completed_at
                db.add(campaign)
                db.commit()
            AiTeamCampaignService.refresh_counts(db, campaign)
            return {
                "ok": True,
                "campaign_id": campaign_id,
                "sent": sent,
                "failed": failed,
                "status": campaign.status,
            }
