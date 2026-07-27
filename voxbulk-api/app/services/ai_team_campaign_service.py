from __future__ import annotations

import csv
import io
import logging
import math
import re
import threading
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote, urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_team_apify_run import AiTeamApifyRun
from app.models.ai_team_campaign import AiTeamCampaign, AiTeamCampaignRecipient
from app.models.ai_team_email_suppression import AiTeamEmailSuppression
from app.models.ai_team_email_template import AiTeamEmailTemplate
from app.models.ai_team_inbound_message import AiTeamInboundMessage
from app.models.promo_offer import PromoOffer
from app.services.ai_team_service import AiTeamService, AiTeamServiceError
from app.services.email_html_inline import inline_email_css
from app.services.promo_offer_service import PromoOfferError, PromoOfferService

logger = logging.getLogger(__name__)

# Shared Expo booth trial for Apify / AI Marketing outreach (register → 3 free Expo days).
DEFAULT_EXPO_PROMO_CODE = "EXPO3DAYS"
# Pace cold SMTP outreach to protect IP / domain reputation.
SEND_PER_MINUTE = 3
SEND_PAUSE_SECONDS = 60.0 / SEND_PER_MINUTE  # 20s between emails

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
                VoxBulk · voxbulk.com ·
                <a href="{{unsubscribe_url}}" style="color:#9ca3af;text-decoration:underline;">Unsubscribe</a>
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
    "event_name",
    "event-name",
    "job_title",
    "email",
    "sector",
    "country_code",
    "promo_code",
    "signup_url",
    "trial_url",
    "tracked_trial_url",
    "direct_signup_url",
    "unsubscribe_url",
    "unsubscribe_link",
    "body",
]


