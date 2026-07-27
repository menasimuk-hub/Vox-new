from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.ai_team_apify_run import AiTeamApifyRun
from app.models.ai_team_message import AiTeamMessage
from app.models.ai_team_prospect import AiTeamProspect
from app.models.ai_team_settings import AiTeamSettings
from app.models.promo_offer import PromoOffer
from app.services.agents.base import AgentMessage
from app.services.apify_service import ApifyService, ApifyServiceError
from app.services.apollo_service import ApolloService, ApolloServiceError
from app.services.expo_directory_scraper_service import ExpoDirectoryScraper, ExpoDirectoryScraperError
from app.services.promo_offer_service import PromoOfferService
from app.services.provider_settings import ProviderSettingsService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.resend_service import ResendService, ResendServiceError

logger = logging.getLogger(__name__)

_DEFAULT_WRITING = (
    "Write a short, direct cold email to {first_name} who is {job_title} at {company} in the {sector} sector. "
    "Focus on saving time on customer feedback. Mention AI phone calls and WhatsApp surveys. "
    "Offer promo code {promo_code}. Under 120 words. No fluff. End with one soft question."
)
_DEFAULT_SIGNATURE = "Best,\nVoxBulk team · voxbulk.com"

_DEFAULT_EMAIL_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;background:#f4f6f8;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;border-collapse:collapse;background:#ffffff;border:1px solid #e5e7eb;">
        <tr><td style="padding:28px 24px;font-size:15px;line-height:1.6;color:#1a1a1a;">
          <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#1a1a1a;">Hi {{first_name}},</p>
          {{body}}
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0 8px;border-collapse:collapse;">
            <tr>
              <td align="center" bgcolor="#ffffff" style="border-radius:6px;background:#ffffff;border:1px solid #111111;">
                <a href="{{trial_url}}" target="_blank"
                   style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:700;line-height:1.2;
                          color:#111111 !important;text-decoration:none;border-radius:6px;background:#ffffff;">
                  <span style="color:#111111 !important;text-decoration:none;">Start free trial</span>
                </a>
              </td>
            </tr>
          </table>
          <p style="margin:12px 0 0;font-size:13px;line-height:1.5;color:#6b7280;">
            Code <strong style="color:#111111;font-family:monospace;">{{promo_code}}</strong> · 3-day Expo trial
          </p>
          <p style="margin:28px 0 0;font-size:12px;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:16px;">VoxBulk · voxbulk.com</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

_SAMPLE_PREVIEW_VARS = {
    "first_name": "Alex",
    "last_name": "Taylor",
    "company": "Example Estates Ltd",
    "promo_code": "EXPO3DAYS",
    "job_title": "Operations Director",
    "email": "alex.taylor@example.com",
    "sector": "property",
    "country_code": "GB",
    "body": (
        "I noticed Example Estates runs feedback across multiple branches. VoxBulk automates "
        "customer surveys by phone and WhatsApp and pushes results into your CRM before your team arrives."
    ),
}

_SECTOR_KEYWORDS = {
    "automotive": ["automotive", "aftersales", "dealership", "car"],
    "property": ["property", "estate", "real estate", "letting"],
    "dental": ["dental", "dentist", "clinic"],
    "recruitment": ["recruitment", "recruiting", "staffing", "hiring"],
}

# Community / no-rental actors used when no exhibitor actor ID is saved.
CURATED_FREE_ACTORS = [
    "vdrmota~contact-info-scraper",
    "foo121~website-contact-scraper",
    "goat255~website-contact-scraper",
]
DEFAULT_FREE_ACTOR = CURATED_FREE_ACTORS[0]


class AiTeamServiceError(ValueError):
    pass