class AiTeamCampaignService:
    SEND_PER_MINUTE = SEND_PER_MINUTE
    SEND_PAUSE_SECONDS = SEND_PAUSE_SECONDS

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
    def _open_pixel_url(recipient_id: str) -> str:
        from app.services.brand_assets import api_public_origin

        api = api_public_origin().rstrip("/") or "https://api.voxbulk.com"
        return f"{api}/public/ai-team/c/{recipient_id}/o.gif"

    @staticmethod
    def _click_wrap_url(recipient_id: str, destination: str) -> str:
        from app.services.brand_assets import api_public_origin

        api = api_public_origin().rstrip("/") or "https://api.voxbulk.com"
        return f"{api}/public/ai-team/c/{recipient_id}/click?u={quote(destination, safe='')}"

    @staticmethod
    def resolve_send_interval_seconds(settings: Any | None = None) -> float:
        """Seconds between queued campaign emails (min 1, max 600)."""
        raw = getattr(settings, "send_interval_seconds", None) if settings is not None else None
        try:
            n = float(raw if raw is not None else AiTeamCampaignService.SEND_PAUSE_SECONDS)
        except (TypeError, ValueError):
            n = float(AiTeamCampaignService.SEND_PAUSE_SECONDS)
        return max(1.0, min(n, 600.0))

    @staticmethod
    def _safe_http_url(url: str) -> str | None:
        dest = str(url or "").strip()
        if not dest:
            return None
        parsed = urlparse(dest)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return dest

    @staticmethod
    def record_open(db: Session, recipient_id: str) -> bool:
        rid = str(recipient_id or "").strip()
        if not rid:
            return False
        row = db.get(AiTeamCampaignRecipient, rid)
        if row is None:
            return False
        now = AiTeamCampaignService._now()
        changed = False
        if row.opened_at is None:
            row.opened_at = now
            changed = True
        row.updated_at = now
        db.add(row)
        if changed:
            campaign = db.get(AiTeamCampaign, row.campaign_id)
            if campaign is not None:
                AiTeamCampaignService.refresh_counts(db, campaign)
            else:
                db.commit()
        else:
            db.commit()
        return True

    @staticmethod
    def record_link_click_and_destination(db: Session, recipient_id: str, destination: str) -> str:
        """Record click on any wrapped link and return a safe redirect URL."""
        dest = AiTeamCampaignService._safe_http_url(unquote(str(destination or "")))
        if not dest:
            dest = AiTeamCampaignService._public_signin_url(DEFAULT_EXPO_PROMO_CODE)
        rid = str(recipient_id or "").strip()
        if rid:
            row = db.get(AiTeamCampaignRecipient, rid)
            if row is not None:
                now = AiTeamCampaignService._now()
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
        return dest

    @staticmethod
    def _apply_engagement_tracking(
        html: str,
        recipient_id: str,
        *,
        track_opens: bool = True,
        track_clicks: bool = True,
    ) -> str:
        """Inject open pixel + wrap http(s) links for click tracking."""
        out = str(html or "")
        rid = str(recipient_id or "").strip()
        if not rid or not out.strip():
            return out

        if track_clicks:
            from app.services.brand_assets import api_public_origin

            api = (api_public_origin().rstrip("/") or "https://api.voxbulk.com").lower()

            def _repl(match: re.Match[str]) -> str:
                quote_ch = match.group(1) or '"'
                href = str(match.group(2) or "").strip()
                if not href or href.startswith("#") or href.lower().startswith("mailto:"):
                    return match.group(0)
                if "unsubscribe" in href.lower():
                    return match.group(0)
                if "/public/ai-team/c/" in href.lower():
                    return match.group(0)
                safe = AiTeamCampaignService._safe_http_url(href)
                if not safe:
                    return match.group(0)
                # Don't wrap our own API host links that are already tracking
                if safe.lower().startswith(api) and "/public/ai-team/" in safe.lower():
                    return match.group(0)
                wrapped = AiTeamCampaignService._click_wrap_url(rid, safe)
                return f"href={quote_ch}{wrapped}{quote_ch}"

            out = re.sub(
                r"""href\s*=\s*(['"])(.*?)\1""",
                _repl,
                out,
                flags=re.I | re.S,
            )

        if track_opens and "o.gif" not in out:
            pixel = (
                f'<img src="{AiTeamCampaignService._open_pixel_url(rid)}" width="1" height="1" '
                f'alt="" style="display:none!important;width:1px;height:1px;border:0;" />'
            )
            if re.search(r"</body\s*>", out, re.I):
                out = re.sub(r"</body\s*>", pixel + "</body>", out, count=1, flags=re.I)
            else:
                out = out + pixel
        return out

    @staticmethod
    def _unsubscribe_url(recipient_id: str | None = None) -> str:
        from app.services.brand_assets import api_public_origin

        api = api_public_origin().rstrip("/") or "https://api.voxbulk.com"
        rid = str(recipient_id or "").strip()
        if rid:
            return f"{api}/public/ai-team/c/{rid}/unsubscribe"
        return f"{api}/public/ai-team/unsubscribe/demo"

    @staticmethod
    def _signup_url(promo_code: str | None = None, *, recipient_id: str | None = None) -> str:
        """Always the direct signup URL — HTML/links are source of truth (no href rewrite).

        ``recipient_id`` is accepted for call-site compatibility but ignored.
        Use ``{{tracked_trial_url}}`` when click tracking is wanted explicitly.
        """
        _ = recipient_id
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
    def recipient_vars(
        row: AiTeamCampaignRecipient,
        *,
        db: Session | None = None,
        campaign: AiTeamCampaign | None = None,
    ) -> dict[str, str]:
        promo = str(row.promo_code or "").strip()
        if db is not None:
            promo = AiTeamCampaignService.resolve_promo_code(db, promo)
        elif not promo:
            promo = DEFAULT_EXPO_PROMO_CODE
        direct = AiTeamCampaignService._public_signin_url(promo)
        tracked = AiTeamCampaignService._tracked_trial_url(row.id)
        unsub = AiTeamCampaignService._unsubscribe_url(row.id)
        event = str(getattr(row, "event_name", None) or "").strip()
        if not event and campaign is not None:
            event = str(getattr(campaign, "event_name", None) or "").strip()
        return {
            "first_name": row.first_name or "there",
            "last_name": row.last_name or "",
            "company": row.company_name or "your company",
            "company_name": row.company_name or "your company",
            "event_name": event,
            "event-name": event,
            "job_title": row.job_title or "",
            "email": row.email or "",
            "sector": row.sector or "",
            "country_code": row.country_code or "GB",
            "promo_code": promo,
            # Tracked for real sends so CTA buttons record clicks in Tracking.
            "signup_url": tracked,
            "trial_url": tracked,
            "direct_signup_url": direct,
            "tracked_trial_url": tracked,
            "unsubscribe_url": unsub,
            "unsubscribe_link": unsub,
        }

    @staticmethod
    def campaign_to_dict(row: AiTeamCampaign) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "event_name": getattr(row, "event_name", None) or "",
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
            "scheduled_at": row.scheduled_at.isoformat() if getattr(row, "scheduled_at", None) else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def get_recipient(db: Session, recipient_id: str) -> AiTeamCampaignRecipient:
        row = db.get(AiTeamCampaignRecipient, str(recipient_id or "").strip())
        if row is None:
            raise AiTeamServiceError("Recipient not found")
        return row

    @staticmethod
    def recipient_detail(db: Session, recipient_id: str) -> dict[str, Any]:
        row = AiTeamCampaignService.get_recipient(db, recipient_id)
        item = AiTeamCampaignService.recipient_to_dict(row)
        camp = db.get(AiTeamCampaign, row.campaign_id)
        item["campaign_name"] = camp.name if camp else ""
        item["campaign_subject"] = camp.subject if camp else ""
        # Prefer stored outbound snapshot; fall back to live render for older rows
        out_subj = getattr(row, "last_outbound_subject", None) or ""
        out_text = getattr(row, "last_outbound_text", None) or ""
        out_html = getattr(row, "last_outbound_html", None) or ""
        if camp is not None and (not out_subj or not (out_html or out_text)):
            try:
                rendered = AiTeamCampaignService.render_for_recipient(db, camp, row)
                out_subj = out_subj or rendered.get("subject") or camp.subject or ""
                out_text = out_text or rendered.get("text") or rendered.get("body_text") or ""
                out_html = out_html or rendered.get("html") or ""
            except Exception:
                out_subj = out_subj or (camp.subject or "")
                out_text = out_text or (camp.body_text or "")
        item["outbound_subject"] = out_subj
        item["outbound_text"] = out_text
        item["outbound_html"] = out_html
        item["inbound_subject"] = getattr(row, "last_inbound_subject", None) or ""
        item["inbound_body"] = getattr(row, "last_inbound_body", None) or ""
        return item

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
            "event_name": getattr(row, "event_name", None) or "",
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
            "unsubscribed_at": row.unsubscribed_at.isoformat() if getattr(row, "unsubscribed_at", None) else None,
            "last_inbound_subject": getattr(row, "last_inbound_subject", None) or None,
            "last_inbound_body": getattr(row, "last_inbound_body", None) or None,
            "last_outbound_subject": getattr(row, "last_outbound_subject", None) or None,
            "last_outbound_text": getattr(row, "last_outbound_text", None) or None,
            "last_outbound_html": getattr(row, "last_outbound_html", None) or None,
        }

    @staticmethod
    def inbound_message_detail(db: Session, message_id: str) -> dict[str, Any]:
        msg = AiTeamCampaignService.get_inbound_message(db, message_id)
        data = AiTeamCampaignService.inbound_message_to_dict(msg)
        data["inbound_subject"] = msg.subject or ""
        data["inbound_body"] = msg.body_text or ""
        data["outbound_subject"] = ""
        data["outbound_text"] = ""
        data["outbound_html"] = ""
        data["campaign_name"] = ""
        if msg.recipient_id:
            try:
                detail = AiTeamCampaignService.recipient_detail(db, msg.recipient_id)
                data["outbound_subject"] = detail.get("outbound_subject") or ""
                data["outbound_text"] = detail.get("outbound_text") or ""
                data["outbound_html"] = detail.get("outbound_html") or ""
                data["campaign_name"] = detail.get("campaign_name") or ""
                data["company_name"] = detail.get("company_name") or ""
                data["full_name"] = detail.get("full_name") or ""
            except AiTeamServiceError:
                pass
        elif msg.campaign_id:
            camp = db.get(AiTeamCampaign, msg.campaign_id)
            if camp:
                data["campaign_name"] = camp.name
                data["outbound_subject"] = camp.subject or ""
                data["outbound_text"] = camp.body_text or ""
                data["outbound_html"] = camp.html_template or ""
        return data


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
            row.html_template = inline_email_css(str(html) if html is not None else None)
        if "template_id" in payload:
            tid = str(payload.get("template_id") or "").strip() or None
            row.template_id = tid
        if "event_name" in payload:
            row.event_name = str(payload.get("event_name") or "").strip()[:255]
        if "scheduled_at" in payload:
            raw = payload.get("scheduled_at")
            if raw is None or str(raw).strip() == "":
                row.scheduled_at = None
                if row.status == "scheduled":
                    row.status = "draft"
            else:
                from datetime import datetime as _dt

                text = str(raw).strip().replace("Z", "+00:00")
                try:
                    parsed = _dt.fromisoformat(text)
                except ValueError as exc:
                    raise AiTeamServiceError("Invalid scheduled_at datetime") from exc
                if parsed.tzinfo is not None:
                    parsed = parsed.replace(tzinfo=None)
                row.scheduled_at = parsed
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
            html_template=inline_email_css(
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
            row.html_template = inline_email_css(str(html) if html is not None else None)
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

        sum_received = int(
            db.scalar(
                select(func.count()).select_from(AiTeamCampaignRecipient).where(
                    (AiTeamCampaignRecipient.replied_at.is_not(None))
                    | (AiTeamCampaignRecipient.last_inbound_body.is_not(None))
                )
            )
            or 0
        )
        inbox_total = int(db.scalar(select(func.count()).select_from(AiTeamInboundMessage)) or 0)

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
        elif st == "received":
            # Only real inbound replies (IMAP). Use Sent filter for outbound-only rows.
            stmt = stmt.where(
                (AiTeamCampaignRecipient.replied_at.is_not(None))
                | (AiTeamCampaignRecipient.last_inbound_body.is_not(None))
            )
        elif st == "unsubscribed":
            stmt = stmt.where(
                (AiTeamCampaignRecipient.unsubscribed_at.is_not(None))
                | (AiTeamCampaignRecipient.status == "unsubscribed")
            )
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

        inbox_rows = list(
            db.execute(
                select(AiTeamInboundMessage)
                .order_by(AiTeamInboundMessage.received_at.desc())
                .limit(100)
            ).scalars().all()
        )
        inbox = [AiTeamCampaignService.inbound_message_to_dict(r) for r in inbox_rows]

        return {
            "summary": {
                "campaigns": len(campaigns),
                "recipients": sum_recipients,
                "sent": sum_sent,
                "failed": sum_failed,
                "pending": sum_pending,
                "clicked": sum_clicked,
                "opened": sum_opened,
                "received": sum_received,
                "inbox": inbox_total,
            },
            "campaigns": campaign_dicts,
            "activity": activity,
            "inbox": inbox,
        }

    @staticmethod
    def inbound_message_to_dict(row: AiTeamInboundMessage) -> dict[str, Any]:
        return {
            "id": row.id,
            "from_email": row.from_email,
            "subject": row.subject,
            "body_text": row.body_text,
            "matched": bool(row.matched),
            "recipient_id": row.recipient_id,
            "campaign_id": row.campaign_id,
            "received_at": row.received_at.isoformat() if row.received_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def get_inbound_message(db: Session, message_id: str) -> AiTeamInboundMessage:
        row = db.get(AiTeamInboundMessage, str(message_id or "").strip())
        if row is None:
            raise AiTeamServiceError("Inbox message not found")
        return row

    @staticmethod
    def delete_inbound_message(db: Session, message_id: str) -> dict[str, Any]:
        row = AiTeamCampaignService.get_inbound_message(db, message_id)
        mid = row.id
        db.delete(row)
        db.commit()
        return {"ok": True, "deleted": mid}

    @staticmethod
    def generate_reply_draft(
        db: Session,
        *,
        inbound_message_id: str | None = None,
        recipient_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate an editable AI reply draft (DeepSeek) for an inbox message or recipient."""
        from_email = ""
        inbound_subject = ""
        inbound_body = ""
        company = ""
        first_name = ""
        campaign_subject = ""

        if inbound_message_id:
            msg = AiTeamCampaignService.get_inbound_message(db, inbound_message_id)
            from_email = msg.from_email or ""
            inbound_subject = msg.subject or ""
            inbound_body = msg.body_text or ""
            if msg.recipient_id:
                recip = db.get(AiTeamCampaignRecipient, msg.recipient_id)
                if recip is not None:
                    company = recip.company_name or ""
                    first_name = recip.first_name or ""
                    camp = db.get(AiTeamCampaign, recip.campaign_id)
                    if camp is not None:
                        campaign_subject = camp.subject or ""
            if msg.campaign_id and not campaign_subject:
                camp = db.get(AiTeamCampaign, msg.campaign_id)
                if camp is not None:
                    campaign_subject = camp.subject or ""
        elif recipient_id:
            recip = db.get(AiTeamCampaignRecipient, str(recipient_id or "").strip())
            if recip is None:
                raise AiTeamServiceError("Recipient not found")
            from_email = recip.email or ""
            inbound_subject = recip.last_inbound_subject or ""
            inbound_body = recip.last_inbound_body or ""
            company = recip.company_name or ""
            first_name = recip.first_name or ""
            camp = db.get(AiTeamCampaign, recip.campaign_id)
            if camp is not None:
                campaign_subject = camp.subject or ""
        else:
            raise AiTeamServiceError("inbound_message_id or recipient_id required")

        if not from_email or "@" not in from_email:
            raise AiTeamServiceError("No From address to reply to")

        settings = AiTeamService.get_settings(db)
        base = (inbound_subject or campaign_subject or "VoxBulk").strip() or "VoxBulk"
        if base.lower().startswith("re:"):
            reply_subject = base[:500]
        else:
            reply_subject = f"Re: {base}"[:500]

        default_sig = "Best,\nVoxBulk team · voxbulk.com"
        signature = getattr(settings, "email_signature", None) or default_sig
        inbound_snippet = (inbound_body or "(empty)")[:4000]

        promo_code = DEFAULT_EXPO_PROMO_CODE
        signup_url = f"https://voxbulk.com/signin?promo={promo_code}"
        from app.services.ai_team_reply_kb import build_reply_kb_context

        kb = build_reply_kb_context(
            from_email=from_email,
            inbound_subject=inbound_subject,
            inbound_body=inbound_body,
            promo_code=promo_code,
            signup_url=signup_url,
        )

        system = (
            "You write professional B2B email replies for VoxBulk "
            "(customer feedback, WhatsApp surveys, voice AI for expo/events). "
            "Return JSON with keys subject and body only. "
            "Body is plain text with short paragraphs and line breaks. "
            "Be polished, clear, and courteous — not salesy or pushy. "
            "You MUST follow the Knowledge base and matched playbooks below. "
            "Do not invent pricing, expired trials, contracts, or technical claims. "
            f"Tone: {getattr(settings, 'email_tone', None) or 'professional and warm'}.\n\n"
            f"{kb['prompt_block']}"
        )
        primary = (kb.get("tags") or ["general"])[0]
        user = (
            f"Reply to this inbound email.\n"
            f"Primary playbook to apply: {primary}\n"
            f"From: {from_email}\n"
            f"Name: {first_name or 'there'}\n"
            f"Company: {company or 'their company'}\n"
            f"Their subject: {inbound_subject or '(none)'}\n"
            f"Their message:\n{inbound_snippet}\n\n"
            f"Suggested subject: {reply_subject}\n"
            f"Signup URL to include when relevant: {kb.get('signup_url')}\n"
            f"Promo code to include when relevant: {kb.get('promo_code')}\n"
            f"Signature to append:\n{signature}"
        )
        try:
            from app.services.agents.base import AgentMessage
            from app.services.providers.openai_service import OpenAIProviderService

            result = OpenAIProviderService.complete(
                db,
                system_prompt=system,
                messages=[AgentMessage(role="user", content=user)],
                max_tokens=700,
                temperature=0.35,
                provider="deepseek",
            )
            text = str(result.assistant_text or "").strip()
        except Exception as exc:
            logger.warning("ai_team_generate_reply_failed err=%s", exc)
            if kb.get("from_is_free_email") or "free_personal_email" in (kb.get("tags") or []):
                text = (
                    f"Hi {first_name or 'there'},\n\n"
                    "Thanks for getting back to us — and sorry for the confusion.\n\n"
                    "The free Expo trial only activates when you register with a company / work email "
                    "(not Gmail, Outlook, Yahoo, or other personal addresses). "
                    "That’s why the account can look like it needs payment.\n\n"
                    f"Please sign up again with your work email here:\n{signup_url}\n\n"
                    f"Use code {promo_code} for the 3-day Expo trial (no card when eligible).\n\n"
                    f"{signature}"
                )
            else:
                text = (
                    f"Hi {first_name or 'there'},\n\n"
                    "Thanks for getting back to us — happy to help.\n\n"
                    f"If you’re trying the Expo offer, register with your company email here:\n{signup_url}\n\n"
                    "If something still blocks access, reply with a short screenshot note and we’ll sort it.\n\n"
                    f"{signature}"
                )

        subject_out = reply_subject
        body_out = text
        try:
            import json as _json

            parsed = _json.loads(text)
            if isinstance(parsed, dict):
                subject_out = str(parsed.get("subject") or subject_out).strip()[:500] or subject_out
                body_out = str(parsed.get("body") or text).strip() or text
        except Exception:
            if "\n" in text:
                first, rest = text.split("\n", 1)
                if first.lower().startswith("subject:"):
                    subject_out = first.split(":", 1)[1].strip()[:500] or subject_out
                    body_out = rest.strip() or text

        return {
            "ok": True,
            "from_email": from_email,
            "subject": subject_out,
            "body": body_out,
            "inbound_message_id": inbound_message_id,
            "recipient_id": recipient_id,
            "kb_tags": kb.get("tags") or [],
            "from_is_free_email": bool(kb.get("from_is_free_email")),
        }

    @staticmethod
    def send_inbox_reply(
        db: Session,
        message_id: str,
        *,
        body: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Reply to an IMAP inbox message From address (matched or unmatched)."""
        msg = AiTeamCampaignService.get_inbound_message(db, message_id)
        to_email = str(msg.from_email or "").strip().lower()
        if not to_email or "@" not in to_email:
            raise AiTeamServiceError("Inbox message has no From address")
        text = str(body or "").strip()
        if not text:
            raise AiTeamServiceError("Enter a reply message")
        settings = AiTeamService.get_settings(db)
        subj = str(subject or "").strip()
        if not subj:
            base = (msg.subject or "VoxBulk").strip() or "VoxBulk"
            subj = base if base.lower().startswith("re:") else f"Re: {base}"
        if re.search(r"</?(?:p|div|br|table|a|html|body)\b", text, re.I):
            html = text
        else:
            parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            if not parts:
                parts = [text]
            html = "".join(
                f'<p style="margin:0 0 12px;">{p.replace(chr(10), "<br>")}</p>'
                for p in parts
            )
        AiTeamService._deliver_email(
            db,
            settings,
            to_email=to_email,
            subject=subj,
            text=text,
            html=html,
            recipient_id=msg.recipient_id,
        )
        now = AiTeamCampaignService._now()
        if msg.recipient_id:
            recip = db.get(AiTeamCampaignRecipient, msg.recipient_id)
            if recip is not None:
                recip.replied_at = recip.replied_at or now
                recip.updated_at = now
                db.add(recip)
                camp = db.get(AiTeamCampaign, recip.campaign_id)
                if camp is not None:
                    AiTeamCampaignService.refresh_counts(db, camp)
        db.commit()
        return {"ok": True, "message": f"Reply sent to {to_email}"}


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
    def delete_recipient(db: Session, campaign_id: str, recipient_id: str) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        if campaign.status == "sending":
            raise AiTeamServiceError("Cannot remove contacts while sending — pause first")
        row = db.get(AiTeamCampaignRecipient, str(recipient_id or "").strip())
        if row is None or row.campaign_id != campaign_id:
            raise AiTeamServiceError("Contact not found in this campaign")
        email = row.email
        db.delete(row)
        db.commit()
        AiTeamCampaignService.refresh_counts(db, campaign)
        return {"ok": True, "deleted": recipient_id, "email": email, "total": campaign.total_count}

    @staticmethod
    def list_suppressions(db: Session, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(AiTeamEmailSuppression)
                .order_by(AiTeamEmailSuppression.unsubscribed_at.desc())
                .limit(max(1, min(int(limit or 500), 2000)))
            ).scalars().all()
        )
        return [
            {
                "id": r.id,
                "email": r.email,
                "unsubscribed_at": r.unsubscribed_at.isoformat() if r.unsubscribed_at else None,
                "source_campaign_id": r.source_campaign_id,
                "source_recipient_id": r.source_recipient_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    @staticmethod
    def delete_suppression(db: Session, suppression_id: str) -> dict[str, Any]:
        row = db.get(AiTeamEmailSuppression, str(suppression_id or "").strip())
        if row is None:
            raise AiTeamServiceError("Unsubscribe entry not found")
        email = row.email
        db.delete(row)
        db.commit()
        return {"ok": True, "deleted": suppression_id, "email": email}

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
        updated = 0
        skipped = 0
        now = AiTeamCampaignService._now()
        campaign_event = str(getattr(campaign, "event_name", None) or "").strip()
        for raw in rows:
            email = str(raw.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue
            event_name = str(
                raw.get("event_name") or raw.get("event-name") or raw.get("event") or ""
            ).strip()[:255]
            if email in existing:
                row = existing[email]
                row.first_name = str(raw.get("first_name") or row.first_name or "").strip()[:120]
                row.last_name = str(raw.get("last_name") or row.last_name or "").strip()[:120]
                company = str(raw.get("company_name") or raw.get("company") or "").strip()[:255]
                if company:
                    row.company_name = company
                if event_name:
                    row.event_name = event_name
                job = str(raw.get("job_title") or "").strip()[:255]
                if job:
                    row.job_title = job
                # Re-import should re-queue previously sent/failed so Send all works again
                if row.status in {"sent", "failed", "cancelled"}:
                    row.status = "pending"
                    row.last_error = None
                    row.sent_at = None
                row.updated_at = now
                db.add(row)
                updated += 1
                continue
            suppressed = AiTeamCampaignService.is_email_suppressed(db, email)
            row = AiTeamCampaignRecipient(
                campaign_id=campaign.id,
                email=email,
                first_name=str(raw.get("first_name") or "").strip()[:120],
                last_name=str(raw.get("last_name") or "").strip()[:120],
                company_name=str(raw.get("company_name") or raw.get("company") or "").strip()[:255],
                event_name=(event_name or campaign_event)[:255],
                job_title=str(raw.get("job_title") or "").strip()[:255],
                sector=str(raw.get("sector") or "").strip().lower()[:64],
                country_code=(str(raw.get("country_code") or raw.get("country") or "GB").strip().upper()[:8] or "GB"),
                promo_code=AiTeamCampaignService.resolve_promo_code(
                    db, str(raw.get("promo_code") or "").strip()
                )[:64],
                status="unsubscribed" if suppressed else "pending",
                unsubscribed_at=now if suppressed else None,
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
        return {
            "ok": True,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total": campaign.total_count,
        }

    @staticmethod
    def import_csv(
        db: Session,
        campaign_id: str,
        raw: bytes,
        mapping: dict[str, str] | None = None,
        *,
        filename: str = "",
    ) -> dict[str, Any]:
        from app.services.csv_column_auto_map import (
            auto_map_headers,
            parse_tabular_bytes,
            rows_from_mapping,
        )

        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        headers, raw_rows = parse_tabular_bytes(raw, filename)
        if not headers:
            raise AiTeamServiceError("File has no header row")
        auto = auto_map_headers(headers)
        user_map = {k: str(v or "").strip() for k, v in (mapping or {}).items() if str(v or "").strip()}
        # Prefer user overrides when provided; fill gaps from auto-detect
        final_map = {**auto, **user_map}
        if not final_map.get("email"):
            raise AiTeamServiceError(
                "Could not find an email column. Use a header like Email, E-mail, or Email Address."
            )
        rows = rows_from_mapping(raw_rows, final_map)
        if not rows:
            raise AiTeamServiceError("No valid email rows found in the sheet")
        result = AiTeamCampaignService._upsert_recipient_rows(db, campaign, rows)
        result["mapping_used"] = final_map
        result["contacts_preview"] = rows[:50]
        return result

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
                    "event_name": str(c.get("event_name") or c.get("event-name") or "").strip(),
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
        campaign_event = str(getattr(campaign, "event_name", None) or "").strip()
        if sample or recipient is None:
            promo = default_promo
            direct = AiTeamCampaignService._public_signin_url(promo)
            vars_map = {
                "first_name": "Alex",
                "last_name": "Taylor",
                "company": "Example Ltd",
                "company_name": "Example Ltd",
                "event_name": campaign_event or "London Packaging Week",
                "event-name": campaign_event or "London Packaging Week",
                "job_title": "Operations Director",
                "email": "alex@example.com",
                "sector": "expo",
                "country_code": "GB",
                "promo_code": promo,
                "signup_url": direct,
                "trial_url": direct,
                "direct_signup_url": direct,
                "tracked_trial_url": direct,
                "unsubscribe_url": AiTeamCampaignService._unsubscribe_url(None),
                "unsubscribe_link": AiTeamCampaignService._unsubscribe_url(None),
            }
        else:
            vars_map = AiTeamCampaignService.recipient_vars(recipient, db=db, campaign=campaign)
            if not (recipient.promo_code or "").strip():
                recipient.promo_code = vars_map["promo_code"]
                recipient.updated_at = AiTeamCampaignService._now()
                db.add(recipient)
                db.commit()
            # Fill blank recipient event from campaign default at send/preview time
            if not (recipient.event_name or "").strip() and campaign_event:
                recipient.event_name = campaign_event
                recipient.updated_at = AiTeamCampaignService._now()
                db.add(recipient)
                db.commit()
                vars_map["event_name"] = campaign_event
                vars_map["event-name"] = campaign_event

        body_merged = AiTeamCampaignService._apply_merge(campaign.body_text or "", vars_map)
        subject = AiTeamCampaignService._apply_merge(campaign.subject or "", vars_map).strip() or "Hello"
        template = str(campaign.html_template or "").strip()

        if template:
            # Authored HTML is source of truth — never wrap or replace with default shell.
            if "{{body}}" in template:
                vars_map["body"] = body_merged
            else:
                vars_map["body"] = ""
        elif body_merged and re.search(r"</?(?:html|body|table|div|a)\b", body_merged, re.I):
            # No wrapper: body itself is a full HTML document.
            template = body_merged
            vars_map["body"] = ""
        else:
            template = _DEFAULT_HTML_TEMPLATE
            vars_map["body"] = body_merged.replace("\n", "<br>") if body_merged else ""

        html = AiTeamCampaignService._apply_merge(template, vars_map)
        html = re.sub(r"\{\{[a-zA-Z0-9_-]+\}\}", "", html)
        # Inline CSS so Gmail/Outlook keep colours/padding even when <style> is stripped.
        html = inline_email_css(html)
        if recipient is not None and not sample:
            settings = AiTeamService.get_settings(db)
            html = AiTeamCampaignService._apply_engagement_tracking(
                html,
                recipient.id,
                track_opens=bool(getattr(settings, "track_opens", True)),
                track_clicks=True,
            )
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
        # Prefer an existing audience row for merge data; else use sample merge.
        sample_source = db.execute(
            select(AiTeamCampaignRecipient)
            .where(AiTeamCampaignRecipient.campaign_id == campaign_id)
            .order_by(AiTeamCampaignRecipient.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        # Ensure the test mailbox is a recipient so IMAP replies (From = dest) can match.
        test_row = db.execute(
            select(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == campaign_id,
                func.lower(AiTeamCampaignRecipient.email) == dest,
            )
        ).scalar_one_or_none()
        now = AiTeamCampaignService._now()
        created_for_test = False
        prior_status = None
        if test_row is None:
            created_for_test = True
            test_row = AiTeamCampaignRecipient(
                campaign_id=campaign.id,
                email=dest,
                first_name=(sample_source.first_name if sample_source else "Test")[:120],
                last_name=(sample_source.last_name if sample_source else "")[:120],
                company_name=(sample_source.company_name if sample_source else "Test company")[:255],
                event_name=(
                    (sample_source.event_name if sample_source else "")
                    or getattr(campaign, "event_name", None)
                    or ""
                )[:255],
                job_title=(sample_source.job_title if sample_source else "")[:255],
                sector=(sample_source.sector if sample_source else "expo")[:64],
                country_code=(sample_source.country_code if sample_source else "GB")[:8],
                promo_code=AiTeamCampaignService.resolve_promo_code(
                    db, sample_source.promo_code if sample_source else None
                )[:64],
                status="test",
                created_at=now,
                updated_at=now,
            )
            db.add(test_row)
            db.commit()
            db.refresh(test_row)
            AiTeamCampaignService.refresh_counts(db, campaign)
        else:
            prior_status = str(test_row.status or "pending")

        rendered = AiTeamCampaignService.render_for_recipient(db, campaign, test_row, sample=False)
        # [TEST] is ONLY for the Send test button — Send all never adds this prefix.
        test_subject = f"[TEST] {rendered['subject']}"
        AiTeamService._deliver_email(
            db,
            settings,
            to_email=dest,
            subject=test_subject,
            text=rendered["text"],
            html=rendered["html"],
            recipient_id=test_row.id,
        )
        # Do not mark real audience contacts as "sent" — that blocked Send all / looked like a campaign send.
        if created_for_test:
            test_row.status = "test"
            test_row.sent_at = now
        else:
            test_row.status = prior_status or "pending"
            if test_row.status == "sent":
                test_row.sent_at = test_row.sent_at or now
            else:
                # Keep them queued for the real campaign send
                test_row.sent_at = None
        test_row.updated_at = now
        test_row.last_error = None
        test_row.last_outbound_subject = test_subject[:500]
        test_row.last_outbound_text = str(rendered.get("text") or "")[:50000] or None
        test_row.last_outbound_html = str(rendered.get("html") or "")[:200000] or None
        db.add(test_row)
        db.commit()
        interval = AiTeamCampaignService.resolve_send_interval_seconds(settings)
        open_url = AiTeamCampaignService._open_pixel_url(test_row.id)
        click_url = AiTeamCampaignService._tracked_trial_url(test_row.id)
        return {
            "ok": True,
            "message": (
                f"Test only — subject starts with [TEST]. Send all uses the real subject (no [TEST]). "
                f"Sent to {dest}. Queue pace: 1 every {int(interval)}s."
            ),
            "recipient_id": test_row.id,
            "send_interval_seconds": int(interval),
            "open_pixel_url": open_url,
            "trial_click_url": click_url,
            "is_test": True,
        }

    @staticmethod
    def send_recipient_reply(
        db: Session,
        recipient_id: str,
        *,
        body: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Compose and send a follow-up to a campaign recipient (Tracking → Received)."""
        rid = str(recipient_id or "").strip()
        row = db.get(AiTeamCampaignRecipient, rid) if rid else None
        if row is None:
            raise AiTeamServiceError("Recipient not found")
        text = str(body or "").strip()
        if not text:
            raise AiTeamServiceError("Enter a reply message")
        campaign = AiTeamCampaignService.get_campaign(db, row.campaign_id)
        settings = AiTeamService.get_settings(db)
        subj = str(subject or "").strip()
        if not subj:
            base = (campaign.subject or "VoxBulk").strip() or "VoxBulk"
            subj = base if base.lower().startswith("re:") else f"Re: {base}"
        if re.search(r"</?(?:p|div|br|table|a|html|body)\b", text, re.I):
            html = text
        else:
            parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            if not parts:
                parts = [text]
            html = "".join(
                f'<p style="margin:0 0 12px;">{p.replace(chr(10), "<br>")}</p>'
                for p in parts
            )
        AiTeamService._deliver_email(
            db,
            settings,
            to_email=row.email,
            subject=subj,
            text=text,
            html=html,
            recipient_id=row.id,
        )
        now = AiTeamCampaignService._now()
        row.replied_at = row.replied_at or now
        row.updated_at = now
        db.add(row)
        AiTeamCampaignService.refresh_counts(db, campaign)
        return {
            "ok": True,
            "message": f"Reply sent to {row.email}",
            "recipient": AiTeamCampaignService.recipient_to_dict(row),
        }

    @staticmethod
    def start_send_all(
        db: Session,
        campaign_id: str,
        *,
        resend: bool = False,
    ) -> dict[str, Any]:
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

        total = int(campaign.total_count or 0)
        if total < 1:
            raise AiTeamServiceError(
                "Audience is empty. Drop Excel/CSV → Preview contacts → click Add to audience first."
            )

        if resend:
            now_reset = AiTeamCampaignService._now()
            for row in db.execute(
                select(AiTeamCampaignRecipient).where(
                    AiTeamCampaignRecipient.campaign_id == campaign_id,
                    AiTeamCampaignRecipient.status.in_(["sent", "failed"]),
                )
            ).scalars().all():
                row.status = "pending"
                row.last_error = None
                row.sent_at = None
                row.updated_at = now_reset
                db.add(row)
            db.commit()
            campaign = AiTeamCampaignService.refresh_counts(db, campaign)

        pending = db.scalar(
            select(func.count()).select_from(AiTeamCampaignRecipient).where(
                AiTeamCampaignRecipient.campaign_id == campaign_id,
                AiTeamCampaignRecipient.status.in_(["pending", "failed"]),
            )
        ) or 0
        if int(pending) < 1:
            sent_n = int(campaign.sent_count or 0)
            failed_n = int(campaign.failed_count or 0)
            if sent_n > 0:
                raise AiTeamServiceError(
                    f"All {sent_n} contact(s) were already sent. "
                    "Use Resend, or re-import the sheet (Add to audience) to queue them again."
                )
            if failed_n < 1 and total > 0:
                raise AiTeamServiceError(
                    f"Audience has {total} contact(s) but none are pending "
                    "(they may be unsubscribed). Re-import the sheet or pick another list."
                )
            raise AiTeamServiceError(
                "No pending emails to send. Drop Excel/CSV and click Add to audience."
            )
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

        rate_pause = AiTeamCampaignService.resolve_send_interval_seconds(settings)
        rate_per_min = max(1, int(round(60.0 / rate_pause)))
        eta_min = max(1, int(math.ceil(int(pending) * rate_pause / 60.0)))
        queued_via = "celery"
        try:
            send_campaign_task.apply_async(args=[campaign_id], queue="voxbulk")
        except Exception as exc:
            logger.warning("ai_team_send_celery_enqueue_failed campaign=%s err=%s — using thread", campaign_id, exc)
            queued_via = "thread"

            def _run() -> None:
                try:
                    AiTeamCampaignService.process_send_job(campaign_id)
                except Exception as run_exc:
                    logger.exception("ai_team_send_thread_failed campaign=%s err=%s", campaign_id, run_exc)

            threading.Thread(target=_run, name=f"ai-team-send-{campaign_id[:8]}", daemon=True).start()

        return {
            "ok": True,
            "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
            "pending": int(pending),
            "send_interval_seconds": int(rate_pause),
            "send_per_minute": rate_per_min,
            "eta_minutes": eta_min,
            "queued_via": queued_via,
            "message": (
                f"Queued {int(pending)} email(s) · 1 every {int(rate_pause)}s "
                f"(~{eta_min} min). Watch the progress bar."
            ),
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
    def pause_send(db: Session, campaign_id: str) -> dict[str, Any]:
        """Stop the send queue; remaining pending stay queued until Resume."""
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        if campaign.status not in {"sending", "scheduled"}:
            raise AiTeamServiceError("Pause only works while sending or scheduled")
        campaign.status = "paused"
        campaign.updated_at = AiTeamCampaignService._now()
        campaign.last_error = None
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return {
            "ok": True,
            "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
            "message": "Paused — remaining emails will not send until you Resume",
        }

    @staticmethod
    def resume_send(db: Session, campaign_id: str) -> dict[str, Any]:
        campaign = AiTeamCampaignService.get_campaign(db, campaign_id)
        if campaign.status not in {"paused", "paused_daily_limit", "cancelled", "scheduled"}:
            raise AiTeamServiceError("Campaign is not paused")
        scheduled = getattr(campaign, "scheduled_at", None)
        now = AiTeamCampaignService._now()
        if campaign.status == "scheduled" and scheduled and scheduled > now:
            return {
                "ok": True,
                "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
                "message": f"Still scheduled for {scheduled.isoformat()} — wait or clear the schedule",
            }
        return AiTeamCampaignService.start_send_all(db, campaign_id, resend=False)

    @staticmethod
    def schedule_send(db: Session, campaign_id: str, scheduled_at: str | datetime | None) -> dict[str, Any]:
        """Queue campaign to start at scheduled_at (UTC naive / local server time)."""
        campaign = AiTeamCampaignService.refresh_counts(
            db, AiTeamCampaignService.get_campaign(db, campaign_id)
        )
        if campaign.status == "sending":
            raise AiTeamServiceError("Cannot schedule while already sending — pause first")
        if int(campaign.total_count or 0) < 1:
            raise AiTeamServiceError("Add an audience before scheduling")
        if not (campaign.subject or "").strip():
            raise AiTeamServiceError("Add a subject before scheduling")
        raw = scheduled_at
        if raw is None or str(raw).strip() == "":
            raise AiTeamServiceError("Pick a send date and time")
        if isinstance(raw, datetime):
            when = raw
        else:
            text = str(raw).strip().replace("Z", "+00:00")
            try:
                when = datetime.fromisoformat(text)
            except ValueError as exc:
                raise AiTeamServiceError("Invalid schedule datetime") from exc
        if when.tzinfo is not None:
            when = when.replace(tzinfo=None)
        now = AiTeamCampaignService._now()
        if when <= now:
            # Due now — start immediately
            campaign.scheduled_at = when
            db.add(campaign)
            db.commit()
            return AiTeamCampaignService.start_send_all(db, campaign_id)
        campaign.scheduled_at = when
        campaign.status = "scheduled"
        campaign.completed_at = None
        campaign.last_error = None
        campaign.updated_at = now
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return {
            "ok": True,
            "campaign": AiTeamCampaignService.campaign_to_dict(campaign),
            "message": f"Scheduled to start at {when.isoformat()} (server time)",
        }

    @staticmethod
    def start_due_scheduled_campaigns(db: Session) -> dict[str, Any]:
        now = AiTeamCampaignService._now()
        rows = list(
            db.execute(
                select(AiTeamCampaign).where(
                    AiTeamCampaign.status == "scheduled",
                    AiTeamCampaign.scheduled_at.is_not(None),
                    AiTeamCampaign.scheduled_at <= now,
                )
            ).scalars().all()
        )
        started = 0
        errors: list[str] = []
        for camp in rows:
            try:
                AiTeamCampaignService.start_send_all(db, camp.id)
                started += 1
            except Exception as exc:
                errors.append(f"{camp.id}: {exc}")
                logger.warning("ai_team_scheduled_start_failed campaign=%s err=%s", camp.id, exc)
        return {"ok": True, "started": started, "checked": len(rows), "errors": errors}

    @staticmethod
    def process_send_job(
        campaign_id: str,
        *,
        pause_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Celery/thread worker: send pending recipients one-by-one at configured interval."""
        SessionLocal = __import__("app.core.database", fromlist=["get_sessionmaker"]).get_sessionmaker()
        sent = 0
        failed = 0
        with SessionLocal() as db:
            campaign = db.get(AiTeamCampaign, campaign_id)
            if campaign is None:
                return {"ok": False, "error": "Campaign not found"}
            settings = AiTeamService.get_settings(db)
            if pause_seconds is None:
                pause_seconds = AiTeamCampaignService.resolve_send_interval_seconds(settings)
            max_day = max(1, int(settings.max_emails_per_day or 50))
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
                if campaign.status in {"cancelled", "paused"}:
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
                if AiTeamCampaignService.is_email_suppressed(db, row.email):
                    now = AiTeamCampaignService._now()
                    row.status = "unsubscribed"
                    row.unsubscribed_at = row.unsubscribed_at or now
                    row.updated_at = now
                    db.add(row)
                    db.commit()
                    AiTeamCampaignService.refresh_counts(db, campaign)
                    continue
                if sent_today >= max_day:
                    campaign.last_error = (
                        f"Daily send limit reached ({max_day}). "
                        "Raise Max/day under Sending only if your domain is warmed up."
                    )
                    campaign.status = "paused_daily_limit"
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
                        recipient_id=row.id,
                    )
                    now = AiTeamCampaignService._now()
                    row.status = "sent"
                    row.sent_at = now
                    row.last_error = None
                    row.provider_message_id = result.get("email_id")
                    row.last_outbound_subject = str(rendered.get("subject") or "")[:500] or None
                    row.last_outbound_text = str(rendered.get("text") or rendered.get("body_text") or "")[:50000] or None
                    row.last_outbound_html = str(rendered.get("html") or "")[:200000] or None
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
                # Pace before next send (skip sleep when queue is empty — loop will exit)
                if pause_seconds > 0:
                    more_pending = db.scalar(
                        select(func.count()).select_from(AiTeamCampaignRecipient).where(
                            AiTeamCampaignRecipient.campaign_id == campaign_id,
                            AiTeamCampaignRecipient.status == "pending",
                        )
                    ) or 0
                    if int(more_pending) > 0:
                        # Re-check cancel while waiting
                        slept = 0.0
                        step = min(2.0, float(pause_seconds))
                        while slept < pause_seconds:
                            time.sleep(step)
                            slept += step
                            db.refresh(campaign)
                            if campaign.status in {"cancelled", "paused"}:
                                break
                        if campaign.status in {"cancelled", "paused"}:
                            break

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
            elif campaign.status == "paused":
                campaign.updated_at = AiTeamCampaignService._now()
                db.add(campaign)
                db.commit()
            AiTeamCampaignService.refresh_counts(db, campaign)
            return {
                "ok": True,
                "campaign_id": campaign_id,
                "sent": sent,
                "failed": failed,
                "status": campaign.status,
                "send_per_minute": max(1, int(round(60.0 / float(pause_seconds or 1)))),
                "send_interval_seconds": int(pause_seconds or 0),
            }

    @staticmethod
    def is_email_suppressed(db: Session, email: str) -> bool:
        addr = str(email or "").strip().lower()
        if not addr or "@" not in addr:
            return False
        return (
            db.execute(
                select(AiTeamEmailSuppression.id).where(AiTeamEmailSuppression.email == addr).limit(1)
            ).scalar_one_or_none()
            is not None
        )

    @staticmethod
    def unsubscribe_confirmation_html(*, already: bool = False) -> str:
        title = "Already unsubscribed" if already else "Unsubscribed"
        msg = (
            "You were already removed from VoxBulk outreach emails."
            if already
            else "You have been unsubscribed from VoxBulk outreach emails. You will not receive further campaign messages from this list."
        )
        return (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{title}</title></head>"
            "<body style=\"font-family:Arial,Helvetica,sans-serif;background:#f4f6f8;margin:0;padding:40px 16px;\">"
            "<div style=\"max-width:480px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;"
            "border-radius:8px;padding:28px 24px;color:#1a1a1a;\">"
            f"<h1 style=\"margin:0 0 12px;font-size:20px;\">{title}</h1>"
            f"<p style=\"margin:0;font-size:15px;line-height:1.5;\">{msg}</p>"
            "<p style=\"margin:20px 0 0;font-size:12px;color:#9ca3af;\">VoxBulk · voxbulk.com</p>"
            "</div></body></html>"
        )

    @staticmethod
    def process_unsubscribe(db: Session, recipient_id: str | None) -> dict[str, Any]:
        """One-click opt-out: suppress email globally and mark matching recipients."""
        rid = str(recipient_id or "").strip()
        if not rid:
            return {"ok": True, "already": False, "html": AiTeamCampaignService.unsubscribe_confirmation_html()}
        row = db.get(AiTeamCampaignRecipient, rid)
        if row is None:
            return {
                "ok": True,
                "already": True,
                "html": AiTeamCampaignService.unsubscribe_confirmation_html(already=True),
            }
        email = str(row.email or "").strip().lower()
        already = AiTeamCampaignService.is_email_suppressed(db, email)
        now = AiTeamCampaignService._now()
        if email and "@" in email and not already:
            db.add(
                AiTeamEmailSuppression(
                    email=email,
                    unsubscribed_at=now,
                    source_recipient_id=row.id,
                    source_campaign_id=row.campaign_id,
                    created_at=now,
                )
            )
        # Mark this + all pending rows with same email
        targets = list(
            db.execute(
                select(AiTeamCampaignRecipient).where(
                    func.lower(AiTeamCampaignRecipient.email) == email
                )
            ).scalars().all()
        ) if email else [row]
        for t in targets:
            t.unsubscribed_at = t.unsubscribed_at or now
            if t.status in {"pending", "failed"}:
                t.status = "unsubscribed"
            t.updated_at = now
            db.add(t)
        db.commit()
        campaign_ids = {t.campaign_id for t in targets}
        for cid in campaign_ids:
            camp = db.get(AiTeamCampaign, cid)
            if camp is not None:
                AiTeamCampaignService.refresh_counts(db, camp)
        return {
            "ok": True,
            "already": already,
            "email": email,
            "html": AiTeamCampaignService.unsubscribe_confirmation_html(already=already),
        }

    @staticmethod
    def normalize_match_email(email: str | None) -> str:
        """Lowercase + Gmail-style normalisation so replies still match audience rows."""
        addr = str(email or "").strip().lower()
        if not addr or "@" not in addr:
            return addr
        local, domain = addr.rsplit("@", 1)
        if domain in {"gmail.com", "googlemail.com"}:
            local = local.split("+", 1)[0].replace(".", "")
            domain = "gmail.com"
        return f"{local}@{domain}"

    @staticmethod
    def record_inbound_reply(
        db: Session,
        *,
        from_email: str,
        subject: str,
        body: str,
        recipient_id: str | None = None,
        reply_to_email: str | None = None,
    ) -> AiTeamCampaignRecipient | None:
        """Match inbound IMAP mail to a campaign recipient.

        Prefer Message-ID / In-Reply-To thread id (``ait-c-<uuid>``), then From / Reply-To.
        """
        rid = str(recipient_id or "").strip()
        if rid:
            row = db.get(AiTeamCampaignRecipient, rid)
            if row is not None:
                return AiTeamCampaignService._apply_inbound_fields(db, row, subject=subject, body=body)

        candidates: list[str] = []
        for raw in (from_email, reply_to_email):
            raw_l = str(raw or "").strip().lower()
            norm = AiTeamCampaignService.normalize_match_email(raw)
            for addr in (raw_l, norm):
                if addr and "@" in addr and addr not in candidates:
                    candidates.append(addr)
        subj_l = str(subject or "").lower()
        looks_like_test_reply = "[test]" in subj_l and (subj_l.startswith("re:") or "re:" in subj_l[:8])

        if not candidates:
            if looks_like_test_reply:
                row = db.execute(
                    select(AiTeamCampaignRecipient)
                    .where(AiTeamCampaignRecipient.status == "sent")
                    .order_by(AiTeamCampaignRecipient.sent_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if row is not None:
                    return AiTeamCampaignService._apply_inbound_fields(db, row, subject=subject, body=body)
            return None

        for addr in candidates:
            row = db.execute(
                select(AiTeamCampaignRecipient)
                .where(
                    func.lower(AiTeamCampaignRecipient.email) == addr,
                    AiTeamCampaignRecipient.status.in_(["sent", "unsubscribed"]),
                )
                .order_by(AiTeamCampaignRecipient.sent_at.desc(), AiTeamCampaignRecipient.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                return AiTeamCampaignService._apply_inbound_fields(db, row, subject=subject, body=body)

        # Gmail dots/+ aliases: compare normalised forms
        recent = list(
            db.execute(
                select(AiTeamCampaignRecipient)
                .where(AiTeamCampaignRecipient.status.in_(["sent", "unsubscribed", "pending"]))
                .order_by(AiTeamCampaignRecipient.sent_at.desc(), AiTeamCampaignRecipient.updated_at.desc())
                .limit(800)
            ).scalars().all()
        )
        norms = {AiTeamCampaignService.normalize_match_email(a) for a in candidates}
        for cand in recent:
            if AiTeamCampaignService.normalize_match_email(cand.email) in norms:
                return AiTeamCampaignService._apply_inbound_fields(db, cand, subject=subject, body=body)

        for addr in candidates:
            row = db.execute(
                select(AiTeamCampaignRecipient)
                .where(func.lower(AiTeamCampaignRecipient.email) == addr)
                .order_by(AiTeamCampaignRecipient.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                return AiTeamCampaignService._apply_inbound_fields(db, row, subject=subject, body=body)

        if looks_like_test_reply:
            row = db.execute(
                select(AiTeamCampaignRecipient)
                .where(AiTeamCampaignRecipient.status == "sent")
                .order_by(AiTeamCampaignRecipient.sent_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                return AiTeamCampaignService._apply_inbound_fields(db, row, subject=subject, body=body)
        return None

    @staticmethod
    def _apply_inbound_fields(
        db: Session,
        row: AiTeamCampaignRecipient,
        *,
        subject: str,
        body: str,
    ) -> AiTeamCampaignRecipient:
        now = AiTeamCampaignService._now()
        row.replied_at = row.replied_at or now
        row.last_inbound_subject = str(subject or "")[:500] or None
        row.last_inbound_body = str(body or "")[:20000] or None
        row.updated_at = now
        db.add(row)
        db.commit()
        campaign = db.get(AiTeamCampaign, row.campaign_id)
        if campaign is not None:
            AiTeamCampaignService.refresh_counts(db, campaign)
        return row