class AiTeamService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def get_settings(db: Session) -> AiTeamSettings:
        row = db.get(AiTeamSettings, "default")
        if row is None:
            now = AiTeamService._now()
            row = AiTeamSettings(
                id="default",
                search_title_keywords="",
                writing_instruction=_DEFAULT_WRITING,
                email_signature=_DEFAULT_SIGNATURE,
                updated_at=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def _provider_connection_flags(view: dict[str, Any]) -> tuple[bool, bool]:
        """Return (configured, api_key_set) from get_platform_config_admin_view."""
        secret_set = view.get("secret_set") if isinstance(view.get("secret_set"), dict) else {}
        api_key_set = bool(secret_set.get("api_key"))
        configured = bool(view.get("configured")) or api_key_set
        return configured, api_key_set

    @staticmethod
    def settings_to_dict(db: Session, row: AiTeamSettings) -> dict[str, Any]:
        apollo_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="apollo")
        resend_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="resend")
        deepseek_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="deepseek")
        apollo_ok, apollo_key = AiTeamService._provider_connection_flags(apollo_view)
        resend_ok, resend_key = AiTeamService._provider_connection_flags(resend_view)
        deepseek_ok, _deepseek_key = AiTeamService._provider_connection_flags(deepseek_view)
        return {
            "search_sector": row.search_sector,
            "search_country": row.search_country,
            "search_company_size": row.search_company_size,
            "search_title_keywords": row.search_title_keywords,
            "search_city_region": row.search_city_region,
            "search_max_per_run": row.search_max_per_run,
            "search_min_score": row.search_min_score,
            "followup_after_days": row.followup_after_days,
            "max_followups": row.max_followups,
            "sender_name": row.sender_name,
            "reply_to_email": row.reply_to_email,
            "from_email": row.from_email,
            "writing_instruction": row.writing_instruction,
            "email_signature": row.email_signature,
            "email_html_template": row.email_html_template or AiTeamService.default_email_html_template(),
            "default_email_html_template": AiTeamService.default_email_html_template(),
            "email_language": row.email_language,
            "email_max_words": row.email_max_words,
            "email_tone": row.email_tone,
            "promo_code_prefix": row.promo_code_prefix,
            "promo_offer_type": row.promo_offer_type,
            "promo_value": row.promo_value,
            "promo_expiry_days": row.promo_expiry_days,
            "promo_max_uses": row.promo_max_uses,
            "promo_code_mode": row.promo_code_mode,
            "smtp_host": row.smtp_host,
            "smtp_port": row.smtp_port,
            "smtp_username": row.smtp_username,
            "smtp_password_configured": bool(row.smtp_password_enc),
            "inbox_email": row.inbox_email,
            "email_delivery_provider": (row.email_delivery_provider or "smtp").strip().lower() or "smtp",
            "imap_host": getattr(row, "imap_host", None) or "",
            "imap_port": int(getattr(row, "imap_port", None) or 993),
            "imap_use_ssl": bool(getattr(row, "imap_use_ssl", True)),
            "imap_use_tls": bool(getattr(row, "imap_use_tls", False)),
            "imap_username": getattr(row, "imap_username", None) or "",
            "imap_password_configured": bool(getattr(row, "imap_password_enc", None)),
            "imap_last_sync_at": row.imap_last_sync_at.isoformat() if getattr(row, "imap_last_sync_at", None) else None,
            "imap_last_sync_message": getattr(row, "imap_last_sync_message", None) or "",
            "imap_configured": bool(
                (getattr(row, "imap_host", None) or row.smtp_host)
                and (getattr(row, "imap_username", None) or row.smtp_username)
                and (getattr(row, "imap_password_enc", None) or row.smtp_password_enc)
            ),
            "resend_sending_domain": row.resend_sending_domain,
            "apify_token_configured": bool(AiTeamService._apify_token_configured(db, row)),
            "apify_user_id": (getattr(row, "apify_user_id", None) or "").strip(),
            "apify_exhibitor_actor_id": row.apify_exhibitor_actor_id or "",
            "apify_contact_actor_id": row.apify_contact_actor_id or "",
            "curated_free_actors": list(CURATED_FREE_ACTORS),
            "default_free_actor": DEFAULT_FREE_ACTOR,
            "run_schedule": row.run_schedule,
            "max_emails_per_day": row.max_emails_per_day,
            "send_interval_seconds": int(getattr(row, "send_interval_seconds", None) or 20),
            "sending_window": row.sending_window,
            "auto_fetch_prospects": row.auto_fetch_prospects,
            "auto_draft_emails": row.auto_draft_emails,
            "auto_followup": row.auto_followup,
            "track_opens": row.track_opens,
            "notify_on_reply": row.notify_on_reply,
            "notify_on_promo_used": row.notify_on_promo_used,
            "auto_send_without_approval": row.auto_send_without_approval,
            "apollo_credit_alert_at": row.apollo_credit_alert_at,
            "agent_paused": row.agent_paused,
            "last_agent_run_at": row.last_agent_run_at.isoformat() if row.last_agent_run_at else None,
            "apollo_connected": apollo_ok,
            "apollo_api_key_configured": apollo_key,
            "resend_connected": resend_ok,
            "resend_api_key_configured": resend_key,
            "deepseek_connected": deepseek_ok,
            "smtp_configured": bool(row.smtp_host and row.smtp_username and row.smtp_password_enc),
            "apify_connected": bool(AiTeamService._apify_token_configured(db, row)),
        }

    @staticmethod
    def update_settings(db: Session, payload: dict[str, Any]) -> AiTeamSettings:
        # Token first (validate + durable provider_configs commit), then other settings.
        raw_apify = payload.get("apify_token")
        if raw_apify:
            key = ApifyService.normalize_token(str(raw_apify))
            if key:
                if ApifyService.looks_like_user_id(key):
                    # Common paste mistake — store as user id, do not treat as API token.
                    payload = {**payload, "apify_user_id": key}
                else:
                    AiTeamService.persist_apify_token(db, key)

        row = AiTeamService.get_settings(db)
        now = AiTeamService._now()
        scalar_fields = [
            "search_sector", "search_country", "search_company_size", "search_title_keywords", "search_city_region",
            "sender_name", "reply_to_email", "from_email", "writing_instruction", "email_signature",
            "email_language", "email_tone", "promo_code_prefix", "promo_offer_type", "promo_code_mode",
            "smtp_host", "smtp_username", "inbox_email", "resend_sending_domain", "email_delivery_provider",
            "apify_user_id", "apify_exhibitor_actor_id", "apify_contact_actor_id",
            "run_schedule", "sending_window",
            "imap_host", "imap_username",
        ]
        int_fields = [
            "search_max_per_run", "search_min_score", "followup_after_days", "max_followups",
            "email_max_words", "promo_value", "promo_expiry_days", "promo_max_uses",
            "smtp_port", "max_emails_per_day", "apollo_credit_alert_at",
            "imap_port", "send_interval_seconds",
        ]
        bool_fields = [
            "auto_fetch_prospects", "auto_draft_emails", "auto_followup", "track_opens",
            "notify_on_reply", "notify_on_promo_used", "auto_send_without_approval", "agent_paused",
            "imap_use_ssl", "imap_use_tls",
        ]
        text_fields = ["email_html_template"]
        for key in text_fields:
            if key in payload:
                val = payload[key]
                if key == "email_html_template" and val is not None:
                    from app.services.email_html_inline import inline_email_css

                    setattr(row, key, inline_email_css(str(val)))
                else:
                    setattr(row, key, str(val) if val is not None else None)
        for key in scalar_fields:
            if key in payload:
                val = str(payload[key] or "").strip()
                if key == "email_delivery_provider":
                    val = val.lower()
                    if val not in {"smtp", "resend"}:
                        val = "smtp"
                setattr(row, key, val)
        for key in int_fields:
            if key in payload:
                setattr(row, key, int(payload[key] or 0))
        if "send_interval_seconds" in payload or getattr(row, "send_interval_seconds", None) is not None:
            try:
                interval = int(getattr(row, "send_interval_seconds", None) or 20)
            except (TypeError, ValueError):
                interval = 20
            row.send_interval_seconds = max(1, min(interval, 600))
        for key in bool_fields:
            if key in payload:
                setattr(row, key, bool(payload[key]))
        if payload.get("smtp_password"):
            enc = get_encryptor()
            row.smtp_password_enc = enc.encrypt_str(str(payload["smtp_password"]))
        if payload.get("imap_password"):
            enc = get_encryptor()
            row.imap_password_enc = enc.encrypt_str(str(payload["imap_password"]))
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _apollo_key(db: Session) -> str:
        cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="apollo")
        return str((cfg or {}).get("api_key") or "").strip()

    @staticmethod
    def _resend_key(db: Session) -> str:
        cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="resend")
        return str((cfg or {}).get("api_key") or "").strip()

    @staticmethod
    def _apify_token_from_provider(db: Session) -> str:
        try:
            cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="apify")
            return ApifyService.normalize_token(str((cfg or {}).get("api_key") or ""))
        except Exception:
            return ""

    @staticmethod
    def _apify_token_configured(db: Session, settings: AiTeamSettings | None = None) -> bool:
        if AiTeamService._apify_token_from_provider(db):
            return True
        row = settings or AiTeamService.get_settings(db)
        return bool(getattr(row, "apify_token_enc", None))

    @staticmethod
    def _apify_token(settings: AiTeamSettings, db: Session | None = None) -> str:
        if db is not None:
            from_provider = AiTeamService._apify_token_from_provider(db)
            if from_provider:
                return from_provider
        if not getattr(settings, "apify_token_enc", None):
            return ""
        try:
            return ApifyService.normalize_token(get_encryptor().decrypt_str(settings.apify_token_enc))
        except Exception:
            return ""

    @staticmethod
    def persist_apify_user_id(db: Session, user_id: str | None) -> str:
        """Store Apify account user id (optional; does not authenticate by itself)."""
        uid = ApifyService.normalize_token(str(user_id or ""))
        if not uid:
            return ""
        if len(uid) > 128:
            raise AiTeamServiceError("Apify user ID is too long")
        row = AiTeamService.get_settings(db)
        row.apify_user_id = uid
        row.updated_at = AiTeamService._now()
        db.add(row)
        db.commit()
        # Keep a copy on provider_configs next to the API key when present
        try:
            cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="apify")
            merged = dict(cfg or {})
            merged["user_id"] = uid
            if merged.get("api_key"):
                ProviderSettingsService.upsert_platform_config(
                    db, provider="apify", is_enabled=True, config=merged
                )
        except Exception:
            logger.warning("apify_user_id_provider_write_failed", exc_info=True)
        return uid

    @staticmethod
    def persist_apify_token(db: Session, token: str) -> str:
        """Normalize, validate against Apify, then persist. Returns the cleaned token."""
        key = ApifyService.normalize_token(token)
        if not key:
            raise AiTeamServiceError("Apify API token is required")
        # Common mistake: paste User ID into the token box — save it as user id, then explain.
        if ApifyService.looks_like_user_id(key):
            try:
                AiTeamService.persist_apify_user_id(db, key)
            except Exception:
                logger.warning("apify_user_id_autosave_failed", exc_info=True)
            raise AiTeamServiceError(
                "That looks like an Apify User ID "
                f"({ApifyService.token_fingerprint(key)}) — saved into the User ID field. "
                "You still need the Personal API token that starts with apify_api_ from "
                "https://console.apify.com/settings/integrations. "
                "User ID alone cannot connect. Or use the Scrape tab (no Apify needed)."
            )
        # Validate BEFORE writing so we never store a rejected token.
        try:
            result = ApifyService.test_connection(key, actor_id=None)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc
        remote_uid = str(result.get("user_id") or "").strip()
        config: dict[str, Any] = {"api_key": key}
        if remote_uid:
            config["user_id"] = remote_uid
        ProviderSettingsService.upsert_platform_config(
            db, provider="apify", is_enabled=True, config=config
        )
        # Dual-write when column exists
        try:
            row = AiTeamService.get_settings(db)
            row.apify_token_enc = get_encryptor().encrypt_str(key)
            if remote_uid:
                row.apify_user_id = remote_uid
            row.updated_at = AiTeamService._now()
            db.add(row)
            db.commit()
        except Exception:
            logger.warning("apify_token_enc_dual_write_failed", exc_info=True)
        # Prove round-trip from DB
        saved = AiTeamService._apify_token_from_provider(db)
        if ApifyService.normalize_token(saved) != key:
            raise AiTeamServiceError(
                "Apify token validated but failed to persist (encryption/DB round-trip mismatch). "
                "Check ENCRYPTION_KEY is stable on the API server."
            )
        return key

    @staticmethod
    def save_provider_keys(
        db: Session,
        *,
        apollo_api_key: str | None = None,
        resend_api_key: str | None = None,
        apify_api_key: str | None = None,
    ) -> None:
        if apollo_api_key is not None and str(apollo_api_key).strip():
            ProviderSettingsService.upsert_platform_config(
                db, provider="apollo", is_enabled=True, config={"api_key": str(apollo_api_key).strip()}
            )
        if resend_api_key is not None and str(resend_api_key).strip():
            ProviderSettingsService.upsert_platform_config(
                db, provider="resend", is_enabled=True, config={"api_key": str(resend_api_key).strip()}
            )
        if apify_api_key is not None and str(apify_api_key).strip():
            # Persist without re-validating here — callers that need validation use persist_apify_token.
            key = ApifyService.normalize_token(apify_api_key)
            if key:
                ProviderSettingsService.upsert_platform_config(
                    db, provider="apify", is_enabled=True, config={"api_key": key}
                )

    @staticmethod
    def default_email_html_template() -> str:
        return _DEFAULT_EMAIL_HTML_TEMPLATE

    @staticmethod
    def effective_html_template(settings: AiTeamSettings) -> str:
        raw = str(settings.email_html_template or "").strip()
        return raw or _DEFAULT_EMAIL_HTML_TEMPLATE

    @staticmethod
    def _body_html_fragment(text: str) -> str:
        clean = str(text or "").strip()
        if not clean:
            return '<p style="margin:0 0 12px;font-size:14px;line-height:1.5;"></p>'
        # Keep rich HTML (pricing tables, buttons, branded blocks) intact — wrapping
        # those in <p color:…> is what squeezes tables and overrides template colours.
        if re.search(
            r"</?(?:table|tr|td|th|div|span|a|img|h[1-6]|ul|ol|li|strong|em|br|p|section|center)\b",
            clean,
            re.I,
        ):
            return clean
        parts = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
        if not parts:
            parts = [clean]
        # Inherit colour from the HTML wrapper — do not force a grey tint.
        return "".join(
            f'<p style="margin:0 0 12px;font-size:14px;line-height:1.5;">{p.replace(chr(10), "<br>")}</p>'
            for p in parts
        )

    @staticmethod
    def _prospect_template_vars(db: Session, prospect: AiTeamProspect, *, body_text: str | None = None) -> dict[str, str]:
        promo = db.get(PromoOffer, prospect.promo_offer_id) if prospect.promo_offer_id else None
        body = str(body_text if body_text is not None else prospect.draft_body or "").strip()
        return {
            "first_name": prospect.first_name or "there",
            "last_name": prospect.last_name or "",
            "company": prospect.company_name or "your company",
            "promo_code": promo.code if promo else "",
            "job_title": prospect.job_title or "",
            "email": prospect.email or "",
            "sector": prospect.sector or "",
            "country_code": prospect.country_code or "GB",
            "body": body,
        }

    @staticmethod
    def render_email_html(
        db: Session,
        settings: AiTeamSettings,
        *,
        prospect: AiTeamProspect | None = None,
        variables: dict[str, str] | None = None,
        body_text: str | None = None,
        template_override: str | None = None,
    ) -> dict[str, str]:
        vars_map = dict(variables or {})
        if prospect is not None:
            vars_map = {**AiTeamService._prospect_template_vars(db, prospect, body_text=body_text), **vars_map}
        body_raw = str(vars_map.get("body") or "").strip()
        vars_map["body"] = AiTeamService._body_html_fragment(body_raw)
        template = str(template_override or AiTeamService.effective_html_template(settings))
        html = template
        for key, val in vars_map.items():
            html = html.replace("{{" + key + "}}", str(val or ""))
        from app.services.email_html_inline import inline_email_css

        html = inline_email_css(html)
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        subject = (prospect.draft_subject if prospect else None) or "Quick idea for your team"
        return {"subject": subject, "html": html, "text": text, "body_text": body_raw}

    @staticmethod
    def prospect_email_preview(db: Session, prospect_id: str) -> dict[str, str]:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        return AiTeamService.render_email_html(db, settings, prospect=prospect)

    @staticmethod
    def template_preview(db: Session, *, template: str | None = None, use_sample: bool = True) -> dict[str, str]:
        settings = AiTeamService.get_settings(db)
        vars_map = dict(_SAMPLE_PREVIEW_VARS) if use_sample else {}
        return AiTeamService.render_email_html(
            db,
            settings,
            variables=vars_map,
            template_override=template,
            body_text=vars_map.get("body"),
        )

    @staticmethod
    def send_template_test_email(db: Session, *, to_email: str, prospect_id: str | None = None) -> dict[str, Any]:
        to_addr = str(to_email or "").strip()
        if not to_addr or "@" not in to_addr:
            raise AiTeamServiceError("Enter a valid test email address")
        settings = AiTeamService.get_settings(db)
        from_addr = AiTeamService._from_address(settings)
        if prospect_id:
            prospect = db.get(AiTeamProspect, prospect_id)
            if prospect is None:
                raise AiTeamServiceError("Prospect not found")
            rendered = AiTeamService.render_email_html(db, settings, prospect=prospect)
        else:
            rendered = AiTeamService.template_preview(db, use_sample=True)
        subject = f"[Test] {rendered['subject']}"
        result = AiTeamService._deliver_email(
            db,
            settings,
            to_email=to_addr,
            subject=subject,
            text=rendered["text"],
            html=rendered["html"],
        )
        return {
            "ok": True,
            "message": f"Test email sent to {to_addr} via {result.get('provider')}",
            "email_id": result.get("email_id"),
            "provider": result.get("provider"),
        }

    @staticmethod
    def _delivery_provider(settings: AiTeamSettings) -> str:
        provider = str(settings.email_delivery_provider or "smtp").strip().lower()
        if provider not in {"smtp", "resend"}:
            return "smtp"
        return provider

    @staticmethod
    def _smtp_password(settings: AiTeamSettings) -> str:
        if not settings.smtp_password_enc:
            return ""
        return get_encryptor().decrypt_str(settings.smtp_password_enc)

    @staticmethod
    def _send_via_smtp(
        settings: AiTeamSettings,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        message_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        host = (settings.smtp_host or "").strip()
        port = int(settings.smtp_port or 587)
        user = (settings.smtp_username or "").strip()
        pwd = AiTeamService._smtp_password(settings)
        from_email = (settings.from_email or user or "").strip()
        if not host or not user or not pwd:
            raise AiTeamServiceError("SMTP host, username, and password are required")
        if not from_email or "@" not in from_email:
            raise AiTeamServiceError("From email is not configured")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = AiTeamService._from_address(settings) if settings.sender_name else from_email
        msg["To"] = to_email
        reply_to = (settings.reply_to_email or "").strip()
        if reply_to:
            msg["Reply-To"] = reply_to
        mid = str(message_id or "").strip()
        if mid:
            msg["Message-ID"] = mid if mid.startswith("<") else f"<{mid}>"
        for hk, hv in (extra_headers or {}).items():
            if hk and hv and hk.lower() not in {"from", "to", "subject", "message-id"}:
                msg[str(hk)] = str(hv)
        msg.attach(MIMEText(text or "", "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))

        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as server:
                server.login(user, pwd)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, pwd)
                server.sendmail(from_email, [to_email], msg.as_string())
        return {"ok": True, "provider": "smtp", "email_id": None, "message_id": mid or None}

    @staticmethod
    def _deliver_email(
        db: Session,
        settings: AiTeamSettings,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        recipient_id: str | None = None,
    ) -> dict[str, Any]:
        rid = str(recipient_id or "").strip()
        message_id = f"<ait-c-{rid}@outreach.voxbulk.com>" if rid else None
        extra = {"X-VoxBulk-Recipient": rid} if rid else None
        provider = AiTeamService._delivery_provider(settings)
        if provider == "smtp":
            return AiTeamService._send_via_smtp(
                settings,
                to_email=to_email,
                subject=subject,
                text=text,
                html=html,
                message_id=message_id,
                extra_headers=extra,
            )
        api_key = AiTeamService._resend_key(db)
        from_addr = AiTeamService._from_address(settings)
        if not from_addr or "@" not in from_addr:
            raise AiTeamServiceError("From email is not configured")
        try:
            result = ResendService.send_email(
                api_key,
                from_email=from_addr,
                to_email=to_email,
                subject=subject,
                text=text,
                html=html,
                reply_to=(settings.reply_to_email or "").strip() or None,
                headers={
                    **({"Message-ID": message_id} if message_id else {}),
                    **({"X-VoxBulk-Recipient": rid} if rid else {}),
                }
                or None,
            )
        except ResendServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc
        return {"ok": True, "provider": "resend", "email_id": result.get("email_id")}

    @staticmethod
    def parse_csv_preview(raw: bytes, filename: str = "") -> dict[str, Any]:
        from app.services.csv_column_auto_map import (
            auto_map_headers,
            parse_tabular_bytes,
            rows_from_mapping,
        )

        headers, raw_rows = parse_tabular_bytes(raw, filename)
        if not headers:
            raise AiTeamServiceError("File has no header row")
        mapping = auto_map_headers(headers)
        contacts = rows_from_mapping(raw_rows, mapping)
        preview_raw = raw_rows[:8]
        return {
            "headers": headers,
            "preview_rows": preview_raw,
            "total_rows": len(raw_rows),
            "suggested_mapping": mapping,
            "contacts": contacts,
            "contacts_count": len(contacts),
            "email_detected": bool(mapping.get("email")),
            "detected_fields": {k: v for k, v in mapping.items() if v},
        }


    @staticmethod
    def import_prospect_rows(
        db: Session,
        rows: list[dict[str, Any]],
        *,
        source: str,
        apply_min_score: bool = False,
        auto_draft: bool | None = None,
    ) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        keywords = [k.strip() for k in (settings.search_title_keywords or "").split(",") if k.strip()]
        do_draft = settings.auto_draft_emails if auto_draft is None else bool(auto_draft)
        created = 0
        skipped = 0
        prospects: list[dict[str, Any]] = []

        for raw in rows:
            email = str(raw.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue
            exists = db.execute(select(AiTeamProspect).where(AiTeamProspect.email == email)).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue

            first_name = str(raw.get("first_name") or "").strip()
            last_name = str(raw.get("last_name") or "").strip()
            company = str(raw.get("company_name") or raw.get("company") or "").strip()
            job_title = str(raw.get("job_title") or "").strip()
            sector = str(raw.get("sector") or settings.search_sector or "").strip().lower()
            country = str(raw.get("country_code") or raw.get("country") or "GB").strip().upper()[:8] or "GB"
            score = int(raw.get("match_score") or 0)
            if not score:
                score = AiTeamService._score_prospect(job_title, company, keywords) if job_title else 70
            if apply_min_score and score < int(settings.search_min_score or 60):
                skipped += 1
                continue
            if not sector:
                sector = AiTeamService._infer_sector(job_title, company, settings.search_sector) or "general"

            profile = raw.get("profile_json")
            if isinstance(profile, dict):
                profile_json = json.dumps(profile)
            elif isinstance(profile, str) and profile.strip():
                profile_json = profile
            else:
                profile_json = json.dumps({k: v for k, v in raw.items() if k != "profile_json"})

            now = AiTeamService._now()
            prospect = AiTeamProspect(
                first_name=first_name,
                last_name=last_name,
                email=email,
                job_title=job_title,
                company_name=company,
                sector=sector,
                country_code=country,
                match_score=score,
                status="new",
                source=str(source or "paste")[:32],
                profile_json=profile_json,
                created_at=now,
                updated_at=now,
            )
            db.add(prospect)
            db.flush()
            AiTeamService.ensure_promo_for_prospect(db, prospect, settings)
            if do_draft:
                try:
                    AiTeamService.draft_email_for_prospect(db, prospect, settings)
                except Exception as exc:
                    logger.warning("ai_team_draft_failed", extra={"email": email, "error": str(exc)})
                    prospect.status = "new"
                    prospect.last_error = f"Draft failed: {exc}"
                    prospect.updated_at = AiTeamService._now()
                    db.add(prospect)
            else:
                prospect.status = "new"
                db.add(prospect)
            created += 1
            prospects.append(AiTeamService.prospect_to_dict(db, prospect))

        db.commit()
        return {"ok": True, "created": created, "skipped": skipped, "prospects": prospects[:20]}

    @staticmethod
    def _parse_email_line(line: str) -> dict[str, Any] | None:
        raw = str(line or "").strip()
        if not raw or raw.startswith("#"):
            return None
        # Name <email@x.com>
        m = re.match(r"^(.+?)\s*<([^>]+@[^>]+)>\s*$", raw)
        if m:
            name = m.group(1).strip().strip('"').strip("'")
            email = m.group(2).strip().lower()
            parts = name.split(None, 1)
            return {
                "email": email,
                "first_name": parts[0] if parts else "",
                "last_name": parts[1] if len(parts) > 1 else "",
            }
        # email, first, last, company
        if "," in raw:
            bits = [b.strip() for b in raw.split(",")]
            email = bits[0].lower()
            if "@" not in email:
                return None
            return {
                "email": email,
                "first_name": bits[1] if len(bits) > 1 else "",
                "last_name": bits[2] if len(bits) > 2 else "",
                "company_name": bits[3] if len(bits) > 3 else "",
            }
        if "@" in raw and " " not in raw:
            return {"email": raw.lower()}
        # fallback: find email token
        em = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", raw, re.I)
        if not em:
            return None
        email = em.group(0).lower()
        name_part = raw[: em.start()].strip(" ,;-")
        parts = name_part.split(None, 1) if name_part else []
        return {
            "email": email,
            "first_name": parts[0] if parts else "",
            "last_name": parts[1] if len(parts) > 1 else "",
        }

    @staticmethod
    def import_emails_text(
        db: Session,
        text: str,
        *,
        company_name: str = "",
        sector: str = "",
        source: str = "paste",
    ) -> dict[str, Any]:
        lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        rows: list[dict[str, Any]] = []
        for line in lines:
            parsed = AiTeamService._parse_email_line(line)
            if not parsed:
                continue
            if company_name and not parsed.get("company_name"):
                parsed["company_name"] = company_name
            if sector:
                parsed["sector"] = sector
            parsed["match_score"] = 75
            rows.append(parsed)
        if not rows:
            raise AiTeamServiceError("No valid emails found to import")
        return AiTeamService.import_prospect_rows(db, rows, source=source or "paste", apply_min_score=False)

    @staticmethod
    def import_csv_prospects(
        db: Session,
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

        headers, raw_rows = parse_tabular_bytes(raw, filename)
        if not headers:
            raise AiTeamServiceError("File has no header row")
        auto = auto_map_headers(headers)
        user_map = {k: str(v or "").strip() for k, v in (mapping or {}).items() if str(v or "").strip()}
        final_map = {**auto, **user_map}
        if not final_map.get("email"):
            raise AiTeamServiceError(
                "Could not find an email column. Use a header like Email, E-mail, or Email Address."
            )
        rows = rows_from_mapping(raw_rows, final_map)
        if not rows:
            raise AiTeamServiceError("No valid email rows found in the sheet")
        result = AiTeamService.import_prospect_rows(db, rows, source="csv", apply_min_score=False)
        result["mapping_used"] = final_map
        return result

    @staticmethod
    def _infer_sector(job_title: str, company: str, configured: str) -> str:
        if configured:
            return configured.strip().lower()
        blob = f"{job_title} {company}".lower()
        for sector, keywords in _SECTOR_KEYWORDS.items():
            if any(k in blob for k in keywords):
                return sector
        return "general"

    @staticmethod
    def _score_prospect(job_title: str, company: str, keywords: list[str]) -> int:
        title = job_title.lower()
        hits = sum(1 for kw in keywords if kw.lower() in title)
        base = 50 + hits * 15
        if company.strip():
            base += 10
        return min(100, base)

    @staticmethod
    def _company_slug(company: str) -> str:
        clean = re.sub(r"[^A-Z0-9]+", "-", company.upper()).strip("-")
        return clean[:20] or "PROSPECT"

    @staticmethod
    def ensure_promo_for_prospect(db: Session, prospect: AiTeamProspect, settings: AiTeamSettings) -> PromoOffer:
        if prospect.promo_offer_id:
            existing = db.get(PromoOffer, prospect.promo_offer_id)
            if existing is not None:
                return existing
        existing = db.execute(
            select(PromoOffer).where(PromoOffer.ai_team_prospect_id == prospect.id, PromoOffer.is_active.is_(True))
        ).scalar_one_or_none()
        if existing is not None:
            prospect.promo_offer_id = existing.id
            db.add(prospect)
            db.commit()
            return existing

        prefix = PromoOfferService.normalize_code(settings.promo_code_prefix or "TRIAL")
        slug = AiTeamService._company_slug(prospect.company_name)
        code = PromoOfferService.normalize_code(f"{prefix}-{slug}")
        if PromoOfferService.get_by_code(db, code):
            code = PromoOfferService.normalize_code(f"{prefix}-{slug[:12]}{prospect.id[:4].upper()}")

        offer_type = PromoOfferService.normalize_offer_type(settings.promo_offer_type)
        value = max(1, int(settings.promo_value or 50))
        raw_type = str(settings.promo_offer_type or "").strip().lower()
        payload: dict[str, Any] = {
            "code": code,
            "name": f"AI Team · {prospect.company_name or prospect.email}",
            "expires_in_days": max(1, int(settings.promo_expiry_days or 14)),
            "max_redemptions": max(1, int(settings.promo_max_uses or 1)),
            "prospect_email": prospect.email,
            "prospect_name": f"{prospect.first_name} {prospect.last_name}".strip(),
        }
        if offer_type in {"expo", "expo_trial"} or raw_type in {"expo", "expo_trial"}:
            payload["benefit_kind"] = "free_usage"
            payload["service_kind"] = "expo"
            payload["usage_amount"] = value
        else:
            payload["offer_type"] = offer_type
            if offer_type == "survey_credits":
                payload["survey_contacts_included"] = value
            elif offer_type == "interview_credits":
                payload["interview_contacts_included"] = value
            else:
                payload["trial_days"] = value

        row = PromoOfferService.create_admin(db, payload)
        row.ai_team_prospect_id = prospect.id
        prospect.promo_offer_id = row.id
        db.add(row)
        db.add(prospect)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def prospect_to_dict(db: Session, row: AiTeamProspect) -> dict[str, Any]:
        promo = db.get(PromoOffer, row.promo_offer_id) if row.promo_offer_id else None
        return {
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "full_name": f"{row.first_name} {row.last_name}".strip(),
            "email": row.email,
            "job_title": row.job_title,
            "company_name": row.company_name,
            "sector": row.sector,
            "country_code": row.country_code,
            "match_score": row.match_score,
            "status": row.status,
            "source": row.source,
            "promo_code": promo.code if promo else None,
            "promo_offer_id": row.promo_offer_id,
            "draft_subject": row.draft_subject,
            "draft_body": row.draft_body,
            "drafted_at": row.drafted_at.isoformat() if row.drafted_at else None,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "opened_at": row.opened_at.isoformat() if row.opened_at else None,
            "replied_at": row.replied_at.isoformat() if row.replied_at else None,
            "converted_at": row.converted_at.isoformat() if row.converted_at else None,
            "emails_sent_count": row.emails_sent_count,
            "last_error": row.last_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def list_prospects(
        db: Session,
        *,
        status: str | None = None,
        q: str | None = None,
        source: str | None = None,
    ) -> list[AiTeamProspect]:
        stmt = select(AiTeamProspect).order_by(AiTeamProspect.updated_at.desc())
        if status:
            stmt = stmt.where(AiTeamProspect.status == status)
        if source:
            stmt = stmt.where(AiTeamProspect.source == source)
        rows = list(db.execute(stmt).scalars().all())
        if q:
            needle = q.lower()
            rows = [
                r for r in rows
                if needle in (r.email or "").lower()
                or needle in (r.company_name or "").lower()
                or needle in f"{r.first_name} {r.last_name}".lower()
                or needle in (r.source or "").lower()
            ]
        return rows

    @staticmethod
    def draft_email_for_prospect(db: Session, prospect: AiTeamProspect, settings: AiTeamSettings) -> AiTeamProspect:
        promo = AiTeamService.ensure_promo_for_prospect(db, prospect, settings)
        variables = {
            "first_name": prospect.first_name or "there",
            "last_name": prospect.last_name or "",
            "job_title": prospect.job_title or "your role",
            "company": prospect.company_name or "your company",
            "sector": prospect.sector or "your sector",
            "country": prospect.country_code or "GB",
            "promo_code": promo.code,
        }
        instruction = settings.writing_instruction or _DEFAULT_WRITING
        for key, val in variables.items():
            instruction = instruction.replace("{" + key + "}", str(val))

        system = (
            "You write B2B cold outreach emails for VoxBulk. Return JSON with keys subject and body. "
            f"Tone: {settings.email_tone}. Language: {settings.email_language}. "
            f"Max words: {settings.email_max_words}. Body is plain text with line breaks."
        )
        user = f"Instruction:\n{instruction}\n\nSignature to append:\n{settings.email_signature or _DEFAULT_SIGNATURE}"
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system,
            messages=[AgentMessage(role="user", content=user)],
            max_tokens=600,
            temperature=0.5,
            provider="deepseek",
        )
        text = str(result.assistant_text or "").strip()
        subject = "Quick idea for your team"
        body = text
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                subject = str(parsed.get("subject") or subject).strip()
                body = str(parsed.get("body") or text).strip()
        except json.JSONDecodeError:
            if "\n" in text:
                first, rest = text.split("\n", 1)
                if first.lower().startswith("subject:"):
                    subject = first.split(":", 1)[1].strip()
                    body = rest.strip()

        now = AiTeamService._now()
        prospect.draft_subject = subject[:500]
        prospect.draft_body = body
        rendered = AiTeamService.render_email_html(db, settings, prospect=prospect, body_text=body)
        prospect.draft_body_html = rendered["html"]
        prospect.drafted_at = now
        prospect.status = "pending"
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def fetch_prospects(db: Session, *, preview: bool = False, limit: int | None = None) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        api_key = AiTeamService._apollo_key(db)
        keywords = [k.strip() for k in (settings.search_title_keywords or "").split(",") if k.strip()]
        if not keywords:
            keywords = ["operations director", "customer experience manager"]

        per_page = limit or (5 if preview else settings.search_max_per_run)
        try:
            people = ApolloService.search_people(
                api_key,
                title_keywords=keywords,
                country=settings.search_country or None,
                city_region=settings.search_city_region or None,
                per_page=per_page,
            )
        except ApolloServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        created = 0
        skipped = 0
        for person in people:
            email = person["email"].lower()
            exists = db.execute(select(AiTeamProspect).where(AiTeamProspect.email == email)).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue
            score = AiTeamService._score_prospect(person["job_title"], person["company_name"], keywords)
            if score < int(settings.search_min_score or 60):
                skipped += 1
                continue
            now = AiTeamService._now()
            sector = AiTeamService._infer_sector(person["job_title"], person["company_name"], settings.search_sector)
            row = AiTeamProspect(
                apollo_id=person.get("apollo_id"),
                first_name=person["first_name"],
                last_name=person["last_name"],
                email=email,
                job_title=person["job_title"],
                company_name=person["company_name"],
                sector=sector,
                country_code=person.get("country_code") or "GB",
                match_score=score,
                status="new",
                profile_json=json.dumps(person.get("profile_json") or {}),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            AiTeamService.ensure_promo_for_prospect(db, row, settings)
            if settings.auto_draft_emails:
                AiTeamService.draft_email_for_prospect(db, row, settings)
            created += 1
        db.commit()
        return {"ok": True, "created": created, "skipped": skipped, "preview": preview}

    @staticmethod
    def _from_address(settings: AiTeamSettings) -> str:
        name = (settings.sender_name or "VoxBulk team").strip()
        email = (settings.from_email or "").strip()
        if name and email:
            return f"{name} <{email}>"
        return email

    @staticmethod
    def send_prospect_email(db: Session, prospect: AiTeamProspect, *, subject: str | None = None, body: str | None = None) -> AiTeamProspect:
        settings = AiTeamService.get_settings(db)
        from_addr = AiTeamService._from_address(settings)
        if not from_addr or "@" not in from_addr:
            raise AiTeamServiceError("From email is not configured")

        # Daily send cap
        day_start = AiTeamService._now().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = db.scalar(
            select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.sent_at >= day_start)
        ) or 0
        # Count new sends only when this prospect has not been sent yet today as first touch;
        # follow-ups still respect a soft cap via emails_sent_count checks below.
        max_day = max(1, int(settings.max_emails_per_day or 10))
        if prospect.sent_at is None and sent_today >= max_day:
            raise AiTeamServiceError(f"Daily send limit reached ({max_day})")

        subj = (subject or prospect.draft_subject or "").strip()
        text = (body or prospect.draft_body or "").strip()
        if not subj or not text:
            raise AiTeamServiceError("Email subject and body are required")

        rendered = AiTeamService.render_email_html(db, settings, prospect=prospect, body_text=text)
        html_out = rendered["html"]
        text_out = rendered["text"]

        try:
            result = AiTeamService._deliver_email(
                db,
                settings,
                to_email=prospect.email,
                subject=subj,
                text=text_out,
                html=html_out,
            )
        except AiTeamServiceError as exc:
            prospect.last_error = str(exc)
            prospect.updated_at = AiTeamService._now()
            db.add(prospect)
            db.commit()
            raise

        now = AiTeamService._now()
        msg = AiTeamMessage(
            prospect_id=prospect.id,
            direction="outbound",
            from_email=settings.from_email,
            to_email=prospect.email,
            subject=subj,
            body_text=text,
            body_html=html_out,
            resend_email_id=result.get("email_id"),
            created_at=now,
        )
        prospect.status = "sent"
        prospect.sent_at = prospect.sent_at or now
        prospect.approved_at = prospect.approved_at or now
        prospect.emails_sent_count = int(prospect.emails_sent_count or 0) + 1
        if result.get("email_id"):
            prospect.resend_email_id = result.get("email_id")
        prospect.last_error = None
        prospect.updated_at = now
        db.add(msg)
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def approve_prospect(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        if not prospect.draft_body:
            AiTeamService.draft_email_for_prospect(db, prospect, settings)
        return AiTeamService.send_prospect_email(db, prospect)

    @staticmethod
    def reject_prospect(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        now = AiTeamService._now()
        prospect.status = "rejected"
        prospect.rejected_at = now
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def delete_prospect(db: Session, prospect_id: str) -> dict[str, Any]:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        # Remove message rows first (no cascade guaranteed across DBs)
        for msg in AiTeamService.list_messages(db, prospect_id):
            db.delete(msg)
        db.delete(prospect)
        db.commit()
        return {"ok": True, "deleted": 1, "id": prospect_id}

    @staticmethod
    def purge_prospects(
        db: Session,
        *,
        status: str | None = "pending",
        statuses: list[str] | None = None,
    ) -> dict[str, Any]:
        """Hard-delete prospects. Default: approval queue (pending + new)."""
        wanted: list[str]
        if statuses:
            wanted = [str(s).strip().lower() for s in statuses if str(s).strip()]
        elif status in {None, "", "queue", "pending"}:
            wanted = ["pending", "new"]
        else:
            wanted = [str(status).strip().lower()]
        if not wanted:
            raise AiTeamServiceError("No status selected to purge")
        rows = list(
            db.execute(select(AiTeamProspect).where(AiTeamProspect.status.in_(wanted))).scalars().all()
        )
        deleted = 0
        for row in rows:
            for msg in AiTeamService.list_messages(db, row.id):
                db.delete(msg)
            db.delete(row)
            deleted += 1
        db.commit()
        return {
            "ok": True,
            "deleted": deleted,
            "statuses": wanted,
            "message": f"Deleted {deleted} prospect(s)",
        }

    @staticmethod
    def export_prospects_csv(
        db: Session,
        *,
        status: str | None = None,
        source: str | None = None,
    ) -> tuple[str, str]:
        if status in {"queue", "pending"}:
            rows = [
                r
                for r in AiTeamService.list_prospects(db, source=source)
                if str(r.status or "").lower() in {"pending", "new"}
            ]
            label = "queue"
        elif status == "engagement":
            rows = [
                r
                for r in AiTeamService.list_prospects(db, source=source)
                if str(r.status or "").lower() in {"sent", "opened", "replied", "converted"}
            ]
            label = "engagement"
        elif status == "opened":
            rows = [
                r
                for r in AiTeamService.list_prospects(db, source=source)
                if r.opened_at or str(r.status or "").lower() in {"opened", "replied", "converted"}
            ]
            label = "opened"
        elif status == "replied":
            rows = [
                r
                for r in AiTeamService.list_prospects(db, source=source)
                if r.replied_at or str(r.status or "").lower() in {"replied", "converted"}
            ]
            label = "replied"
        else:
            rows = AiTeamService.list_prospects(db, status=status, source=source)
            label = status or "all"
        if not rows:
            raise AiTeamServiceError("No prospects to export")
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "email",
                "first_name",
                "last_name",
                "company_name",
                "job_title",
                "status",
                "source",
                "sector",
                "promo_code",
                "draft_subject",
                "sent_at",
                "opened_at",
                "replied_at",
                "match_score",
            ]
        )
        for r in rows:
            d = AiTeamService.prospect_to_dict(db, r)
            writer.writerow(
                [
                    d.get("email") or "",
                    d.get("first_name") or "",
                    d.get("last_name") or "",
                    d.get("company_name") or "",
                    d.get("job_title") or "",
                    d.get("status") or "",
                    d.get("source") or "",
                    d.get("sector") or "",
                    d.get("promo_code") or "",
                    d.get("draft_subject") or "",
                    d.get("sent_at") or "",
                    d.get("opened_at") or "",
                    d.get("replied_at") or "",
                    d.get("match_score") or "",
                ]
            )
        return f"ai-team-{label}.csv", "\ufeff" + buf.getvalue()

    @staticmethod
    def regenerate_draft(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        return AiTeamService.draft_email_for_prospect(db, prospect, settings)

    @staticmethod
    def update_draft(db: Session, prospect_id: str, *, subject: str, body: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        now = AiTeamService._now()
        prospect.draft_subject = subject.strip()[:500]
        prospect.draft_body = body.strip()
        rendered = AiTeamService.render_email_html(db, settings, prospect=prospect, body_text=body.strip())
        prospect.draft_body_html = rendered["html"]
        prospect.drafted_at = now
        prospect.status = "pending"
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def mark_converted(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        now = AiTeamService._now()
        prospect.status = "converted"
        prospect.converted_at = now
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def record_inbound_reply(db: Session, *, prospect_id: str, body: str, from_email: str) -> AiTeamMessage:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        now = AiTeamService._now()
        msg = AiTeamMessage(
            prospect_id=prospect.id,
            direction="inbound",
            from_email=from_email,
            to_email=prospect.email,
            subject="Re: " + (prospect.draft_subject or ""),
            body_text=body,
            created_at=now,
        )
        prospect.status = "replied"
        prospect.replied_at = now
        prospect.updated_at = now
        db.add(msg)
        db.add(prospect)
        db.commit()
        db.refresh(msg)
        return msg

    @staticmethod
    def send_reply(db: Session, prospect_id: str, *, body: str) -> AiTeamMessage:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        subject = "Re: " + (prospect.draft_subject or "VoxBulk")
        AiTeamService.send_prospect_email(db, prospect, subject=subject, body=body)
        return db.execute(
            select(AiTeamMessage).where(AiTeamMessage.prospect_id == prospect.id).order_by(AiTeamMessage.created_at.desc())
        ).scalars().first()

    @staticmethod
    def list_messages(db: Session, prospect_id: str) -> list[AiTeamMessage]:
        return list(
            db.execute(
                select(AiTeamMessage).where(AiTeamMessage.prospect_id == prospect_id).order_by(AiTeamMessage.created_at.asc())
            ).scalars().all()
        )

    @staticmethod
    def list_replies(db: Session) -> list[AiTeamProspect]:
        return list(
            db.execute(
                select(AiTeamProspect)
                .where(AiTeamProspect.status.in_(["replied", "opened", "sent"]))
                .order_by(AiTeamProspect.replied_at.desc(), AiTeamProspect.updated_at.desc())
            ).scalars().all()
        )

    @staticmethod
    def dashboard_stats(db: Session) -> dict[str, Any]:
        pending = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "pending")) or 0
        sent = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "sent")) or 0
        opened = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "opened")) or 0
        replied = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "replied")) or 0
        converted = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "converted")) or 0
        week_ago = AiTeamService._now() - timedelta(days=7)
        sent_week = db.scalar(
            select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.sent_at >= week_ago)
        ) or 0
        promo_used = db.scalar(
            select(func.count()).select_from(PromoOffer).where(
                PromoOffer.ai_team_prospect_id.isnot(None), PromoOffer.redemption_count > 0
            )
        ) or 0
        total_sent = sent + opened + replied + converted
        open_rate = round((opened + replied + converted) / total_sent * 100) if total_sent else 0
        reply_rate = round(replied / total_sent * 100) if total_sent else 0
        return {
            "pending_approval": pending,
            "sent_this_week": sent_week,
            "open_rate": open_rate,
            "reply_rate": reply_rate,
            "replied_count": replied,
            "promo_used": promo_used,
            "converted": converted,
            "total_prospects": db.scalar(select(func.count()).select_from(AiTeamProspect)) or 0,
        }

    @staticmethod
    def analytics(db: Session) -> dict[str, Any]:
        stats = AiTeamService.dashboard_stats(db)
        rows = list(db.execute(select(AiTeamProspect)).scalars().all())
        funnel = {
            "found": len(rows),
            "qualified": len([r for r in rows if r.match_score >= 60]),
            "sent": len([r for r in rows if r.status in {"sent", "opened", "replied", "converted"}]),
            "opened": len([r for r in rows if r.status in {"opened", "replied", "converted"} or r.opened_at]),
            "replied": len([r for r in rows if r.status in {"replied", "converted"} or r.replied_at]),
            "converted": len([r for r in rows if r.status == "converted"]),
        }
        sectors: dict[str, dict[str, int]] = {}
        for r in rows:
            sec = r.sector or "general"
            bucket = sectors.setdefault(sec, {"sent": 0, "opened": 0, "replied": 0, "converted": 0})
            if r.status in {"sent", "opened", "replied", "converted"}:
                bucket["sent"] += 1
            if r.opened_at or r.status in {"opened", "replied", "converted"}:
                bucket["opened"] += 1
            if r.replied_at or r.status in {"replied", "converted"}:
                bucket["replied"] += 1
            if r.status == "converted":
                bucket["converted"] += 1
        sector_rows = []
        for sec, b in sectors.items():
            sent = b["sent"] or 0
            sector_rows.append({
                "sector": sec,
                "sent": sent,
                "open_pct": round(b["opened"] / sent * 100) if sent else 0,
                "reply_pct": round(b["replied"] / sent * 100) if sent else 0,
                "converted": b["converted"],
            })
        return {"stats": stats, "funnel": funnel, "sectors": sector_rows}

    @staticmethod
    def list_promo_codes(db: Session) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(PromoOffer).where(PromoOffer.ai_team_prospect_id.isnot(None)).order_by(PromoOffer.created_at.desc())
            ).scalars().all()
        )
        out = []
        for row in rows:
            status = "unused"
            if row.redemption_count > 0:
                status = "used"
            elif row.expires_at and row.expires_at < AiTeamService._now():
                status = "expired"
            out.append({
                **PromoOfferService.to_admin_dict(row),
                "usage_status": status,
            })
        return out

    @staticmethod
    def run_agent(db: Session) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        if settings.agent_paused:
            return {"ok": False, "message": "Agent is paused"}
        result = {"fetch": None, "approved": []}
        if settings.auto_fetch_prospects:
            result["fetch"] = AiTeamService.fetch_prospects(db, preview=False)
        pending = AiTeamService.list_prospects(db, status="pending")
        if settings.auto_send_without_approval:
            for p in pending[: max(0, int(settings.max_emails_per_day or 10))]:
                try:
                    AiTeamService.approve_prospect(db, p.id)
                    result["approved"].append(p.id)
                except Exception as exc:
                    logger.warning("ai_team_auto_send_failed", extra={"prospect_id": p.id, "error": str(exc)})
        settings.last_agent_run_at = AiTeamService._now()
        db.add(settings)
        db.commit()
        return {"ok": True, **result}

    @staticmethod
    def test_smtp(settings: AiTeamSettings, *, to_email: str, db: Session) -> dict[str, Any]:
        host = (settings.smtp_host or "").strip()
        port = int(settings.smtp_port or 587)
        user = (settings.smtp_username or "").strip()
        if not host or not user:
            raise AiTeamServiceError("SMTP host and username are required")
        pwd = AiTeamService._smtp_password(settings)
        if not pwd:
            raise AiTeamServiceError("SMTP password is required")
        to_addr = str(to_email or settings.inbox_email or settings.from_email or user).strip()
        result = AiTeamService._send_via_smtp(
            settings,
            to_email=to_addr,
            subject="VoxBulk AI Team SMTP test",
            text="SMTP connection test from AI Team settings.",
            html="<p>SMTP connection test from AI Team settings.</p>",
        )
        return {"ok": True, "message": f"SMTP test sent to {to_addr}", "provider": result.get("provider")}

    @staticmethod
    def test_apify(db: Session, *, token: str | None = None, check_actor: bool = False) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        key = str(token or "").strip() or AiTeamService._apify_token(settings, db=db)
        actor = None
        if check_actor:
            actor = (settings.apify_exhibitor_actor_id or settings.apify_contact_actor_id or "").strip() or None
        try:
            return ApifyService.test_connection(key, actor_id=actor)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

    @staticmethod
    def test_all_connections(db: Session, *, to_email: str | None = None) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        checks: list[dict[str, Any]] = []

        # Apify
        try:
            apify = AiTeamService.test_apify(db)
            checks.append({"id": "apify", "ok": True, "message": apify.get("message") or "Apify OK"})
        except Exception as exc:
            checks.append({"id": "apify", "ok": False, "message": str(exc)})

        # Email delivery
        provider = AiTeamService._delivery_provider(settings)
        to_addr = str(to_email or settings.inbox_email or settings.reply_to_email or settings.from_email or "").strip()
        try:
            if provider == "smtp":
                if not (settings.smtp_host and settings.smtp_username and settings.smtp_password_enc):
                    raise AiTeamServiceError("SMTP is not fully configured")
                if to_addr and "@" in to_addr:
                    smtp = AiTeamService.test_smtp(settings, to_email=to_addr, db=db)
                    checks.append({"id": "email", "ok": True, "message": smtp.get("message") or "SMTP OK"})
                else:
                    # Login-only style check without requiring recipient
                    host = settings.smtp_host
                    port = int(settings.smtp_port or 587)
                    user = settings.smtp_username
                    pwd = AiTeamService._smtp_password(settings)
                    context = ssl.create_default_context()
                    if port == 465:
                        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
                            server.login(user, pwd)
                    else:
                        with smtplib.SMTP(host, port, timeout=20) as server:
                            server.starttls(context=context)
                            server.login(user, pwd)
                    checks.append({"id": "email", "ok": True, "message": "SMTP login OK (no test recipient)"})
            else:
                key = AiTeamService._resend_key(db)
                if not key:
                    raise AiTeamServiceError("Resend API key is not configured")
                from_email = AiTeamService._from_address(settings)
                fallback = to_addr or settings.from_email
                res = ResendService.test_connection(key, from_email=from_email, to_email=fallback)
                checks.append({"id": "email", "ok": True, "message": res.get("message") or "Resend OK"})
        except Exception as exc:
            checks.append({"id": "email", "ok": False, "message": str(exc)})

        # From address
        from_ok = bool(settings.from_email and "@" in settings.from_email)
        checks.append({
            "id": "from_email",
            "ok": from_ok,
            "message": settings.from_email if from_ok else "From email is not configured",
        })

        # Promo
        promo_ok = bool(settings.promo_code_prefix)
        checks.append({
            "id": "promo",
            "ok": promo_ok,
            "message": f"Promo prefix {settings.promo_code_prefix or '—'} · type {settings.promo_offer_type or '—'}",
        })

        # DeepSeek (optional)
        try:
            deepseek_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="deepseek")
            deepseek_ok, _ = AiTeamService._provider_connection_flags(deepseek_view)
            checks.append({
                "id": "deepseek",
                "ok": deepseek_ok,
                "message": "DeepSeek configured" if deepseek_ok else "DeepSeek not configured (AI drafts need it)",
            })
        except Exception as exc:
            checks.append({"id": "deepseek", "ok": False, "message": str(exc)})

        all_ok = all(c["ok"] for c in checks if c["id"] in {"apify", "email", "from_email"})
        return {"ok": all_ok, "provider": provider, "checks": checks}

    @staticmethod
    def _run_to_dict(row: AiTeamApifyRun) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        try:
            raw = json.loads(row.stats_json or "{}")
            if isinstance(raw, dict):
                stats = raw
        except Exception:
            stats = {}
        progress = stats.get("progress") if isinstance(stats.get("progress"), dict) else {}
        stands_total = int(
            progress.get("stands_total")
            or stats.get("stands_found")
            or row.item_count
            or 0
        )
        stands_done = int(progress.get("stands_done") or 0)
        if str(row.status or "").upper() == "SUCCEEDED" and stands_total and not stands_done:
            stands_done = stands_total
        return {
            "id": row.id,
            "apify_run_id": row.apify_run_id,
            "actor_id": row.actor_id,
            "expo_url": row.expo_url,
            "status": row.status,
            "dataset_id": row.dataset_id,
            "item_count": row.item_count,
            "imported_count": row.imported_count,
            "emails_found": int(
                stats.get("emails_total")
                or stats.get("emails_found")
                or progress.get("emails_found")
                or 0
            ),
            "emails_added": int(stats.get("emails_added") or 0) if "emails_added" in stats else None,
            "emails_skipped": int(stats.get("emails_skipped") or 0) if "emails_skipped" in stats else None,
            "emails_total": int(stats.get("emails_total") or stats.get("emails_found") or 0)
            if ("emails_total" in stats or stats.get("merge_update"))
            else None,
            "stands_found": int(stats.get("stands_found") or stands_total or 0),
            "stands_with_email": int(stats.get("stands_with_email") or progress.get("stands_with_email") or 0),
            "provider": stats.get("provider") or progress.get("provider") or (
                "builtin" if str(row.actor_id or "").startswith("builtin:") else "apify"
            ),
            "is_update": bool(stats.get("merge_update") or stats.get("is_update")),
            "progress": {
                "phase": progress.get("phase") or ("done" if str(row.status or "").upper() == "SUCCEEDED" else "queued"),
                "message": progress.get("message") or stats.get("message") or "",
                "stands_total": stands_total,
                "stands_done": stands_done,
                "stands_with_email": int(progress.get("stands_with_email") or stats.get("stands_with_email") or 0),
                "emails_found": int(progress.get("emails_found") or stats.get("emails_found") or 0),
                "emails_added": int(progress.get("emails_added") or stats.get("emails_added") or 0)
                if ("emails_added" in progress or "emails_added" in stats)
                else None,
                "emails_skipped": int(progress.get("emails_skipped") or stats.get("emails_skipped") or 0)
                if ("emails_skipped" in progress or "emails_skipped" in stats)
                else None,
                "errors": int(progress.get("errors") or stats.get("errors") or 0),
                "heartbeat_at": progress.get("heartbeat_at")
                or (row.updated_at.isoformat() if row.updated_at else None),
                "follow_websites": bool(
                    progress.get("follow_websites")
                    if "follow_websites" in progress
                    else stats.get("follow_websites")
                ),
            },
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }

    @staticmethod
    def _write_scrape_progress(run_id: str, progress: dict[str, Any]) -> None:
        """Persist live scrape progress (short separate session; safe from Celery worker)."""
        from app.core.database import get_sessionmaker

        session = get_sessionmaker()()
        try:
            row = session.get(AiTeamApifyRun, run_id)
            if row is None or str(row.status or "").upper() != "RUNNING":
                return
            try:
                stats = json.loads(row.stats_json or "{}")
                if not isinstance(stats, dict):
                    stats = {}
            except Exception:
                stats = {}
            now = AiTeamService._now()
            hb = progress.get("heartbeat_at") or (now.isoformat() + "Z")
            stats["progress"] = {
                "phase": progress.get("phase") or "stands",
                "message": str(progress.get("message") or "")[:240],
                "stands_total": int(progress.get("stands_total") or 0),
                "stands_done": int(progress.get("stands_done") or 0),
                "stands_with_email": int(progress.get("stands_with_email") or 0),
                "emails_found": int(progress.get("emails_found") or 0),
                "errors": int(progress.get("errors") or 0),
                "heartbeat_at": hb,
                "follow_websites": bool(progress.get("follow_websites")),
                "provider": progress.get("provider") or stats.get("provider") or "pending",
            }
            # Mirror live counters for the table columns while RUNNING
            if stats["progress"]["stands_total"]:
                stats["stands_found"] = stats["progress"]["stands_total"]
            stats["stands_with_email"] = stats["progress"]["stands_with_email"]
            stats["emails_found"] = stats["progress"]["emails_found"]
            stats["errors"] = stats["progress"]["errors"]
            if progress.get("provider"):
                stats["provider"] = progress.get("provider")
            row.stats_json = json.dumps(stats, ensure_ascii=False)
            row.updated_at = now
            session.add(row)
            session.commit()
        except Exception:
            logger.debug("directory_scrape_progress_write_failed run_id=%s", run_id, exc_info=True)
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    @staticmethod
    def run_directory_scrape_job(
        run_id: str,
        *,
        follow_websites: bool = False,
        max_stands: int = 500,
        merge_existing: bool = False,
    ) -> dict[str, Any]:
        """Execute a queued builtin directory scrape and persist results on the run row.

        When merge_existing is True (or stats_json has prior_contacts from an Update),
        keep emails already stored on the run and only append newly found addresses.
        """
        from app.core.database import get_sessionmaker

        session = get_sessionmaker()()
        try:
            row = session.get(AiTeamApifyRun, run_id)
            if row is None:
                return {"ok": False, "error": "run not found"}
            url = str(row.expo_url or "").strip()
            prior_contacts: list[dict[str, Any]] = []
            prior_skip_emails: set[str] = set()
            try:
                stats0 = json.loads(row.stats_json or "{}")
                if isinstance(stats0, dict):
                    raw_prior = stats0.get("prior_contacts")
                    if isinstance(raw_prior, list):
                        prior_contacts = [c for c in raw_prior if isinstance(c, dict) and c.get("email")]
                    if not prior_contacts and merge_existing:
                        raw_contacts = stats0.get("contacts")
                        if isinstance(raw_contacts, list):
                            prior_contacts = [
                                c for c in raw_contacts if isinstance(c, dict) and c.get("email")
                            ]
                    raw_skip = stats0.get("prior_skip_emails")
                    if isinstance(raw_skip, list):
                        prior_skip_emails = {
                            str(e or "").strip().lower()
                            for e in raw_skip
                            if str(e or "").strip() and "@" in str(e)
                        }
            except Exception:
                prior_contacts = []
                prior_skip_emails = set()
            merge_mode = bool(merge_existing or prior_contacts or prior_skip_emails)
            last_progress_at = 0.0

            def _on_progress(payload: dict[str, Any]) -> None:
                nonlocal last_progress_at
                import time as _time

                # Force-pause / abort check (admin click)
                check = get_sessionmaker()()
                try:
                    live = check.get(AiTeamApifyRun, run_id)
                    st = str(getattr(live, "status", "") or "").upper()
                    if st in {"ABORTED", "PAUSED"}:
                        from app.services.expo_directory_scraper_service import ScrapeAborted

                        raise ScrapeAborted(f"Scrape {st.lower()}")
                finally:
                    check.close()

                now_ts = _time.monotonic()
                phase = str(payload.get("phase") or "")
                done = int(payload.get("stands_done") or 0)
                total = int(payload.get("stands_total") or 0)
                # Throttle DB writes: phase changes, every 5 stands, or every 1.5s
                force = phase in {"listing", "done"} or done <= 1 or (total and done >= total)
                if not force and (now_ts - last_progress_at) < 1.5 and (done % 5) != 0:
                    return
                last_progress_at = now_ts
                AiTeamService._write_scrape_progress(run_id, payload)

            try:
                result = ExpoDirectoryScraper.scrape(
                    url,
                    follow_websites=bool(follow_websites),
                    max_stands=max(1, min(int(max_stands or 500), 1000)),
                    progress_callback=_on_progress,
                )
            except Exception as exc:
                from app.services.expo_directory_scraper_service import ScrapeAborted

                if isinstance(exc, ScrapeAborted):
                    row = session.get(AiTeamApifyRun, run_id) or row
                    now = AiTeamService._now()
                    row.status = "ABORTED"
                    row.error = "Force paused by admin"
                    row.finished_at = now
                    row.updated_at = now
                    try:
                        stats = json.loads(row.stats_json or "{}")
                        if not isinstance(stats, dict):
                            stats = {}
                    except Exception:
                        stats = {}
                    prog = stats.get("progress") if isinstance(stats.get("progress"), dict) else {}
                    prog = {**(prog or {}), "phase": "paused", "message": "Force paused — scrape stopped"}
                    stats["progress"] = prog
                    row.stats_json = json.dumps(stats, ensure_ascii=False)
                    session.add(row)
                    session.commit()
                    return {"ok": True, "aborted": True, "run_id": run_id}
                if isinstance(exc, ExpoDirectoryScraperError):
                    row.status = "FAILED"
                    row.error = str(exc)[:2000]
                    row.finished_at = AiTeamService._now()
                    row.updated_at = row.finished_at
                    session.add(row)
                    session.commit()
                    return {"ok": False, "error": str(exc)}
                logger.exception("directory_scrape_failed run_id=%s", run_id)
                row.status = "FAILED"
                row.error = f"Directory scrape failed: {exc}"[:2000]
                row.finished_at = AiTeamService._now()
                row.updated_at = row.finished_at
                session.add(row)
                session.commit()
                return {"ok": False, "error": str(exc)}

            contacts = AiTeamService._slim_directory_contacts(result.get("contacts") or [])
            finished = AiTeamService._now()
            # If admin aborted while last batch finished, honour abort
            session.refresh(row)
            if str(row.status or "").upper() in {"ABORTED", "PAUSED"}:
                return {"ok": True, "aborted": True, "run_id": run_id}

            emails_found = int(result.get("emails_found") or len(contacts) or 0)
            emails_skipped = 0
            emails_added = emails_found
            if merge_mode:
                prior_slim = AiTeamService._slim_directory_contacts(prior_contacts)
                by_email: dict[str, dict[str, Any]] = {}
                for c in prior_slim:
                    em = str(c.get("email") or "").strip().lower()
                    if em and "@" in em:
                        by_email[em] = c
                known = set(by_email.keys()) | set(prior_skip_emails)
                emails_skipped = 0
                emails_added = 0
                for c in contacts:
                    em = str(c.get("email") or "").strip().lower()
                    if not em or "@" not in em:
                        continue
                    if em in known:
                        emails_skipped += 1
                        if em in by_email:
                            # Refresh sparse prior fields when the new scrape has better data
                            prev = by_email[em]
                            for key in (
                                "first_name",
                                "last_name",
                                "company_name",
                                "job_title",
                                "website",
                                "profile_url",
                                "event_name",
                                "stand_number",
                            ):
                                if not str(prev.get(key) or "").strip() and str(c.get(key) or "").strip():
                                    prev[key] = c.get(key)
                            by_email[em] = prev
                        continue
                    by_email[em] = c
                    known.add(em)
                    emails_added += 1
                contacts = list(by_email.values())

            row.status = "SUCCEEDED"
            row.item_count = len(contacts) if merge_mode else int(
                result.get("emails_found") or len(contacts) or result.get("stands_found") or 0
            )
            stands_total = int(result.get("stands_found") or 0)
            payload = {
                "provider": result.get("provider"),
                "editions": result.get("editions") or [],
                "stands_found": result.get("stands_found"),
                "stands_with_email": result.get("stands_with_email"),
                "emails_found": emails_found,
                "emails_skipped": emails_skipped if merge_mode else None,
                "emails_added": emails_added if merge_mode else None,
                "emails_total": len(contacts),
                "merge_update": bool(merge_mode),
                "errors": result.get("errors"),
                "warning": result.get("warning"),
                "follow_websites": bool(follow_websites),
                "contacts": contacts,
                "progress": {
                    "phase": "done",
                    "message": (
                        f"Update complete · {emails_added} new · {emails_skipped} already had"
                        if merge_mode
                        else "Completed"
                    ),
                    "stands_total": stands_total,
                    "stands_done": stands_total,
                    "stands_with_email": int(result.get("stands_with_email") or 0),
                    "emails_found": emails_found,
                    "emails_added": emails_added if merge_mode else None,
                    "emails_skipped": emails_skipped if merge_mode else None,
                    "errors": int(result.get("errors") or 0),
                    "heartbeat_at": finished.isoformat() + "Z",
                    "follow_websites": bool(follow_websites),
                    "provider": result.get("provider"),
                },
            }
            # Drop bulky prior_contacts snapshot once merged
            row.stats_json = json.dumps(
                {k: v for k, v in payload.items() if v is not None},
                ensure_ascii=False,
            )
            row.error = None
            row.finished_at = finished
            row.updated_at = finished
            session.add(row)
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                # Last resort: keep counts but drop contact bodies so the run is not stuck FAILED.
                logger.exception("directory_scrape_stats_commit_failed run_id=%s", run_id)
                row = session.get(AiTeamApifyRun, run_id)
                if row is None:
                    return {"ok": False, "error": str(exc)}
                slim = {k: v for k, v in payload.items() if k != "contacts" and v is not None}
                slim["contacts"] = [
                    {"email": c.get("email"), "company_name": c.get("company_name")}
                    for c in contacts
                    if isinstance(c, dict) and c.get("email")
                ]
                row.status = "SUCCEEDED"
                row.item_count = int(slim.get("emails_total") or len(slim["contacts"]) or 0)
                row.stats_json = json.dumps(slim, ensure_ascii=False)
                row.error = None
                row.finished_at = finished
                row.updated_at = finished
                session.add(row)
                session.commit()
            return {
                "ok": True,
                "stands_found": result.get("stands_found"),
                "emails_found": emails_found,
                "emails_skipped": emails_skipped if merge_mode else 0,
                "emails_added": emails_added if merge_mode else emails_found,
                "emails_total": len(contacts),
                "provider": result.get("provider"),
                "merge_update": bool(merge_mode),
            }
        finally:
            session.close()

    @staticmethod
    def _slim_directory_contacts(contacts: list[Any]) -> list[dict[str, Any]]:
        """Keep importable fields only — drop bulky nested profile blobs."""
        out: list[dict[str, Any]] = []
        for raw in contacts or []:
            if not isinstance(raw, dict):
                continue
            email = str(raw.get("email") or "").strip()
            if not email or "@" not in email:
                continue
            profile = raw.get("profile_json") if isinstance(raw.get("profile_json"), dict) else {}
            out.append(
                {
                    "email": email,
                    "first_name": str(raw.get("first_name") or "")[:80],
                    "last_name": str(raw.get("last_name") or "")[:80],
                    "company_name": str(raw.get("company_name") or "")[:200],
                    "job_title": str(raw.get("job_title") or "")[:120],
                    "sector": str(raw.get("sector") or "")[:80],
                    "country_code": str(raw.get("country_code") or "")[:8],
                    "website": str(raw.get("website") or profile.get("website") or "")[:500],
                    "profile_url": str(raw.get("profile_url") or profile.get("profile_url") or "")[:500],
                    "event_name": str(raw.get("event_name") or "")[:200],
                    "stand_number": str(raw.get("stand_number") or "")[:40],
                    "stand_id": str(raw.get("stand_id") or "")[:40],
                    "edition_id": raw.get("edition_id"),
                    "source": str(raw.get("source") or "expo_directory")[:40],
                }
            )
        return out

    @staticmethod
    def start_directory_scrape(
        db: Session,
        *,
        expo_url: str,
        follow_websites: bool = True,
        max_stands: int = 500,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Built-in scrape: list exhibitors → extract emails (no Apify).

        Queues Celery when available (survives gunicorn). Falls back to in-process
        thread only if Celery enqueue fails. Pass wait=True for sync tests.
        """
        url = str(expo_url or "").strip().replace("\\", "/")
        if not url.startswith("http"):
            raise AiTeamServiceError("Enter a valid expo directory URL (https://…)")

        now = AiTeamService._now()
        row = AiTeamApifyRun(
            apify_run_id=None,
            actor_id="builtin:directory",
            expo_url=url,
            status="RUNNING",
            dataset_id=None,
            created_at=now,
            updated_at=now,
            stats_json=json.dumps(
                {
                    "provider": "pending",
                    "message": "queued",
                    "follow_websites": bool(follow_websites),
                    "progress": {
                        "phase": "queued",
                        "message": "Queued — waiting for Celery worker…",
                        "stands_total": 0,
                        "stands_done": 0,
                        "stands_with_email": 0,
                        "emails_found": 0,
                        "errors": 0,
                        "heartbeat_at": now.isoformat() + "Z",
                        "follow_websites": bool(follow_websites),
                        "provider": "pending",
                    },
                }
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        run_id = row.id

        if wait:
            AiTeamService.run_directory_scrape_job(
                run_id, follow_websites=follow_websites, max_stands=max_stands
            )
            # End the create-run transaction so we see the worker session's commit
            # (MySQL REPEATABLE READ otherwise still shows RUNNING).
            db.commit()
            db.expire_all()
            row = db.get(AiTeamApifyRun, run_id)
            if row is None:
                raise AiTeamServiceError("Scrape run disappeared")
            if str(row.status).upper() == "FAILED":
                raise AiTeamServiceError(row.error or "Directory scrape failed")
            return {
                "ok": True,
                "run": AiTeamService._run_to_dict(row),
                "stands_found": AiTeamService._run_to_dict(row).get("stands_found"),
                "emails_found": AiTeamService._run_to_dict(row).get("emails_found"),
                "provider": AiTeamService._run_to_dict(row).get("provider"),
            }

        queued = False
        queue_error = ""
        celery_task_id = ""
        # Default: run in the API process so scrape code matches the live gunicorn build.
        # Stale Celery workers (e.g. root Supervisor not restarted after deploy) used the
        # old HTML-only path → SUCCEEDED with 0 emails in a few seconds.
        use_celery = str(os.environ.get("VOX_SCRAPE_USE_CELERY") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if use_celery:
            try:
                from app.workers.ai_team_tasks import scrape_directory_task

                async_result = scrape_directory_task.apply_async(
                    args=[run_id],
                    kwargs={
                        "follow_websites": bool(follow_websites),
                        "max_stands": max(1, min(int(max_stands or 500), 1000)),
                    },
                    queue="voxbulk",
                )
                celery_task_id = str(async_result.id or "")
                if celery_task_id:
                    row.apify_run_id = celery_task_id
                    row.updated_at = AiTeamService._now()
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                queued = True
            except Exception as exc:
                queue_error = str(exc)
                logger.warning("directory_scrape_celery_enqueue_failed: %s", exc)

        if not queued:
            try:
                AiTeamService.run_directory_scrape_job(
                    run_id,
                    follow_websites=bool(follow_websites),
                    max_stands=max_stands,
                )
                # Job uses its own Session — reopen so we never return a stale RUNNING row.
                db.commit()
                db.expire_all()
                row = db.get(AiTeamApifyRun, run_id)
                if row is None:
                    raise AiTeamServiceError("Scrape run disappeared after finish")
                db.refresh(row)
                info = AiTeamService._run_to_dict(row)
                emails_n = int(info.get("emails_found") or row.item_count or 0)
                return {
                    "ok": True,
                    "run": info,
                    "queued_via": "inline",
                    "emails_found": emails_n,
                    "provider": info.get("provider"),
                    "message": f"Scrape finished · {emails_n} email(s)",
                }
            except AiTeamServiceError:
                raise
            except Exception as inline_exc:
                row = db.get(AiTeamApifyRun, run_id) or row
                row.status = "FAILED"
                row.error = (
                    f"Inline scrape failed: {inline_exc}"
                    if not queue_error
                    else f"Celery enqueue failed ({queue_error[:200]}); inline scrape also failed: {inline_exc}"
                )[:2000]
                row.finished_at = AiTeamService._now()
                row.updated_at = row.finished_at
                db.add(row)
                db.commit()
                raise AiTeamServiceError(row.error) from inline_exc

        return {
            "ok": True,
            "run": AiTeamService._run_to_dict(row),
            "queued_via": "celery",
            "celery_task_id": celery_task_id,
            "message": "Scrape queued on Celery — live progress updates every few seconds.",
        }

    @staticmethod
    def _builtin_run_contacts(row: AiTeamApifyRun) -> list[dict[str, Any]]:
        """Contacts stored on a scrape run (builtin stats_json), regardless of actor prefix."""
        try:
            stats = json.loads(row.stats_json or "{}")
        except Exception:
            return []
        contacts = stats.get("contacts") if isinstance(stats, dict) else None
        if not isinstance(contacts, list):
            # Update jobs stash prior emails here until the scrape finishes
            prior = stats.get("prior_contacts") if isinstance(stats, dict) else None
            if isinstance(prior, list):
                contacts = prior
            else:
                return []
        return [c for c in contacts if isinstance(c, dict) and str(c.get("email") or "").strip()]

    @staticmethod
    def _load_run_contacts_for_update(db: Session, row: AiTeamApifyRun) -> list[dict[str, Any]]:
        """All known emails for this run (stored contacts, or Apify dataset preview)."""
        contacts = AiTeamService._builtin_run_contacts(row)
        if contacts:
            return contacts
        if str(row.actor_id or "").startswith("builtin:"):
            return []
        if not row.dataset_id:
            return []
        try:
            preview = AiTeamService.preview_apify_run(db, row.id, limit=10000)
            return list(preview.get("preview") or [])
        except Exception:
            logger.debug("update_scrape_prior_apify_load_failed run_id=%s", row.id, exc_info=True)
            return []

    @staticmethod
    def _known_emails_for_directory(db: Session, *, expo_url: str, exclude_run_id: str | None = None) -> set[str]:
        """Emails already stored on other scrape runs for the same directory URL."""
        url = str(expo_url or "").strip()
        known: set[str] = set()
        if not url:
            return known
        rows = list(
            db.execute(
                select(AiTeamApifyRun).where(AiTeamApifyRun.expo_url == url).limit(50)
            ).scalars().all()
        )
        for r in rows:
            if exclude_run_id and r.id == exclude_run_id:
                continue
            for c in AiTeamService._builtin_run_contacts(r):
                em = str(c.get("email") or "").strip().lower()
                if em and "@" in em:
                    known.add(em)
        return known

    @staticmethod
    def update_scrape_run(
        db: Session,
        run_id: str,
        *,
        follow_websites: bool = True,
        max_stands: int = 500,
        engine: str = "auto",
    ) -> dict[str, Any]:
        """Re-scrape the same expo_url on an existing run; keep old emails, append only new ones."""
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Scrape run not found")
        st = str(row.status or "").upper()
        if st in {"RUNNING", "READY", "CREATED", "ABORTING"}:
            raise AiTeamServiceError("Scrape is still running — Force pause or wait, then Update")
        url = str(row.expo_url or "").strip().replace("\\", "/")
        if not url.startswith("http"):
            raise AiTeamServiceError("This run has no valid directory URL to update")

        prior = AiTeamService._slim_directory_contacts(
            AiTeamService._load_run_contacts_for_update(db, row)
        )
        prior_emails = {
            str(c.get("email") or "").strip().lower()
            for c in prior
            if str(c.get("email") or "").strip() and "@" in str(c.get("email") or "")
        }
        known_extra = AiTeamService._known_emails_for_directory(
            db, expo_url=url, exclude_run_id=row.id
        ) - prior_emails
        prior_count = len(prior_emails)
        now = AiTeamService._now()
        # Force built-in for Update so results land in stats_json contacts (mergeable).
        _ = engine
        row.actor_id = "builtin:directory"
        row.status = "RUNNING"
        row.error = None
        row.finished_at = None
        row.dataset_id = None
        row.apify_run_id = None
        row.updated_at = now
        row.stats_json = json.dumps(
            {
                "provider": "pending",
                "message": "update queued",
                "merge_update": True,
                "is_update": True,
                "follow_websites": bool(follow_websites),
                "prior_contacts": prior,
                "prior_skip_emails": sorted(known_extra),
                "prior_emails_count": prior_count,
                "progress": {
                    "phase": "queued",
                    "message": f"Updating — keeping {prior_count} existing email(s), scanning for new…",
                    "stands_total": 0,
                    "stands_done": 0,
                    "stands_with_email": 0,
                    "emails_found": 0,
                    "errors": 0,
                    "heartbeat_at": now.isoformat() + "Z",
                    "follow_websites": bool(follow_websites),
                    "provider": "pending",
                },
            },
            ensure_ascii=False,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        queued = False
        queue_error = ""
        celery_task_id = ""
        use_celery = str(os.environ.get("VOX_SCRAPE_USE_CELERY") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if use_celery:
            try:
                from app.workers.ai_team_tasks import scrape_directory_task

                async_result = scrape_directory_task.apply_async(
                    args=[run_id],
                    kwargs={
                        "follow_websites": bool(follow_websites),
                        "max_stands": max(1, min(int(max_stands or 500), 1000)),
                        "merge_existing": True,
                    },
                    queue="voxbulk",
                )
                celery_task_id = str(async_result.id or "")
                if celery_task_id:
                    row.apify_run_id = celery_task_id
                    row.updated_at = AiTeamService._now()
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                queued = True
            except Exception as exc:
                queue_error = str(exc)
                logger.warning("directory_scrape_update_celery_enqueue_failed: %s", exc)

        if not queued:
            try:
                job = AiTeamService.run_directory_scrape_job(
                    run_id,
                    follow_websites=bool(follow_websites),
                    max_stands=max_stands,
                    merge_existing=True,
                )
                db.commit()
                db.expire_all()
                row = db.get(AiTeamApifyRun, run_id)
                if row is None:
                    raise AiTeamServiceError("Scrape run disappeared after update")
                db.refresh(row)
                info = AiTeamService._run_to_dict(row)
                added = int(job.get("emails_added") or info.get("emails_added") or 0)
                skipped = int(job.get("emails_skipped") or info.get("emails_skipped") or 0)
                found = int(job.get("emails_found") or info.get("emails_found") or 0)
                total = int(job.get("emails_total") or info.get("emails_total") or info.get("emails_found") or 0)
                return {
                    "ok": True,
                    "run": info,
                    "queued_via": "inline",
                    "emails_found": found,
                    "emails_skipped": skipped,
                    "emails_added": added,
                    "emails_total": total,
                    "provider": info.get("provider"),
                    "message": f"Update finished · {found} found · {skipped} already had · {added} new · {total} total",
                }
            except AiTeamServiceError:
                raise
            except Exception as inline_exc:
                row = db.get(AiTeamApifyRun, run_id) or row
                row.status = "FAILED"
                row.error = (
                    f"Update scrape failed: {inline_exc}"
                    if not queue_error
                    else f"Celery enqueue failed ({queue_error[:200]}); update also failed: {inline_exc}"
                )[:2000]
                row.finished_at = AiTeamService._now()
                row.updated_at = row.finished_at
                db.add(row)
                db.commit()
                raise AiTeamServiceError(row.error) from inline_exc

        return {
            "ok": True,
            "run": AiTeamService._run_to_dict(row),
            "queued_via": "celery",
            "celery_task_id": celery_task_id,
            "emails_found": 0,
            "emails_skipped": 0,
            "emails_added": 0,
            "emails_total": prior_count,
            "message": f"Update queued — keeping {prior_count} existing email(s); live progress updates every few seconds.",
        }

    @staticmethod
    def resolve_scrape_actor(
        settings: AiTeamSettings,
        *,
        actor_id: str | None = None,
    ) -> tuple[str, str]:
        """Pick actor ID and source: override | saved | auto_free."""
        override = str(actor_id or "").strip()
        if override:
            return override, "override"
        saved = str(
            settings.apify_exhibitor_actor_id or settings.apify_contact_actor_id or ""
        ).strip()
        if saved:
            return saved, "saved"
        return DEFAULT_FREE_ACTOR, "auto_free"

    @staticmethod
    def start_smart_scrape(
        db: Session,
        *,
        expo_url: str,
        follow_websites: bool = True,
        engine: str = "auto",
        actor_id: str | None = None,
        max_stands: int = 500,
    ) -> dict[str, Any]:
        """Apify-first scrape with curated free actor + built-in fallback.

        engine: auto | apify | builtin
        """
        url = str(expo_url or "").strip().replace("\\", "/")
        if not url.startswith("http"):
            raise AiTeamServiceError("Enter a valid expo directory URL (https://…)")

        mode = str(engine or "auto").strip().lower()
        if mode not in {"auto", "apify", "builtin"}:
            mode = "auto"

        def _builtin(reason: str, *, fallback_from: str | None = None, apify_error: str | None = None) -> dict[str, Any]:
            result = AiTeamService.start_directory_scrape(
                db,
                expo_url=url,
                follow_websites=follow_websites,
                max_stands=max_stands,
            )
            out: dict[str, Any] = {
                **result,
                "ok": True,
                "engine": "builtin",
                "actor_id": None,
                "actor_source": None,
                "reason": reason,
                "message": result.get("message") or "Using built-in scrape",
            }
            if fallback_from:
                out["fallback_from"] = fallback_from
                out["message"] = f"Apify failed — using built-in. {apify_error or reason}"
            if apify_error:
                out["apify_error"] = apify_error
            return out

        if mode == "builtin":
            return _builtin("Forced built-in scrape")

        # Exhibitor directories: built-in first (Easyfairs / SPA APIs / HTML + website follow).
        # Free Apify "website-contact" actors often scrape only the SPA shell → 0 emails.
        path_l = urlparse(url).path.lower()
        looks_directory = any(
            token in path_l
            for token in ("/exhibitor", "/exhibitors", "/directory", "/stands", "/participants")
        )
        if mode == "auto" and looks_directory:
            return _builtin("Exhibitor directory — built-in first (SPA/API/HTML); use Force Apify only if needed")

        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)

        if mode == "apify" and not token:
            raise AiTeamServiceError("Apify API token is not configured — save it under Apify API, or use engine=auto")

        if mode == "auto" and not token:
            return _builtin("Apify token not configured — using built-in")

        actor, actor_source = AiTeamService.resolve_scrape_actor(settings, actor_id=actor_id)
        try:
            result = AiTeamService.start_apify_run(db, expo_url=url, actor_id=actor)
            # start_apify_run may still return builtin if actor empty — we always pass actor.
            run = result.get("run") or {}
            used_builtin = str(run.get("actor_id") or "").startswith("builtin:")
            if used_builtin:
                return {
                    **result,
                    "ok": True,
                    "engine": "builtin",
                    "actor_id": None,
                    "actor_source": None,
                    "reason": "Apify path returned built-in scrape",
                    "message": result.get("message") or "Using built-in scrape",
                }
            source_label = {
                "override": "override",
                "saved": "saved actor",
                "auto_free": "auto free actor",
            }.get(actor_source, actor_source)
            return {
                **result,
                "ok": True,
                "engine": "apify",
                "actor_id": actor,
                "actor_source": actor_source,
                "reason": f"Apify token ready; using {source_label}",
                "message": f"Using Apify · {actor}" + (f" ({source_label})" if actor_source == "auto_free" else ""),
            }
        except (AiTeamServiceError, ApifyServiceError) as exc:
            if mode == "apify":
                raise AiTeamServiceError(str(exc)) from exc
            return _builtin(
                f"Apify failed to start; using built-in",
                fallback_from="apify",
                apify_error=str(exc),
            )

    @staticmethod
    def list_exhibition_directories() -> list[dict[str, Any]]:
        """Curated UK exhibition exhibitor-directory URLs shipped with the API."""
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "data" / "uk_exhibition_directories.json"
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            url = str(row.get("url") or "").strip()
            if not name or not url.startswith("http"):
                continue
            out.append(
                {
                    "name": name,
                    "url": url,
                    "source": str(row.get("source") or ""),
                    "note": str(row.get("note") or ""),
                }
            )
        return out

    @staticmethod
    def start_bulk_scrapes(
        db: Session,
        *,
        urls: list[str],
        follow_websites: bool = True,
        engine: str = "auto",
        max_stands: int = 500,
    ) -> dict[str, Any]:
        """Start scrapes for many directory URLs (sequential; each uses smart scrape)."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in urls or []:
            u = str(raw or "").strip().replace("\\", "/")
            if not u.startswith("http"):
                continue
            key = u.split("#")[0].rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(u.split("#")[0])
        if not cleaned:
            raise AiTeamServiceError("Paste at least one https:// exhibitor directory URL")
        if len(cleaned) > 40:
            raise AiTeamServiceError("Bulk scrape is limited to 40 URLs at a time")

        results: list[dict[str, Any]] = []
        ok_n = 0
        fail_n = 0
        emails_total = 0
        for url in cleaned:
            try:
                one = AiTeamService.start_smart_scrape(
                    db,
                    expo_url=url,
                    follow_websites=follow_websites,
                    engine=engine,
                    max_stands=max_stands,
                )
                run = one.get("run") if isinstance(one, dict) else None
                emails = int(
                    (one or {}).get("emails_found")
                    or ((run or {}).get("emails_found") if isinstance(run, dict) else 0)
                    or ((run or {}).get("item_count") if isinstance(run, dict) else 0)
                    or 0
                )
                emails_total += emails
                ok_n += 1
                results.append(
                    {
                        "ok": True,
                        "url": url,
                        "emails_found": emails,
                        "provider": (one or {}).get("provider")
                        or ((run or {}).get("provider") if isinstance(run, dict) else None),
                        "status": (run or {}).get("status") if isinstance(run, dict) else None,
                        "run_id": (run or {}).get("id") if isinstance(run, dict) else None,
                        "message": (one or {}).get("message") or "ok",
                    }
                )
            except Exception as exc:
                fail_n += 1
                results.append({"ok": False, "url": url, "error": str(exc)[:400]})
        return {
            "ok": fail_n == 0,
            "started": len(cleaned),
            "succeeded": ok_n,
            "failed": fail_n,
            "emails_found_total": emails_total,
            "results": results,
            "message": f"Bulk scrape finished · {ok_n} ok · {fail_n} failed · {emails_total} email(s)",
        }

    @staticmethod
    def start_apify_run(db: Session, *, expo_url: str, actor_id: str | None = None) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        url = str(expo_url or "").strip()
        if not url.startswith("http"):
            raise AiTeamServiceError("Enter a valid expo directory URL (https://…)")
        actor = str(actor_id or settings.apify_exhibitor_actor_id or settings.apify_contact_actor_id or "").strip()
        # No actor configured → use built-in directory scraper (Easyfairs / HTML).
        if not actor:
            return AiTeamService.start_directory_scrape(db, expo_url=url, follow_websites=True)

        token = AiTeamService._apify_token(settings, db=db)
        if not token:
            raise AiTeamServiceError("Apify API token is not configured (or clear the Actor ID to use built-in scrape)")

        # Common actor input keys — actors ignore unknown fields
        run_input = {
            "startUrls": [{"url": url}],
            "url": url,
            "expoUrl": url,
            "expo_url": url,
        }
        try:
            started = ApifyService.start_actor_run(token, actor_id=actor, run_input=run_input)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        now = AiTeamService._now()
        row = AiTeamApifyRun(
            apify_run_id=started.get("apify_run_id"),
            actor_id=actor,
            expo_url=url,
            status=str(started.get("status") or "READY"),
            dataset_id=started.get("dataset_id"),
            stats_json=json.dumps(
                {
                    "provider": "apify",
                    "progress": {
                        "phase": "queued",
                        "message": "Queued on Apify — status updates every few seconds",
                        "stands_total": 0,
                        "stands_done": 0,
                        "stands_with_email": 0,
                        "emails_found": 0,
                        "errors": 0,
                        "heartbeat_at": now.isoformat() + "Z",
                        "provider": "apify",
                    },
                },
                ensure_ascii=False,
            ),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"ok": True, "run": AiTeamService._run_to_dict(row)}

    @staticmethod
    def list_apify_runs(db: Session, *, limit: int = 30) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(AiTeamApifyRun).order_by(AiTeamApifyRun.created_at.desc()).limit(max(1, min(limit, 100)))
            ).scalars().all()
        )
        # Keep Apify READY/RUNNING rows in sync so UI does not look stuck on READY
        open_statuses = {"READY", "RUNNING", "ABORTING", "TIMING-OUT"}
        for row in rows:
            st = str(row.status or "").upper()
            if st not in open_statuses:
                continue
            if str(row.actor_id or "").startswith("builtin:"):
                continue
            if not row.apify_run_id:
                continue
            try:
                AiTeamService.refresh_apify_run(db, row.id)
                db.refresh(row)
            except Exception:
                logger.debug("apify_run_auto_refresh_failed run_id=%s", row.id, exc_info=True)
        return [AiTeamService._run_to_dict(r) for r in rows]

    @staticmethod
    def abort_scrape_run(db: Session, run_id: str) -> dict[str, Any]:
        """Force-pause a scrape (Apify abort API or local builtin stop flag)."""
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Scrape run not found")
        st = str(row.status or "").upper()
        if st in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            return {
                "ok": True,
                "run": AiTeamService._run_to_dict(row),
                "message": f"Already finished ({row.status})",
            }
        now = AiTeamService._now()
        is_builtin = str(row.actor_id or "").startswith("builtin:")
        if not is_builtin and row.apify_run_id:
            settings = AiTeamService.get_settings(db)
            token = AiTeamService._apify_token(settings, db=db)
            if token:
                try:
                    remote = ApifyService.abort_run(token, apify_run_id=row.apify_run_id)
                    row.status = str(remote.get("status") or "ABORTING")
                except ApifyServiceError as exc:
                    # Still mark local pause so UI stops treating it as live
                    logger.warning("apify_abort_failed run_id=%s err=%s", run_id, exc)
                    row.status = "ABORTED"
                    row.error = f"Force pause requested (Apify abort failed: {exc})"[:2000]
            else:
                row.status = "ABORTED"
                row.error = "Force paused locally (no Apify token to abort remote run)"
        else:
            row.status = "ABORTED"
            row.error = "Force paused by admin"
        try:
            stats = json.loads(row.stats_json or "{}")
            if not isinstance(stats, dict):
                stats = {}
        except Exception:
            stats = {}
        prog = stats.get("progress") if isinstance(stats.get("progress"), dict) else {}
        stats["progress"] = {
            **(prog or {}),
            "phase": "paused",
            "message": "Force paused — scrape stopped",
            "heartbeat_at": now.isoformat() + "Z",
        }
        row.stats_json = json.dumps(stats, ensure_ascii=False)
        if str(row.status).upper() in {"ABORTED", "FAILED", "SUCCEEDED", "TIMED-OUT"}:
            row.finished_at = row.finished_at or now
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "ok": True,
            "run": AiTeamService._run_to_dict(row),
            "message": "Scrape force-paused",
        }

    @staticmethod
    def delete_apify_run(db: Session, run_id: str) -> dict[str, Any]:
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Scrape run not found")
        if str(row.status or "").upper() in {"RUNNING", "READY", "ABORTING"}:
            raise AiTeamServiceError("Cannot delete an active scrape — Force pause first")
        db.delete(row)
        db.commit()
        return {"ok": True, "deleted": 1, "id": run_id}

    @staticmethod
    def purge_apify_runs(db: Session, *, include_running: bool = False) -> dict[str, Any]:
        """Delete all saved scrape/Apify run rows (URLs + stored contact payloads)."""
        rows = list(db.execute(select(AiTeamApifyRun)).scalars().all())
        deleted = 0
        skipped_running = 0
        for row in rows:
            if not include_running and str(row.status or "").upper() == "RUNNING":
                skipped_running += 1
                continue
            db.delete(row)
            deleted += 1
        db.commit()
        return {
            "ok": True,
            "deleted": deleted,
            "skipped_running": skipped_running,
            "message": (
                f"Removed {deleted} scrape run(s)"
                + (f" · left {skipped_running} still RUNNING" if skipped_running else "")
            ),
        }

    @staticmethod
    def refresh_apify_run(db: Session, run_id: str) -> dict[str, Any]:
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Apify run not found")
        if str(row.actor_id or "").startswith("builtin:"):
            # Auto-recover stuck queued scrapes (other Redis workers used to steal these tasks).
            if str(row.status or "").upper() == "RUNNING":
                age_s = 0.0
                if row.updated_at:
                    age_s = max(0.0, (AiTeamService._now() - row.updated_at).total_seconds())
                try:
                    stats = json.loads(row.stats_json or "{}")
                except Exception:
                    stats = {}
                progress = stats.get("progress") if isinstance(stats, dict) else {}
                phase = str((progress or {}).get("phase") or stats.get("message") or "")
                stuck_queued = age_s >= 90 and (
                    phase in {"queued", ""} or int((progress or {}).get("stands_done") or 0) == 0
                )
                if stuck_queued:
                    try:
                        from app.workers.ai_team_tasks import scrape_directory_task

                        follow = True
                        if isinstance(progress, dict) and "follow_websites" in progress:
                            follow = bool(progress.get("follow_websites"))
                        elif isinstance(stats, dict) and "follow_websites" in stats:
                            follow = bool(stats.get("follow_websites"))
                        async_result = scrape_directory_task.apply_async(
                            args=[run_id],
                            kwargs={"follow_websites": follow, "max_stands": 500},
                            queue="voxbulk",
                        )
                        row.apify_run_id = str(async_result.id or row.apify_run_id or "")
                        AiTeamService._write_scrape_progress(
                            run_id,
                            {
                                "phase": "queued",
                                "message": "Re-queued on dedicated voxbulk Celery queue…",
                                "stands_total": int((progress or {}).get("stands_total") or 0),
                                "stands_done": 0,
                                "stands_with_email": 0,
                                "emails_found": 0,
                                "errors": 0,
                                "follow_websites": follow,
                                "provider": "pending",
                            },
                        )
                        db.refresh(row)
                    except Exception as exc:
                        logger.warning("directory_scrape_requeue_failed run_id=%s err=%s", run_id, exc)
            db.refresh(row)
            return {"ok": True, "run": AiTeamService._run_to_dict(row)}
        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)
        if not token or not row.apify_run_id:
            raise AiTeamServiceError("Cannot refresh run — missing Apify token or run id")
        try:
            remote = ApifyService.get_run(token, apify_run_id=row.apify_run_id)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        now = AiTeamService._now()
        row.status = str(remote.get("status") or row.status)
        if remote.get("dataset_id"):
            row.dataset_id = remote.get("dataset_id")
        remote_stats = remote.get("stats") or {}
        try:
            prev = json.loads(row.stats_json or "{}")
            if not isinstance(prev, dict):
                prev = {}
        except Exception:
            prev = {}
        st_up = str(row.status or "").upper()
        phase = "queued" if st_up in {"READY", "CREATED"} else (
            "running" if st_up == "RUNNING" else (
                "paused" if st_up in {"ABORTING", "ABORTED"} else (
                    "done" if st_up == "SUCCEEDED" else "error"
                )
            )
        )
        msg = {
            "READY": "Queued on Apify — waiting to start (this can take 1–2 min)",
            "CREATED": "Created on Apify — waiting to start",
            "RUNNING": "Apify actor is running…",
            "ABORTING": "Aborting on Apify…",
            "ABORTED": "Force paused / aborted",
            "SUCCEEDED": "Completed on Apify",
            "FAILED": "Failed on Apify",
            "TIMED-OUT": "Timed out on Apify",
        }.get(st_up, f"Apify status: {row.status}")
        compute = remote_stats.get("computeUnits")
        if st_up == "RUNNING" and compute is not None:
            msg = f"Apify running · compute {compute}"
        progress = {
            "phase": phase,
            "message": msg,
            "stands_total": int((prev.get("progress") or {}).get("stands_total") or 0),
            "stands_done": int((prev.get("progress") or {}).get("stands_done") or 0),
            "stands_with_email": int((prev.get("progress") or {}).get("stands_with_email") or 0),
            "emails_found": int(prev.get("emails_found") or (prev.get("progress") or {}).get("emails_found") or 0),
            "errors": int((prev.get("progress") or {}).get("errors") or 0),
            "heartbeat_at": now.isoformat() + "Z",
            "provider": "apify",
            "apify_stats": remote_stats,
        }
        merged = {
            **prev,
            "provider": "apify",
            "apify_stats": remote_stats,
            "progress": progress,
        }
        row.stats_json = json.dumps(merged, ensure_ascii=False)
        row.updated_at = now
        if st_up in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            row.finished_at = row.finished_at or now
            if st_up != "SUCCEEDED":
                row.error = row.error or f"Run ended with status {row.status}"
            elif row.dataset_id:
                try:
                    items = ApifyService.fetch_dataset_items(token, dataset_id=row.dataset_id, limit=5000)
                    row.item_count = len(items)
                    emails = 0
                    contacts_payload: list[dict[str, Any]] = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        normalized = ApifyService.normalize_contact_item(
                            item, expo_url=row.expo_url or "", run_id=row.apify_run_id or row.id
                        )
                        if normalized and normalized.get("email"):
                            emails += 1
                            contacts_payload.append(normalized)
                    merged["emails_found"] = emails
                    if emails > 0:
                        merged["contacts"] = contacts_payload[:5000]
                        merged["progress"] = {
                            **progress,
                            "phase": "done",
                            "message": f"Completed · {emails} email(s) from {len(items)} item(s)",
                            "emails_found": emails,
                            "stands_total": len(items),
                            "stands_done": len(items),
                        }
                        row.stats_json = json.dumps(merged, ensure_ascii=False)
                    else:
                        # Wrong actor / SPA shell — kick built-in which handles SPA APIs
                        merged["progress"] = {
                            **progress,
                            "phase": "done",
                            "message": (
                                f"Apify returned 0 emails from {len(items)} item(s) "
                                "(often a SPA shell). Starting built-in directory scrape…"
                            ),
                            "emails_found": 0,
                            "stands_total": len(items),
                            "stands_done": len(items),
                        }
                        merged["apify_zero_emails"] = True
                        row.stats_json = json.dumps(merged, ensure_ascii=False)
                        row.error = (
                            "Apify found 0 emails — auto built-in scrape started. "
                            "Prefer Auto/Built-in for /exhibitors directories."
                        )[:2000]
                        db.add(row)
                        db.commit()
                        try:
                            AiTeamService.start_directory_scrape(
                                db,
                                expo_url=row.expo_url or "",
                                follow_websites=True,
                                max_stands=500,
                            )
                        except Exception as fallback_exc:
                            logger.warning(
                                "apify_zero_email_builtin_fallback_failed run_id=%s err=%s",
                                row.id,
                                fallback_exc,
                            )
                        db.refresh(row)
                        return {"ok": True, "run": AiTeamService._run_to_dict(row), "fallback_builtin": True}
                except ApifyServiceError as exc:
                    row.error = str(exc)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"ok": True, "run": AiTeamService._run_to_dict(row)}

    @staticmethod
    def preview_apify_run(db: Session, run_id: str, *, limit: int = 5000) -> dict[str, Any]:
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Apify run not found")
        builtin = AiTeamService._builtin_run_contacts(row)
        if builtin or str(row.actor_id or "").startswith("builtin:"):
            cap = max(1, min(int(limit or 5000), 10000))
            return {
                "ok": True,
                "run": AiTeamService._run_to_dict(row),
                "total_items": int(row.item_count or len(builtin)),
                "contacts_with_email": len(builtin),
                "preview": builtin[:cap],
            }
        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)
        if not token or not row.dataset_id:
            raise AiTeamServiceError("Dataset not ready yet — wait for the run to succeed")
        try:
            items = ApifyService.fetch_dataset_items(token, dataset_id=row.dataset_id, limit=500)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        contacts = []
        for item in items:
            normalized = ApifyService.normalize_contact_item(
                item, expo_url=row.expo_url, run_id=row.apify_run_id or row.id
            )
            if normalized:
                contacts.append(normalized)
        cap = max(1, min(int(limit or 5000), 10000))
        return {
            "ok": True,
            "run": AiTeamService._run_to_dict(row),
            "total_items": len(items),
            "contacts_with_email": len(contacts),
            "preview": contacts[:cap],
        }

    @staticmethod
    def export_apify_run_csv(db: Session, run_id: str) -> tuple[str, str]:
        """Return (filename, csv_text) for all contacts with email in a scrape run."""
        preview = AiTeamService.preview_apify_run(db, run_id, limit=10000)
        contacts = preview.get("preview") or []
        if not contacts:
            raise AiTeamServiceError("No emails to export for this run")
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "email",
                "first_name",
                "last_name",
                "company_name",
                "job_title",
                "website",
                "profile_url",
                "event_name",
                "stand_number",
                "sector",
                "country_code",
            ]
        )
        for c in contacts:
            if not isinstance(c, dict):
                continue
            writer.writerow(
                [
                    c.get("email") or "",
                    c.get("first_name") or "",
                    c.get("last_name") or "",
                    c.get("company_name") or "",
                    c.get("job_title") or "",
                    c.get("website") or "",
                    c.get("profile_url") or "",
                    c.get("event_name") or "",
                    c.get("stand_number") or "",
                    c.get("sector") or "",
                    c.get("country_code") or "",
                ]
            )
        # UTF-8 BOM so Excel opens accents correctly
        body = "\ufeff" + buf.getvalue()
        short = str(run_id or "run")[:8]
        return f"expo-emails-{short}.csv", body

    @staticmethod
    def import_apify_run(db: Session, run_id: str) -> dict[str, Any]:
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Apify run not found")

        builtin = AiTeamService._builtin_run_contacts(row)
        if builtin or str(row.actor_id or "").startswith("builtin:"):
            if not builtin:
                raise AiTeamServiceError("No contacts with email found in this scrape")
            result = AiTeamService.import_prospect_rows(db, builtin, source="expo", apply_min_score=False)
            row.imported_count = int(row.imported_count or 0) + int(result.get("created") or 0)
            row.updated_at = AiTeamService._now()
            db.add(row)
            db.commit()
            db.refresh(row)
            return {
                "ok": True,
                "run": AiTeamService._run_to_dict(row),
                "created": result.get("created"),
                "skipped": result.get("skipped"),
                "contacts_with_email": len(builtin),
                "total_items": int(row.item_count or len(builtin)),
            }

        preview = AiTeamService.preview_apify_run(db, run_id, limit=5000)
        contacts = []
        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)
        items = ApifyService.fetch_dataset_items(token, dataset_id=row.dataset_id, limit=5000)
        for item in items:
            normalized = ApifyService.normalize_contact_item(
                item, expo_url=row.expo_url, run_id=row.apify_run_id or row.id
            )
            if normalized:
                contacts.append(normalized)
        if not contacts:
            raise AiTeamServiceError("No contacts with email found in this Apify dataset")
        result = AiTeamService.import_prospect_rows(db, contacts, source="apify", apply_min_score=False)
        row.imported_count = int(row.imported_count or 0) + int(result.get("created") or 0)
        row.item_count = len(items)
        row.updated_at = AiTeamService._now()
        db.add(row)
        db.commit()
        return {
            "ok": True,
            "run": AiTeamService._run_to_dict(row),
            "created": result.get("created"),
            "skipped": result.get("skipped"),
            "contacts_with_email": len(contacts),
            "total_items": preview.get("total_items"),
        }

    @staticmethod
    def process_due_followups(db: Session) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        if not settings.auto_followup or settings.agent_paused:
            return {"ok": True, "sent": 0, "skipped": 0, "message": "Follow-ups paused or disabled"}
        after_days = max(1, int(settings.followup_after_days or 3))
        max_followups = max(0, int(settings.max_followups or 2))
        if max_followups <= 0:
            return {"ok": True, "sent": 0, "skipped": 0, "message": "max_followups is 0"}
        cutoff = AiTeamService._now() - timedelta(days=after_days)
        rows = list(
            db.execute(
                select(AiTeamProspect).where(
                    AiTeamProspect.status.in_(["sent", "opened"]),
                    AiTeamProspect.sent_at.isnot(None),
                    AiTeamProspect.sent_at <= cutoff,
                    AiTeamProspect.replied_at.is_(None),
                )
            ).scalars().all()
        )
        sent = 0
        skipped = 0
        for prospect in rows:
            if int(prospect.followups_sent or 0) >= max_followups:
                skipped += 1
                continue
            # Space follow-ups by followup_after_days from last outbound
            last_msg = db.execute(
                select(AiTeamMessage)
                .where(AiTeamMessage.prospect_id == prospect.id, AiTeamMessage.direction == "outbound")
                .order_by(AiTeamMessage.created_at.desc())
            ).scalars().first()
            if last_msg and last_msg.created_at and last_msg.created_at > cutoff:
                skipped += 1
                continue
            subject = f"Re: {prospect.draft_subject or 'quick follow-up'}"
            body = (
                f"Hi {prospect.first_name or 'there'},\n\n"
                f"Just bumping this in case it got buried. Happy to share a short demo of how "
                f"VoxBulk helps teams like {prospect.company_name or 'yours'} capture expo leads.\n\n"
                f"{settings.email_signature or _DEFAULT_SIGNATURE}"
            )
            try:
                AiTeamService.send_prospect_email(db, prospect, subject=subject, body=body)
                prospect.followups_sent = int(prospect.followups_sent or 0) + 1
                prospect.updated_at = AiTeamService._now()
                db.add(prospect)
                db.commit()
                sent += 1
            except Exception as exc:
                skipped += 1
                logger.warning("ai_team_followup_failed", extra={"prospect_id": prospect.id, "error": str(exc)})
        return {"ok": True, "sent": sent, "skipped": skipped}

    @staticmethod
    def generate_sample_email(db: Session) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        class _Sample:
            first_name = "Alex"
            last_name = "Taylor"
            email = "alex.taylor@example.com"
            job_title = "Operations director"
            company_name = "Example Estates"
            sector = "property"
            country_code = "GB"
            match_score = 88
            status = "new"
            id = "sample"
            promo_offer_id = None
            draft_subject = None
            draft_body = None
            draft_body_html = None
            drafted_at = None

        sample = _Sample()
        instruction = settings.writing_instruction or _DEFAULT_WRITING
        variables = {
            "first_name": sample.first_name,
            "last_name": sample.last_name,
            "job_title": sample.job_title,
            "company": sample.company_name,
            "sector": sample.sector,
            "country": sample.country_code,
            "promo_code": "TRIAL-EXAMPLE",
        }
        for key, val in variables.items():
            instruction = instruction.replace("{" + key + "}", str(val))
        system = (
            "You write B2B cold outreach emails for VoxBulk. Return JSON with keys subject and body. "
            f"Tone: {settings.email_tone}. Language: {settings.email_language}. "
            f"Max words: {settings.email_max_words}."
        )
        user = f"Instruction:\n{instruction}\n\nSignature:\n{settings.email_signature or _DEFAULT_SIGNATURE}"
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system,
            messages=[AgentMessage(role="user", content=user)],
            max_tokens=600,
            temperature=0.5,
            provider="deepseek",
        )
        text = str(result.assistant_text or "").strip()
        subject = "Quick idea for your team"
        body = text
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                subject = str(parsed.get("subject") or subject).strip()
                body = str(parsed.get("body") or text).strip()
        except json.JSONDecodeError:
            pass
        return {"subject": subject, "body": body}
